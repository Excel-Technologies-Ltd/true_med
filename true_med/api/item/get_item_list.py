import frappe
from frappe.utils import cint

from true_med.utils import cache as item_cache
from true_med.utils.pagination import paginate

ITEM_LIST_FIELDS = [
    "name",
    "item_code",
    "item_name",
    "item_group",
    "brand",
    "description",
    "custom_product_type",
    "custom_sub_title",
    "custom_equivalent_to",
    "image",
    "custom_ingredients",
    "standard_rate",
    "stock_uom",
    "is_stock_item",
    "has_variants",
    "variant_of",
    "has_batch_no",
    "has_serial_no",
    "disabled",
    "shelf_life_in_days",
    "weight_per_unit",
    "weight_uom",
    "modified",
    "creation",
]

ITEM_PRICE_FIELDS = [
    "item_code",
    "name",
    "price_list",
    "buying",
    "selling",
    "currency",
    "price_list_rate",
    "uom",
    "packing_unit",
    "lead_time_days",
    "valid_from",
    "valid_upto",
    "customer",
    "supplier",
    "note",
    "batch_no",
]

ALLOWED_SORT_FIELDS = {
    "item_code",
    "item_name",
    "item_group",
    "brand",
    "standard_rate",
    "modified",
    "creation",
}


