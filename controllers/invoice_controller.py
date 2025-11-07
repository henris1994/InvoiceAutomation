
from fastapi.responses import JSONResponse
from fastapi import  HTTPException,APIRouter
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from models.dbconfigs import get_db_connection
from services.invoice_orchestrator import get_data
from services.notifications.s3bucketupload import fetch_and_upload_invoice_attachments
from services.notifications.mail_sender import send_email
from models.queries import sql_executor
router = APIRouter()
# Main  API Endpoint
@router.get("/invoice/{invoiceID}")
def get_po_data(invoiceID: str):
    return get_data(invoiceID)


#API Endpoint invoice-succesufully-proccesed by rpa bot
@router.post("/rpa/invoice-processed")
def process_invoice(payload: dict):
    nyc_tz = ZoneInfo("America/New_York")
    current_dt = datetime.now(nyc_tz)
    invoice_id = payload.get("invoice_id").strip().lower()
    po_number = payload.get("po_number").strip().lower()
    transaction_id = (payload.get("transaction_id") or "").strip().lower()
    trx_id = "error"
    trx_valid = False

    if not invoice_id or not po_number or not transaction_id: #change
         return JSONResponse(status_code=400, content={
        "success": False,
        "code": "MISSING_FIELDS",
        "message": "Missing invoice_id , po_number or transaction_id in request.",
        "errors": []
        }
        )
    
    #check if transaction_id that rpa sent exists in sampro 
    def build_trx_query(transaction_id: str) -> str:
        trx = (transaction_id or "").replace("'", "''")  # escape single quotes

        return f"""
        SELECT TOP 1
            a.apjrnl_id AS TransactionID,
            a.apjrnl_invce_nmbr AS InvoiceNumber,
            p.prchseordr_id AS PO_ID
        FROM apjrnl a
        LEFT JOIN prchseordr p
            ON a.prchseordr_rn = p.prchseordr_rn
        WHERE a.apjrnl_id = '{trx}'
        
        """
    trx_query= build_trx_query(transaction_id)  
    result=sql_executor(trx_query)
 
    if not result:
        trx_id="error"
    else:
        row = result[0]   # take the first dict
        
        db_trx_id = row.get("TransactionID", "").strip()
        db_inv_id = row.get("InvoiceNumber", "").strip()
        db_po_id  = row.get("PO_ID", "").strip()

        if (db_trx_id == transaction_id and 
            db_inv_id == invoice_id and 
            db_po_id == po_number):
            trx_id = db_trx_id
            trx_valid = True
        else:
            trx_id = "error"
            trx_valid = False

    conn = get_db_connection() #get vendordbconnnection
    cursor = conn.cursor(dictionary=True)

    try:
        #check if invoice exists in processscheduler table 
        cursor.execute("""
            SELECT 1 FROM processscheduler
            WHERE Invoice_id = %s AND Sampro_ponumber = %s
        """, (invoice_id, po_number))

        if cursor.fetchone() is None:
            return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "code": "INVOICE_NOT_FOUND",
                "message": "The invoice or PO number was not found in processsscheduler.",
                "errors": [f"invoice_id: {invoice_id}", f"po_number: {po_number}"]
            }
        )
        #Select oldest locked invoice for this PO
        cursor.execute("""
            SELECT * FROM processscheduler
            WHERE Sampro_ponumber = %s AND locked = 1
            ORDER BY Date ASC
        """, (po_number,))
        locked_invoices = cursor.fetchall()

        for inv in locked_invoices:
            inv_id = inv['Invoice_id']
            response = get_data(inv_id)

            result = json.loads(response.body)
            status_code = response.status_code

            wrapped={
                "body":result,
                "status":status_code
            }

            if status_code == 200:
                cursor.execute("""
                    UPDATE processscheduler
                    SET status = 'Ready_to_proccess', locked = 0,Date = %s,Decision_Payload = %s
                    WHERE Invoice_id = %s
                """, (current_dt,json.dumps(wrapped),inv_id,))
                conn.commit()
                break   
            else:
                status_reason = result.get("message", "validation_failed")
                new_status = result.get("invoice_type", "error")

                cursor.execute("""
                    UPDATE processscheduler
                    SET status = %s, status_reason = %s, locked = 0,Date = %s,Decision_Payload = %s
                    WHERE Invoice_id = %s
                """, (new_status, status_reason, current_dt ,json.dumps(wrapped), inv_id))

            conn.commit()

        #Mark the triggering invoice as processed
        cursor.execute("""
            UPDATE processscheduler
            SET status = 'Processed',status_reason = 'Processed' ,locked = 0,Date = %s,transaction_id=%s
            WHERE Invoice_id = %s
        """, (current_dt,trx_id,invoice_id,))
        conn.commit()

        #upload pdf-s to s3 bucket for this invoice
        uploaded_paths = fetch_and_upload_invoice_attachments(invoice_id, transaction_id)

        if uploaded_paths:
            print(f"Uploaded {len(uploaded_paths)} PDFs: {uploaded_paths}")

            # Join multiple URLs into a single comma-separated string
            urls_combined = ", ".join(uploaded_paths)

            try:
                cursor.execute("""
                    UPDATE processscheduler
                    SET Invoice_url = %s
                    WHERE Invoice_id = %s
                """, (urls_combined, invoice_id))
                conn.commit()
                print(f" Updated Invoice_url for invoice_id={invoice_id}")
            except Exception as e:
                print(f" Failed to update Invoice_url: {e}")

        else:
            print(f"No attachments uploaded for {invoice_id}")


        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "code": "INVOICE_PROCESSED",
                "message": "Invoice processed and PO queue updated successfully.",
                "data": {
                    "invoice_id": invoice_id,
                    "po_number": po_number,
                    "transaction_id": transaction_id,
                    "trx_valid:":trx_valid,
                    "updated": True
                }
            }
        )


    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()




