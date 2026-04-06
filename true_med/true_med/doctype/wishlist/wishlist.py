import frappe
from frappe import _
from frappe.model.document import Document


class Wishlist(Document):
    def validate(self):
        self._remove_duplicate_items()

    def _remove_duplicate_items(self):
        """Ensure each item appears only once in the wishlist."""
        seen = set()
        unique_items = []
        for row in self.items:
            if row.item_code not in seen:
                seen.add(row.item_code)
                unique_items.append(row)
        self.items = unique_items
