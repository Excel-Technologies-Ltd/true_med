import frappe
import requests
import re
from frappe import _

def verify_turnstile(token: str, ip: str) -> bool:
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

def check_rate_limit(ip: str):
    """
    Dynamically checks rate limit for form submissions based on site_config.json.
    Throws TooManyRequestsError if limit is exceeded.
    """
    limit = frappe.utils.cint(frappe.conf.get("form_rate_limit"))
    seconds = frappe.utils.cint(frappe.conf.get("form_rate_limit_seconds"))
    
    if not limit or not seconds:
        return
        
    cache_key = f"true_med_form_rate_limit:{ip}"
    
    # We use a redis pipeline to properly increment and set expiry
    pipeline = frappe.cache().pipeline()
    pipeline.incr(cache_key)
    # We only set expire if we are the ones who created it (count = 1), but redis EXPIRE will just update it.
    # To be safe, we can just always set EXPIRE on every request, but it resets the window.
    # A better sliding window: 
    # Use get to check count, if None set with expire, else incr.
    
    count = frappe.utils.cint(frappe.cache().get(cache_key))
    if count >= limit:
        frappe.throw(_("Too many requests. Please try again later."), frappe.TooManyRequestsError)
        
    if count == 0:
        frappe.cache().set_value(cache_key, 1, expires_in_sec=seconds)
    else:
        # standard redis incr bypasses standard cache method easily via pipeline or we can just set_value but the expiry is tricky.
        # let's just use simple get/set. In high concurrency it might lose some counts, but it's okay for basic rate limit.
        frappe.cache().set_value(cache_key, count + 1, expires_in_sec=seconds)

