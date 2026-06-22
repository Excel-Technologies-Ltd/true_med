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
    "brand",
    "reviewer_name",
    "item_code",
    "item_name",
    "sales_invoice",
    "rating",
    "title",
    "review",
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

_REVIEW_RESERVED = BASE_LIST_API_RESERVED_KEYS | frozenset(
    {'item_code', 'status'}
)
_REVIEW_FORBIDDEN = frozenset({
    'item_code',
    'customer',
    'sales_invoice',
    'status',
})
APPROVED_REVIEW_STATUS = 'Approved'


@frappe.whitelist(allow_guest=True)
def get_item_review_list(
    item_code: str = None,
    page: int = 1,
    page_length: int = 20,
    field_filters: str = None,
    sort_by: str = "creation",
    sort_order: str = "desc",
    **kwargs  # <-- 1. Catch all extra URL parameters here
) -> dict:
    """
    Public API — paginated approved item reviews only.
    ...
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
        
    # 2. Dynamically apply kwargs to filters
    for field in REVIEW_LIST_FIELDS:
        if field in kwargs and field not in _REVIEW_FORBIDDEN:
            val = kwargs[field]
            if val not in (None, ""):
                # Safely cast rating to float, treat the rest as strings
                if field == "rating":
                    filters[field] = float(val)
                else:
                    filters[field] = val

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

    filters['status'] = APPROVED_REVIEW_STATUS

    data, pagination = paginate(
        doctype="Item Review",
        fields=REVIEW_LIST_FIELDS,
        filters=filters,
        order_by=f"`tabItem Review`.`{sort_by}` {sort_order}",
        page=page,
        page_length=page_length,
        ignore_permissions=True,
    )

    _attach_review_images(data)

    # Strip internal fields not suitable for public consumption
    for row in data:
        row.pop("customer", None)
        row.pop("sales_invoice", None)

    summary_brand = filters.get('brand')
    if not isinstance(summary_brand, str):
        summary_brand = None

    summary = _get_rating_summary(
        resolved_item or None,
        status=APPROVED_REVIEW_STATUS,
        brand=summary_brand,
    )

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

    return {
        'data': _get_rating_summary(
            item_code,
            status=APPROVED_REVIEW_STATUS,
        ),
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _get_rating_summary(
    item_code: str | None = None,
    status: str | None = None,
    brand: str | None = None,
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
    if brand:
        conditions.append('brand = %s')
        params.append(brand)

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
        'brand': brand or None,
        'status': status or None,
        'avg_rating': avg_rating,
        'total_reviews': total,
        'breakdown': breakdown,
    }


def _get_review_images_doctype() -> str | None:
    field = frappe.get_meta('Item Review').get_field('images')
    return field.options if field else None


def _attach_review_images(reviews: list) -> None:
    """Attach Review Images child rows (file paths) in one bulk query."""
    if not reviews:
        return

    child_doctype = _get_review_images_doctype()
    if not child_doctype:
        for row in reviews:
            row['images'] = []
        return

    review_names = [row['name'] for row in reviews if row.get('name')]
    if not review_names:
        for row in reviews:
            row['images'] = []
        return

    all_images = frappe.get_all(
        child_doctype,
        filters={
            'parent': ['in', review_names],
            'parenttype': 'Item Review',
        },
        fields=['parent', 'image', 'idx'],
        order_by='parent asc, idx asc',
        ignore_permissions=True,
    )

    images_by_review = {}
    for row in all_images:
        image_path = row.get('image')
        if not image_path:
            continue
        images_by_review.setdefault(row['parent'], []).append(
            {'image': image_path}
        )

    for row in reviews:
        row['images'] = images_by_review.get(row['name'], [])
