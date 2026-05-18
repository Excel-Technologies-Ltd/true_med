import frappe
from frappe.utils import cint

from true_med.utils import cache as brand_cache
from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import paginate

BRAND_LIST_FIELDS = [
    "name",
    "brand",
    "description",
    "custom_meta_title",
    "custom_meta_description",
    "custom_keywords",
    "custom_faq",
    "image",
    "modified",
    "creation",
]

ALLOWED_SORT_FIELDS = {
    "brand",
    "modified",
    "creation",
}

_BRAND_LIST_RESERVED = BASE_LIST_API_RESERVED_KEYS


@frappe.whitelist(allow_guest=True)
def get_brand_list(
    page: int = 1,
    page_length: int = 20,
    search: str = None,
    field_filters: str = None,
    sort_by: str = "brand",
    sort_order: str = "asc",
) -> dict:
    """
    Public API — paginated Brand list with item count per brand.

    Results are cached in Redis and automatically invalidated when Brand
    documents change.

    Query Parameters:
        page         (int)       Page number, 1-based. Default: 1
        page_length  (int)       Records per page. Default: 20, max: 100
        search       (str)       Partial match (LIKE) on brand name
        field_filters (str)      JSON object of {field: value} AND filters.
                                 Keys must be BRAND_LIST_FIELDS (non-table).
        sort_by      (str)       brand | modified | creation
        sort_order   (asc|desc)  Sort direction. Default: asc

    Endpoint:
        GET /api/method/true_med.api.brand.brand_list.get_brand_list
    """
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "brand"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    ff_parsed = normalize_field_filters_json(field_filters)

    cache_key = brand_cache.brand_list_key(
        page=page,
        page_length=page_length,
        search=search,
        field_filters=ff_parsed,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    cached = brand_cache.get(cache_key)
    if cached:
        return cached

    filters = {}
    query_ff = get_query_field_filters(
        allowed_fields=frozenset(BRAND_LIST_FIELDS),
        reserved_keys=_BRAND_LIST_RESERVED,
    )
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype="Brand",
        allowed_fields=frozenset(BRAND_LIST_FIELDS),
    )
    merge_doctype_field_filters(
        filters,
        ff_parsed,
        doctype="Brand",
        allowed_fields=frozenset(BRAND_LIST_FIELDS),
    )

    fields = _get_existing_brand_fields()
    if sort_by not in fields:
        sort_by = "brand"

    or_filters = _build_search_filters(search)
    order_by = f"`tabBrand`.`{sort_by}` {sort_order}"

    data, pagination = paginate(
        doctype="Brand",
        fields=fields,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        page=cint(page),
        page_length=cint(page_length),
        ignore_permissions=True,
    )

    _attach_item_count(data)
    _attach_faq(data)

    result = {"data": data, "pagination": pagination}
    brand_cache.set(cache_key, result, ttl=brand_cache.BRAND_LIST_TTL)
    return result


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _get_existing_brand_fields() -> list:
    """Return only DB-backed Brand fields to avoid SQL errors when custom fields differ."""
    meta = frappe.get_meta("Brand")
    existing = []
    for field in BRAND_LIST_FIELDS:
        if field in ("name", "modified", "creation"):
            existing.append(field)
            continue
        field_meta = meta.get_field(field)
        if not field_meta:
            continue
        if field_meta.fieldtype in ("Table", "Table MultiSelect"):
            continue
        existing.append(field)
    return existing


def _build_search_filters(search: str | None) -> list:
    if not search or not str(search).strip():
        return []
    keyword = f"%{str(search).strip()}%"
    return [["brand", "like", keyword]]


def _attach_faq(brands: list) -> None:
    """Attach custom_faq child rows to each brand in a single bulk query."""
    if not brands:
        return

    names = [b["name"] for b in brands]
    rows = frappe.get_all(
        "Got Questions",
        filters={"parent": ["in", names], "parenttype": "Brand"},
        fields=["parent", "question", "answer", "idx"],
        order_by="parent asc, idx asc",
        ignore_permissions=True,
    )

    faq_by_parent = {}
    for row in rows:
        faq_by_parent.setdefault(row["parent"], []).append(
            {"question": row.get("question"), "answer": row.get("answer")}
        )

    for b in brands:
        b["custom_faq"] = faq_by_parent.get(b["name"], [])


def _attach_item_count(brands: list) -> None:
    """
    Attach item_count to each brand — active top-level items only — in one query.
    """
    if not brands:
        return

    brand_names = [b["name"] for b in brands]

    rows = frappe.db.sql(
        """
        SELECT brand, COUNT(*) AS cnt
        FROM   `tabItem`
        WHERE  brand IN ({placeholders})
          AND  disabled = 0
          AND  IFNULL(variant_of, '') = ''
        GROUP  BY brand
        """.format(placeholders=", ".join(["%s"] * len(brand_names))),
        brand_names,
        as_dict=True,
    )

    counts = {r["brand"]: r["cnt"] for r in rows}
    for b in brands:
        b["item_count"] = counts.get(b["name"], 0)
