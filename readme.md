# 🧾 Invoice Automation API

## 📘 Overview
The **Invoice Automation API** is a backend service that automates the **invoice-to–Purchase Order (PO)** validation, comparison, and entry process for vendor invoices received from **marketplaces** (databases where vendors upload their invoices).

Traditionally, the Accounts Payable (AP) team manually compared each invoice against its PO in **Sampro**, checking part numbers, prices, quantities, and ensuring that invoices weren’t duplicated. This manual workflow was slow, error-prone, and created major bottlenecks.

The **Invoice Automation API** replaces that process with a fully automated validation pipeline. It compares invoices to their POs programmatically, enforces business rules, and generates structured **JSON payloads** for direct ingestion by an **RPA bot** that creates the invoice in Sampro.

All API outputs are stored in the **`processscheduler`** table, which logs every response and serves as the integration point for downstream systems like the RPA Bot and the KPI Dashboard.  
This automation significantly reduces AP workload, improves data accuracy, and speeds up processing times.

> **Note:**  
> Currently, this API only allows invoices whose item prices exactly match their corresponding PO line items.  
> Business rules are defined under: `service/validation/invoicerules.py`.

---

## 🧩 End-to-End Flow

1. **Vendors upload invoices**  
   Vendors submit invoices to the **Marketplace** database. Each record includes part numbers, unit prices, taxes, extra charges, and PO references.

2. **ActivePieces detects new invoices**  
   A scheduled **ActivePieces** flow (runs every 10 minutes) fetches newly created invoices.

3. **Check PO lock status**  
   ActivePieces verifies that the PO is **unlocked** (no previous invoices waiting in the queue for RPA entry). This prevents duplicate or overlapping automation runs.

4. **Invoice Automation API call**  
   For each unlocked PO, ActivePieces calls the **Invoice Automation API**.

5. **API validation and response**  
   - The API validates the invoice against its PO in **Sampro**.  
   - If all checks pass, it returns a structured **JSON payload** and HTTP **200** (`status = "Ready_to_process"`).  
   - If validation fails, it returns **400** or **404**, including error details explaining the failure reason.

6. **ActivePieces saves the output**  
   The JSON response is stored in the **`processscheduler`** table, which acts as a master queue and audit log for all invoices and statuses (`ready_to_process`, `manual_review`, `bad_invoice`, etc.).

7. **KPI Invoice Automation UI**  
   The **KPI Dashboard** fetches data from `processscheduler` and displays invoices in real time.  
   The AP team can review and trigger an email to the **RPA bot** for invoices marked `Ready_to_process`.  
   The email content contains the JSON payload the bot needs to enter the invoice in **Sampro**.

8. **RPA Bot workflow**  
   The **RPA bot** polls its email inbox for invoices sent by the AP team.  
   Upon receiving the JSON payload, it automatically creates the invoice in **Sampro ERP**.  
   Once complete, the bot calls one of the API’s success or failure endpoints, updating the invoice’s status in the `processscheduler` table.  
   *(All controller routes are defined in the `controllers/` directory of this repository.)*

---

## 💡 Tips

- Documentation for **ActivePieces** is available in Notion.  
- ActivePieces uses this API to validate whether an invoice is **eligible** for entry into Sampro — this is the endpoint’s primary purpose.  
- For the full end-to-end architecture, refer to **ActivePieces documentation** in Notion.

---




## Development
1. ```python3 -m venv .venv``` creates a virtual env named .venv
2. ```source .venv/bin/activate``` activates venv
3. ```pip install -r requirements.txt``` installs deps
4. ```uvicorn app2:app --reload --port 8080``` starts the app on port 8080. 8000 already taken.

## Production Environment Setups
1. ```python3 -m venv .venv``` creates a virtual env named .venv
2. ```source .venv/bin/activate``` activates venv
3. ```pip install -r requirements.txt``` installs deps
4. Create Gunicorn service ```sudo nano /etc/systemd/system/invoice_automation.service``` \
    **Update content to this**
    ```
    [Unit]
    Description=Gunicorn instance for FastAPI invoice_automation
    After=network.target

    [Service]
    User=ubuntu
    Group=www-data
    WorkingDirectory=/home/ubuntu/invoice_automation
    Environment="PATH=/home/ubuntu/invoice_automation/.venv/bin"
    ExecStart=/home/ubuntu/invoice_automation/.venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker app2>

    [Install]
    WantedBy=multi-user.target
    ```
5. Execute these commands
    ```
    sudo systemctl daemon-reload
    sudo systemctl enable invoice_automation
    sudo systemctl start invoice_automation
    sudo systemctl status invoice_automation
    ```
6. Configure Nginx as Reverse Proxy
    ```
    sudo nano /etc/nginx/sites-available/invoice_automation
    ```
    Update Content
    ```
    server {
        server_name invoice-automation.chatdnas.com;

        location / {
                    proxy_pass http://127.0.0.1:8080;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```
7. Enable Nginx site
    ```
    sudo ln -s /etc/nginx/sites-available/invoice_automation /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl reload nginx
    ```
8. Enabled HTTPS
    ```bash
    sudo apt install certbot python3-certbot-nginx -y
    sudo certbot --nginx -d invoice_automation.chatdnas.com # this takes care of auto renewal
    ```
