// Copyright (c) 2026, Excel Technologies Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Wishlist Item", {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.item_code) {
			row.added_on = frappe.datetime.nowdate();
			frm.refresh_field("items");
		}
	},
});
