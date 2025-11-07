from models.bussinessmodifyables import jobidtoglentity,tax_mock,glaccount
from decimal import Decimal
from utils.utilfunctions import to_decimal
from fastapi.responses import JSONResponse
from models.queries import sql_executor
#check if invoice has already been processed
def check_invoice_transaction(invoiceid: str, ponumber: str):
    """
    Checks if an invoice has a transaction ID in apjrnl.
    Returns a plain Python dict with status and message.
    """

    sql_query = f"""
        SELECT 
            a.apjrnl_id AS TransactionID,
            a.apjrnl_invce_nmbr AS InvoiceNumber,
            p.prchseordr_id AS PO_ID
        FROM apjrnl a
        LEFT JOIN prchseordr p
            ON a.prchseordr_rn = p.prchseordr_rn
        WHERE a.apjrnl_invce_nmbr = '{invoiceid}';
    """

    result = sql_executor(sql_query)

    # Handle SQL endpoint error
    if "ERROR" in result:
        return {
            "invoiceid": invoiceid,
            "ponumber": ponumber,
            "status": "samprodberrorapi",
            "message": f"SQL error: {result['ERROR']}",
            "invoice_type": "manual_review",
            "status_code": 500
        }

    data = result.get("data", result) if isinstance(result, dict) else result
    if not data:
        # No record found
        return {
            "invoiceid": invoiceid,
            "ponumber": ponumber,
            "status": "ok",
            "message": "No transaction found for this invoice",
            "invoice_type": "new",
            "status_code": 200
        }

    # Record found → already processed
    trx = data[0]
    return {
        "invoiceid": invoiceid,
        "ponumber": ponumber,
        "status": "error",
        "transaction_id":trx.get('TransactionID').strip(),
        "message": f"Invoice already processed (TransactionID: {trx.get('TransactionID').strip()})",
        "invoice_type": "user_processed",
        "status_code": 400
    }

#check if invoice exist and then if po exists
def validate_single_po(invoiceID,invoice_data,PoData):
    # Find invoice by ID
    
    invoice = next((inv for inv in invoice_data if inv['invoiceID'].lower() == invoiceID.lower()), None)
    
    
    if not invoice:
        return {'invoiceid':f'{invoiceID}','ponumber':'','status': 'error', 'message': f'Invoice ID {invoiceID} not found.','invoice_type':'bad_invoice'}, 404

    invoice_po_number = invoice['PONumber'].lower()
    invoice_no = invoice['invoiceID'].lower()
    print('InvoiceNo:')
    print(invoice_no)
    print('PONumber:')
    print(invoice_po_number)
   
    #invoice_po_number='368526'  #Delete later 
    purchase_order = next((po for po in PoData if po['prchseordr_id'].lower() == invoice_po_number), None)
    
    if not purchase_order:
        return {'invoiceid':f'{invoice_no}','status': 'error', 'message': f'purchase order id  {invoice_po_number} not found.','invoice_type':'bad_invoice'}, 404
    print("FOUND PO FOR THIS INVOICE")
   
    return True

#check if invoice total matches invoice line items totals(total might be inflated)
def check_invoice_total(invoice_data):
    first_row = invoice_data[0]
    invoiceid=first_row['invoiceID']
    ponumber=first_row['PONumber']
    invoice_total=to_decimal(first_row['InvoiceDetailSummary:NetAmount'])
    invoice_handling=to_decimal(first_row['InvoiceDetailSummary:SpecialHandlingAmount'])
    invoice_tax=to_decimal(first_row['InvoiceDetailItem:Tax'])

    inv_line_total = Decimal('0.00')
    for item in invoice_data:
        
        unit_price=to_decimal(item['InvoiceDetailItem:UnitPrice'])
        unit_quantity=int(item['InvoiceDetailItem:quantity'])
        inv_line_total += (unit_price*unit_quantity)

    if(invoice_total!=inv_line_total + invoice_handling + invoice_tax):
        return JSONResponse(content={'invoiceid':f'{invoiceid}','ponumber':f'{ponumber}','status': 'error', 'message': 'Invoice Total does not equal invoice line items total','invoice_type':'manual_review'},status_code=400)
    return None

def check_taxinfo(PoData,invoice_data): 
    gl_entity = PoData[0]['gl_entity_id'].lower()
    job_id = PoData[0]['job_id'].upper()
    job_id = job_id[:2]
    glaccountvalue=''
    print('JOBBBBBBBB ID:' )
    
    if  gl_entity:
        gl_entity = gl_entity[:2] + 'a99'
        authorityid = tax_mock.get(gl_entity) # returns value or None if not found
        glaccountvalue=glaccount.get(gl_entity)
        print("TTTAAAXXX-gl:")
    else:
        gl_entity=jobidtoglentity.get(job_id)
        authorityid = tax_mock.get(gl_entity) # returns value or None if not found
        glaccountvalue=glaccount.get(gl_entity)
        print("TTTAAAXXX-jobid:")
    
    taxbase=invoice_data[0]['InvoiceDetailSummary:NetAmount'] - invoice_data[0]['InvoiceDetailItem:Tax'] - invoice_data[0]['InvoiceDetailSummary:SpecialHandlingAmount']
    taxamount=invoice_data[0]['InvoiceDetailItem:Tax']
    rate = round(taxamount / taxbase * 100, 4)  if taxbase else 0.0
    
    
    tax_info = {
        "authority_id": authorityid,
        "gl_account": glaccountvalue,
        "tax_base": f"{taxbase:.3f}",
        "rate": f"{rate:.4f}",
        "tax_amount": f"{taxamount:.3f}"
    }
    print(tax_info)
    
    return tax_info


        
