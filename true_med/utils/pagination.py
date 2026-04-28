import frappe
from frappe.model.db_query import DatabaseQuery
from frappe.utils import cint

# Hard cap to prevent abusive requests that dump the entire catalogue.
MAX_PAGE_LENGTH = 100


def get_pagination_meta(total_count: int, page: int, page_length: int) -> dict:
    """
    Build pagination metadata from total count, current page, and page size.

    Returns a dict with:
        total_count     - total number of matching records
        total_pages     - total number of pages
        current_page    - current page number (1-based)
        page_length     - records per page
        has_next        - whether a next page exists
        has_previous    - whether a previous page exists
        next_page       - next page number or None
        previous_page   - previous page number or None
    """
    total_pages = max(1, -(-total_count // page_length)) if page_length else 1  # ceiling division

    return {
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_length": page_length,
        "has_next": page < total_pages,
        "has_previous": page > 1,
        "next_page": page + 1 if page < total_pages else None,
        "previous_page": page - 1 if page > 1 else None,
    }


def paginate(
    doctype: str,
    fields: list,
    filters: dict | list = None,
    or_filters: dict | list = None,
    order_by: str = "modified desc",
    page: int = 1,
    page_length: int = 20,
    ignore_permissions: bool = False,
) -> tuple[list, dict]:
    """
    Generic paginator for any DocType.

    Args:
        doctype:            Frappe DocType name (e.g. "Item")
        fields:             List of field names to fetch
        filters:            Dict or list of filter conditions (AND)
        or_filters:         Dict or list of filter conditions (OR)
        order_by:           SQL ORDER BY clause, e.g. "modified desc"
        page:               1-based page number
        page_length:        Number of records per page
        ignore_permissions: Skip Frappe role permission checks (use for
                            public/guest endpoints that are already gated
                            by @frappe.whitelist(allow_guest=True))

    Returns:
        (data, pagination) tuple where:
            data       - list of record dicts
            pagination - dict from get_pagination_meta()

    Usage:
        data, meta = paginate("Item", ["item_code", "item_name"],
                              filters={"disabled": 0}, page=2,
                              ignore_permissions=True)
    """
    page = max(1, cint(page))
    page_length = min(max(1, cint(page_length)), MAX_PAGE_LENGTH)
    limit_start = (page - 1) * page_length

    total_count = _count_with_optional_or_filters(
        doctype,
        filters,
        or_filters,
        ignore_permissions,
    )

    data = frappe.get_list(
        doctype,
        fields=fields,
        filters=filters or {},
        or_filters=or_filters or [],
        order_by=order_by,
        limit_start=limit_start,
        limit_page_length=page_length,
        ignore_permissions=ignore_permissions,
    )

    pagination = get_pagination_meta(total_count, page, page_length)

    return data, pagination


def _count_with_optional_or_filters(
    doctype: str,
    filters: dict | list,
    or_filters: dict | list,
    ignore_permissions: bool,
) -> int:
    """
    frappe.db.count ignores or_filters; use DatabaseQuery when OR logic applies.
    """
    if or_filters:
        cnt_rows = DatabaseQuery(doctype).execute(
            fields=[f"count(`tab{doctype}`.`name`) as total_count"],
            filters=filters or {},
            or_filters=or_filters or [],
            order_by=None,
            limit_start=0,
            limit_page_length=0,
            ignore_permissions=ignore_permissions,
        )
        if not cnt_rows:
            return 0
        return int((cnt_rows[0] or {}).get("total_count") or 0)

    return frappe.db.count(doctype, filters or {})
