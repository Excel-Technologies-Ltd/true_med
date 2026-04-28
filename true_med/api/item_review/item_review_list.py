import frappe
from frappe import _
from frappe.utils import cint

from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import paginate

REVIEW_LIST_FIELDS = [
    "name",
    "customer",
    "reviewer_name",
    "item_code",
    "item_name",
    "sales_invoice",
    "rating",
    "title",
    "review",
    "image",
    "status",
    "modified",
    "creation",
]

ALLOWED_SORT_FIELDS = {
    "rating",
    "title",
    "modified",
    "creation",
}

_REVIEW_RESERVED = BASE_LIST_API_RESERVED_KEYS | frozenset({"item_code"})
_REVIEW_FORBIDDEN = frozenset({"item_code", "status", "customer", "sales_invoice"})


@frappe.whitelist(allow_guest=True)
def get_item_review_list(
    item_code: str = None,
    page: int = 1,
    page_length: int = 20,
    field_filters: str = None,
    sort_by: str = "creation",
    sort_order: str = "desc",
) -> dict:
    """
    Public API — paginated approved reviews for a given item.

    Only Approved reviews are returned. Customer identifiers are never
    exposed to guests; the response shows reviewer_name only.

    Query Parameters:
        item_code     (str, required) Item to fetch reviews for
        page          (int)           Page number, 1-based. Default: 1
        page_length   (int)           Records per page. Default: 20, max: 100
        field_filters (str)           JSON AND filters on review fields
        Other keys in REVIEW_LIST_FIELDS (except item_code/status/...) as ?key=
        sort_by       (str)           rating | title | modified | creation
        sort_order   (asc|desc)      Default: desc

    Summary statistics (avg_rating, total_reviews, rating breakdown) are
    included in the response under the `summary` key.

    Endpoint:
        GET /api/method/true_med.api.item_review.item_review_list.get_item_review_list?item_code=ITEM-001
    """
    if not item_code:
        frappe.throw(_("item_code is required"), frappe.MandatoryError)

    if not frappe.db.exists("Item", item_code):
        frappe.throw(_("Item {0} not found").format(item_code), frappe.DoesNotExistError)

    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "creation"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    filters = {
        "item_code": item_code,
        "status": "Approved",
    }
    query_ff = get_query_field_filters(
        allowed_fields=frozenset(REVIEW_LIST_FIELDS),
        reserved_keys=_REVIEW_RESERVED,
        forbidden_fields=_REVIEW_FORBIDDEN,
    )
    ff_json = normalize_field_filters_json(field_filters)
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype="Item Review",
        allowed_fields=frozenset(REVIEW_LIST_FIELDS),
        forbidden_fields=_REVIEW_FORBIDDEN,
    )
    merge_doctype_field_filters(
        filters,
        ff_json,
        doctype="Item Review",
        allowed_fields=frozenset(REVIEW_LIST_FIELDS),
        forbidden_fields=_REVIEW_FORBIDDEN,
    )

    data, pagination = paginate(
        doctype="Item Review",
        fields=REVIEW_LIST_FIELDS,
        filters=filters,
        order_by=f"`tabItem Review`.`{sort_by}` {sort_order}",
        page=cint(page),
        page_length=cint(page_length),
        ignore_permissions=True,
    )

    # Strip internal fields not suitable for public consumption
    for row in data:
        row.pop("customer", None)
        row.pop("sales_invoice", None)

    summary = _get_rating_summary(item_code)

    return {
        "data": data,
        "pagination": pagination,
        "summary": summary,
    }


@frappe.whitelist(allow_guest=True)
def get_item_rating_summary(item_code: str) -> dict:
    """
    Public API — lightweight rating summary for an item without full review list.

    Returns avg_rating, total_reviews, and a star breakdown (1–5).

    Endpoint:
        GET /api/method/true_med.api.item_review.item_review_list.get_item_rating_summary?item_code=ITEM-001
    """
    if not item_code:
        frappe.throw(_("item_code is required"), frappe.MandatoryError)

    return {"data": _get_rating_summary(item_code)}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _get_rating_summary(item_code: str) -> dict:
    """
    Compute average rating and per-star breakdown in a single SQL query.

    Frappe's Rating fieldtype stores values as floats between 0 and 1
    (e.g. 0.6 = 3 stars on a 5-star scale). We multiply by 5 to get the
    familiar 1–5 star value and round to one decimal for the average.
    """
    rows = frappe.db.sql(
        """
        SELECT
            ROUND(rating * 5) AS star,
            COUNT(*)          AS cnt
        FROM `tabItem Review`
        WHERE item_code = %s
          AND status    = 'Approved'
        GROUP BY ROUND(rating * 5)
        """,
        item_code,
        as_dict=True,
    )

    breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total = 0
    weighted_sum = 0.0

    for row in rows:
        star = int(row["star"] or 0)
        cnt = int(row["cnt"])
        if 1 <= star <= 5:
            breakdown[star] = cnt
        total += cnt
        weighted_sum += star * cnt

    avg_rating = round(weighted_sum / total, 1) if total else 0.0

    return {
        "item_code": item_code,
        "avg_rating": avg_rating,
        "total_reviews": total,
        "breakdown": breakdown,
    }
