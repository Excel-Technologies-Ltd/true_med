import json

import frappe
from frappe import _
from frappe.utils import flt, nowdate


@frappe.whitelist(allow_guest=True)
def create_invoice(
    customer_name: str,
    email: str,
    items: list | str,
    phone: str = None,
    billing_address: dict | str = None,
    shipping_address: dict | str = None,
    notes: str = None,
) -> dict:
    """
    Public API — create a Sales Invoice (order) for eCommerce.

    Works for both guest and authenticated users. For authenticated users the
    system links the invoice to their existing Customer record; for guests it
    creates (or reuses) a Customer matched by email address.

    Request body (JSON or form-data):
        customer_name    (str, required)  Full name of the buyer
        email            (str, required)  Email — used to identify / create Customer
        items            (list, required) [{"item_code": "X", "qty": 2}, ...]
                                          Optionally include "rate" to override price.
        phone            (str)            Contact phone number
        billing_address  (dict)           {address_line1, address_line2, city,
                                           state, pincode, country}
        shipping_address (dict)           Same shape; defaults to billing_address
        notes            (str)            Order notes / delivery instructions

    Response:
        {
            "data": {
                "name": "ACC-SINV-2026-00001",
                "customer": "John Doe",
                "status": "Unpaid",
                "posting_date": "2026-04-06",
                "grand_total": 110.00,
                "outstanding_amount": 110.00,
                "items": [...]
            }
        }

    Endpoint:
        POST /api/method/true_med.api.sales_invoice.create_invoice.create_invoice
    """
    # Frappe passes list/dict params as JSON strings when called over HTTP
    items = _parse_json(items, "items")
    billing_address = _parse_json(billing_address, "billing_address") if billing_address else None
    shipping_address = _parse_json(shipping_address, "shipping_address") if shipping_address else None

    _validate_inputs(customer_name, email, items)

    customer = _get_or_create_customer(customer_name, email, phone)

    company = _get_default_company()

    # Resolve addresses — billing required for address field on invoice,
    # shipping defaults to billing when not provided separately.
    billing_addr_name = None
    shipping_addr_name = None
    if billing_address:
        billing_addr_name = _upsert_address(customer, billing_address, "Billing")
        shipping_addr_name = billing_addr_name
    if shipping_address:
        shipping_addr_name = _upsert_address(customer, shipping_address, "Shipping")

    # set_missing_values() → _get_party_details() calls frappe.has_permission()
    # with throw=True, which is NOT bypassed by frappe.flags.ignore_permissions
    # (that flag only affects db_query list calls). The only reliable way to
    # satisfy ERPNext's internal permission checks for a Guest request is to
    # temporarily run as Administrator, then always restore the original user.
    _original_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        invoice = _build_invoice(
            customer=customer,
            company=company,
            items=items,
            billing_address=billing_addr_name,
            shipping_addr_name=shipping_addr_name,
            notes=notes,
        )
        invoice.insert(ignore_permissions=True)
    finally:
        frappe.set_user(_original_user)

    return {"data": _serialize_invoice(invoice)}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_inputs(customer_name: str, email: str, items: list):
    if not customer_name:
        frappe.throw(_("customer_name is required"), frappe.MandatoryError)

    if not email or "@" not in email:
        frappe.throw(_("A valid email address is required"), frappe.ValidationError)

    if not items or not isinstance(items, list):
        frappe.throw(_("items must be a non-empty list"), frappe.MandatoryError)

    for idx, row in enumerate(items, start=1):
        if not row.get("item_code"):
            frappe.throw(
                _("Row {0}: item_code is required").format(idx), frappe.MandatoryError
            )
        if flt(row.get("qty", 0)) <= 0:
            frappe.throw(
                _("Row {0}: qty must be greater than 0").format(idx),
                frappe.ValidationError,
            )
        if not frappe.db.exists("Item", {"name": row["item_code"], "disabled": 0}):
            frappe.throw(
                _("Item {0} does not exist or is disabled").format(row["item_code"]),
                frappe.ValidationError,
            )


