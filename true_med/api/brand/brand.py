import frappe
from frappe import _

from true_med.utils import cache as brand_cache


@frappe.whitelist(allow_guest=True)
def get_brand(brand: str = None) -> dict:
    """
    Public API — single Brand detail with item count.

    Results are cached in Redis per brand name and invalidated automatically
    when the Brand document changes.

    Path Parameter:
        brand  (str, required)  The name of the brand to fetch.

    Error responses:
        400  brand not provided
        404  brand not found

    Endpoint:
        GET /api/method/true_med.api.brand.brand.get_brand?brand=Acme
    """
    brand = brand or frappe.form_dict.get("brand") or (
        frappe.local.request.args.get("brand") if getattr(frappe.local, "request", None) else None
    )
    if not brand:
        frappe.throw(_("brand is required"), frappe.MandatoryError)

    if not frappe.db.exists("Brand", brand):
        frappe.throw(_("Brand {0} not found").format(brand), frappe.DoesNotExistError)

    cache_key = brand_cache.brand_detail_key(brand)
    cached = brand_cache.get(cache_key)
    if cached:
        return cached

    data = _get_brand_data(brand)
    data["item_count"] = _get_item_count(brand)
    data["custom_faq"] = _get_faq(brand)

    result = {"data": data}
    brand_cache.set(cache_key, result, ttl=brand_cache.BRAND_DETAIL_TTL)
    return result


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _get_brand_data(brand: str) -> dict:
    fields = ["name", "brand", "description", "image"]
    doc = frappe.db.get_value("Brand", brand, fields, as_dict=True)
    return dict(doc)


def _get_faq(brand: str) -> list:
    return frappe.get_all(
        "Got Questions",
        filters={"parent": brand, "parenttype": "Brand"},
        fields=["question", "answer"],
        order_by="idx asc",
        ignore_permissions=True,
    )


def _get_item_count(brand: str) -> int:
    """Count active top-level items for this brand."""
    return frappe.db.count(
        "Item",
        filters={"brand": brand, "disabled": 0, "variant_of": ["is", "not set"]},
    )
