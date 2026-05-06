import frappe
from frappe import _
from frappe.utils import cint

from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import get_list_request_value, paginate

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
_REVIEW_FORBIDDEN = frozenset({"item_code", "customer", "sales_invoice"})


@frappe.whitelist(allow_guest=True)
def get_item_review_list(
    item_code: str = None,
    status: str = None,
    page: int = 1,
    page_length: int = 20,
    field_filters: str = None,
    sort_by: str = "creation",
    sort_order: str = "desc",
) -> dict:
    """
    Public API — paginated item reviews.

    Customer identifiers are never exposed to guests; the response shows
    reviewer_name only.

    Query Parameters:
        item_code     (str, optional) When set, limit to this item (must exist).
                                      When omitted, all item reviews.
        status        (str, optional) Filter by status (Approved/Pending/Rejected).
        page          (int)           Page number, 1-based. Default: 1
        page_length   (int)           Records per page. Default: 20, max: 100
        field_filters (str)           JSON AND filters on review fields
        Other keys in REVIEW_LIST_FIELDS (except item_code/status/...) as ?key=
        sort_by       (str)           rating | title | modified | creation
        sort_order   (asc|desc)      Default: desc

    Summary statistics (avg_rating, total_reviews, rating breakdown) are
    included in the response under the `summary` key (scoped by item_code
    and status when provided, otherwise global).

    Endpoint:
        GET /api/method/true_med.api.item_review.item_review_list.get_item_review_list
        GET ...get_item_review_list?item_code=ITEM-001
    """
    resolved_item = get_list_request_value('item_code') or item_code
    resolved_item = str(resolved_item).strip() if resolved_item else ''

    if resolved_item and not frappe.db.exists('Item', resolved_item):
        frappe.throw(_('Item {0} not found').format(resolved_item), frappe.DoesNotExistError)

    raw_page = get_list_request_value('page')
    raw_pl = get_list_request_value('page_length')
    page = max(1, cint(raw_page if raw_page not in (None, '') else page))
    page_length = cint(raw_pl if raw_pl not in (None, '') else page_length)

    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "creation"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    filters = {}
    if resolved_item:
        filters['item_code'] = resolved_item
    if status:
        filters['status'] = status
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
        page=page,
        page_length=page_length,
        ignore_permissions=True,
    )

    # Strip internal fields not suitable for public consumption
    for row in data:
        row.pop("customer", None)
        row.pop("sales_invoice", None)

    summary = _get_rating_summary(resolved_item or None, status=status)

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

def _get_rating_summary(
    item_code: str | None = None,
    status: str | None = None,
) -> dict:
    """
    Compute average rating and per-star breakdown in a single SQL query.

    Pass ``item_code`` to scope to one item; omit or pass None for all
    reviews. Pass ``status`` to scope to a specific review status.

    Frappe's Rating fieldtype stores values as floats between 0 and 1
    (e.g. 0.6 = 3 stars on a 5-star scale). We multiply by 5 to get the
    familiar 1–5 star value and round to one decimal for the average.
    """
    conditions = []
    params = []
    if item_code:
        conditions.append('item_code = %s')
        params.append(item_code)
    if status:
        conditions.append('status = %s')
        params.append(status)

    where_sql = ''
    if conditions:
        where_sql = 'WHERE ' + ' AND '.join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            ROUND(rating * 5) AS star,
            COUNT(*)          AS cnt
        FROM `tabItem Review`
        {where_sql}
        GROUP BY ROUND(rating * 5)
        """,
        params,
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
        'item_code': item_code or None,
        'status': status or None,
        'avg_rating': avg_rating,
        'total_reviews': total,
        'breakdown': breakdown,
    }
