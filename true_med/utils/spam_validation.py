import frappe
import requests
import re
from frappe import _

def verify_turnstile(token: str, ip: str = None) -> bool:
    """
    Verifies the Cloudflare Turnstile token.
    Returns True if valid, False otherwise.
    """
    if not token:
        return False
        
    secret_key = frappe.conf.get("turnstile_secret_key")
    if not secret_key:
        frappe.logger().warning("Turnstile secret key not configured in site_config.json")
        # Assume valid if not configured, or return False. Depending on strictness.
        return True
        
    if not ip:
        if hasattr(frappe.local, "request") and frappe.local.request:
            ip = frappe.local.request.remote_addr
        else:
            ip = "127.0.0.1"
            
    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": secret_key,
                "response": token,
                "remoteip": ip
            },
            timeout=5
        )
        result = response.json()
        return result.get("success", False)
    except Exception as e:
        frappe.logger().error(f"Turnstile verification failed: {str(e)}")
        return False

def analyze_submission(data: dict) -> tuple[str, str]:
    """
    Analyzes submission data for spam patterns.
    Returns a tuple of (status, spam_reason).
    Status can be 'Approved', 'Review', or 'Spam'.
    """
    # 1. Honeypot check
    website_url_hp = data.get("website_url_hp")
    if website_url_hp:
        return "Spam", "Honeypot field filled"

    # 2. Length checks
    first_name = data.get("first_name") or ""
    last_name = data.get("last_name") or ""
    message = data.get("message") or ""
    
    if len(first_name) > 50 or len(last_name) > 50:
        return "Review", "Name exceeds 50 characters"
        
    if len(message) > 5000:
        return "Review", "Message exceeds 5000 characters"

    # 3. Disposable/fake email check (basic domain check)
    email = data.get("email") or ""
    disposable_domains = ["mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com", "yopmail.com"]
    email_domain = email.split("@")[-1].lower() if "@" in email else ""
    if email_domain in disposable_domains:
        return "Spam", "Disposable email address detected"

    # 4. Keyboard mash check
    consonant_mash_pattern = re.compile(r'[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{6,}')
    if consonant_mash_pattern.search(first_name) or consonant_mash_pattern.search(last_name):
        return "Spam", "Possible keyboard mash detected in name"
        
    return "Approved", ""

def get_form_rate_limit():
    """
    Returns the global form rate limit from site_config.json, defaults to 3.
    Intended to be used as a callable in Frappe's @rate_limit decorator.
    """
    return frappe.utils.cint(frappe.conf.get("global_form_rate_limit") or 3)

