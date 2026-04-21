import frappe
from frappe.utils import cint

from true_med.utils import cache as item_cache
from true_med.utils.pagination import paginate

@frappe.whitelist(allow_guest=True)
def get_best_selling_list(
    page: int = 1,
    page_length: int = 20,
    sort_by: str = "total_qty",
    sort_order: str = "desc",
) -> dict:
    """
    Public API — paginated list of best-selling items.
    
    Items are ranked based on the total quantity sold across submitted Sales Invoices.
    
    Query Parameters:
        page         (int)           Page number, 1-based. Default: 1
        page_length  (int)           Records per page. Default: 20
        sort_by      (str)           Field to sort by. Default: total_qty
        sort_order   (asc|desc)      Sort direction. Default: desc
    """
    page = cint(page) or 1
    page_length = cint(page_length) or 20
    offset = (page - 1) * page_length
    
    # Ensure safe sort directions
    sort_order = "asc" if str(sort_order).lower() == "asc" else "desc"
    # Ensure safe sort fields to prevent SQL injection
    sort_by = "total_qty" if sort_by not in ["total_qty", "item_code"] else sort_by

    # 1. Fetch aggregated best-selling item codes using standard SQL
    # 'docstatus = 1' ensures we only count items from submitted invoices
    item_list = frappe.db.sql(
        f"""
        SELECT 
            item_code, 
            SUM(qty) AS total_qty
        FROM 
            `tabSales Invoice Item`
        WHERE 
            docstatus = 1
        GROUP BY 
            item_code
        ORDER BY 
            {sort_by} {sort_order}
        LIMIT %s OFFSET %s
        """,
        (page_length, offset),
        as_dict=True
    )

    # 2. Calculate pagination metadata safely (Total distinct items sold)
    count_query = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT item_code) AS total_count
        FROM `tabSales Invoice Item`
        WHERE docstatus = 1
        """,
        as_dict=True
    )
    total_records = count_query[0].total_count if count_query else 0

    pagination = {
        "page": page,
        "page_length": page_length,
        "total_records": total_records,
        "total_pages": (total_records + page_length - 1) // page_length if total_records > 0 else 0,
        "has_next_page": (page * page_length) < total_records
    }

    # 3. Fetch full Item details for the items on the current page
    item_codes = [row["item_code"] for row in item_list if row.get("item_code")]
    
    items_by_code = {}
    if item_codes:
        items = frappe.get_all(
            "Item",
            fields=["name", "item_name", "item_group", "image", "description", "standard_rate"],
            filters={"name": ["in", item_codes]}
        )
        for item in items:
            items_by_code[item["name"]] = item

    # 4. Merge details while preserving the best-selling sort order
    best_selling_items = []
    for row in item_list:
        code = row["item_code"]
        if code in items_by_code:
            item_data = items_by_code[code].copy()
            item_data["total_qty_sold"] = row["total_qty"]
            best_selling_items.append(item_data)

    return {"items": best_selling_items, "pagination": pagination}