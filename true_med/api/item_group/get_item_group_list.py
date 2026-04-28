import frappe
from frappe import _
from frappe.utils import cint

from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import paginate

ITEM_GROUP_FIELDS = [
    "name",
    "item_group_name",
    "parent_item_group",
    "is_group",
    "image",
    "description",
    "show_in_website",
    "route",
    "weightage",
    "lft",
    "rgt",
]

ALLOWED_SORT_FIELDS = {
    "item_group_name",
    "weightage",
    "lft",
    "modified",
    "creation",
}

_ITEM_GROUP_RESERVED = BASE_LIST_API_RESERVED_KEYS | frozenset(
    {"parent_item_group", "is_group", "show_in_website"}
)


@frappe.whitelist(allow_guest=True)
def get_item_group_list(
    page: int = 1,
    page_length: int = 20,
    parent_item_group: str = None,
    is_group: int = None,
    show_in_website: int = None,
    search: str = None,
    field_filters: str = None,
    sort_by: str = "lft",
    sort_order: str = "asc",
) -> dict:
    """
    Public API — paginated Item Group list.

    Item Group is a tree structure. By default all groups are returned.
    Use `parent_item_group` to fetch direct children of a specific node.

    Query Parameters:
        page               (int)      Page number, 1-based. Default: 1
        page_length        (int)      Records per page. Default: 20, max: 100
        parent_item_group  (str)      Return only direct children of this group
        is_group           (0|1)      Filter leaf (0) or branch (1) nodes
        show_in_website    (0|1)      Filter groups shown on the website
        search             (str)      Partial match on item_group_name
        field_filters      (str)      JSON AND filters; overrides same key from query string
        Other query keys in ITEM_GROUP_FIELDS apply as exact AND filters
        (e.g. ?route=shop/vitamins).
        sort_by            (str)      item_group_name | weightage | lft | modified | creation
        sort_order         (asc|desc) Default: asc

    Response:
        {
            "data": [
                {
                    "name": "Products",
                    "parent_item_group": "All Item Groups",
                    "is_group": 0,
                    "children_count": 3,
                    ...
                }
            ],
            "pagination": { ... }
        }

    Endpoint:
        GET /api/method/true_med.api.item_group.get_item_group_list.get_item_group_list
    """
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "lft"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    filters = _build_filters(
        parent_item_group=parent_item_group,
        is_group=is_group,
        show_in_website=show_in_website,
    )
    query_ff = get_query_field_filters(
        allowed_fields=frozenset(ITEM_GROUP_FIELDS),
        reserved_keys=_ITEM_GROUP_RESERVED,
    )
    ff_json = normalize_field_filters_json(field_filters)
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype="Item Group",
        allowed_fields=frozenset(ITEM_GROUP_FIELDS),
    )
    merge_doctype_field_filters(
        filters,
        ff_json,
        doctype="Item Group",
        allowed_fields=frozenset(ITEM_GROUP_FIELDS),
    )
    or_filters = _build_search_filters(search)
    order_by = f"`tabItem Group`.`{sort_by}` {sort_order}"

    data, pagination = paginate(
        doctype="Item Group",
        fields=ITEM_GROUP_FIELDS,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        page=cint(page),
        page_length=cint(page_length),
        ignore_permissions=True,
    )

    _attach_children_count(data)
    _attach_item_count(data)

    return {"data": data, "pagination": pagination}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _build_filters(
    parent_item_group=None,
    is_group=None,
    show_in_website=None,
) -> dict:
    filters = {}

    if parent_item_group is not None:
        filters["parent_item_group"] = parent_item_group

    if is_group is not None:
        filters["is_group"] = cint(is_group)

    if show_in_website is not None:
        filters["show_in_website"] = cint(show_in_website)

    return filters


def _build_search_filters(search: str | None) -> list:
    if not search:
        return []
    keyword = f"%{search}%"
    return [["item_group_name", "like", keyword]]


def _attach_children_count(groups: list) -> None:
    """
    Attach the number of direct children for each group in a single query.
    Only groups with is_group=1 can have children.
    """
    if not groups:
        return

    group_names = [g["name"] for g in groups if g.get("is_group")]
    if not group_names:
        for g in groups:
            g["children_count"] = 0
        return

    rows = frappe.db.sql(
        """
        SELECT parent_item_group, COUNT(*) AS cnt
        FROM   `tabItem Group`
        WHERE  parent_item_group IN ({placeholders})
        GROUP  BY parent_item_group
        """.format(placeholders=", ".join(["%s"] * len(group_names))),
        group_names,
        as_dict=True,
    )

    counts = {r["parent_item_group"]: r["cnt"] for r in rows}
    for g in groups:
        g["children_count"] = counts.get(g["name"], 0)

def _attach_item_count(groups: list) -> None:
    """
    Attach the total number of items linked directly to each item group in a single query.
    """
    if not groups:
        return

    # We need the count for all groups returned in the current page
    group_names = [g["name"] for g in groups]
    
    if not group_names:
        return

    # Single grouped query against tabItem
    rows = frappe.db.sql(
        """
        SELECT item_group, COUNT(*) AS cnt
        FROM   `tabItem`
        WHERE  item_group IN ({placeholders})
        GROUP  BY item_group
        """.format(placeholders=", ".join(["%s"] * len(group_names))),
        group_names,
        as_dict=True,
    )

    # Map the results to a dictionary for O(1) lookups
    counts = {r["item_group"]: r["cnt"] for r in rows}
    
    # Assign the count back to the original paginated data
    for g in groups:
        g["item_count"] = counts.get(g["name"], 0)        