# ---------------------------------------------------------------------------
# Customer resolution
# ---------------------------------------------------------------------------

def _get_or_create_customer(customer_name: str, email: str, phone: str = None) -> str:
    """
    Return a Customer name for the order.

    Priority:
      1. Authenticated non-admin user → find Customer linked to their account.
      2. Email match → find Customer via Contact → Dynamic Link lookup.
      3. No match → create a new Customer + Contact.
    """
    if frappe.session.user not in ("Guest", "Administrator"):
        linked = frappe.db.get_value(
            "Customer", {"email_id": frappe.session.user}, "name"
        )
        if linked:
            return linked

    existing = _find_customer_by_email(email)
    if existing:
        return existing

    return _create_customer(customer_name, email, phone)


def _find_customer_by_email(email: str) -> str | None:
    """
    Return the Customer linked to a Contact whose primary email matches,
    or None if not found.
    """
    result = frappe.db.sql(
        """
        SELECT dl.link_name
        FROM   `tabContact`      c
        JOIN   `tabDynamic Link` dl
               ON  dl.parent       = c.name
               AND dl.parenttype   = 'Contact'
               AND dl.link_doctype = 'Customer'
        WHERE  c.email_id = %s
        LIMIT  1
        """,
        email,
    )
    return result[0][0] if result else None


def _create_customer(customer_name: str, email: str, phone: str = None) -> str:
    """Create a Customer document and an associated Contact."""
    customer_group = (
        frappe.db.get_single_value("Selling Settings", "customer_group")
        or frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
        or "All Customer Groups"
    )
    territory = (
        frappe.db.get_single_value("Selling Settings", "territory")
        or frappe.db.get_value("Territory", {"is_group": 0}, "name")
        or "All Territories"
    )

    customer_doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_type": "Individual",
            "customer_group": customer_group,
            "territory": territory,
        }
    )
    customer_doc.insert(ignore_permissions=True)

    contact_data = {
        "doctype": "Contact",
        "first_name": customer_name,
        "email_id": email,
        # Child table rows must include "doctype" so Frappe converts them
        # from plain dicts to Document objects before _set_defaults runs.
        "email_ids": [
            {"doctype": "Contact Email", "email_id": email, "is_primary": 1}
        ],
        "links": [
            {
                "doctype": "Dynamic Link",
                "link_doctype": "Customer",
                "link_name": customer_doc.name,
            }
        ],
    }
    if phone:
        contact_data["phone"] = phone
        contact_data["phone_nos"] = [
            {"doctype": "Contact Phone", "phone": phone, "is_primary_phone": 1}
        ]

    contact = frappe.get_doc(contact_data)
    contact.insert(ignore_permissions=True)

    return customer_doc.name


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

def _upsert_address(customer: str, addr: dict, addr_type: str) -> str:
    """
    Return the name of an Address for this customer, creating one if a matching
    record (same address_line1 + city) does not already exist.
    """
    address_line1 = addr.get("address_line1", "")
    city = addr.get("city", "")

    existing = frappe.db.sql(
        """
        SELECT a.name
        FROM   `tabAddress`      a
        JOIN   `tabDynamic Link` dl
               ON  dl.parent       = a.name
               AND dl.parenttype   = 'Address'
               AND dl.link_doctype = 'Customer'
               AND dl.link_name    = %s
        WHERE  a.address_line1 = %s
               AND a.city = %s
        LIMIT  1
        """,
        (customer, address_line1, city),
    )
    if existing:
        return existing[0][0]

    address_doc = frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": f"{customer}-{addr_type}",
            "address_type": addr_type,
            "address_line1": address_line1,
            "address_line2": addr.get("address_line2", ""),
            "city": city,
            "state": addr.get("state", ""),
            "pincode": addr.get("pincode", ""),
            "country": addr.get("country", "Bangladesh"),
            "is_primary_address": 1 if addr_type == "Billing" else 0,
            "is_shipping_address": 1 if addr_type == "Shipping" else 0,
            "links": [
                {
                    "doctype": "Dynamic Link",
                    "link_doctype": "Customer",
                    "link_name": customer,
                }
            ],
        }
    )
    address_doc.insert(ignore_permissions=True)
    return address_doc.name


