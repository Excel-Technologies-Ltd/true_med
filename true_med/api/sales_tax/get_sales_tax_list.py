import frappe
from frappe.utils import cint, flt

from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import paginate

SALES_TAX_LIST_FIELDS = [
    "name",
    "title",
    "company",
    "is_default",
    "tax_category",
    "modified",
    "creation",
]

ALLOWED_SORT_FIELDS = {
    "title",
    "modified",
    "creation",
}

_SALES_TAX_LIST_RESERVED = BASE_LIST_API_RESERVED_KEYS | frozenset({"include_taxes"})


@frappe.whitelist(allow_guest=True)
def get_sales_tax_list(
    page: int = 1,
    page_length: int = 20,
    search: str = None,
    field_filters: str = None,
    include_taxes: int = 1,
    sort_by: str = "title",
    sort_order: str = "asc",
) -> dict:
    """
    Public API — paginated list of enabled Sales Taxes and Charges Templates.

    Query Parameters:
        page          (int)       Page number, 1-based. Default: 1
        page_length   (int)       Records per page. Default: 20, max: 100
        search        (str)       Partial match (LIKE) on title
        field_filters (str)       JSON object of {field: value} AND filters.
                                  Keys must be SALES_TAX_LIST_FIELDS.
        Other allowed fields as ?company=TrueMed%20Pharma%20Inc&is_default=1
        include_taxes (0|1)       Attach tax rows + total_rate. Default: 1
        sort_by       (str)       title | modified | creation
        sort_order    (asc|desc)  Sort direction. Default: asc

    Response:
        {
            "data": [
                {
                    "name": "Wyoming - TPI",
                    "title": "Wyoming",
                    "company": "TrueMed Pharma Inc",
                    "is_default": 0,
                    "tax_category": null,
                    "total_rate": 4.0,
                    "taxes": [
                        {"charge_type": "On Net Total", "account_head": "Tax - TPI",
                         "description": "...", "rate": 4.0, ...}
                    ]
                }
            ],
            "pagination": {...}
        }

    Endpoint:
        GET /api/method/true_med.api.sales_tax.get_sales_tax_list.get_sales_tax_list
    """
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "title"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    filters = {"disabled": 0}
    query_ff = get_query_field_filters(
        allowed_fields=frozenset(SALES_TAX_LIST_FIELDS),
        reserved_keys=_SALES_TAX_LIST_RESERVED,
    )
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype="Sales Taxes and Charges Template",
        allowed_fields=frozenset(SALES_TAX_LIST_FIELDS),
    )
    merge_doctype_field_filters(
        filters,
        normalize_field_filters_json(field_filters),
        doctype="Sales Taxes and Charges Template",
        allowed_fields=frozenset(SALES_TAX_LIST_FIELDS),
    )

    data, pagination = paginate(
        doctype="Sales Taxes and Charges Template",
        fields=SALES_TAX_LIST_FIELDS,
        filters=filters,
        or_filters=_build_search_filters(search),
        order_by=f"`tabSales Taxes and Charges Template`.`{sort_by}` {sort_order}",
        page=cint(page),
        page_length=cint(page_length),
        ignore_permissions=True,
    )

    if cint(include_taxes):
        _attach_taxes(data)

    return {"data": data, "pagination": pagination}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _build_search_filters(search: str | None) -> list:
    if not search or not str(search).strip():
        return []
    keyword = f"%{str(search).strip()}%"
    return [["title", "like", keyword]]


def _attach_taxes(templates: list) -> None:
    """Attach tax rows and their summed rate to each template in one query."""
    if not templates:
        return

    names = [t["name"] for t in templates]
    rows = frappe.get_all(
        "Sales Taxes and Charges",
        filters={
            "parent": ["in", names],
            "parenttype": "Sales Taxes and Charges Template",
        },
        fields=[
            "parent",
            "charge_type",
            "account_head",
            "description",
            "rate",
            "included_in_print_rate",
            "cost_center",
        ],
        order_by="parent asc, idx asc",
        ignore_permissions=True,
    )

    taxes_by_parent = {}
    for row in rows:
        parent = row.pop("parent")
        taxes_by_parent.setdefault(parent, []).append(row)

    for t in templates:
        taxes = taxes_by_parent.get(t["name"], [])
        t["taxes"] = taxes
        t["total_rate"] = flt(sum(flt(r["rate"]) for r in taxes))
