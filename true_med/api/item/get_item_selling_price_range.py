import frappe

from true_med.utils import cache as item_cache
from true_med.utils.cache import ITEM_SELLING_PRICE_RANGE_CACHE_KEY
from true_med.utils.item_visibility import visible_item_group_sql


def _visible_item_conditions(alias_item: str = "i", alias_template: str = "t") -> str:
    """
    Catalogue items: enabled top-level items, plus enabled variants of enabled
    templates (template prices live on their variants). The top-level item's
    Item Group must be shown on the website.
    """
    i, t = alias_item, alias_template
    return (
        f"IFNULL(`{i}`.`disabled`, 0) = 0 "
        f"AND (IFNULL(`{i}`.`variant_of`, '') = '' OR IFNULL(`{t}`.`disabled`, 0) = 0) "
        f"AND {visible_item_group_sql(f'COALESCE(`{t}`.`item_group`, `{i}`.`item_group`)')}"
    )


@frappe.whitelist(allow_guest=True)
def get_item_selling_price_range() -> dict:
    """
    Public API — min and max price_list_rate from Item Price rows where
    selling = 1, scoped to catalogue items (enabled top-level items and the
    enabled variants of enabled templates, in Item Groups shown on the website).

    Response:
        {
            "data": {
                "min_price": float | null,
                "max_price": float | null,
                "currency": str | null
            }
        }

    Endpoint:
        GET /api/method/true_med.api.item.get_item_selling_price_range.get_item_selling_price_range
    """
    cached = frappe.cache().get_value(ITEM_SELLING_PRICE_RANGE_CACHE_KEY)
    if cached is not None:
        return cached

    vis = _visible_item_conditions("i")
    row = frappe.db.sql(
        f"""
        SELECT
            MIN(ip.price_list_rate) AS min_price,
            MAX(ip.price_list_rate) AS max_price,
            SUBSTRING_INDEX(
                GROUP_CONCAT(DISTINCT ip.currency ORDER BY ip.currency),
                ',',
                1
            ) AS currency
        FROM `tabItem Price` ip
        INNER JOIN `tabItem` i ON i.name = ip.item_code
        LEFT JOIN `tabItem` t ON t.name = i.variant_of
        WHERE ip.selling = 1
          AND {vis}
        """,
        as_dict=True,
    )
    r = (row or [{}])[0]
    min_p = r.get("min_price")
    max_p = r.get("max_price")
    out = {
        "data": {
            "min_price": float(min_p) if min_p is not None else None,
            "max_price": float(max_p) if max_p is not None else None,
            "currency": r.get("currency") or None,
        }
    }
    frappe.cache().set_value(
        ITEM_SELLING_PRICE_RANGE_CACHE_KEY,
        out,
        expires_in_sec=item_cache.ITEM_LIST_TTL,
    )
    return out
