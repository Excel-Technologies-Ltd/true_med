import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def get_sales_tax(title: str = None, name: str = None) -> dict:
    """
    Public API — Sales Taxes and Charges Template detail with all tax rows.

    Query Parameters (one required):
        title  (str)  Template title, e.g. "Wyoming"
        name   (str)  Template name, e.g. "Wyoming - TPI" (as returned by the list API)

    Response:
        {
            "data": {
                "name": "Wisconsin - THB",
                "title": "Wisconsin - THB",
                "company": "True Med",
                "is_default": 0,
                "disabled": 0,
                "tax_category": null,
                "taxes": [
                    {
                        "charge_type": "On Net Total",
                        "account_head": "...",
                        "description": "...",
                        "rate": 5.0,
                        "included_in_print_rate": 0,
                        "cost_center": null
                    }
                ]
            }
        }

    Error responses:
        400  neither title nor name provided
        404  template not found

    Endpoint:
        GET /api/method/true_med.api.sales_tax.get_sales_tax.get_sales_tax?title=Wisconsin
        GET /api/method/true_med.api.sales_tax.get_sales_tax.get_sales_tax?name=Wisconsin%20-%20TPI
    """
    title = title or _get_request_arg("title")
    name = name or _get_request_arg("name")
    if not title and not name:
        frappe.throw(_("title or name is required"), frappe.MandatoryError)

    # `name` is the composite key ("Wisconsin - TPI"); `title` is "Wisconsin"
    lookup = {"name": name} if name else {"title": title}
    lookup["disabled"] = 0
    template = frappe.db.get_value("Sales Taxes and Charges Template", lookup, "name")
    if not template:
        frappe.throw(
            _("Sales Taxes and Charges Template {0} not found").format(name or title),
            frappe.DoesNotExistError,
        )
    name = template

    data = _get_template_data(name)
    data["taxes"] = _get_taxes(name)

    return {"data": data}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _get_request_arg(key: str):
    return frappe.form_dict.get(key) or (
        frappe.local.request.args.get(key)
        if getattr(frappe.local, "request", None)
        else None
    )


def _get_template_data(title: str) -> dict:
    fields = ["name", "title", "company", "is_default", "disabled", "tax_category"]
    doc = frappe.db.get_value(
        "Sales Taxes and Charges Template", title, fields, as_dict=True
    )
    return dict(doc)


def _get_taxes(title: str) -> list:
    return frappe.get_all(
        "Sales Taxes and Charges",
        filters={
            "parent": title,
            "parenttype": "Sales Taxes and Charges Template",
        },
        fields=[
            "charge_type",
            "account_head",
            "description",
            "rate",
            "included_in_print_rate",
            "cost_center",
        ],
        order_by="idx asc",
        ignore_permissions=True,
    )
