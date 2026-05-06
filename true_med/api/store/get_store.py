import frappe
from frappe import _

from true_med.utils.pagination import get_list_request_value

STORE_FIELDS = [
    'name',
    'company_name',
    'street_address',
    'city',
    'state',
    'zip',
    'phone',
    'full_address',
    'modified',
    'creation',
]


@frappe.whitelist(allow_guest=True)
def get_store(name: str = None) -> dict:
    """
    Public API — full Store document by name.

    Query Parameters:
        name  (str, required)  The Store document name (primary key).

    Note:
        JSON POST bodies replace query-string params in Frappe's form_dict.
        ``name`` is resolved from form_dict, then from the raw URL query string.

    Error responses:
        400  name not provided
        404  store not found

    Endpoint:
        GET /api/method/true_med.api.store.get_store.get_store?name=STORE-001
    """
    store_name = get_list_request_value('name') or name
    store_name = str(store_name).strip() if store_name else ''

    if not store_name:
        frappe.throw(_('name is required'), frappe.MandatoryError)

    if not frappe.db.exists('Store', store_name):
        frappe.throw(_('Store {0} not found').format(store_name), frappe.DoesNotExistError)

    data = frappe.db.get_value(
        'Store',
        store_name,
        STORE_FIELDS,
        as_dict=True,
    )

    return {'data': data}
