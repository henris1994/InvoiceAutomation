
from utils.utilfunctions import int_or_zero,to_decimal,format_date

#CLEAN SAMPRO SQL DATA
def clean_po_line_data(rows):
    """
    Cleans PO/line rows with fields like:
    prchseordr_id, po_wrkordr_rn, vndr_id, glentty_rn, glentty_id,
    jb_rn, jb_id, wrkordr_rn, wrkordr_id, line_source, line_no,
    vendor_part, description, uom, qty_ordered_line, qty_received_line,
    qty_received_imhstry, qty_vouchered, unit_cost
    """
    cleaned = []

    for r in rows:
        try:
            cleaned_record = {
            # Header / identifiers
            'prchseordr_id' : str(r.get('prchseordr_id', '')).strip(),
            'vndr_id' : str(r.get('vndr_id', '')).strip(),
            'glentty_rn' : int_or_zero(r.get('glentty_rn')),
            'glentty_id' : str(r.get('glentty_id', '')).strip().upper(),
            'jb_rn' : int_or_zero(r.get('jb_rn')),
            'jb_id' : str(r.get('jb_id', '')).strip(),

            
            'workorder_rn' : int_or_zero(r.get('wrkordr_rn') if r.get('wrkordr_rn') not in (None, '') else r.get('po_wrkordr_rn')),
            'workorder_id' : str(r.get('wrkordr_id', '')).strip(),

            # Line & item
            'line_source' : str(r.get('line_source', '')).strip().lower(),
            'line_no' : int_or_zero(r.get('line_no')),
            'vendor_part' : str(r.get('vendor_part', '')).strip(),
            'description' : str(r.get('description', '')).strip(),
            'uom' : str(r.get('uom', '')).strip(),  # keep '' if all spaces

            # Quantities & price
            'qty_ordered_line' : to_decimal(r.get('qty_ordered_line')),
            'qty_received_line' : to_decimal(r.get('qty_received_line')),
            'qty_received_imhstry' : to_decimal(r.get('qty_received_imhstry')),
            'qty_vouchered' : to_decimal(r.get('qty_vouchered')),
            'unit_cost' : to_decimal(r.get('unit_cost'))
            }
           

           

            cleaned.append(cleaned_record)

        except Exception as e:
            print(f"Error processing record: {e}")

    return cleaned
#CLEAN MARKETPLACE DB DATA
def clean_invoice_data(invoice_data):
    cleaned = []
 
    for record in invoice_data:
        try:
            cleaned_record = {
                'invoiceID': str(record.get('invoiceID', '')).strip(),
                'invoiceDate': format_date(record.get('invoiceDate')),
                'InvoiceDetailSummary:SubtotalAmount': to_decimal(record.get('InvoiceDetailSummary:SubtotalAmount')),
                'InvoiceDetailSummary:NetAmount': to_decimal(record.get('InvoiceDetailSummary:NetAmount')),
                'isTaxInLine': str(record.get('isTaxInLine', 'No')).strip().lower(),
                'InvoiceDetailItem:Tax': to_decimal(record.get('InvoiceDetailItem:Tax')),
                'PONumber': str(record.get('PONumber', '')).strip(),
                'InvoiceDetailSummary:ShippingAmount': to_decimal(record.get('InvoiceDetailSummary:ShippingAmount')),
                'InvoiceDetailSummary:SpecialHandlingAmount': to_decimal(record.get('InvoiceDetailSummary:SpecialHandlingAmount')),
                'SellerPartNumber': str(record.get('SellerPartNumber', '')).strip(),
                'InvoiceDetailItem:quantity': int_or_zero(record.get('InvoiceDetailItem:quantity')),
                'InvoiceDetailItem:UnitPrice': to_decimal(record.get('InvoiceDetailItem:UnitPrice')),
                'InvoiceDetailItem:UnitOfMeasure': str(record.get('InvoiceDetailItem:UnitOfMeasure', '')).strip(),
                'ItemDescription': str(record.get('ItemDescription', '')).strip(),
                'createdAt': format_date(record.get('createdAt'))
                
            }

            cleaned.append(cleaned_record)
        except Exception as e:
            print(f"Error processing record: {e}")
    
    return cleaned