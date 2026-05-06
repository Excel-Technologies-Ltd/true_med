import frappe
from frappe.utils import cint

from true_med.utils.list_query_filters import (
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import get_list_request_value, paginate

STORE_LIST_FIELDS = [
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

ALLOWED_SORT_FIELDS = {
    'company_name',
    'city',
    'state',
    'zip',
    'modified',
    'creation',
    'name',
}

@frappe.whitelist(allow_guest=True)
def get_store_list(
    page: int = 1,
    page_length: int = 10,
    search: str = None,
    field_filters: str = None,
    sort_by: str = 'company_name',
    sort_order: str = 'asc',
) -> dict:
    """
    Public API — paginated Store list.

    Query Parameters:
        page          (int)      Page number, 1-based. Default: 1
        page_length   (int)      Records per page. Default: 10, max: 100
        search        (str)      Partial match on company_name, city, state, zip
        field_filters (str)      JSON AND filters; overrides query-string keys
        Other keys in STORE_LIST_FIELDS apply as exact AND filters (?name=...).
        sort_by       (str)      company_name | city | state | zip | name |
                                 modified | creation
        sort_order    (asc|desc) Default: asc

    Endpoint:
        GET /api/method/true_med.api.store.get_store_list.get_store_list
    """
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else 'company_name'
    sort_order = 'asc' if str(sort_order).lower() == 'asc' else 'desc'

    raw_page = get_list_request_value('page')
    raw_pl = get_list_request_value('page_length')
    page = max(1, cint(raw_page if raw_page not in (None, '') else page))
    page_length = cint(raw_pl if raw_pl not in (None, '') else page_length)

    filters = {}
    query_ff = get_query_field_filters(
        allowed_fields=frozenset(STORE_LIST_FIELDS),
        reserved_keys=None,
    )
    ff_json = normalize_field_filters_json(field_filters)
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype='Store',
        allowed_fields=frozenset(STORE_LIST_FIELDS),
    )
    merge_doctype_field_filters(
        filters,
        ff_json,
        doctype='Store',
        allowed_fields=frozenset(STORE_LIST_FIELDS),
    )

    or_filters = _build_search_filters(search)
    order_by = f'`tabStore`.`{sort_by}` {sort_order}'

    data, pagination = paginate(
        doctype='Store',
        fields=STORE_LIST_FIELDS,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        page=page,
        page_length=page_length,
        ignore_permissions=True,
    )

    return {'data': data, 'pagination': pagination}


def _build_search_filters(search: str | None) -> list:
    if not search or not str(search).strip():
        return []
    keyword = f'%{str(search).strip()}%'
    return [
        ['company_name', 'like', keyword],
        ['city', 'like', keyword],
        ['state', 'like', keyword],
        ['zip', 'like', keyword],
    ]
