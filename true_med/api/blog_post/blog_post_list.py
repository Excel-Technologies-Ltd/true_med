import frappe
from frappe.utils import cint

from true_med.utils import cache as blog_cache
from true_med.utils.list_query_filters import (
    BASE_LIST_API_RESERVED_KEYS,
    get_query_field_filters,
    merge_doctype_field_filters,
    normalize_field_filters_json,
)
from true_med.utils.pagination import paginate

# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------

BLOG_LIST_FIELDS = [
    "name",
    "title",
    "published_on",
    "published",
    "blog_category",
    "blogger",
    "route",
    "blog_intro",
    "meta_image",
    "meta_title",
    "meta_description",
    "read_time",
    "featured",
    "disable_comments",
    "disable_likes",
    "modified",
    "creation",
]

ALLOWED_SORT_FIELDS = {
    "title",
    "published_on",
    "modified",
    "creation",
    "read_time",
    "blog_category",
    "blogger",
}

_BLOG_POST_RESERVED = BASE_LIST_API_RESERVED_KEYS | frozenset(
    {"blog_category", "blogger", "featured", "published"}
)


@frappe.whitelist(allow_guest=True)
def get_blog_post_list(
    page: int = 1,
    page_length: int = 20,
    blog_category: str = None,
    blogger: str = None,
    featured: int = None,
    published: int = 1,
    search: str = None,
    field_filters: str = None,
    sort_by: str = "published_on",
    sort_order: str = "desc",
) -> dict:
    """
    Public API — paginated blog post list with filters.

    Only published posts are returned by default. Results are cached in Redis
    and automatically invalidated when Blog Posts change.

    Query Parameters:
        page          (int)      Page number, 1-based. Default: 1
        page_length   (int)      Records per page. Default: 20, max: 100
        blog_category (str)      Filter by blog category name
        blogger       (str)      Filter by blogger name
        featured      (0|1)      Filter featured posts only
        published     (0|1)      Filter published posts (default 1)
        search        (str)      Partial match on title or blog_intro
        field_filters (str)      JSON AND filters; overrides same key from query string
        Other query keys in BLOG_LIST_FIELDS apply as exact AND filters.
        sort_by       (str)      Field to sort by. Allowed: title, published_on,
                                 modified, creation, read_time, blog_category, blogger
        sort_order    (asc|desc) Sort direction. Default: desc

    Endpoint:
        GET /api/method/true_med.api.blog_post.blog_post_list.get_blog_post_list
    """
    sort_by = sort_by if sort_by in ALLOWED_SORT_FIELDS else "published_on"
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"

    ff_json = normalize_field_filters_json(field_filters)
    query_ff = get_query_field_filters(
        allowed_fields=frozenset(BLOG_LIST_FIELDS),
        reserved_keys=_BLOG_POST_RESERVED,
    )

    cache_key = blog_cache.blog_list_key(
        page=page,
        page_length=page_length,
        blog_category=blog_category,
        blogger=blogger,
        featured=featured,
        published=published,
        search=search,
        field_filters=ff_json,
        query_field_filters=query_ff,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    cached = blog_cache.get(cache_key)
    if cached:
        return cached

    filters = _build_filters(
        blog_category=blog_category,
        blogger=blogger,
        featured=featured,
        published=published,
    )
    merge_doctype_field_filters(
        filters,
        query_ff,
        doctype="Blog Post",
        allowed_fields=frozenset(BLOG_LIST_FIELDS),
    )
    merge_doctype_field_filters(
        filters,
        ff_json,
        doctype="Blog Post",
        allowed_fields=frozenset(BLOG_LIST_FIELDS),
    )
    or_filters = _build_search_filters(search)
    order_by = f"`tabBlog Post`.`{sort_by}` {sort_order}"

    data, pagination = paginate(
        doctype="Blog Post",
        fields=BLOG_LIST_FIELDS,
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        page=cint(page),
        page_length=cint(page_length),
        ignore_permissions=True,
    )

    _attach_blogger_info(data)

    result = {"data": data, "pagination": pagination}
    blog_cache.set(cache_key, result, ttl=blog_cache.BLOG_LIST_TTL)

    return result


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _build_filters(
    blog_category=None,
    blogger=None,
    featured=None,
    published=1,
) -> dict:
    filters = {}

    filters["published"] = cint(published) if published is not None else 1

    if blog_category:
        filters["blog_category"] = blog_category

    if blogger:
        filters["blogger"] = blogger

    if featured is not None:
        filters["featured"] = cint(featured)

    return filters


def _build_search_filters(search: str | None) -> list:
    """Return OR filters for a free-text search on title and intro."""
    if not search:
        return []

    keyword = f"%{search}%"
    return [
        ["title", "like", keyword],
        ["blog_intro", "like", keyword],
    ]


def _attach_blogger_info(posts: list) -> None:
    """
    Attach blogger detail (full_name, avatar, bio) to each post in-place
    using a single bulk query (no N+1).
    """
    if not posts:
        return

    blogger_names = list({p["blogger"] for p in posts if p.get("blogger")})
    if not blogger_names:
        for post in posts:
            post["blogger_info"] = {}
        return

    all_bloggers = frappe.get_all(
        "Blogger",
        filters={"name": ["in", blogger_names]},
        fields=["name", "full_name", "short_name", "avatar", "bio"],
        ignore_permissions=True,
    )
    blogger_map = {b["name"]: b for b in all_bloggers}

    for post in posts:
        post["blogger_info"] = blogger_map.get(post.get("blogger"), {})
