import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def get_item_group(item_group: str) -> dict:
    """
    Public API — single Item Group detail with its direct children and
    ancestor breadcrumb trail.

    Path Parameter:
        item_group  (str, required)  The name (or item_group_name) of the group.

    Response:
        {
            "data": {
                "name": "Products",
                "item_group_name": "Products",
                "parent_item_group": "All Item Groups",
                "is_group": 1,
                "image": null,
                "description": "...",
                "show_in_website": 1,
                "route": "products",
                "weightage": 0,
                "lft": 2,
                "rgt": 11,
                "breadcrumbs": [
                    {"name": "All Item Groups", "item_group_name": "All Item Groups"},
                    {"name": "Products",        "item_group_name": "Products"}
                ],
                "children": [
                    {
                        "name": "Vitamins",
                        "item_group_name": "Vitamins",
                        "is_group": 0,
                        "image": null,
                        "children_count": 0
                    },
                    ...
                ]
            }
        }

    Error responses:
        400  item_group not provided
        404  item_group not found

    Endpoint:
        GET /api/method/true_med.api.item_group.get_item_group.get_item_group?item_group=Products
    """
    if not item_group:
        frappe.throw(_("item_group is required"), frappe.MandatoryError)

    if not frappe.db.exists("Item Group", item_group):
        frappe.throw(
            _("Item Group {0} not found").format(item_group),
            frappe.DoesNotExistError,
        )

    data = _get_item_group_data(item_group)
    data["breadcrumbs"] = _get_breadcrumbs(item_group)
    data["children"] = _get_children(item_group)

    return {"data": data}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _get_item_group_data(item_group: str) -> dict:
    fields = [
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
    doc = frappe.db.get_value(
        "Item Group", item_group, fields, as_dict=True
    )
    return dict(doc)


def _get_breadcrumbs(item_group: str) -> list:
    """
    Return the ancestor chain from the root down to (and including) this group,
    using the nested set lft/rgt values — a single query, no recursion.
    """
    # Find lft/rgt of the current node
    current = frappe.db.get_value(
        "Item Group", item_group, ["lft", "rgt"], as_dict=True
    )
    if not current:
        return []

    ancestors = frappe.db.sql(
        """
        SELECT name, item_group_name
        FROM   `tabItem Group`
        WHERE  lft <= %s AND rgt >= %s
        ORDER  BY lft ASC
        """,
        (current.lft, current.rgt),
        as_dict=True,
    )
    return [{"name": a.name, "item_group_name": a.item_group_name} for a in ancestors]


def _get_children(item_group: str) -> list:
    """Return direct children of this group with their own children count."""
    children = frappe.get_all(
        "Item Group",
        filters={"parent_item_group": item_group},
        fields=[
            "name",
            "item_group_name",
            "is_group",
            "image",
            "show_in_website",
            "route",
            "weightage",
            "lft",
        ],
        order_by="lft asc",
        ignore_permissions=True,
    )

    if not children:
        return []

    # Count grandchildren in a single query
    child_names = [c["name"] for c in children if c.get("is_group")]
    counts = {}
    if child_names:
        rows = frappe.db.sql(
            """
            SELECT parent_item_group, COUNT(*) AS cnt
            FROM   `tabItem Group`
            WHERE  parent_item_group IN ({placeholders})
            GROUP  BY parent_item_group
            """.format(placeholders=", ".join(["%s"] * len(child_names))),
            child_names,
            as_dict=True,
        )
        counts = {r["parent_item_group"]: r["cnt"] for r in rows}

    for child in children:
        child["children_count"] = counts.get(child["name"], 0)

    return children
