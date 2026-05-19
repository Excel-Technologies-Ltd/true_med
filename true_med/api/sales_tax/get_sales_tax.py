import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def get_sales_tax(title: str = None) -> dict:
    """
    Public API — Sales Taxes and Charges Template detail with all tax rows.

    Query Parameter:
        title  (str, required)  The title/name of the template.

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
        400  title not provided
        404  template not found

    Endpoint:
        GET /api/method/true_med.api.sales_tax.get_sales_tax.get_sales_tax?title=Wisconsin%20-%20THB
    """
    title = title or frappe.form_dict.get("title") or (
        frappe.local.request.args.get("title")
        if getattr(frappe.local, "request", None)
        else None
    )
    if not title:
        frappe.throw(_("title is required"), frappe.MandatoryError)

    # Look up by the `title` field (e.g. "Wisconsin"), not by the composite name
    name = frappe.db.get_value(
        "Sales Taxes and Charges Template", {"title": title, "disabled": 0}, "name"
    )
    if not name:
        frappe.throw(
            _("Sales Taxes and Charges Template {0} not found").format(title),
            frappe.DoesNotExistError,
        )

    data = _get_template_data(name)
    data["taxes"] = _get_taxes(name)

    return {"data": data}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


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
