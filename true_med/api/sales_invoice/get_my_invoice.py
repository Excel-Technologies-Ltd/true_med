import frappe

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

    customer = frappe.db.get_value("Customer", {"email_id": frappe.session.user})

    filters = {"customer": customer}



    data, pagination = paginate(
        "Sales Invoice",
        fields=["name", "customer", "customer_name", "grand_total", "currency", "status", "creation"],
        filters=filters,
        order_by=f"{sort_by} {sort_order}",
        page=page,
        page_length=page_length,
    )

    invoice_names = [inv["name"] for inv in data]

    items_by_invoice = {}
    if invoice_names:
        rows = frappe.get_all(
            "Sales Invoice Item",
            fields=["parent", "item_code", "item_name", "qty", "uom", "rate", "amount", "description"],
            filters={"parent": ["in", invoice_names]},
            order_by="idx asc",
        )
        for row in rows:
            items_by_invoice.setdefault(row["parent"], []).append({
                k: v for k, v in row.items() if k != "parent"
            })

    for inv in data:
        inv["items"] = items_by_invoice.get(inv["name"], [])

    return {"invoices": data, "pagination": pagination}    