# ---------------------------------------------------------------------------
# Invoice builder
# ---------------------------------------------------------------------------

def _get_default_company() -> str:
    company = frappe.defaults.get_global_default("company")
    if not company:
        company = frappe.db.get_value("Company", {}, "name")
    if not company:
        frappe.throw(
            _("No default company configured. Please set up a default company."),
            frappe.ValidationError,
        )
    return company


def _build_invoice(
    customer: str,
    company: str,
    items: list,
    billing_address: str = None,
    shipping_addr_name: str = None,
    notes: str = None,
) -> "frappe.model.document.Document":
    """
    Construct a Sales Invoice Document, then call set_missing_values() and
    calculate_taxes_and_totals() so ERPNext fills in accounts, currency, taxes,
    and computes all amounts correctly before the document is inserted.
    """
    selling_price_list = (
        frappe.db.get_single_value("Selling Settings", "selling_price_list")
        or frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
        or "Standard Selling"
    )

    invoice_items = []
    for row in items:
        item_meta = frappe.db.get_value(
            "Item",
            row["item_code"],
            ["item_name", "description", "stock_uom"],
            as_dict=True,
        )
        item_row = {
            "item_code": row["item_code"],
            "item_name": item_meta.item_name,
            "description": item_meta.description or item_meta.item_name,
            "qty": flt(row["qty"]),
            "uom": row.get("uom") or item_meta.stock_uom,
        }
        # Allow caller to override the rate; otherwise ERPNext fetches from price list
        if row.get("rate"):
            item_row["rate"] = flt(row["rate"])

        invoice_items.append(item_row)

    doc_data = {
        "doctype": "Sales Invoice",
        "naming_series": "ACC-SINV-.YYYY.-",
        "customer": customer,
        "company": company,
        "posting_date": nowdate(),
        "due_date": nowdate(),
        "selling_price_list": selling_price_list,
        "update_stock": 0,
        "items": invoice_items,
    }
    if billing_address:
        doc_data["customer_address"] = billing_address
    if shipping_addr_name:
        doc_data["shipping_address_name"] = shipping_addr_name
    if notes:
        doc_data["terms"] = notes

    invoice = frappe.get_doc(doc_data)

    # ERPNext fills in income accounts, cost centre, currency, exchange rate,
    # applies pricing rules, and sums up all totals + taxes
    invoice.set_missing_values()
    invoice.calculate_taxes_and_totals()

    return invoice


# ---------------------------------------------------------------------------
# Response serializer
# ---------------------------------------------------------------------------

def _serialize_invoice(doc) -> dict:
    return {
        "name": doc.name,
        "customer": doc.customer,
        "customer_name": doc.customer_name,
        "status": doc.status,
        "posting_date": str(doc.posting_date),
        "due_date": str(doc.due_date),
        "currency": doc.currency,
        "selling_price_list": doc.selling_price_list,
        "total": flt(doc.total),
        "net_total": flt(doc.net_total),
        "total_taxes_and_charges": flt(doc.total_taxes_and_charges),
        "grand_total": flt(doc.grand_total),
        "rounded_total": flt(doc.rounded_total),
        "outstanding_amount": flt(doc.outstanding_amount),
        "items": [
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "qty": flt(row.qty),
                "uom": row.uom,
                "rate": flt(row.rate),
                "amount": flt(row.amount),
            }
            for row in doc.items
        ],
    }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _parse_json(value, field_name: str):
    """Deserialise a value that may have arrived as a JSON string over HTTP."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            frappe.throw(
                _("Invalid JSON for field '{0}'").format(field_name),
                frappe.ValidationError,
            )
    return value
