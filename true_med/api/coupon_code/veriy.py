import frappe
from frappe.utils import today, getdate


@frappe.whitelist(allow_guest=True)
def verify_coupon_code(coupon_code: str, customer: str = None) -> dict:
    """
    Verify a coupon code and return its discount details.

    Args:
        coupon_code  (str)  The coupon code string to verify.
        customer     (str)  Optional customer name. If the coupon is restricted
                            to a specific customer, this must match.

    Returns a dict with:
        valid        (bool)   Whether the coupon is usable right now.
        message      (str)    Human-readable reason when valid=False.
        coupon       (dict)   Coupon fields (present whether valid or not).
        discount     (dict)   Discount info from the linked Pricing Rule
                              (only present when valid=True and a rule exists).

    Endpoint:
        GET /api/method/true_med.api.coupon_code.veriy.verify_coupon_code
        ?coupon_code=SAVE10&customer=CUST-0001
    """
    if not coupon_code or not str(coupon_code).strip():
        frappe.throw("coupon_code is required", frappe.ValidationError)

    code = str(coupon_code).strip().upper()

    doc = frappe.db.get_value(
        "Coupon Code",
        {"coupon_code": code},
        [
            "name",
            "coupon_name",
            "coupon_type",
            "coupon_code",
            "customer",
            "pricing_rule",
            "valid_from",
            "valid_upto",
            "maximum_use",
            "used",
            "description",
        ],
        as_dict=True,
    )

    if not doc:
        return {"valid": False, "message": "Coupon code not found.", "coupon": None, "discount": None}

    coupon_data = {
        "name": doc.name,
        "coupon_name": doc.coupon_name,
        "coupon_type": doc.coupon_type,
        "coupon_code": doc.coupon_code,
        "customer": doc.customer,
        "pricing_rule": doc.pricing_rule,
        "valid_from": str(doc.valid_from) if doc.valid_from else None,
        "valid_upto": str(doc.valid_upto) if doc.valid_upto else None,
        "maximum_use": doc.maximum_use,
        "used": doc.used or 0,
        "description": doc.description,
    }

    # Customer restriction check
    if doc.customer and customer and doc.customer != customer:
        return {
            "valid": False,
            "message": "This coupon is not valid for the given customer.",
            "coupon": coupon_data,
            "discount": None,
        }

    # Date range check
    today_date = getdate(today())
    if doc.valid_from and getdate(doc.valid_from) > today_date:
        return {
            "valid": False,
            "message": f"This coupon is not valid yet. It starts on {doc.valid_from}.",
            "coupon": coupon_data,
            "discount": None,
        }
    if doc.valid_upto and getdate(doc.valid_upto) < today_date:
        return {
            "valid": False,
            "message": f"This coupon expired on {doc.valid_upto}.",
            "coupon": coupon_data,
            "discount": None,
        }

    # Usage limit check
    if doc.maximum_use and (doc.used or 0) >= doc.maximum_use:
        return {
            "valid": False,
            "message": "This coupon has reached its maximum usage limit.",
            "coupon": coupon_data,
            "discount": None,
        }

    # Fetch discount info from linked Pricing Rule
    discount = _get_discount_info(doc.pricing_rule)

    return {
        "valid": True,
        "message": "Coupon code is valid.",
        "coupon": coupon_data,
        "discount": discount,
    }


def _get_discount_info(pricing_rule_name: str) -> dict | None:
    """Return discount details from the linked Pricing Rule."""
    if not pricing_rule_name:
        return None

    rule = frappe.db.get_value(
        "Pricing Rule",
        pricing_rule_name,
        [
            "name",
            "price_or_product_discount",
            "rate_or_discount",
            "discount_percentage",
            "discount_amount",
            "rate",
            "apply_discount_on",
            "margin_type",
            "margin_rate_or_amount",
            "free_item",
            "free_qty",
            "free_item_rate",
            "free_item_uom",
            "currency",
        ],
        as_dict=True,
    )

    if not rule:
        return None

    return {
        "pricing_rule": rule.name,
        "price_or_product_discount": rule.price_or_product_discount,
        "rate_or_discount": rule.rate_or_discount,
        "discount_percentage": rule.discount_percentage,
        "discount_amount": rule.discount_amount,
        "rate": rule.rate,
        "apply_discount_on": rule.apply_discount_on,
        "margin_type": rule.margin_type,
        "margin_rate_or_amount": rule.margin_rate_or_amount,
        "free_item": rule.free_item,
        "free_qty": rule.free_qty,
        "free_item_rate": rule.free_item_rate,
        "free_item_uom": rule.free_item_uom,
        "currency": rule.currency,
    }
