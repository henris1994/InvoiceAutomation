from utils.utilfunctions import norm
#give RPA bot the view of line items as sampro displays the PO line items
def sortlinenumbers(podata, line_items):
    # build poview (only eligible lines)
    poview = [
        {
            'line_source': po.get('line_source', '').lower(),
            'line_number': po.get('line_no'),
            'item_id': po.get('vendor_part', '').lower(),
            'quantity': '0',
            'unit_cost': 0,
            'amount': 0
        }
        for po in podata
        if (po['qty_received_imhstry'] - po['qty_vouchered']) > 0
    ]

    # index line_items by (source, line_no)
    items_by_line = {
        (item.get('line_source', '').lower(), norm(item.get('line_number'))): item
        for item in line_items
        if item.get('line_number') and item.get('line_source')
    }

    # merge invoice data into poview
    poview = [
        items_by_line.get((row['line_source'], norm(row['line_number'])), row)
        for row in poview
    ]

    # renumber separately for each source
    grouped, merged = {}, []
    for row in poview:
        grouped.setdefault(row['line_source'], []).append(row)

    for src in ("list", "listgn"):   # tab order
        for new_num, item in enumerate(grouped.get(src, []), start=1):
            item['line_number'] = new_num
            merged.append(item)

    return merged