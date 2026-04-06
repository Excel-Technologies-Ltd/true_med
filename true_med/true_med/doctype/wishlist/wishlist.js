// Copyright (c) 2026, Excel Technologies Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Wishlist", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Clear Wishlist"), function () {
				frappe.confirm(
					__("Remove all items from {0}'s wishlist?", [frm.doc.user]),
					function () {
						frm.clear_table("items");
						frm.save();
					}
				);
			});
		}
	},
});
