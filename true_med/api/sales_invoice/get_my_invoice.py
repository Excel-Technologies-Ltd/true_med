import frappe

from true_med.utils import cache as item_cache
from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import paginate

_SI_LIST_FIELDS = frozenset(
    {
        "name",
        "customer",
        "customer_name",
        "grand_total",
        "custom_delivery_status",
        "currency",
        "status",
        "creation",
        "posting_date",
        "due_date",
        "title",
        "company",
        "is_return",
    }
)
_SI_INVOICE_RESERVED = BASE_LIST_API_RESERVED_KEYS | frozenset({"customer"})


@frappe.whitelist()
def get_my_invoice_list(
    page: int = 1,
    page_length: int = 20,
    field_filters: str = None,
    sort_by: str = "creation",
    sort_order: str = "desc",
) -> dict:
    """
    Authenticated API — paginated list of sales invoices for the current user.

    Only Sales Invoices linked to the current user (via customer or directly)
    are returned.

    Query Parameters:
        page          (int)           Page number, 1-based. Default: 1
        page_length   (int)           Records per page. Default: 20, max: 100
        field_filters (str)           JSON AND filters (cannot set customer)
        Other allowed Sales Invoice fields as ?status=Paid&grand_total=100
        sort_by       (str)           Field to sort by. Default: creation
        sort_order    (asc|desc)      Sort direction. Default: desc
    """
    if not frappe.session.user:
        return {"invoices": [], "total": 0}

    sort_by = sort_by if sort_by in item_cache.ALLOWED_SORT_FIELDS else "creation"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    customer = frappe.db.get_value("Customer", {"email_id": frappe.session.user})

    filters = {"customer": customer}
    query_ff = get_query_field_filters(
        allowed_fields=_SI_LIST_FIELDS,
        reserved_keys=_SI_INVOICE_RESERVED,
        forbidden_fields=frozenset({"customer"}),
    )
    ff_json = normalize_field_filters_json(field_filters)
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype="Sales Invoice",
        allowed_fields=_SI_LIST_FIELDS,
        forbidden_fields=frozenset({"customer"}),
    )
    merge_doctype_field_filters(
        filters,
        ff_json,
        doctype="Sales Invoice",
        allowed_fields=_SI_LIST_FIELDS,
        forbidden_fields=frozenset({"customer"}),
    )

    data, pagination = paginate(
        "Sales Invoice",
        fields=["name", "customer", "customer_name", "grand_total", "currency", "custom_delivery_status", "status", "creation"],
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
            fields=["parent", "item_code", "item_name", "qty", "uom", "rate", "amount", "description", "image"],
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