# Invoice Automation Bot
📘 Overview

The Invoice Automation API is a backend service designed to automate the invoice-to–Purchase Order (PO) validation, comparison, and entry process for vendor invoices received from marketplaces (databases where vendors upload their invoices).

Traditionally, the Accounts Payable (AP) department manually compares each incoming invoice with its corresponding PO in Sampro, checking part numbers, prices, quantities, and ensuring that the invoice hasn’t already been processed. This manual workflow is time-consuming, error-prone, and a major bottleneck in the invoice lifecycle.

The system replaces that manual verification process with a fully automated pipeline that performs all validation checks programmatically and prepares the data for direct ingestion by an RPA (Robotic Process Automation) bot. Once an invoice passes all validations, it is automatically packaged into a structured JSON payload containing all the details required for the RPA bot to create the invoice in Sampro.

All JSON payloads are stored in the processscheduler table, which records every output this endpoint produces. This allows the RPA bot to enter invoices without human intervention while ensuring all business rules are consistently enforced.

In essence, the system acts as an intelligent pre-processor between marketplace data and the ERP system — automatically selecting and validating invoices before they reach Sampro.
The result is a dramatic reduction in AP workload, improved data accuracy, and faster processing turnaround.

Note:
At the moment, this API is configured to only allow invoices whose items have the exact same prices as their corresponding PO items.
All business rules can be found in:
service/validation/invoicerules.py

⚙️ Key Features

Automated PO Matching – Locates the correct Purchase Order in Sampro for each invoice using vendor and item identifiers.

Comprehensive Validation Engine – Applies a full suite of business logic checks: price, quantity, part number, duplication, and balance validations.

RPA-Ready JSON Output – Produces structured payloads that allow RPA bots to enter invoices directly into Sampro without additional parsing.

Audit & Logging – Every validation and decision is logged, enabling traceability and auditability for compliance and financial review.

Seamless Integration – Built with modular connectors for SQL Server (Sampro), MySQL (Marketplace + ProcessScheduler), and REST API endpoints to integrate with external systems.

 Business Impact

Reduced Manual Processing – Automates 80–90% of AP workload.

Improved Accuracy – Eliminates human data-entry errors and duplicate invoices.

Faster Cycle Times – Valid invoices are ready for posting in minutes.

Transparent Operations – All invoice outcomes (bad_invoice, early_invoice, manual_review, ready_to_process, etc.) are logged in the processscheduler table.
ActivePieces is used as the main flow orchestrator.

 Tips

Documentation for ActivePieces can be found in Notion.

ActivePieces uses this API endpoint to validate whether an invoice is eligible to be entered into Sampro — this is the sole function of the endpoint.

To understand the end-to-end workflow, refer to the ActivePieces documentation in Notion.




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
