import frappe
from frappe import _
from true_med.utils.spam_validation import verify_turnstile, analyze_submission, get_form_rate_limit
from frappe.rate_limiter import rate_limit


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=get_form_rate_limit, seconds=86400, ip_based=True)
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
    # Basic validation
    for field, value in [
        ("first_name", first_name),
        ("phone_number", phone_number),
        ("email", email),
        ("subject", subject),
        ("message", message),
        ("brand", brand),
        ("cf_turnstile_response", cf_turnstile_response),
    ]:
        if not value or not str(value).strip():
            if field == "cf_turnstile_response":
                frappe.throw(_("Please complete the captcha verification"), frappe.MandatoryError)
            else:
                frappe.throw(_("{0} is required").format(field.replace("_", " ").title()), frappe.MandatoryError)

    if not frappe.utils.validate_email_address(email):
        frappe.throw(_("Invalid email address"), frappe.ValidationError)

    # Spam Validation
    status = "Review"
    spam_reason = ""
    
    if not verify_turnstile(cf_turnstile_response):
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


