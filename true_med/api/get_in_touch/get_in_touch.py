import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def submit_get_in_touch(
    first_name: str,
    phone_number: str,
    email: str,
    subject: str,
    message: str,
    last_name: str = None,
) -> dict:
    """
    Public API — submit a Get in Touch contact form.

    Required fields:
        first_name   (str)  Sender's first name
        phone_number (str)  Contact phone number
        email        (str)  Contact email address
        subject      (str)  Message subject
        message      (str)  Message body

    Optional fields:
        last_name    (str)  Sender's last name

    Returns the created document name on success.

    Endpoint:
        POST /api/method/true_med.api.get_in_touch.get_in_touch.submit_get_in_touch
    """
    # Basic validation
    for field, value in [
        ("first_name", first_name),
        ("phone_number", phone_number),
        ("email", email),
        ("subject", subject),
        ("message", message),
    ]:
        if not value or not str(value).strip():
            frappe.throw(_("{0} is required").format(field.replace("_", " ").title()), frappe.MandatoryError)

    if not frappe.utils.validate_email_address(email):
        frappe.throw(_("Invalid email address"), frappe.ValidationError)

    full_name = " ".join(filter(None, [first_name.strip(), (last_name or "").strip()]))

    doc = frappe.get_doc(
        {
            "doctype": "Get in Touch",
            "first_name": first_name.strip(),
            "last_name": (last_name or "").strip() or None,
            "full_name": full_name,
            "phone_number": str(phone_number).strip(),
            "email": email.strip(),
            "subject": subject.strip(),
            "message": message.strip(),
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "message": _("Thank you for getting in touch. We will respond shortly."),
        "name": doc.name,
    }
