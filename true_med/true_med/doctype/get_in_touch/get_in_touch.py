# Copyright (c) 2026, Excel Technologies Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class GetinTouch(Document):
    def after_insert(self):
        if self.status == "Approved":
            admin_email = frappe.db.get_value("User", "Administrator", "email") or "admin@example.com"
            frappe.sendmail(
                recipients=[admin_email],
                subject=f"New Get in Touch Submission: {self.name}",
                message=f"A new Get in Touch submission has been received and approved.<br><br>Name: {self.full_name}<br>Email: {self.email}<br>Message: {self.message}"
            )
