import frappe
from frappe.utils import cint

from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import paginate

BLOG_CATEGORY_FIELDS = [
    "name",
    "title",
    "route",
    "published",
    "creation",
    "modified"
]

ALLOWED_CATEGORY_SORT_FIELDS = {
    "title",
    "published",
    "creation",
    "modified",
}

_BLOG_CATEGORY_RESERVED = BASE_LIST_API_RESERVED_KEYS | frozenset({"published"})


@frappe.whitelist(allow_guest=True)
def get_blog_category_list(
    page: int = 1,
    page_length: int = 20,
    published: int = None,
    search: str = None,
    field_filters: str = None,
    sort_by: str = "title",
    sort_order: str = "asc",
) -> dict:
    """
    Public API — paginated Blog Category list with post counts.

    Query Parameters:
        page          (int)      Page number, 1-based. Default: 1
        page_length   (int)      Records per page. Default: 20, max: 100
        published     (0|1)      Filter unpublished (0) or published (1) categories
        search        (str)      Partial match on category title
        field_filters (str)      JSON AND filters; overrides same key from query string
        Other keys in BLOG_CATEGORY_FIELDS apply as exact AND filters (?route=...).
        sort_by       (str)      title | published | creation | modified
        sort_order    (asc|desc) Default: asc

    Response:
        {
            "data": [
                {
                    "name": "Health Tips",
                    "title": "Health Tips",
                    "route": "health-tips",
                    "published": 1,
                    "post_count": 12,
                    ...
                }
            ],
            "pagination": { ... }
        }
    """
    sort_by = sort_by if sort_by in ALLOWED_CATEGORY_SORT_FIELDS else "title"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    filters = _build_category_filters(published=published)
    query_ff = get_query_field_filters(
        allowed_fields=frozenset(BLOG_CATEGORY_FIELDS),
        reserved_keys=_BLOG_CATEGORY_RESERVED,
    )
    ff_json = normalize_field_filters_json(field_filters)
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype="Blog Category",
        allowed_fields=frozenset(BLOG_CATEGORY_FIELDS),
    )
    merge_doctype_field_filters(
        filters,
        ff_json,
        doctype="Blog Category",
        allowed_fields=frozenset(BLOG_CATEGORY_FIELDS),
    )
    or_filters = _build_category_search_filters(search)
    order_by = f"`tabBlog Category`.`{sort_by}` {sort_order}"

    data, pagination = paginate(
        doctype="Blog Category",
        fields=BLOG_CATEGORY_FIELDS,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        page=cint(page),
        page_length=cint(page_length),
        ignore_permissions=True,
    )

    _attach_post_count(data)

    return {"data": data, "pagination": pagination}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _build_category_filters(published=None) -> dict:
    filters = {}

    if published is not None:
        filters["published"] = cint(published)

    return filters


def _build_category_search_filters(search: str | None) -> list:
    if not search:
        return []
    keyword = f"%{search}%"
    return [["title", "like", keyword]]


def _attach_post_count(categories: list) -> None:
    """
    Attach the total number of blog posts linked to each blog category in a single query.
    """
    if not categories:
        return

    # Gather category names for the current page
    category_names = [c["name"] for c in categories]
    
    if not category_names:
        return

    # Single grouped query against tabBlog Post
    # We also ensure we only count published posts (optional, remove `AND published = 1` if you want all posts)
    rows = frappe.db.sql(
        """
        SELECT blog_category, COUNT(*) AS cnt
        FROM   `tabBlog Post`
        WHERE  blog_category IN ({placeholders})
          AND  published = 1
        GROUP  BY blog_category
        """.format(placeholders=", ".join(["%s"] * len(category_names))),
        category_names,
        as_dict=True,
    )

    # Map the results to a dictionary for O(1) lookups
    counts = {r["blog_category"]: r["cnt"] for r in rows}
    
    # Assign the count back to the original paginated data
    for c in categories:
        c["post_count"] = counts.get(c["name"], 0)