import frappe
from frappe.utils import get_filter


def get_hidden_item_groups() -> list[str]:
    """
    Item Groups with "Show in Website" unticked. These groups and every item
    in them are hidden from the public website APIs.
    """
    return frappe.get_all(
        "Item Group",
        filters={"show_in_website": 0},
        pluck="name",
        ignore_permissions=True,
    )


def is_item_group_visible(item_group: str | None) -> bool:
    return bool(item_group) and bool(
        frappe.db.get_value("Item Group", item_group, "show_in_website")
    )


def visible_item_group_sql(column: str = "i.item_group") -> str:
    """SQL condition: ``column`` is an Item Group shown on the website."""
    return (
        f"{column} IN (SELECT `name` FROM `tabItem Group` WHERE `show_in_website` = 1)"
    )


def exclude_hidden_item_groups(filters: dict, doctype: str = "Item") -> dict | list:
    """
    Return ``filters`` with items of hidden Item Groups excluded.

    The dict form cannot hold a second condition on ``item_group`` (the caller
    may already filter by it), so when anything is hidden the filters are
    converted to Frappe's list form and the exclusion is appended.
    """
    hidden = get_hidden_item_groups()
    if not hidden:
        return filters

    as_list = []
    for fieldname, value in (filters or {}).items():
        f = get_filter(doctype, {fieldname: value})
        as_list.append([doctype, f.fieldname, f.operator, f.value])
    as_list.append([doctype, "item_group", "not in", hidden])
    return as_list
