import frappe

def lead_after_insert(doc, method):
    # Only process leads from the website (Advertisement or our specific forms)
    # The API sets source = "Advertisement"
    if doc.source == "Advertisement" and getattr(doc, "status", None) == "Approved":
        admin_email = frappe.db.get_value("User", "Administrator", "email") or "admin@example.com"
        frappe.sendmail(
            recipients=[admin_email],
            subject=f"New Lead Submission: {doc.name}",
            message=f"A new Lead submission has been received and approved.<br><br>Name: {doc.first_name or ''} {doc.last_name or ''}<br>Email: {doc.email_id}"
        )
