import frappe
from frappe.utils import add_days, nowdate

def delete_old_spam_submissions():
    """
    Deletes records marked as 'Spam' that are older than 30 days
    for Get in Touch, Request Quote, and Lead DocTypes.
    """
    date_threshold = add_days(nowdate(), -30)
    
    doctypes_to_clean = ["Get in Touch", "Request Quote", "Lead"]
    
    for doctype in doctypes_to_clean:
        try:
            records = frappe.get_all(
                doctype,
                filters={
                    "status": "Spam",
                    "creation": ("<", date_threshold)
                },
                pluck="name"
            )
            
            for record_name in records:
                frappe.delete_doc(doctype, record_name, ignore_permissions=True)
                
            if records:
                frappe.logger().info(f"Deleted {len(records)} old spam records from {doctype}")
        except Exception as e:
            frappe.logger().error(f"Failed to delete old spam submissions for {doctype}: {str(e)}")
