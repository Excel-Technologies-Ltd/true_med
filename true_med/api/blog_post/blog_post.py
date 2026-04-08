import frappe
from frappe import _

from true_med.utils import cache as blog_cache

# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------

BLOG_POST_FIELDS = [
    "name",
    "title",
    "published_on",
    "published",
    "blog_category",
    "blogger",
    "route",
    "blog_intro",
    "content_type",
    "content",
    "content_md",
    "content_html",
    "meta_image",
    "meta_title",
    "meta_description",
    "read_time",
    "featured",
    "disable_comments",
    "disable_likes",
    "hide_cta",
    "email_sent",
    "enable_email_notification",
    "modified",
    "creation",
]


@frappe.whitelist(allow_guest=True)
def get_blog_post(name: str) -> dict:
    """
    Public API — full blog post detail by document name.

    Response includes all scalar fields, resolved blogger profile,
    resolved blog category, and content in all formats stored (HTML,
    Markdown, rich text). Results are cached in Redis per post and
    invalidated automatically when the Blog Post changes.

    Query Parameters:
        name  (str, required)  The `name` of the Blog Post document.

    Error responses:
        400  name not provided
        404  post not found or not published

    Endpoint:
        GET /api/method/true_med.api.blog_post.blog_post.get_blog_post?name=my-first-post
    """
    if not name:
        frappe.throw(_("name is required"), frappe.MandatoryError)

    cache_key = blog_cache.blog_detail_key(name)
    cached = blog_cache.get(cache_key)
    if cached:
        return cached

    if not frappe.db.exists("Blog Post", name):
        frappe.throw(_("Blog Post {0} not found").format(name), frappe.DoesNotExistError)

    doc = frappe.get_doc("Blog Post", name)

    if not doc.published:
        frappe.throw(_("Blog Post {0} not found").format(name), frappe.DoesNotExistError)

    data = _serialize_post(doc)

    result = {"data": data}
    blog_cache.set(cache_key, result, ttl=blog_cache.BLOG_DETAIL_TTL)

    return result


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _serialize_post(doc) -> dict:
    """Convert a Blog Post Document to a plain response dict."""
    data = {field: doc.get(field) for field in BLOG_POST_FIELDS if hasattr(doc, field)}

    # Resolve blogger profile
    data["blogger_info"] = _get_blogger_info(doc.blogger)

    # Resolve blog category
    data["category_info"] = _get_category_info(doc.blog_category)

    return data


def _get_blogger_info(blogger_name: str) -> dict:
    """Fetch and return the blogger's public profile."""
    if not blogger_name:
        return {}

    blogger = frappe.db.get_value(
        "Blogger",
        blogger_name,
        ["name", "full_name", "short_name", "avatar", "bio"],
        as_dict=True,
    )
    return blogger or {}


def _get_category_info(category_name: str) -> dict:
    """Fetch and return blog category info."""
    if not category_name:
        return {}

    category = frappe.db.get_value(
        "Blog Category",
        category_name,
        ["name", "title", "route", "published"],
        as_dict=True,
    )
    return category or {}
