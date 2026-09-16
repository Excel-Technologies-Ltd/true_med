import frappe
from frappe import _
from true_med.utils.spam_validation import verify_turnstile, analyze_submission, check_rate_limit


@frappe.whitelist(allow_guest=True)
def submit_get_in_touch(
    first_name: str,
    phone_number: str,
    email: str,
    subject: str,
    message: str,
    last_name: str = None,
    brand : str = None,
    company : str = None,
    cf_turnstile_response: str = None,
    website_url_hp: str = None,
) -> dict:
    """
    Public API — submit a Get in Touch contact form.
    """
    # Rate limit check
    if hasattr(frappe.local, "request") and frappe.local.request:
        remote_ip = frappe.local.request.remote_addr
        check_rate_limit(remote_ip)
    else:
        remote_ip = "127.0.0.1"

    # Basic validation
    for field, value in [
        ("first_name", first_name),
        ("phone_number", phone_number),
        ("email", email),
        ("subject", subject),
        ("message", message),
        ("brand", brand),
    ]:
        if not value or not str(value).strip():
            frappe.throw(_("{0} is required").format(field.replace("_", " ").title()), frappe.MandatoryError)

    if not frappe.utils.validate_email_address(email):
        frappe.throw(_("Invalid email address"), frappe.ValidationError)

    # Spam Validation
    status = "Review"
    spam_reason = ""
    
    if not verify_turnstile(cf_turnstile_response, remote_ip):
        status = "Spam"
        spam_reason = "Turnstile verification failed"
    else:
        submission_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "message": message,
            "website_url_hp": website_url_hp
        }
        status, spam_reason = analyze_submission(submission_data)

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
            "brand": brand,
            "company": company,
            "status": status,
            "spam_reason": spam_reason,
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "message": _("Thank you for getting in touch. We will respond shortly."),
        "name": doc.name,
    }


