// Copyright (c) 2026, Excel Technologies Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('Get in Touch', {
	phone_number: function(frm) {
		frm.doc.full_name = frm.doc.first_name + ' ' + frm.doc.last_name;
		frm.refresh_field('full_name');
	}
});
