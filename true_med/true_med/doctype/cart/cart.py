import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Cart(Document):
    def validate(self):
        self._validate_qty()
        self._calculate_amounts()

    def _validate_qty(self):
        for row in self.items:
            if flt(row.qty) <= 0:
                frappe.throw(
                    _("Row {0}: Qty must be greater than 0 for item {1}").format(
                        row.idx, row.item_code
                    )
                )

    def _calculate_amounts(self):
        """Recompute row amounts and cart totals."""
        total_qty = 0.0
        total_amount = 0.0

        for row in self.items:
            row.amount = flt(row.qty) * flt(row.rate)
            total_qty += flt(row.qty)
            total_amount += row.amount

        self.total_qty = total_qty
        self.total_amount = total_amount
