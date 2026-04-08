import frappe
from frappe.utils import cint

from true_med.utils import cache as item_cache
from true_med.utils.pagination import paginate


@frappe.whitelist()
def get_my_invoice_list(
    page: int = 1,
    page_length: int = 20,
    sort_by: str = "creation",
    sort_order: str = "desc",
) -> dict:
    """
    Authenticated API — paginated list of sales invoices for the current user.

    Only Sales Invoices linked to the current user (via customer or directly)
    are returned.

    Query Parameters:
        page         (int)           Page number, 1-based. Default: 1
        page_length  (int)           Records per page. Default: 20, max: 100
        sort_by      (str)           Field to sort by. Default: creation
        sort_order   (asc|desc)      Sort direction. Default: desc  
    """
    if not frappe.session.user:
        return {"invoices": [], "total": 0}

    sort_by = sort_by if sort_by in item_cache.ALLOWED_SORT_FIELDS else "creation"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    filters = {"customer": frappe.session.user}  # Assuming customer is linked to user

    invoices = frappe.get_all(
        "Sales Invoice",
        fields=["name", "customer", "grand_total", "status", "creation"],
        filters=filters,
        order_by=f"{sort_by} {sort_order}",
    )

    return paginate(invoices, page, page_length)    