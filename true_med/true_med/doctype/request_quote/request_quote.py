# Copyright (c) 2026, Excel Technologies Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class RequestQuote(Document):
    def after_insert(self):
        if self.status == "Approved":
            admin_email = frappe.db.get_value("User", "Administrator", "email") or "admin@example.com"
            frappe.sendmail(
                recipients=[admin_email],
                subject=f"New Request Quote Submission: {self.name}",
                message=f"A new Request Quote submission has been received and approved.<br><br>Name: {self.first_name} {self.last_name}<br>Email: {self.email}<br>Product: {self.product_name}"
            )
