import frappe
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

    total_count = frappe.db.count(doctype, filters or {})

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
