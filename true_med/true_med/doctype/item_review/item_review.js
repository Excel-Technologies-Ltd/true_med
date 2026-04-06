// Copyright (c) 2026, Excel Technologies Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Review", {
	refresh(frm) {
		// Only System Manager can change status
		const can_manage = frappe.user.has_role("System Manager");
		frm.set_df_property("status", "read_only", can_manage ? 0 : 1);

		if (can_manage && !frm.is_new()) {
			if (frm.doc.status === "Pending") {
				frm.add_custom_button(__("Approve"), function () {
					frm.set_value("status", "Approved");
					frm.save();
				}, __("Actions")).addClass("btn-success");

				frm.add_custom_button(__("Reject"), function () {
					frm.set_value("status", "Rejected");
					frm.save();
				}, __("Actions")).addClass("btn-danger");
			}
		}
	},

	sales_invoice(frm) {
		// Reset item when the invoice changes — previous item may no longer be valid
		if (frm.doc.sales_invoice) {
			frm.set_value("item_code", "");
			frm.set_query("item_code", function () {
				return {
					query: "true_med.true_med.doctype.item_review.item_review.get_invoice_items",
					filters: { sales_invoice: frm.doc.sales_invoice },
				};
			});
		}
	},

	customer(frm) {
		// Re-filter invoices to those belonging to the selected customer
		if (frm.doc.customer) {
			frm.set_query("sales_invoice", function () {
				return {
					filters: {
						customer: frm.doc.customer,
						docstatus: 1,
					},
				};
			});
		}
	},
});
