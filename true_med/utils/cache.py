"""
Redis cache helpers for the True Med public API.

All public item APIs are cached in Redis (Frappe's built-in cache layer).
Cache is automatically invalidated via doc_events in hooks.py whenever
an Item or Item Price document is saved or deleted.

Key namespaces
--------------
  true_med|item:{item_code}          — single item detail
  true_med|item_list:{params_hash}   — paginated list result
"""

import hashlib
import json

import frappe

# ---------------------------------------------------------------------------
# TTLs
# ---------------------------------------------------------------------------
ITEM_DETAIL_TTL = 600   # 10 minutes — item content changes rarely
ITEM_LIST_TTL = 180     # 3 minutes  — list is filter-sensitive, keep short

# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------
_DETAIL_NS = "true_med|item:"
_LIST_NS = "true_med|item_list:"


def item_detail_key(item_code: str) -> str:
    return f"{_DETAIL_NS}{item_code}"


def item_list_key(**params) -> str:
    """Deterministic key from all query params that affect the list result."""
    payload = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{_LIST_NS}{digest}"


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
    _bust_list_caches()


def on_item_price_change(doc, method=None):
    """
    Item Price changes affect list pages (prices are embedded) and the
    detail page for the related item.
    Registered in hooks.py for Item Price on_update / on_trash.
    """
    frappe.cache().delete_value(item_detail_key(doc.item_code))
    _bust_list_caches()


def _bust_list_caches():
    """Delete all item list cache entries."""
    frappe.cache().delete_keys(_LIST_NS)
