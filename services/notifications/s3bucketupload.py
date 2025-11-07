import boto3
import botocore
import uuid
import zipfile
from io import BytesIO
import requests
import os
def fetch_and_upload_invoice_attachments(invoice_id: str, transaction_id: str) -> list:
    """
    Fetch the ZIP of attachments for the given invoice_id, extract PDFs,
    and upload each to S3 using invoice_id + transaction_id in the name.
    Returns list of uploaded S3 paths.
    """
    # ========= CONFIG =========
    BASE_URL = "https://tools.daynitetools.com/api"
    SEARCH_ENDPOINT = f"{BASE_URL}/emailsearch"
    DOWNLOAD_ENDPOINT = f"{BASE_URL}/downloadattachment"
    BUCKET_NAME = "daynitetools-invoice-automation-bucket"
    TMP_DIR = "/tmp"
    USER_EMAIL = "AP@wearetheone.com"
    # ==========================
    uploaded_paths = []

    try:
        api_key = os.getenv("TOOLS_API_KEY")
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json"
        }
        # Step 1️ Search for the email
        payload = {
            "search_term": invoice_id,
            "user": USER_EMAIL,
            "strict": True,
            "attachments": True
        }
        search_resp = requests.post(SEARCH_ENDPOINT, headers=headers, json=payload, timeout=60)

        search_resp.raise_for_status()
        data = search_resp.json()
        matches = data.get("matches", [])
        if not matches:
            print(f"No emails found for invoice_id={invoice_id}")
            return uploaded_paths

        email_id = matches[0].get("id")
        print(f" Found email ID: {email_id}")

        if not email_id:
            print(f" No email found for invoice_id={invoice_id}")
            return uploaded_paths

        download_payload = {
            "graph_id": email_id,
            "user": USER_EMAIL  
            }

        # Step 2️ Download the ZIP
        print(f" Downloading attachments ZIP for invoice {invoice_id}...")
        dl_resp = requests.post(DOWNLOAD_ENDPOINT, headers=headers, json=download_payload, timeout=120)

        dl_resp.raise_for_status()

        if "zip" not in dl_resp.headers.get("Content-Type", ""):
            print(f"Expected ZIP, got Content-Type={dl_resp.headers.get('Content-Type')}")
            return uploaded_paths

        zip_data = BytesIO(dl_resp.content)
        with zipfile.ZipFile(zip_data, "r") as zf:
            pdf_files = [f for f in zf.namelist() if f.lower().endswith(".pdf")]
            if not pdf_files:
                print(" No PDF files found inside ZIP.")
                return uploaded_paths

                
            sts = boto3.client("sts")
            identity = sts.get_caller_identity()
            print(f" Using IAM Role ARN: {identity['Arn']}")
            s3 = boto3.client("s3")
              # Verify identity
           

            for pdf_file in pdf_files:
                with zf.open(pdf_file) as pdf_data:
                    pdf_bytes = pdf_data.read()
                    filename = os.path.basename(pdf_file)
                    key = f"invoices/{invoice_id}/{invoice_id}_{transaction_id}_{filename}"

                    print(f"⬆ Uploading {filename} → s3://{BUCKET_NAME}/{key}")
                    s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=pdf_bytes, ContentType="application/pdf")

                    region = "us-east-1"  # your bucket's region
                    public_url = f"https://{BUCKET_NAME}.s3.{region}.amazonaws.com/{key}"

                    uploaded_paths.append(public_url)
                    print(f" Browser URL: {public_url}")

            print(f" Uploaded {len(uploaded_paths)} PDFs for invoice {invoice_id}.")

        return uploaded_paths

    except Exception as e:
        print(f" Error processing invoice {invoice_id}: {e}")
        return uploaded_paths  