@frappe.whitelist(allow_guest=True)
def get_item_list(
    page: int = 1,
    page_length: int = 20,
    item_group: str = None,
    brand: str = None,
    search: str = None,
    is_stock_item: int = None,
    has_variants: int = None,
    disabled: int = 0,
    sort_by: str = "modified",
    sort_order: str = "desc",
) -> dict:
    """
    Public API — paginated item list with filters and embedded prices.

    By default only top-level items are returned (template items and standalone
    items). Variant items are excluded from the list; they are accessible via
    the get_item endpoint which embeds them inside the parent template.

    Results are cached in Redis and automatically invalidated when Items or
    Item Prices change.

    Query Parameters:
        page          (int)      Page number, 1-based. Default: 1
        page_length   (int)      Records per page. Default: 20, max: 100
        item_group    (str)      Filter by exact item group name
        brand         (str)      Filter by exact brand name
        search        (str)      Partial match on item_code or item_name
        is_stock_item (0|1)      Filter stocked items only
        has_variants  (0|1)      Narrow to template (1) or standalone (0) items
        disabled      (0|1)      Include disabled items (default 0 = active only)
        sort_by       (str)      Field to sort by. Allowed: item_code, item_name,
                                 item_group, brand, standard_rate, modified, creation
        sort_order    (asc|desc) Sort direction. Default: desc

    Endpoint:
        GET /api/method/true_med.api.item.get_item_list.get_item_list
    """
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "modified"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"
    fields = _get_existing_item_fields()
    if sort_by not in fields:
        sort_by = "modified"

    cache_key = item_cache.item_list_key(
        page=page,
        page_length=page_length,
        item_group=item_group,
        brand=brand,
        search=search,
        is_stock_item=is_stock_item,
        has_variants=has_variants,
        disabled=disabled,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    cached = item_cache.get(cache_key)
    if cached:
        return cached

    filters = _build_filters(
        item_group=item_group,
        brand=brand,
        is_stock_item=is_stock_item,
        has_variants=has_variants,
        disabled=disabled,
    )

    or_filters = _build_search_filters(search)
    order_by = f"`tabItem`.`{sort_by}` {sort_order}"

    data, pagination = paginate(
        doctype="Item",
        fields=fields,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        page=cint(page),
        page_length=cint(page_length),
        ignore_permissions=True,
    )

    _attach_prices(data)
    _attach_custom_images(data)
    _attach_custom_key_benefits(data)

    result = {"data": data, "pagination": pagination}
    item_cache.set(cache_key, result, ttl=item_cache.ITEM_LIST_TTL)

    return result


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _build_filters(
    item_group=None,
    brand=None,
    is_stock_item=None,
    has_variants=None,
    disabled=0,
) -> dict:
    filters = {}

    # Always exclude variant items — they are only visible through their
    # parent template's detail endpoint.
    filters["variant_of"] = ["is", "not set"]

    filters["disabled"] = cint(disabled) if disabled is not None else 0

    if item_group:
        filters["item_group"] = item_group

    if brand:
        filters["brand"] = brand

    if is_stock_item is not None:
        filters["is_stock_item"] = cint(is_stock_item)

    if has_variants is not None:
        filters["has_variants"] = cint(has_variants)

    return filters


def _get_existing_item_fields() -> list:
    """
    Return only real DB-backed Item fields to avoid SQL errors when custom
    fields differ between environments.
    """
    meta = frappe.get_meta("Item")
    existing = []
    for field in ITEM_LIST_FIELDS:
        if field in ("name", "modified", "creation") or meta.get_field(field):
            existing.append(field)
    return existing


def _build_search_filters(search: str | None) -> list:
    """Return OR filters for a free-text search across code and name."""
    if not search:
        return []

    keyword = f"%{search}%"
    return [
        ["item_code", "like", keyword],
        ["item_name", "like", keyword],
    ]


def _attach_prices(items: list) -> None:
    """
    Attach prices to each item in-place using a single bulk query (no N+1).
    Fetches all Item Price rows for the entire page at once.
    """
    if not items:
        return

    item_codes = [item["item_code"] for item in items]

    all_prices = frappe.get_all(
        "Item Price",
        filters={"item_code": ["in", item_codes]},
        fields=ITEM_PRICE_FIELDS,
        order_by="selling desc, buying desc, price_list asc",
        ignore_permissions=True,
    )

    prices_by_item = {}
    for price in all_prices:
        prices_by_item.setdefault(price["item_code"], []).append(price)

    for item in items:
        item["prices"] = prices_by_item.get(item["item_code"], [])


def _attach_custom_images(items: list) -> None:
    """
    Attach custom_images child table rows to each item in a single bulk query.
    custom_images is a Table field on Item — its rows live in a separate DB
    table and cannot be fetched via frappe.get_list() on the parent doctype.
    The child DocType name is resolved once from Item's meta so this stays
    correct even if the child table is renamed.
    """
    if not items:
        return

    child_doctype = _get_custom_images_doctype()
    if not child_doctype:
        for item in items:
            item["custom_images"] = []
        return

    item_codes = [item["item_code"] for item in items]

    all_images = frappe.get_all(
        child_doctype,
        filters={"parent": ["in", item_codes], "parenttype": "Item"},
        fields=["parent", "name", "media_file", "idx"],
        order_by="parent asc, idx asc",
        ignore_permissions=True,
    )

    images_by_item = {}
    for row in all_images:
        images_by_item.setdefault(row["parent"], []).append({"media_file": row["media_file"]})

    for item in items:
        item["custom_images"] = images_by_item.get(item["item_code"], [])


def _attach_custom_key_benefits(items: list) -> None:
    """
    Attach custom_key_benefits child table rows to each item in a single query.
    """
    if not items:
        return

    child_doctype = _get_custom_key_benefits_doctype()
    if not child_doctype:
        for item in items:
            item["custom_key_benefits"] = []
        return

    item_codes = [item["item_code"] for item in items]
    all_rows = frappe.get_all(
        child_doctype,
        filters={"parent": ["in", item_codes], "parenttype": "Item"},
        fields=[
            "parent",
            "benefit_title",
            "benefit_icon",
            "description",
            "image",
            "idx",
        ],
        order_by="parent asc, idx asc",
        ignore_permissions=True,
    )

    rows_by_item = {}
    for row in all_rows:
        rows_by_item.setdefault(row["parent"], []).append(
            {
                "benefit_title": row.get("benefit_title"),
                "benefit_icon": row.get("benefit_icon"),
                "description": row.get("description"),
                "image": row.get("image"),
            }
        )

    for item in items:
        item["custom_key_benefits"] = rows_by_item.get(item["item_code"], [])


def _get_custom_images_doctype() -> str | None:
    """Return the child DocType linked to the custom_images field on Item."""
    field = frappe.get_meta("Item").get_field("custom_images")
    return field.options if field else None


def _get_custom_key_benefits_doctype() -> str | None:
    """Return child DocType linked to custom_key_benefits on Item."""
    field = frappe.get_meta("Item").get_field("custom_key_benefits")
    if not field or field.fieldtype != "Table":
        return None
    return field.options