@router.post("/rpa/failed")
def rpa_failed(payload: dict):
    current_dt = datetime.now()
    invoice_id = payload.get("invoice_id").strip().lower()
    po_number = payload.get("po_number").strip().lower()
    failed_reason = payload.get("failed_reason").strip().lower()

    status = "failed"
    status_reason = "rpa" + failed_reason  

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        sql = """
            UPDATE processscheduler
            SET Status = %s,
                Status_reason = %s,
                Date = %s
            WHERE LOWER(Invoice_id) = %s
              AND LOWER(Sampro_ponumber) = %s
        """
        cur.execute(sql, (status, status_reason ,current_dt, invoice_id, po_number))
        conn.commit()

        if cur.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="No matching invoice_id + po_number in processscheduler."
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "code": "db_updated",
                "message": "Status updated to failed.",
                "data": {
                    "invoice_id": invoice_id,
                    "po_number": po_number,
                    "status": status,
                    "status_reason": status_reason,
                },
            },
        )
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()
        

#endpoint to send email to rpa
@router.post("/invoice/send-email")
def email_invoice(payload: dict):
    invoice_id = payload.get("invoice_id")

    if not invoice_id:
        raise HTTPException(status_code=400, detail="Missing invoice_id in request.")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        #Step 1: Query decision_payload for the invoice
        cursor.execute("""
            SELECT decision_payload,Status
            FROM processscheduler
            WHERE Invoice_id = %s
            LIMIT 1
        """, (invoice_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found in processscheduler.")
        if row["Status"] != "Ready_to_proccess":
            raise HTTPException(status_code=400, detail=f"Invoice {invoice_id} already processed (current status: {row['Status']}).")
        decision_payload = row["decision_payload"]

        #format the decision load as the rpa wants it 
        payload_dict = json.loads(decision_payload, object_pairs_hook=dict)  # preserves insertion order
        body_items = payload_dict.get("body", [])
        chunks = [json.dumps(obj) for obj in body_items]
        emailcontent = chunks[0]  # first object with no delimiter

        for chunk in chunks[1:]:
            emailcontent += "\n?()?\n" + chunk
        
        send_email(emailcontent)
        cursor.execute("""
            UPDATE processscheduler
            SET Status = %s,
            Status_reason=%s
            WHERE Invoice_id = %s
        """, ("sent_to_rpa","Email sent to RPA" , invoice_id))
        conn.commit()
        #Return API response
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "invoice_id": invoice_id,
                "decision_payload": decision_payload,
                "message": "Email sent successfully"
            }
        )

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()