import frappe
from frappe import _

from true_med.utils import cache as sbm_cache


@frappe.whitelist(allow_guest=True)
def get_shop_by_moment(name: str = None) -> dict:
    """
    Public API — single Shop by Moment detail with item count.

    Results are cached in Redis per name and invalidated automatically
    when the Shop by Moment document changes.

    Path Parameter:
        name  (str, required)  The name (moment_name) of the Shop by Moment to fetch.

    Error responses:
        400  name not provided
        404  name not found

    Endpoint:
        GET /api/method/true_med.api.shop_by_moment.shop_by_moment.get_shop_by_moment?name=Energy
    """
    name = name or frappe.form_dict.get("name") or (
        frappe.local.request.args.get("name") if getattr(frappe.local, "request", None) else None
    )
    if not name:
        frappe.throw(_("name is required"), frappe.MandatoryError)

    if not frappe.db.exists("Shop by Moment", name):
        frappe.throw(_("Shop by Moment {0} not found").format(name), frappe.DoesNotExistError)

    cache_key = sbm_cache.shop_by_moment_detail_key(name)
    cached = sbm_cache.get(cache_key)
    if cached:
        return cached

    data = _get_shop_by_moment_data(name)
    data["item_count"] = _get_item_count(name)

    result = {"data": data}
    sbm_cache.set(cache_key, result, ttl=sbm_cache.SHOP_BY_MOMENT_DETAIL_TTL)
    return result


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _get_shop_by_moment_data(name: str) -> dict:
    fields = ["name", "moment_name", "feature_image", "creation", "modified"]
    doc = frappe.db.get_value("Shop by Moment", name, fields, as_dict=True)
    return dict(doc)


def _get_item_count(name: str) -> int:
    """Count active top-level items for this moment."""
    return frappe.db.count(
        "Item",
        filters={"custom_shop_by_moment": name, "disabled": 0, "variant_of": ["is", "not set"]},
    )
