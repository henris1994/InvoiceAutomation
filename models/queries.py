import mysql.connector
from models.dbconfigs import marketplace_config,db_config
import requests
import os
#sampro PO query
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





#MARKETPLACE invoice QUERY
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