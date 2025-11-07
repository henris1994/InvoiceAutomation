from models.dbconfigs import marketplace_config,db_config
from utils.utilfunctions import int_or_zero,to_decimal,format_date
import pyodbc
import mysql.connector
from mysql.connector import connect, Error
import requests
import os

def build_po_query(po_id: str) -> str:
    """
    Return the full T-SQL with @po_id set to the provided value.
    Safely escapes single quotes in po_id.
    """
    po = (po_id or "").replace("'", "''")  # SQL-escape single quotes

    sql = f"""
DECLARE @po_id VARCHAR(50) = '{po}';

-- 1) PO lines (LIST + LISTGN)
WITH all_lines AS (
    SELECT
        'LIST' AS line_source,
        prchseordr_rn,
        prchseordrlst_rn AS ordrlst_rn,
        prchseordrlst_ln AS line_no,
        prchseordrlst_vndr_prt_nmbr AS vendor_part,
        prchseordrlst_dscrptn       AS description,
        prchseordrlst_unt_msre      AS uom,
        prchseordrlst_qntty_ordrd   AS qty_ordered_line,
        prchseordrlst_qntty_rcvd    AS qty_received_line,
        prchseordrlst_unt_cst       AS unit_cost,
        NULLIF(invntryitm_rn,0)     AS invntryitm_rn,
        po_glentty_glentty_rn       AS line_glentty_rn  -- GL entity from line
    FROM prchseordrlst

    UNION ALL

    SELECT
        'LISTGN',
        prchseordr_rn,
        prchseordrlstgn_rn,
        prchseordrlstgn_ln,
        prchseordrlstgn_vndr_prt_nmbr,
        prchseordrlstgn_dscrptn,
        prchseordrlstgn_unt_msre,
        prchseordrlstgn_qntty_ordrd,
        prchseordrlstgn_qntty_rcvd,
        prchseordrlstgn_unt_cst,
        NULL,
         glentty_rn  -- GL entity from line
    FROM prchseordrlstgn
),

-- 2) LISTGN: map PO line RN -> reference RN from Purchase rows
listgn_ref_map AS (
    SELECT DISTINCT
        RTRIM(imhstry_ordr_id) AS po_id_trim,
        i.imhstry_ordrlst_rn   AS ordrlst_rn,
        i.imhstry_rfrnce_rn    AS ref_rn
    FROM imhstry i
    WHERE i.imhstry_ordr_type='P'
      AND RTRIM(i.imhstry_ordr_id)=RTRIM(@po_id)
      AND i.imhstry_srce_jrnl='Purchase'
      AND ISNULL(i.invntryitm_rn,0)=0
      AND i.imhstry_rvrsl='N'
      AND i.imhstry_vdd='N'
      AND NULLIF(i.imhstry_ordrlst_rn,0) IS NOT NULL
),

-- 3) RECEIVED by inventory item (LIST)
received_by_item AS (
    SELECT
        RTRIM(imhstry_ordr_id) AS po_id_trim,
        invntryitm_rn,
        SUM(TRY_CAST(imhstry_qntty_rcvd AS decimal(18,6))) AS qty_received
    FROM imhstry
    WHERE imhstry_ordr_type='P'
      AND RTRIM(imhstry_ordr_id)=RTRIM(@po_id)
      AND imhstry_srce_jrnl='Receipt'
      AND ISNULL(invntryitm_rn,0)<>0
      
    GROUP BY RTRIM(imhstry_ordr_id), invntryitm_rn
),

-- 4) RECEIVED by reference (LISTGN)
received_by_ref AS (
    SELECT
        RTRIM(imhstry_ordr_id) AS po_id_trim,
        imhstry_rfrnce_rn,
        SUM(TRY_CAST(imhstry_qntty_rcvd AS decimal(18,6))) AS qty_received
    FROM imhstry
    WHERE imhstry_ordr_type='P'
      AND RTRIM(imhstry_ordr_id)=RTRIM(@po_id)
      AND imhstry_srce_jrnl='Receipt'
      AND ISNULL(invntryitm_rn,0)=0
     
    GROUP BY RTRIM(imhstry_ordr_id), imhstry_rfrnce_rn
),

-- 5) VOUCHERED by inventory item (LIST)
vouchered_by_item AS (
    SELECT
        RTRIM(imhstry_ordr_id) AS po_id_trim,
        invntryitm_rn,
        SUM(TRY_CAST(imhstry_qntty_invcd_ap AS decimal(18,6))) AS qty_vouchered
    FROM imhstry
    WHERE imhstry_ordr_type='P'
      AND RTRIM(imhstry_ordr_id)=RTRIM(@po_id)
      AND imhstry_srce_jrnl='AP Purchase'
      AND ISNULL(invntryitm_rn,0)<>0
      AND imhstry_vdd='N'
    GROUP BY RTRIM(imhstry_ordr_id), invntryitm_rn
),

-- 6) VOUCHERED by reference (LISTGN)
vouchered_by_ref AS (
    SELECT
        RTRIM(imhstry_ordr_id) AS po_id_trim,
        imhstry_rfrnce_rn,
        SUM(TRY_CAST(imhstry_qntty_invcd_ap AS decimal(18,6))) AS qty_vouchered
    FROM imhstry
    WHERE imhstry_ordr_type='P'
      AND RTRIM(imhstry_ordr_id)=RTRIM(@po_id)
      AND imhstry_srce_jrnl='AP Purchase'
      AND ISNULL(invntryitm_rn,0)=0
      AND imhstry_vdd='N'
    GROUP BY RTRIM(imhstry_ordr_id), imhstry_rfrnce_rn
)

SELECT
    p.prchseordr_id,
    p.po_wrkordr_rn,
    vndr.vndr_id,
     -- Use line GL entity FIRST, then fallback to location/company
    COALESCE(gl_line.glentty_rn, glc.glentty_rn, gcmp.glentty_rn) AS glentty_rn,
    COALESCE(gl_line.glentty_id, glc.glentty_id, gcmp.glentty_id) AS glentty_id,
    jb.jb_rn,
    jb.jb_id,
    wo.wrkordr_rn,
    wo.wrkordr_id,
    al.line_source,
    al.line_no,
    al.vendor_part,
    al.description,
    al.uom,
    al.qty_ordered_line,
    al.qty_received_line,

    -- RECEIVED
    CASE
        WHEN al.line_source='LIST'
            THEN ISNULL(rbi.qty_received,0)
        ELSE ISNULL(rbr.qty_received,0)
    END AS qty_received_imhstry,

    -- VOUCHERED
    CASE
        WHEN al.line_source='LIST'
            THEN ISNULL(vbi.qty_vouchered,0)
        ELSE ISNULL(vbr.qty_vouchered,0)
    END AS qty_vouchered,

    al.unit_cost

FROM prchseordr p
LEFT JOIN vndr vndr          ON p.vndr_rn=vndr.vndr_rn
LEFT JOIN wrkordr wo         ON p.po_wrkordr_rn=wo.wrkordr_rn
LEFT JOIN jbbllngitm         ON jbbllngitm.jbbllngitm_rn=wo.jbbllngitm_rn
LEFT JOIN jbcstcde           ON jbcstcde.jbcstcde_rn=wo.jbcstcde_rn
LEFT JOIN jb                 ON jb.jb_rn=COALESCE(NULLIF(p.jb_rn,0),NULLIF(jbbllngitm.jb_rn,0),NULLIF(jbcstcde.jb_rn,0))
LEFT JOIN lctn l             ON p.lctn_rn=l.lctn_rn
LEFT JOIN glentty gj         ON gj.glentty_rn=jb.jb_glentty_glentty_rn
LEFT JOIN glentty glc        ON glc.glentty_rn=l.glentty_rn
LEFT JOIN glentty gcmp       ON gcmp.glentty_rn=p.cmpny_glentty_glentty_rn

LEFT JOIN all_lines al ON p.prchseordr_rn=al.prchseordr_rn
LEFT JOIN glentty gl_line    ON gl_line.glentty_rn=al.line_glentty_rn  -- Line GL entity

-- LIST joins
LEFT JOIN received_by_item rbi ON rbi.po_id_trim=RTRIM(p.prchseordr_id)
                              AND al.invntryitm_rn=rbi.invntryitm_rn
LEFT JOIN vouchered_by_item vbi ON vbi.po_id_trim=RTRIM(p.prchseordr_id)
                               AND al.invntryitm_rn=vbi.invntryitm_rn

-- LISTGN joins
LEFT JOIN listgn_ref_map lref ON lref.po_id_trim=RTRIM(p.prchseordr_id)
                             AND al.line_source='LISTGN'
                             AND al.ordrlst_rn=lref.ordrlst_rn
LEFT JOIN received_by_ref rbr ON rbr.po_id_trim=RTRIM(p.prchseordr_id)
                             AND rbr.imhstry_rfrnce_rn=lref.ref_rn
LEFT JOIN vouchered_by_ref vbr ON vbr.po_id_trim=RTRIM(p.prchseordr_id)
                              AND vbr.imhstry_rfrnce_rn=lref.ref_rn

WHERE RTRIM(p.prchseordr_id)=RTRIM(@po_id)
ORDER BY al.line_source, al.line_no;



"""
    return sql