def can_close_po(invoice_items, po_items):
    #how many units are invoiced per item
    invoice_qty_by_item = {}
    for item in invoice_items:
        part_number = item['SellerPartNumber'].lower()
        invoice_qty_by_item[part_number] = invoice_qty_by_item.get(part_number, 0) + int(item['InvoiceDetailItem:quantity'])

    close_po = True  

    for po in po_items:
        item_id = po['vendor_part'].lower()
        ordered = po['qty_ordered_line']
        received = po['qty_received_imhstry']
        vouchered = po['qty_vouchered']

        eligible_to_voucher = received - vouchered
        invoice_qty = invoice_qty_by_item.get(item_id, 0)

        #  If item not fully received, PO cannot be closed
        if received < ordered:
            close_po = False
            print(f" Cannot close PO: item '{item_id}' not fully received.")
            continue

        # If invoice does not voucher all received-but-unvouchered units
        if invoice_qty < eligible_to_voucher:
            close_po = False
            print(f" Cannot close PO: item '{item_id}' still has {eligible_to_voucher - invoice_qty} unvouchered units.")

    return close_po



#validate if invoice is trying to overvouch
def validatevouch(invoice_items, po_items):
    matching_pos = []
    for item in invoice_items:
        part_number = item['SellerPartNumber'].lower()
        matching_pos += [po for po in po_items if po['vendor_part'].lower() == part_number]
        
    isVoucherEligible = True;     
        
    for match in matching_pos:
        part_number_po=match['vendor_part']
        ordered = match['qty_ordered_line']
        received = match['qty_received_imhstry']
        vouchered = match['qty_vouchered']
        unitcost=match['unit_cost']
        elegibletobevouchered=received - vouchered

        totalpo_line_item=ordered*unitcost
        allowed_price_peritem=(totalpo_line_item +100) /ordered
       
       
        invoice_item = next((item for item in invoice_items if item['SellerPartNumber'].lower() == part_number_po.lower()),None)# there will always be one
        # if (elegibletobevouchered < int(invoice_item['InvoiceDetailItem:quantity']) or ordered < received or  Decimal(match['unit_cost']) != Decimal(invoice_item['InvoiceDetailItem:UnitPrice'])) :
        #     isVoucherEligible = False
        invoice_qty = int(invoice_item['InvoiceDetailItem:quantity'])
        invoice_price = Decimal(invoice_item['InvoiceDetailItem:UnitPrice'])
        po_price = Decimal(match['unit_cost'])


        if invoice_qty + vouchered > ordered:
            print(f"{part_number_po}:Quantity Ordered={ordered},Quantity Received={received},Quantity Vouchered={vouchered},elegibletobevouchered={elegibletobevouchered}, Quantity(invoiced)={invoice_item['InvoiceDetailItem:quantity']}, po_price={match['unit_cost']}, invoice_price={invoice_item['InvoiceDetailItem:UnitPrice']}")

            isVoucherEligible = False
            return {
            "invoiceid" : invoice_item['invoiceID'],
            "ponumber" : match['prchseordr_id'],
            "status": "error",
            "message": f"Bad Invoice qnt higher than ordered",
            "invoice_type":"bad_invoice",
            "code": 400
        }


        if elegibletobevouchered < invoice_qty:
            print(f"{part_number_po}:Quantity Ordered={ordered},Quantity Received={received},Quantity Vouchered={vouchered},elegibletobevouchered={elegibletobevouchered}, Quantity(invoiced)={invoice_item['InvoiceDetailItem:quantity']}, po_price={match['unit_cost']}, invoice_price={invoice_item['InvoiceDetailItem:UnitPrice']}")
            isVoucherEligible = False
            return {
            "invoiceid" : invoice_item['invoiceID'],
            "ponumber" : match['prchseordr_id'],
            "status": "error",
            "message": f"Not enough received to voucher this invoice item: requested from invoice {invoice_qty}, but only {elegibletobevouchered} eligible",
            "invoice_type":"early_invoice",
            "code": 400
        }
            
           
        if ordered < received:
            isVoucherEligible = False
            return {
            "invoiceid" : invoice_item['invoiceID'],
            "ponumber" : match['prchseordr_id'],
            "status": "error",
            "message": f"Overreceipt: PO ordered {ordered}, but received {received}",
            "invoice_type":"bad_invoice",
            "code": 400
        }
           

        if po_price != invoice_price:
            isVoucherEligible = False
            return {
            "invoiceid" : invoice_item['invoiceID'],
            "ponumber" : match['prchseordr_id'],
            "status": "error",
            "message": f"Price mismatch: PO unit price is {po_price}, but invoice price is {invoice_price}",
            "invoice_type":"manual_review",
            "code": 400
        }
        
       
           

        print("Part Number:")    
        print(f"{part_number_po}:Quantity Ordered={ordered},Quantity Received={received},Quantity Vouchered={vouchered},elegibletobevouchered={elegibletobevouchered}, Quantity(invoiced)={invoice_item['InvoiceDetailItem:quantity']}, po_price={match['unit_cost']}, invoice_price={invoice_item['InvoiceDetailItem:UnitPrice']}")
     # Find matching PO line item
        
        print("ALLOWED PRICE PER ITEM:")
        
        print(allowed_price_peritem)
        print("Total item PO_line:")
        print(totalpo_line_item)
    
    print(isVoucherEligible)
    return {
    "status": "ok",
    "message": "Invoice validated successfully",
    "code": 200
}   

def check_for_duplicate_items(invoice):
    seen = set()
    duplicates = set()

    for item in invoice:
        part_number = item['SellerPartNumber'].lower().strip()
        if part_number in seen:
            duplicates.add(part_number)
        else:
            seen.add(part_number)

    if duplicates:
        print("Duplicate item IDs found:", list(duplicates))
        return False

    return True
    
