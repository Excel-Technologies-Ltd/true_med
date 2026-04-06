import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_invoice_items(doctype, txt, searchfield, start, page_len, filters):
    """
    Server-side search query used by item_review.js to restrict the item_code
    field to only items present in the selected Sales Invoice.
    """
    sales_invoice = filters.get("sales_invoice") if filters else None
    if not sales_invoice:
        return []

    return frappe.db.sql(
        """
        SELECT sii.item_code, sii.item_name
        FROM `tabSales Invoice Item` sii
        WHERE sii.parent = %(invoice)s
          AND (
              sii.item_code LIKE %(txt)s
              OR sii.item_name LIKE %(txt)s
          )
        ORDER BY sii.item_code
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "invoice": sales_invoice,
            "txt": f"%{txt}%",
            "start": start,
            "page_len": page_len,
        },
    )


class ItemReview(Document):
    def validate(self):
        self._validate_invoice_belongs_to_customer()
        self._validate_item_in_invoice()
        self._prevent_duplicate_review()

    # ------------------------------------------------------------------
    # Validations
    # ------------------------------------------------------------------

    def _validate_invoice_belongs_to_customer(self):
        """
        Ensure the Sales Invoice was billed to the reviewing customer.
        Prevents a customer from reviewing using someone else's invoice.
        """
        invoice_customer = frappe.db.get_value(
            "Sales Invoice", self.sales_invoice, "customer"
        )
        if not invoice_customer:
            frappe.throw(
                _("Sales Invoice {0} does not exist.").format(self.sales_invoice)
            )
        if invoice_customer != self.customer:
            frappe.throw(
                _(
                    "Sales Invoice {0} does not belong to customer {1}."
                ).format(self.sales_invoice, self.customer)
            )

    def _validate_item_in_invoice(self):
        """
        The reviewed item must appear in the linked Sales Invoice's item lines.
        This is the core business rule: you can only review items you actually bought.
        """
        invoice_items = frappe.get_all(
            "Sales Invoice Item",
            filters={"parent": self.sales_invoice},
            pluck="item_code",
        )

        if self.item_code not in invoice_items:
            frappe.throw(
                _(
                    "Item {0} is not part of Sales Invoice {1}. "
                    "You can only review items you have purchased."
                ).format(self.item_code, self.sales_invoice)
            )

    def _prevent_duplicate_review(self):
        """
        One review per customer per item per Sales Invoice.
        Allows re-saving the same document (excludes self.name from check).
        """
        filters = {
            "customer": self.customer,
            "sales_invoice": self.sales_invoice,
            "item_code": self.item_code,
            "name": ["!=", self.name],
        }
        if frappe.db.exists("Item Review", filters):
            frappe.throw(
                _(
                    "You have already reviewed item {0} for Sales Invoice {1}."
                ).format(self.item_code, self.sales_invoice)
            )
