# Invoice Automation Bot
📘 Overview

This Invoice Automation API is a backend service designed to automate the invoice-to-PurchaseOrder  validation and entry process for vendor invoices received from  marketplaces(database which vendors input their invoices).
Traditionally, the Accounts Payable (AP) department manually compares each incoming invoice with its corresponding Purchase Order (PO) in Sampro, checking part numbers, prices, quantities, and ensuring that the invoice hasn’t already been processed. This manual workflow is time-consuming, error-prone, and a bottleneck in the invoice lifecycle.

The system replaces that manual verification process with a fully automated pipeline that performs all validation checks programmatically and prepares the data for direct ingestion by an RPA (Robotic Process Automation) bot. Once an invoice passes all validations, it is automatically packaged into a structured JSON payload containing all the details required to create the invoice in Sampro by the RPA Bot. All the json payloads are store in the processscheduler table-stores every output this endpoint produces. This allows the RPA bot to enter invoices without human intervention, while ensuring all business rules are consistently enforced.

In essence, the system acts as an intelligent pre-processor between marketplace data and the ERP system — automatically selecting , validating, invoices before they reach Sampro. The result is a dramatic reduction in AP workload, improved data accuracy, and faster processing turnaround.
At the moment, this API is configured to only allow invoices whose items have the exact same prices as their corresponding PO items.--bussines rules can be found under service/validation invoicerules.py

Key Features

Automated PO Matching: Locates the correct Purchase Order in sampro  for each invoice using vendor and item identifiers.

Comprehensive Validation Engine: Applies a full suite of business logic checks — price, quantity, part number, duplication, and balance validations.

RPA-Ready JSON Output: Produces structured payloads that allow RPA bots to enter invoices directly into Sampro without any additional parsing.

Audit & Logging: Every validation and decision is logged, enabling traceability and auditability for compliance and financial review.

Seamless Integration: Built with modular connectors for SQL Server (Sampro), MySQL (Marketplace + ProcessScheduler), and API endpoints to integrate with external systems.

Business Impact

Reduced Manual Processing: 80–90% of AP workload automated.

Improved Accuracy: Eliminates human data-entry errors and duplicate invoices.

Faster Cycle Times: Valid invoices are ready for posting in minutes.

Transparent Operations: All invoice outcomes (bad_invoice, early_invoice,manual_review,Ready_to_proccess etc.) are logged in a processscheduler table  using Activepieces as the main flow Orchestrator.
Tips:
 (ActivePieces) docs can be found in notion. Active pieces uses this Endpoint to validate if an invoice is elegible to be input into Sampro.This is the sole function of this Api Endpoint.To Get a better understanding of how the whole flow works check ActivePieces docs in Notion.




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