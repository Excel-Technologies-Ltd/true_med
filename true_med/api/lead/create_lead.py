import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def submit_lead(
    email: str,
    first_name: str = None,
    last_name: str = None,
    phone_number: str = None,
) -> dict:
    """
    Public API — create a CRM Lead.

    Required fields:
        email        (str)  Lead email address

    Optional fields:
        first_name   (str)  Lead first name
        last_name    (str)  Lead last name
        phone_number (str)  Lead mobile number

    Rules:
        - Source is always set to "Advertisement"

    Endpoint:
        POST /api/method/true_med.api.lead.create_lead.submit_lead
    """
    if not email or not str(email).strip():
        frappe.throw(_("Email is required"), frappe.MandatoryError)

    email = str(email).strip()
    if not frappe.utils.validate_email_address(email):
        frappe.throw(_("Invalid email address"), frappe.ValidationError)

    lead_source = _ensure_advertisement_lead_source()

    lead_doc = frappe.get_doc(
        {
            "doctype": "Lead",
            "email_id": email,
            "first_name": (first_name or "").strip() or None,
            "last_name": (last_name or "").strip() or None,
            "mobile_no": str(phone_number).strip() if phone_number else None,
            "source": lead_source,
        }
    )
    try:
        lead_doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except frappe.DuplicateEntryError:
        frappe.db.rollback()
        existing = frappe.db.get_value("Lead", {"email_id": email}, "name")
        return {
            "message": _("you already have subscribed"),
        }

    return {
        "message": _("You have subscribed successfully."),
    }


def _ensure_advertisement_lead_source() -> str:
    source_name = "Advertisement"
    if frappe.db.exists("Lead Source", source_name):
        return source_name

    source_doc = frappe.get_doc(
        {
            "doctype": "Lead Source",
            "source_name": source_name,
        }
    )
    source_doc.insert(ignore_permissions=True)
    return source_doc.name
