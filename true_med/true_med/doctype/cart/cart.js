// Copyright (c) 2026, Excel Technologies Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cart", {
	refresh(frm) {
		frm.trigger("render_totals");

		if (!frm.is_new()) {
			frm.add_custom_button(__("Clear Cart"), function () {
				frappe.confirm(
					__("Remove all items from {0}'s cart?", [frm.doc.user]),
					function () {
						frm.clear_table("items");
						frm.set_value("total_qty", 0);
						frm.set_value("total_amount", 0);
						frm.save();
					}
				);
			});
		}
	},

	render_totals(frm) {
		// Recalculate summary row whenever the form renders
		let total_qty = 0;
		let total_amount = 0;
		(frm.doc.items || []).forEach((row) => {
			total_qty += flt(row.qty);
			total_amount += flt(row.amount);
		});
		frm.set_value("total_qty", total_qty);
		frm.set_value("total_amount", total_amount);
	},
});

frappe.ui.form.on("Cart Item", {
	qty(frm, cdt, cdn) {
		calculate_row_amount(frm, cdt, cdn);
	},

	rate(frm, cdt, cdn) {
		calculate_row_amount(frm, cdt, cdn);
	},

	items_remove(frm) {
		frm.trigger("render_totals");
	},
});

function calculate_row_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
	frm.trigger("render_totals");
}
