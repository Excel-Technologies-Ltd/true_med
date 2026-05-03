import re

import frappe
from frappe.utils import cint

from true_med.api.item.get_item_list import ITEM_LIST_FIELDS
from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import MAX_PAGE_LENGTH

_FIELD_NAME_OK = re.compile(r"^[A-Za-z0-9_]+$")
_BEST_SELLING_ITEM_FORBIDDEN = frozenset({"variant_of"})
_BEST_SELLING_RESERVED = BASE_LIST_API_RESERVED_KEYS | frozenset()


def _item_prefilters_for_best_selling(field_filters: str | None) -> dict:
    raw_query = get_query_field_filters(
        allowed_fields=frozenset(ITEM_LIST_FIELDS),
        reserved_keys=_BEST_SELLING_RESERVED,
        forbidden_fields=_BEST_SELLING_ITEM_FORBIDDEN,
    )
    raw_json = normalize_field_filters_json(field_filters)
    merged = {}
    merge_doctype_field_filters(
        merged,
        raw_query,
        doctype="Item",
        allowed_fields=frozenset(ITEM_LIST_FIELDS),
        forbidden_fields=_BEST_SELLING_ITEM_FORBIDDEN,
    )
    merge_doctype_field_filters(
        merged,
        raw_json,
        doctype="Item",
        allowed_fields=frozenset(ITEM_LIST_FIELDS),
        forbidden_fields=_BEST_SELLING_ITEM_FORBIDDEN,
    )
    return merged


def _item_join_and_where(prefilters: dict) -> tuple[str, str, list]:
    if not prefilters:
        return "", "", []
    parts = []
    vals = []
    for col, val in prefilters.items():
        if col not in ITEM_LIST_FIELDS or not _FIELD_NAME_OK.match(col):
            continue
        parts.append(f"i.`{col}` = %s")
        vals.append(val)
    if not parts:
        return "", "", []
    join_sql = " INNER JOIN `tabItem` i ON i.name = sii.item_code "
    where_sql = " AND " + " AND ".join(parts)
    return join_sql, where_sql, vals


@frappe.whitelist(allow_guest=True)
def get_best_selling_list(
    page: int = 1,
    page_length: int = 20,
    field_filters: str = None,
    sort_by: str = "total_qty",
    sort_order: str = "desc",
) -> dict:
    """
    Public API — paginated list of best-selling items.

    Items are ranked on total qty from submitted Sales Invoices. Optional
    filters match Item fields (query string or JSON field_filters), same
    rules as get_item_list (variant_of cannot be overridden).

    Query Parameters:
        page          (int)           Page number, 1-based. Default: 1
        page_length   (int)           Records per page. Default: 20, max: 100
        field_filters (str)           JSON AND Item filters (overrides query keys)
        Other Item list fields as ?item_group=...&custom_product_type=...
        sort_by       (str)           total_qty | item_code
        sort_order    (asc|desc)      Sort direction. Default: desc
    """
    page = max(1, cint(page) or 1)
    page_length = min(max(1, cint(page_length) or 20), MAX_PAGE_LENGTH)
    offset = (page - 1) * page_length

    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"
    sort_by = "total_qty" if sort_by not in ("total_qty", "item_code") else sort_by

    item_prefilters = _item_prefilters_for_best_selling(field_filters)
    join_sql, where_extra, extra_params = _item_join_and_where(item_prefilters)

    item_list = frappe.db.sql(
        f"""
        SELECT
            sii.item_code,
            SUM(sii.qty) AS total_qty
        FROM `tabSales Invoice Item` sii
        {join_sql}
        WHERE sii.docstatus = 1
        {where_extra}
        GROUP BY sii.item_code
        ORDER BY {sort_by} {sort_order}
        LIMIT %s OFFSET %s
        """,
        tuple(extra_params) + (page_length, offset),
        as_dict=True,
    )

    count_rows = frappe.db.sql(
        f"""
        SELECT COUNT(DISTINCT sii.item_code) AS total_count
        FROM `tabSales Invoice Item` sii
        {join_sql}
        WHERE sii.docstatus = 1
        {where_extra}
        """,
        tuple(extra_params),
        as_dict=True,
    )
    total_records = int(count_rows[0]["total_count"]) if count_rows else 0

    pagination = {
        "page": page,
        "page_length": page_length,
        "total_records": total_records,
        "total_pages": (total_records + page_length - 1) // page_length
        if total_records > 0
        else 0,
        "has_next_page": (page * page_length) < total_records,
    }

    item_codes = [row["item_code"] for row in item_list if row.get("item_code")]

    items_by_code = {}
    if item_codes:
        items = frappe.get_all(
            "Item",
            fields=[
                "name",
                "item_code",
                "item_name",
                "item_group",
                "image",
                "description",
                "standard_rate",
            ],
            filters={"name": ["in", item_codes]},
        )
        for item in items:
            items_by_code[item["name"]] = item

    best_selling_items = []
    for row in item_list:
        code = row["item_code"]
        if code in items_by_code:
            item_data = items_by_code[code].copy()
            item_data["total_qty_sold"] = row["total_qty"]
            best_selling_items.append(item_data)

    return {"items": best_selling_items, "pagination": pagination}
