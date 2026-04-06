import re

import frappe
from frappe import _
from frappe.utils import flt

from true_med.utils import cache as item_cache

ITEM_PRICE_FIELDS = [
    "item_code",
    "name",
    "price_list",
    "buying",
    "selling",
    "currency",
    "price_list_rate",
    "uom",
    "packing_unit",
    "lead_time_days",
    "valid_from",
    "valid_upto",
    "customer",
    "supplier",
    "note",
    "batch_no",
]

# Scalar fields returned in the item detail response (child tables are separate)
ITEM_FIELDS = [
    "item_code",
    "item_name",
    "item_group",
    "brand",
    "description",
    "image",
    "standard_rate",
    "stock_uom",
    "sales_uom",
    "purchase_uom",
    "is_stock_item",
    "is_sales_item",
    "is_purchase_item",
    "has_variants",
    "variant_of",
    "variant_based_on",
    "has_batch_no",
    "has_serial_no",
    "has_expiry_date",
    "shelf_life_in_days",
    "end_of_life",
    "disabled",
    "weight_per_unit",
    "weight_uom",
    "valuation_rate",
    "valuation_method",
    "warranty_period",
    "country_of_origin",
    "lead_time_days",
    "min_order_qty",
    "safety_stock",
    "max_discount",
    "over_delivery_receipt_allowance",
    "over_billing_allowance",
    "is_fixed_asset",
    "default_bom",
    "inspection_required_before_purchase",
    "inspection_required_before_delivery",
    "allow_negative_stock",
    "published_in_website",
    "grant_commission",
    "total_projected_qty",
    "modified",
    "creation",
]


@frappe.whitelist(allow_guest=True)
def get_item(item_code: str) -> dict:
    """
    Public API — full item detail by item_code.

    Response includes all scalar fields, child tables (barcodes, UOMs,
    attributes, taxes, item_defaults), all Item Price entries, and — for
    template items — the full list of variants with their own attributes
    and prices.

    Results are cached in Redis per item_code and invalidated automatically
    when the Item or any of its Item Price records change.

    Path Parameter:
        item_code  (str, required)  The item_code of the item to fetch.

    Error responses:
        400  item_code not provided
        404  item not found

    Endpoint:
        GET /api/method/true_med.api.item.get_item.get_item?item_code=ITEM-001
    """
    if not item_code:
        frappe.throw(_("item_code is required"), frappe.MandatoryError)

    resolved = _resolve_item_code(item_code)
    if not resolved:
        frappe.throw(_("Item {0} not found").format(item_code), frappe.DoesNotExistError)

    cache_key = item_cache.item_detail_key(resolved)
    cached = item_cache.get(cache_key)
    if cached:
        return cached

    doc = frappe.get_doc("Item", resolved)

    data = _serialize_item(doc)

    # Bulk-fetch prices for both the template and all its variants in the
    # fewest possible queries so the cache is warm for all child data.
    if doc.has_variants:
        data["variants"] = _get_variants_with_data(resolved)
        data["prices"] = _get_prices_for_codes([resolved])
    else:
        data["variants"] = []
        data["prices"] = _get_prices_for_codes([resolved])

    result = {"data": data}
    item_cache.set(cache_key, result, ttl=item_cache.ITEM_DETAIL_TTL)

    return result


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _resolve_item_code(item_code: str) -> str | None:
    """
    Resolve item_code, tolerating the URL encoding quirk where + is decoded
    as a space (application/x-www-form-urlencoded standard).

    Strategy:
      1. Try exact match.
      2. If the code contains 2+ consecutive spaces (signature of a decoded +),
         collapse them to a SQL % wildcard and do a LIKE lookup.
    """
    if frappe.db.exists("Item", item_code):
        return item_code

    like_pattern = re.sub(r" {2,}", "%", item_code)
    if like_pattern == item_code:
        return None  # no multi-spaces present, nothing to recover

    result = frappe.db.sql(
        "SELECT `name` FROM `tabItem` WHERE `name` LIKE %s LIMIT 1",
        like_pattern,
    )
    return result[0][0] if result else None


def _get_prices_for_codes(item_codes: list) -> list:
    """
    Fetch Item Price rows for one or more item codes in a single query.
    Returns records sorted selling-first, then by price list name.
    """
    prices = frappe.get_all(
        "Item Price",
        filters={"item_code": ["in", item_codes]},
        fields=ITEM_PRICE_FIELDS,
        order_by="selling desc, buying desc, price_list asc",
        ignore_permissions=True,
    )
    return prices


def _get_variants_with_data(template_code: str) -> list:
    """
    Fetch all variants of a template item with their attributes and prices.

    Uses exactly 3 queries regardless of variant count (no N+1):
      1. Fetch all variant Item rows
      2. Bulk-fetch all Item Variant Attribute rows
      3. Bulk-fetch all Item Price rows for all variants
    """
    variants = frappe.get_all(
        "Item",
        filters={"variant_of": template_code},
        fields=[
            "item_code",
            "item_name",
            "image",
            "standard_rate",
            "stock_uom",
            "disabled",
            "modified",
        ],
        order_by="item_name asc",
        ignore_permissions=True,
    )

    if not variants:
        return []

    variant_codes = [v["item_code"] for v in variants]

    # Query 2: attributes for all variants
    all_attrs = frappe.get_all(
        "Item Variant Attribute",
        filters={"parent": ["in", variant_codes]},
        fields=["parent", "attribute", "attribute_value"],
        ignore_permissions=True,
    )
    attrs_by_variant = {}
    for attr in all_attrs:
        attrs_by_variant.setdefault(attr["parent"], []).append(
            {"attribute": attr["attribute"], "attribute_value": attr["attribute_value"]}
        )

    # Query 3: prices for all variants
    all_prices = _get_prices_for_codes(variant_codes)
    prices_by_variant = {}
    for price in all_prices:
        prices_by_variant.setdefault(price["item_code"], []).append(price)

    for variant in variants:
        variant["attributes"] = attrs_by_variant.get(variant["item_code"], [])
        variant["prices"] = prices_by_variant.get(variant["item_code"], [])

    return variants


def _serialize_item(doc) -> dict:
    """Convert an Item Document to a plain dict. Child tables are separate keys."""
    data = {field: doc.get(field) for field in ITEM_FIELDS if hasattr(doc, field)}

    data["barcodes"] = [
        {"barcode": row.barcode, "barcode_type": row.barcode_type}
        for row in (doc.barcodes or [])
    ]

    data["uoms"] = [
        {"uom": row.uom, "conversion_factor": flt(row.conversion_factor)}
        for row in (doc.uoms or [])
    ]

    data["attributes"] = [
        {
            "attribute": row.attribute,
            "attribute_value": row.attribute_value,
            "from_range": flt(row.from_range),
            "to_range": flt(row.to_range),
            "increment": flt(row.increment),
            "numeric_values": row.numeric_values,
        }
        for row in (doc.attributes or [])
    ]

    data["taxes"] = [
        {
            "item_tax_template": row.item_tax_template,
            "tax_category": row.tax_category,
            "valid_from": row.valid_from,
        }
        for row in (doc.taxes or [])
    ]

    data["item_defaults"] = [
        {
            "company": row.company,
            "default_warehouse": row.default_warehouse,
            "default_price_list": row.default_price_list,
            "buying_cost_center": row.buying_cost_center,
            "selling_cost_center": row.selling_cost_center,
            "expense_account": row.expense_account,
            "income_account": row.income_account,
        }
        for row in (doc.item_defaults or [])
    ]

    return data
