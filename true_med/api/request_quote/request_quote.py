import frappe
from frappe import _
from frappe.utils.file_manager import save_file
from true_med.utils.spam_validation import verify_turnstile, analyze_submission, get_form_rate_limit
from frappe.rate_limiter import rate_limit

VALID_PRODUCT_FORMATS = {
    "Tablet", "Powder", "Capsule", "Softgel", "Liquid", "Gummies", "Cream", "Stock Formula"
}

VALID_TIME_FRAMES = {
    "Immediately",
    "Very Soon (2-3 weeks)",
    "Near Future (3-6 weeks)",
    "Foreseeable Future (6-12 weeks)",
    "Not-So-Foreseeable Future (12+ weeks)",
    "Just Kicking The Tires For Now",
}

VALID_HEAR_ABOUT_US = {"Google", "Bing", "Facebook", "Referral", "LinkedIn", "others"}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=get_form_rate_limit, seconds=86400, ip_based=True)
def submit_request_quote(
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    company_name: str,
    product_name: str,
    order_quantity: str,
    product_format: str,
    serving_size: str = None,
    servbottle_or_bulk: str = None,
    target_price_point: str = None,
    time_frame_to_start_manufacturing: str = None,
    is_there_an_allergy_claim: str = None,
    how_did_you_hear_about_us: str = None,
    others_name: str = None,
    website: str = None,
    comments: str = None,
    additional_details: str = None,
    # New File Upload Parameters
    formulaingredient_file_name: str = None,
    formulaingredient_file_data: str = None,
    cf_turnstile_response: str = None,
    website_url_hp: str = None,
) -> dict:
    """
    Public API — submit a Request Quote form without authentication.
    ...
    """
    # Required field validation
    for field, value in [
        ("first_name", first_name),
        ("last_name", last_name),
        ("email", email),
        ("phone", phone),
        ("company_name", company_name),
        ("product_name", product_name),
        ("order_quantity", order_quantity),
        ("product_format", product_format),
        ("cf_turnstile_response", cf_turnstile_response),
    ]:
        if not value or not str(value).strip():
            if field == "cf_turnstile_response":
                frappe.throw(_("Please complete the captcha verification"), frappe.MandatoryError)
            else:
                frappe.throw(
                    _("{0} is required").format(field.replace("_", " ").title()),
                    frappe.MandatoryError,
                )

    if not frappe.utils.validate_email_address(email):
        frappe.throw(_("Invalid email address"), frappe.ValidationError)

    if product_format not in VALID_PRODUCT_FORMATS:
        frappe.throw(
            _("Invalid product format. Must be one of: {0}").format(
                ", ".join(sorted(VALID_PRODUCT_FORMATS))
            ),
            frappe.ValidationError,
        )

    if time_frame_to_start_manufacturing and time_frame_to_start_manufacturing not in VALID_TIME_FRAMES:
        frappe.throw(
            _("Invalid time frame value"),
            frappe.ValidationError,
        )

    if is_there_an_allergy_claim and is_there_an_allergy_claim not in ("Yes", "No"):
        frappe.throw(_("is_there_an_allergy_claim must be 'Yes' or 'No'"), frappe.ValidationError)

    if how_did_you_hear_about_us and how_did_you_hear_about_us not in VALID_HEAR_ABOUT_US:
        frappe.throw(_("Invalid value for how_did_you_hear_about_us"), frappe.ValidationError)

    if how_did_you_hear_about_us == "others" and not (others_name or "").strip():
        frappe.throw(_("others_name is required when how_did_you_hear_about_us is 'others'"), frappe.MandatoryError)

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
            "message": (comments or "") + " " + (additional_details or ""),
            "website_url_hp": website_url_hp
        }
        status, spam_reason = analyze_submission(submission_data)

    # 1. Create the base document first
    doc = frappe.get_doc(
        {
            "doctype": "Request Quote",
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
            "email": email.strip(),
            "phone": str(phone).strip(),
            "company_name": company_name.strip(),
            "product_name": product_name.strip(),
            "order_quantity": str(order_quantity).strip(),
            "product_format": product_format,
            "serving_size": (serving_size or "").strip() or None,
            "servbottle_or_bulk": (servbottle_or_bulk or "").strip() or None,
            "target_price_point": (target_price_point or "").strip() or None,
            "time_frame_to_start_manufacturing": time_frame_to_start_manufacturing or None,
            "is_there_an_allergy_claim": is_there_an_allergy_claim or None,
            "how_did_you_hear_about_us": how_did_you_hear_about_us or None,
            "others_name": (others_name or "").strip() or None,
            "website": (website or "").strip() or None,
            "comments": (comments or "").strip() or None,
            "additional_details": (additional_details or "").strip() or None,
            "status": status,
            "spam_reason": spam_reason,
        }
    )
    doc.insert(ignore_permissions=True)

    # 2. Handle the file attachment if provided
    if formulaingredient_file_name and formulaingredient_file_data:
        try:
            # save_file automatically attaches it to the DocType and DocName
            saved_file = save_file(
                fname=formulaingredient_file_name,
                content=formulaingredient_file_data,
                dt="Request Quote",
                dn=doc.name,
                folder="Home/Attachments", 
                decode=True, # Tells Frappe to decode the Base64 string
                is_private=0 # Marks file as private (recommended for guest uploads)
            )
            
            # Link the generated file URL to your specific attach field
            doc.db_set("formulaingredient_file", saved_file.file_url)
            
        except Exception as e:
            frappe.log_error(message=frappe.get_traceback(), title="Quote File Upload Failed")
            # You can decide whether to throw an error here or let the quote succeed without the file.

    # 3. Commit the transaction
    frappe.db.commit()

    return {
        "message": _("Thank you for your quote request. We will get back to you shortly."),
        "name": doc.name,
    }