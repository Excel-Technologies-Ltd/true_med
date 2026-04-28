"""
Shared helpers for True Med list APIs.

Undeclared query-string keys are ignored by Frappe whitelisted methods. Any
filter on a list field can be passed as ?field_name=value; these helpers read
frappe.local.form_dict, validate keys, coerce types from DocType meta, and
merge into the filters dict used with paginate / get_all.

Also supports JSON `field_filters` (same shape as a dict); JSON overrides
plain query params for duplicate keys when you merge JSON second.
"""

import frappe
from frappe.utils import cint, flt

# Standard control params for list endpoints (never treated as doctype fields).
BASE_LIST_API_RESERVED_KEYS = frozenset(
    {
        "cmd",
        "page",
        "page_length",
        "search",
        "search_fields",
        "field_filters",
        "price_min",
        "price_max",
        "sort_by",
        "sort_order",
    }
)


def get_query_field_filters(
    *,
    allowed_fields: set[str] | frozenset[str],
    reserved_keys: set[str] | frozenset[str] | None = None,
    forbidden_fields: set[str] | frozenset[str] | None = None,
) -> dict:
    """
    Return {fieldname: raw_value} from the current request for keys that are
    allowed DocType list columns, excluding reserved and forbidden keys.
    """
    reserved = BASE_LIST_API_RESERVED_KEYS | frozenset(reserved_keys or [])
    forbidden = frozenset(forbidden_fields or [])
    allowed = frozenset(allowed_fields) - forbidden

    fd = frappe.local.form_dict or {}
    out = {}
    for key in fd:
        if key not in allowed or key in reserved:
            continue
        val = fd.get(key)
        if val is None or val == "":
            continue
        out[key] = val
    return out


def merge_doctype_field_filters(
    filters: dict,
    field_filters: dict | None,
    *,
    doctype: str,
    allowed_fields: set[str] | frozenset[str],
    forbidden_fields: set[str] | frozenset[str] | None = None,
) -> None:
    """Merge validated field filters into filters dict (mutates filters)."""
    if not field_filters:
        return

    forbidden = frozenset(forbidden_fields or [])
    allowed = frozenset(allowed_fields)
    meta = frappe.get_meta(doctype)

    for key, raw in field_filters.items():
        if key in forbidden or key not in allowed:
            continue
        df = meta.get_field(key)
        if not df or df.fieldtype in ("Table", "Table MultiSelect"):
            continue
        if raw is None or raw == "":
            continue
        filters[key] = coerce_field_filter_value(df.fieldtype, raw)


def coerce_field_filter_value(fieldtype: str, raw):
    if fieldtype == "Check":
        return cint(raw)
    if fieldtype == "Int":
        return cint(raw)
    if fieldtype in ("Float", "Currency", "Percent"):
        return flt(raw)
    return raw


def normalize_field_filters_json(field_filters) -> dict | None:
    if not field_filters:
        return None
    if isinstance(field_filters, str):
        field_filters = frappe.parse_json(field_filters)
    if not isinstance(field_filters, dict):
        return None
    return field_filters
