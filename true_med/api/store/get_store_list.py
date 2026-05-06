import frappe
from frappe.utils import cint, flt
import math

from true_med.utils.list_query_filters import (
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import (
    get_list_request_value,
    get_pagination_meta,
    paginate,
)

STORE_LIST_FIELDS = [
    'name',
    'company_name',
    'street_address',
    'city',
    'state',
    'zip',
    'phone',
    'full_address',
    'longitude',
    'latitude',
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
    'latitude',
    'longitude',
    'distance_km',
}

@frappe.whitelist(allow_guest=True)
def get_store_list(
    page: int = 1,
    page_length: int = 10,
    search: str = None,
    field_filters: str = None,
    sort_by: str = 'company_name',
    sort_order: str = 'asc',
    latitude: float = None,
    longitude: float = None,
    radius: float = None,
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
        latitude      (float)    User latitude for proximity search
        longitude     (float)    User longitude for proximity search
        radius        (float)    Search radius in kilometers

    Endpoint:
        GET /api/method/true_med.api.store.get_store_list.get_store_list
    """
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else 'company_name'
    sort_order = 'asc' if str(sort_order).lower() == 'asc' else 'desc'

    raw_page = get_list_request_value('page')
    raw_pl = get_list_request_value('page_length')
    raw_lat = get_list_request_value('latitude')
    raw_lon = get_list_request_value('longitude')
    raw_radius = get_list_request_value('radius')
    page = max(1, cint(raw_page if raw_page not in (None, '') else page))
    page_length = cint(raw_pl if raw_pl not in (None, '') else page_length)
    latitude = _to_float(raw_lat if raw_lat not in (None, '') else latitude)
    longitude = _to_float(raw_lon if raw_lon not in (None, '') else longitude)
    radius = _to_float(raw_radius if raw_radius not in (None, '') else radius)

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

    use_location_filter = all(value is not None
                              for value in (latitude, longitude, radius))
    if sort_by == 'distance_km' and not use_location_filter:
        sort_by = 'company_name'
    if use_location_filter:
        return _get_store_list_with_location_filter(
            filters=filters,
            or_filters=or_filters,
            page=page,
            page_length=page_length,
            sort_by=sort_by,
            sort_order=sort_order,
            latitude=latitude,
            longitude=longitude,
            radius=radius,
        )

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


def _to_float(value):
    if value in (None, ''):
        return None
    try:
        return flt(value)
    except Exception:
        return None


def _get_store_list_with_location_filter(
    *,
    filters: dict,
    or_filters: list,
    page: int,
    page_length: int,
    sort_by: str,
    sort_order: str,
    latitude: float,
    longitude: float,
    radius: float,
) -> dict:
    records = frappe.get_list(
        'Store',
        fields=STORE_LIST_FIELDS,
        filters=filters,
        or_filters=or_filters or [],
        order_by='`tabStore`.`company_name` asc',
        ignore_permissions=True,
        limit_page_length=0,
    )

    nearby_records = []
    for row in records:
        store_lat = _to_float(row.get('latitude'))
        store_lon = _to_float(row.get('longitude'))
        if store_lat is None or store_lon is None:
            continue

        distance_km = _haversine_km(latitude, longitude, store_lat, store_lon)
        if distance_km <= radius:
            row['distance_km'] = round(distance_km, 3)
            nearby_records.append(row)

    if sort_by == 'distance_km':
        reverse = sort_order == 'desc'
        nearby_records.sort(key=lambda d: d.get('distance_km', 0), reverse=reverse)
    elif sort_by in ALLOWED_SORT_FIELDS:
        reverse = sort_order == 'desc'
        nearby_records.sort(key=lambda d: str(d.get(sort_by) or ''), reverse=reverse)

    total_count = len(nearby_records)
    page_length = max(1, min(cint(page_length), 100))
    start = (page - 1) * page_length
    end = start + page_length

    return {
        'data': nearby_records[start:end],
        'pagination': get_pagination_meta(total_count, page, page_length),
    }


def _haversine_km(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
) -> float:
    radius_km = 6371.0
    lat1 = math.radians(from_lat)
    lon1 = math.radians(from_lon)
    lat2 = math.radians(to_lat)
    lon2 = math.radians(to_lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c
