from decimal import Decimal
#transform response as UI expects it 
def transform_for_ui(response):
    output = []
    invoice_total = Decimal(response['invoice_total'])
    # 1️ Invoice header (first JSON object)
    header = {
        "type": "general_info",
        "po_number": str(response['po_number']),
        "invoice_number": str(response['invoice_number']),
        "invoice_date": str(response['invoice_date']),
        "invoice_total": f"{invoice_total:.2f}",
        "gl_entity_id": str(response['gl_entity_id']),
        "line_item_count": str(response['line_item_count']),
        "has_taxes": str(response['has_taxes']).lower(),
        "has_extra_charges": str(response['has_extra_charges']).lower(),
        "extra_charge_count": str(response['extra_charge_count']),
        "close_po": str(response['close_po']).lower(),
        "ai_match": response['ai_match'],
        "invoice_file_path": str(response['invoice_file_path'])
    }
    output.append(header)

    # 2️ Line items
    for item in response['line_items']:
        output.append({
            "type": item['line_source'],
            "line_number": str(item['line_number']),   
            "line_item_id": item['item_id'],
            "quantity": str(item['quantity']),
            "unit_cost": f"{item['unit_cost']:.3f}",
            "amount": f"{item['amount']:.3f}"
        })

    # 3️ Tax info
    if response.get('has_taxes') and response.get('tax_info'):
        tax = response['tax_info']
        output.append({
        "type": "tax_info",
        "authority_id": tax['authority_id'],
        "gl_account": tax['gl_account'],
        "tax_base": str(tax['tax_base']),
        "rate": str(tax['rate']),
        "tax_amount": str(tax['tax_amount'])
    })


    # 4️ Extra charges (put the extra charge after general items for RPA)
    line_count = len([i for i in response['line_items'] if i['line_source']=='listgn'])
    for idx, charge in enumerate(response['extra_charges'], start=1):
        output.append({
            "type": "extra_charges",
            "charge_number": str(line_count + idx),
            "quantity": str(charge['quantity']),
            "unit_cost": f"{charge['unit_cost']:.2f}",
            "cost_category": charge['cost_category'],
            "description": charge['description']
        })

    return output