import frappe
from frappe.utils import cint

from true_med.utils.list_query_filters import (
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import paginate

PRODUCT_TYPE_FIELDS = [
    "name",
    "type_name",
    "modified",
    "creation",
]

ALLOWED_SORT_FIELDS = {"type_name", "modified", "creation", "name"}


@frappe.whitelist(allow_guest=True)
def get_product_type_list(
    page: int = 1,
    page_length: int = 50,
    search: str = None,
    field_filters: str = None,
    sort_by: str = "type_name",
    sort_order: str = "asc",
) -> dict:
    """
    Public API — paginated Product Type list for filters and storefront UI.

    Query Parameters:
        page         (int)      Page number, 1-based. Default: 1
        page_length  (int)      Records per page. Default: 50, max: 100
        search        (str)      Partial match on type_name
        field_filters (str)      JSON AND filters; overrides query-string keys
        Other keys in PRODUCT_TYPE_FIELDS apply as exact AND filters (?name=...).
        sort_by      (str)      type_name | name | modified | creation
        sort_order   (asc|desc) Default: asc

    Endpoint:
        GET /api/method/true_med.api.product_type.product_type_list.get_product_type_list
    """
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "type_name"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    filters = {}
    query_ff = get_query_field_filters(
        allowed_fields=frozenset(PRODUCT_TYPE_FIELDS),
        reserved_keys=None,
    )
    ff_json = normalize_field_filters_json(field_filters)
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype="Product Type",
        allowed_fields=frozenset(PRODUCT_TYPE_FIELDS),
    )
    merge_doctype_field_filters(
        filters,
        ff_json,
        doctype="Product Type",
        allowed_fields=frozenset(PRODUCT_TYPE_FIELDS),
    )

    or_filters = _build_search_filters(search)
    order_by = f"`tabProduct Type`.`{sort_by}` {sort_order}"

    data, pagination = paginate(
        doctype="Product Type",
        fields=PRODUCT_TYPE_FIELDS,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        page=cint(page),
        page_length=cint(page_length),
        ignore_permissions=True,
    )

    return {"data": data, "pagination": pagination}


def _build_search_filters(search: str | None) -> list:
    if not search or not str(search).strip():
        return []
    keyword = f"%{str(search).strip()}%"
    return [["type_name", "like", keyword]]
