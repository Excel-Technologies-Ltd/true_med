"""
Redis cache helpers for the True Med public API.

All public APIs are cached in Redis (Frappe's built-in cache layer).
Cache is automatically invalidated via doc_events in hooks.py whenever
a tracked document is saved or deleted.

Key namespaces
--------------
  true_med|item:{item_code}           — single item detail
  true_med|item_list:{params_hash}    — paginated item list result
  true_med|item_selling_price_range   — min/max selling prices (facet)
  true_med|blog:{name}                — single blog post detail
  true_med|blog_list:{params_hash}    — paginated blog list result
"""

import hashlib
import json

import frappe

# ---------------------------------------------------------------------------
# Allowed sort fields (used by list APIs for input validation)
# ---------------------------------------------------------------------------
ALLOWED_SORT_FIELDS = {"creation", "modified", "name", "grand_total", "status"}

# ---------------------------------------------------------------------------
# TTLs
# ---------------------------------------------------------------------------
ITEM_DETAIL_TTL = 600    # 10 minutes
ITEM_LIST_TTL = 180      # 3 minutes
BLOG_DETAIL_TTL = 600    # 10 minutes — blog content changes rarely
BLOG_LIST_TTL = 180      # 3 minutes

# ---------------------------------------------------------------------------
# Key builders — items
# ---------------------------------------------------------------------------
_ITEM_DETAIL_NS = "true_med|item:"
_ITEM_LIST_NS = "true_med|item_list:"
ITEM_SELLING_PRICE_RANGE_CACHE_KEY = "true_med|item_selling_price_range"


def item_detail_key(item_code: str) -> str:
    return f"{_ITEM_DETAIL_NS}{item_code}"


def item_list_key(**params) -> str:
    """Deterministic key from all query params that affect the list result."""
    payload = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{_ITEM_LIST_NS}{digest}"


# ---------------------------------------------------------------------------
# Key builders — blog posts
# ---------------------------------------------------------------------------
_BLOG_DETAIL_NS = "true_med|blog:"
_BLOG_LIST_NS = "true_med|blog_list:"


def blog_detail_key(name: str) -> str:
    return f"{_BLOG_DETAIL_NS}{name}"


def blog_list_key(**params) -> str:
    """Deterministic key from all blog list query params."""
    payload = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{_BLOG_LIST_NS}{digest}"


# ---------------------------------------------------------------------------
# Low-level get/set
# ---------------------------------------------------------------------------

def get(key: str):
    return frappe.cache().get_value(key)


def set(key: str, value, ttl: int):  # noqa: A001
    frappe.cache().set_value(key, value, expires_in_sec=ttl)


# ---------------------------------------------------------------------------
# Invalidation — called from hooks.py doc_events
# ---------------------------------------------------------------------------

def on_item_change(doc, method=None):
    """
    Invalidate the detail cache for this item and bust all list caches.
    Registered in hooks.py for Item on_update / on_trash.
    """
    frappe.cache().delete_value(item_detail_key(doc.name))
    _bust_item_list_caches()
    _bust_item_selling_price_range_cache()


def on_item_price_change(doc, method=None):
    """
    Item Price changes affect list pages (prices are embedded) and the
    detail page for the related item.
    Registered in hooks.py for Item Price on_update / on_trash.
    """
    frappe.cache().delete_value(item_detail_key(doc.item_code))
    _bust_item_list_caches()
    _bust_item_selling_price_range_cache()


def _bust_item_list_caches():
    """Delete all item list cache entries."""
    frappe.cache().delete_keys(_ITEM_LIST_NS)


def _bust_item_selling_price_range_cache():
    frappe.cache().delete_value(ITEM_SELLING_PRICE_RANGE_CACHE_KEY)


# ---------------------------------------------------------------------------
# Invalidation — blog posts (called from hooks.py doc_events)
# ---------------------------------------------------------------------------

def on_blog_post_change(doc, method=None):
    """
    Invalidate the detail cache for this blog post and bust all list caches.
    Registered in hooks.py for Blog Post on_update / on_trash.
    """
    frappe.cache().delete_value(blog_detail_key(doc.name))
    _bust_blog_list_caches()


def on_blogger_change(doc, method=None):
    """
    Blogger profile changes affect any list or detail that embeds blogger_info.
    Bust all blog caches so stale profile data is not served.
    """
    _bust_blog_list_caches()
    # Cannot target individual posts efficiently without a reverse lookup;
    # bust all detail keys by prefix instead.
    frappe.cache().delete_keys(_BLOG_DETAIL_NS)


def on_blog_category_change(doc, method=None):
    """Blog Category changes can affect list grouping and detail category_info."""
    _bust_blog_list_caches()
    frappe.cache().delete_keys(_BLOG_DETAIL_NS)


def _bust_blog_list_caches():
    """Delete all blog list cache entries."""
    frappe.cache().delete_keys(_BLOG_LIST_NS)
