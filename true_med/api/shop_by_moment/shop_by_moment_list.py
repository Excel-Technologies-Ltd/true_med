import frappe
from frappe.utils import cint

from true_med.utils import cache as sbm_cache
from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import paginate

SHOP_BY_MOMENT_LIST_FIELDS = [
    "name",
    "moment_name",
    "feature_image",
    "priority",
    "publish_to_website",
    "modified",
    "creation",
]

ALLOWED_SORT_FIELDS = {
    "name",
    "moment_name",
    "modified",
    "creation",
}

# `publish_to_website` is forced to 1 for this public endpoint; it must never be
# accepted as a client-supplied filter (query string or JSON field_filters).
_RESERVED = BASE_LIST_API_RESERVED_KEYS | frozenset({"publish_to_website"})
_FORBIDDEN_FILTERS = frozenset({"publish_to_website"})


@frappe.whitelist(allow_guest=True)
def get_shop_by_moment_list(
    page: int = 1,
    page_length: int = 20,
    search: str = None,
    field_filters: str = None,
    sort_by: str = "moment_name",
    sort_order: str = "asc",
) -> dict:
    """
    Public API — paginated Shop by Moment list with item count per moment.

    Results are cached in Redis and automatically invalidated when Shop by Moment
    documents change.

    Query Parameters:
        page         (int)       Page number, 1-based. Default: 1
        page_length  (int)       Records per page. Default: 20, max: 100
        search       (str)       Partial match (LIKE) on moment_name
        field_filters (str)      JSON object of {field: value} AND filters.
        sort_by      (str)       moment_name | modified | creation
        sort_order   (asc|desc)  Sort direction. Default: asc

    Endpoint:
        GET /api/method/true_med.api.shop_by_moment.shop_by_moment_list.get_shop_by_moment_list
    """
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "moment_name"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    ff_parsed = normalize_field_filters_json(field_filters)

    cache_key = sbm_cache.shop_by_moment_list_key(
        page=page,
        page_length=page_length,
        search=search,
        field_filters=ff_parsed,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    cached = sbm_cache.get(cache_key)
    if cached:
        return cached

    filters = {}
    query_ff = get_query_field_filters(
        allowed_fields=frozenset(SHOP_BY_MOMENT_LIST_FIELDS),
        reserved_keys=_RESERVED,
    )
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype="Shop by Moment",
        allowed_fields=frozenset(SHOP_BY_MOMENT_LIST_FIELDS),
        forbidden_fields=_FORBIDDEN_FILTERS,
    )
    merge_doctype_field_filters(
        filters,
        ff_parsed,
        doctype="Shop by Moment",
        allowed_fields=frozenset(SHOP_BY_MOMENT_LIST_FIELDS),
        forbidden_fields=_FORBIDDEN_FILTERS,
    )

    fields = _get_existing_shop_by_moment_fields()

    # Public endpoint: only website-published moments are ever exposed. Forced
    # last so no client filter (query string or field_filters) can override it.
    if "publish_to_website" in fields:
        filters["publish_to_website"] = 1

    or_filters = _build_search_filters(search)
    order_by = _build_order_by(sort_by, sort_order, has_priority="priority" in fields)

    data, pagination = paginate(
        doctype="Shop by Moment",
        fields=fields,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        page=cint(page),
        page_length=cint(page_length),
        ignore_permissions=True,
    )

    _attach_item_count(data)

    result = {"data": data, "pagination": pagination}
    sbm_cache.set(cache_key, result, ttl=sbm_cache.SHOP_BY_MOMENT_LIST_TTL)
    return result


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _get_existing_shop_by_moment_fields() -> list:
    """
    Return only DB-backed Shop by Moment fields so the endpoint keeps working
    in environments where `priority` / `publish_to_website` have not been
    migrated yet.
    """
    meta = frappe.get_meta("Shop by Moment")
    existing = []
    for field in SHOP_BY_MOMENT_LIST_FIELDS:
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


def _build_order_by(sort_by: str, sort_order: str, has_priority: bool = True) -> str:
    """
    Pin prioritized moments to the top, then apply the requested sort.

    `priority` is a unique text field holding a position number. Moments with a
    value are listed first, ordered by that number ascending (1, 2, 3, …);
    moments without one (NULL / empty) follow, ordered by ``sort_by``. The
    ordering is global, so pinning is preserved across paginated pages.

    ``has_priority`` guards against environments where the field has not been
    migrated yet, so we never reference a missing column. Only whitelisted sort
    identifiers and the literal asc/desc reach the SQL, so this is not injectable.
    """
    base = f"`tabShop by Moment`.`{sort_by}` {sort_order}"
    if not has_priority:
        return base

    priority_col = "`tabShop by Moment`.`priority`"
    return (
        f"NULLIF({priority_col}, '') IS NULL ASC, "
        f"CAST({priority_col} AS UNSIGNED) ASC, "
        f"{base}"
    )


def _build_search_filters(search: str | None) -> list:
    if not search or not str(search).strip():
        return []
    keyword = f"%{str(search).strip()}%"
    return [["moment_name", "like", keyword]]


def _attach_item_count(moments: list) -> None:
    """
    Attach item_count to each moment — active top-level items only — in one query.
    """
    if not moments:
        return

    moment_names = [m["name"] for m in moments]

    rows = frappe.db.sql(
        """
        SELECT custom_shop_by_moment, COUNT(*) AS cnt
        FROM   `tabItem`
        WHERE  custom_shop_by_moment IN ({placeholders})
          AND  disabled = 0
          AND  IFNULL(variant_of, '') = ''
        GROUP  BY custom_shop_by_moment
        """.format(placeholders=", ".join(["%s"] * len(moment_names))),
        moment_names,
        as_dict=True,
    )

    counts = {r["custom_shop_by_moment"]: r["cnt"] for r in rows}
    for m in moments:
        m["item_count"] = counts.get(m["name"], 0)
