from models.queries import build_po_query,sql_executor,getDBRecordById
from models.data import clean_invoice_data,clean_po_line_data
from models.bussinessmodifyables import jobidtoglentity
from fastapi.responses import JSONResponse
from services.matching.promt import chatgpt_match_by_description
from services.matching.matcher_orchestrator import validate_and_match_invoice_items_against_po_strict
from services.transformations.rpa_formatter import transform_for_ui
from services.transformations.sortpolines import sortlinenumbers
from services.validation.invoicerules import (
    validate_single_po,
    check_for_duplicate_items,
    validatevouch,
    can_close_po,
    check_taxinfo,
    check_invoice_total,
    check_invoice_transaction
)

#this function acts as an orchestrator and  calls all the other validations functions one by one  (each function performs a validation action invoice against po )
#this function needs to reach to the end of it to produce a valid json payload for the RPA bot , if it doesnt the invoice failed some validation function
#if an invoice fails a validation function  along this function, returns a json payload with a status of 400/404 with its respective reason why it failed
#can be cleaned up a little bit more (move the extra charges and tax into separate function outside of this function)
def get_data(invoiceID):
    
    line_items=[]
    charges=[]
    tax_info = []
    extra_charge_count=0
    line_item_count=0
    #get the invoice data from marketplace
    dbinvoicedata = getDBRecordById(invoiceID)
    invoice_data=clean_invoice_data(dbinvoicedata)
    #get the purchase order number for this invoice
    invoice_datapo=invoice_datapo = next(
    (rec.get('PONumber') for rec in (invoice_data or []) if isinstance(rec, dict) and 'PONumber' in rec),
    None
)
    #get the Po from the invoice PO-Number
    querysampro=build_po_query(invoice_datapo)
    queryendpointresults=sql_executor(querysampro)
    #Cleanpodata
    PoData= clean_po_line_data(queryendpointresults)
    print(PoData)

    #check if invoice exists and if po exists
    result = validate_single_po(invoiceID,invoice_data,PoData)
    if result is not True:
       
        return JSONResponse(content=result[0], status_code=result[1])
    #check if invoice is already entered in Sampro by checking if it has a transaction_id
    inv_state=check_invoice_transaction(invoiceID,invoice_datapo)
   
    print(inv_state)
    if (inv_state["status"]=="error"):
        return JSONResponse(content=inv_state, status_code=inv_state["status_code"])

    #check if invoice total is correct
    total_check = check_invoice_total(invoice_data)
    if total_check is not None:
        return total_check


    #compare invoice part numbers to po and AI checking for missing partnumbers and general items which dont have partnumbers
    resp = validate_and_match_invoice_items_against_po_strict(
    invoice_id=invoiceID,
    invoice_items=invoice_data,
    po_items=PoData,
    ai_match_fn=chatgpt_match_by_description,
    accept_threshold=0.80
    )

    if resp["pass"]:
        # New po and invoice structures from validate_and_match function with all the id-s including the added ones from descp AI matching 
        invoice_items_ready = resp["invoice_items_resolved"]
        po_items_ready      = resp["po_items_resolved"]
        used_ai_to_match = resp["used_ai_match"]
        print("aiiiiiiiiiiiiiiiiiiiiiiiiiiimaatchhh")
        print(used_ai_to_match)
    else:
        
        print(resp["fail_reasons"])
        return JSONResponse(content={
        "invoiceid" : resp['invoice_id'],
        "po_id":resp['po_id'],
        "invoice_type" :"manual_review",
        "message":"AI Item Matching failed",
        "fail_reasons": resp.get("fail_reasons", []),
        "ai_Response": resp.get("ai_resp"),
        'status': 'error'
        },status_code= 400)
        
       

    if not check_for_duplicate_items(invoice_items_ready):
        return JSONResponse(content={'invoiceid':f'{invoiceID}','ponumber':f'{invoice_datapo}','status': 'error', 'message': 'Duplicate item IDs found','invoice_type':'manual_review'},status_code=400)
    
    #check if invoice is elegible to be processed ( tip : an invoice is either elegible to be  processed or not,if the invoice is 
    #elegible to be processed all its items will be processed, there is no scenario where some items can be processed and others not
    #if a line item in the invoice fails its validation against the PO , the whole invoice cannot be proccessed)
    #This function checks the quantities,prices in the invoice and validates if the po has room for this invoice to be processed.
    validate=validatevouch(invoice_items_ready, po_items_ready)
    if validate["status"] == "error":
        return JSONResponse(content=validate, status_code=validate["code"])
    
    


    #Calculate tax freight close po 

    close_po=can_close_po(invoice_items_ready, po_items_ready)
   
    #check marketplaceDb if it has taxes
    IsInlineTax=invoice_items_ready[0]['isTaxInLine']
    shared_special_handling=invoice_items_ready[0]['InvoiceDetailSummary:SpecialHandlingAmount']

    if IsInlineTax=='yes':
        hastax=True
        tax_info=check_taxinfo(po_items_ready,invoice_items_ready)
        
    else:
        hastax=False
        
    
        #check if there is freight
    if shared_special_handling is not None and shared_special_handling > 0 and shared_special_handling<=500:
        hasextracharges=True
        extra_charge_count=extra_charge_count+1
        
        charges.append({
            'charge_number':extra_charge_count,
            'quantity': ('1'),
            'unit_cost': shared_special_handling,
            'cost_category': ('FREIGHT'),
            'description': ('Freight Charge'),
        })
        print("Extra Charges:")
        print(charges)
    elif shared_special_handling>500:
         return JSONResponse(content={'invoiceid':f'{invoiceID}','ponumber':f'{invoice_datapo}','status': 'error', 'message': 'Freight needs manual review, Freight exceeds 500 Dollars!','invoice_type':'manual_review'},status_code=400)
    else:
        hasextracharges=False
        
    
        

  
          
    
    for item in invoice_items_ready:
        item_id = item['SellerPartNumber'].lower()
        unit_price = item['InvoiceDetailItem:UnitPrice'] 
        quantity = item['InvoiceDetailItem:quantity']
        line_item_count=line_item_count+1
        poitem= next((po for po in po_items_ready if po['vendor_part'].lower() == item_id), None)
        line_number=poitem['line_no']
        line_source=poitem['line_source']
        line_items.append({
        'line_number':line_number,
        'line_source':line_source,
        'item_id': item_id,
        'quantity': quantity,
        'unit_cost': unit_price,
        'amount': int(quantity)*unit_price
        
            
        
    })
    #function  that produces the Purchase Order view exactly as it appears in Sampro.   
    poview=sortlinenumbers(po_items_ready,line_items)
   

   #get gl_entity by glentty or by job_id
    short_gl=''
    gl_entity = po_items_ready[0]['glentty_id'].lower()
    job_id = po_items_ready[0]['jb_id'].upper()
    
    if  gl_entity:
        short_gl = po_items_ready[0]['glentty_id'].lower()
        gl_entty = short_gl[:2] + 'a99'
    else:
        job_id = job_id[:2]
        gl_entty=jobidtoglentity.get(job_id)
        gl_entty = gl_entty[:2] + 'a99'
       
        
        print("glentity-jobid:")
    response = {
        'type': 'general_info',
        'po_number': invoice_items_ready[0]['PONumber'],    
        'invoice_number': invoice_items_ready[0]['invoiceID'],
        'invoice_date': invoice_items_ready[0]['createdAt'],
        
        'invoice_total': invoice_items_ready[0]['InvoiceDetailSummary:NetAmount'],
        'gl_entity_id':gl_entty,
        'has_taxes': hastax,
        'tax_info': tax_info,
        'has_extra_charges': hasextracharges,
        'extra_charge_count':extra_charge_count,
        'extra_charges': charges,
        'line_items':poview,
        
        'line_item_count':line_item_count,
        
        'close_po': close_po, 
        'ai_match':used_ai_to_match,

        'invoice_file_path': ""
    }
    #transform the json response as The RPA Bot requires it 
    uiresponse=transform_for_ui(response)
   
    print("Invoice Processed Successfully.")
    print("TOTAL:",invoice_items_ready[0]['InvoiceDetailSummary:NetAmount'])



    print(charges)

    return JSONResponse(content=uiresponse,status_code=200)