#EXECUTE ABOVE SQL
def sql_executor(sql_query: str):
    url = "http://10.10.30.183/api/v1/sql" # local IP
    headers = {
        "content-type": "application/json",
        "X-API-Key": os.getenv('sql_client_api_key')
    }
    payload = {
        "sql_query": sql_query
    }

    response = requests.post(url, headers=headers, json=payload)
    try:
        data = response.json()
        return data
    except ValueError:
        return {"ERROR": response.text}

# TO TEST:
# python -m test-sql
if __name__ == "__main__":
    res = sql_executor(sql_query="WITH MainQuery AS (SELECT clntste.clntste_id as SiteId, clntste_stre_nmbr as StoreNo, clntste.clntste_nme as SiteName, wrkordr.wrkordr_id as WorkOrderId, wrkordr.wrkordr_po as PONo, wrkordr.wrkordr_nme as Description, srvcectgry.srvcectgry_id as ServiceCategoryId, wrkordr.wrkordr_type as WorkType, case when right(wrkordr_entrd_by, 1) = '2' OR right(wrkordr_entrd_by, 1) = '3' then reverse(substring(reverse(wrkordr_entrd_by), 2, 25)) else wrkordr_entrd_by end as EnteredBy, wrkordr_dte_opnd + '   ' + LTRIM(RIGHT(CONVERT(VARCHAR(20), cast(wrkordr_tme_opnd as datetime), 100), 7)) + ' (' + left(DATENAME(weekday,wrkordr_dte_opnd),3) + ')' as Created, (select max(wrkordrtchncn_dte_schdld + ' (' + left(DATENAME(weekday,wrkordrtchncn_dte_schdld),3) + ')') from wrkordrtchncn where wrkordrtchncn.wrkordr_rn = wrkordr.wrkordr_rn) as Scheduled, CASE WHEN wrkordr_escltn_stts IN ('Parts Received','Pending') THEN 'Parts Ordered' ELSE wrkordr_escltn_stts END as Status, (SELECT COUNT(wrkordreqpmnt_rn) from wrkordreqpmnt where wrkordreqpmnt.wrkordr_rn = wrkordr.wrkordr_rn) as Equipment, CASE WHEN wrkordr.srvcerqst_wblg_rn <> 0 THEN CONVERT(char(10),wblg_id) ELSE '' END as ServiceRequestNo from wrkordr join clntste on wrkordr.clntste_rn = clntste.clntste_rn join wbprfle on clntste.wbprfle_rn = wbprfle.wbprfle_rn join srvcectgry on wrkordr.srvcectgry_rn = srvcectgry.srvcectgry_rn join wblg on wrkordr.srvcerqst_wblg_rn = wblg.wblg_rn join rmte_wbusrclntste on rmte_wbusrclntste.clntste_rn = clntste.clntste_rn join scrty on wrkordr.scrty_rn = scrty.scrty_rn where rmte_wbusrclntste.wbusr_id = 'dhill' and (wrkordr_stts_ctgry = 'Open') and wrkordr.wrkordr_id >= '700000') SELECT SiteId, StoreNo, SiteName, WorkOrderId, PONo, Description, ServiceCategoryId, WorkType, EnteredBy, Created, Scheduled, Status, Equipment, ServiceRequestNo, EnteredBy FROM MainQuery ORDER BY Created DESC, WorkOrderId")
    print(res)





#MARKETPLACE QUERY
def getDBRecordById(invoice_id):

    conn_mysql = mysql.connector.connect(**marketplace_config
    
)
    cursor_mysql = conn_mysql.cursor(dictionary=True)
    cursor_mysql.execute( """
    SELECT 
        PONumber,
        invoiceID,
        invoiceDate,
        `InvoiceDetailSummary:SubtotalAmount`,
        `InvoiceDetailSummary:NetAmount`,
        `InvoiceDetailSummary:GrossAmount`,
        isTaxInLine,
        `InvoiceDetailItem:Tax`,
        `InvoiceDetailSummary:ShippingAmount`,
        `InvoiceDetailSummary:SpecialHandlingAmount`,
        SellerPartNumber,
        `InvoiceDetailItem:quantity`,
        `InvoiceDetailItem:UnitPrice`,
        `InvoiceDetailItem:UnitOfMeasure`,
        ItemDescription,
        createdAt,
        updatedAt
                 
    FROM InvoiceItems
    WHERE invoiceID = %s
    
    """,(invoice_id,))
    data=cursor_mysql.fetchall()
    cursor_mysql.close()
    conn_mysql.close()
    return data


    
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