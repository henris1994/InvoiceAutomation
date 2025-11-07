# Invoice Automation API
📘 Overview

The Invoice Automation API is a backend service designed to automate the invoice-to–Purchase Order (PO) validation, comparison, and entry process for vendor invoices received from marketplaces (databases where vendors upload their invoices).

Traditionally, the Accounts Payable (AP) department manually compares each incoming invoice with its corresponding PO in Sampro, checking part numbers, prices, quantities, and ensuring that the invoice hasn’t already been processed. This manual workflow is time-consuming, error-prone, and a major bottleneck in the invoice lifecycle.

The system replaces that manual verification process with a fully automated pipeline that performs all validation checks programmatically and prepares the data for direct ingestion by an RPA (Robotic Process Automation) bot. Once an invoice passes all validations, it is automatically packaged into a structured JSON payload containing all the details required for the RPA bot to create the invoice in Sampro.

All JSON payloads are stored in the processscheduler table, which records every output this endpoint produces. This allows the RPA bot to enter invoices without human intervention while ensuring all business rules are consistently enforced.
The result is a dramatic reduction in AP workload, improved data accuracy, and faster processing turnaround.

Note:
At the moment, this API is configured to only allow invoices whose items have the exact same prices as their corresponding PO items.
All business rules can be found in:
service/validation/invoicerules.py

🧩 Flow Explanation
1.Vendors upload invoices-
Vendors submit their invoices to the Marketplace portal/database. Each record contains item part numbers, unit_prices,taxes,extracharges and PO references etc.

2.ActivePieces detects new invoices
A scheduled flow every 10 minutes (ActivePieces) pulls the newly created invoices.

3.Check PO lock status
Before calling the Invoice Automation API, ActivePieces verifies that the corresponding Purchase Order (PO) is unlocked — meaning there are no previous invoices still queued for RPA entry. This prevents duplicate or overlapping processing.

4.Invoice Automation API
Once a PO is confirmed available, ActivePieces calls the Invoice Automation Endpoint.
The API compares the invoice from marketplace against its PO in Sampro, runs all validation checks, and returns a structured JSON payload describing whether the invoice is valid and ready for automation.
If the API response is 200 , invoice passed all validations gets marked with status='Ready_to_process', otherwise API Response will be 400/404 with corresponding fields explaining the failure reason.

5.Activepieces saves the output
The Activepieces system receives this JSON response and stores it in the processscheduler table, which acts as the master log and queue of all validation results (ready_to_process, manual_review, bad_invoice, etc.).

6.KPI Invoice Automation UI
The front-end KPI dashboard fetches results from the processscheduler table and displays them to users in real time — allowing AP staff to monitor which invoices are valid, pending, or rejected.
In the kpi AP team can send an email To the Rpa bot for the invoices that have status Ready_to_process(email content is the json object the RPA BOT needs to input the invoice in sampro.

7.RPA Bot workflow
Separately, the RPA bot polls the email for invoices sent by the AP team.
It uses the JSON payload to automatically create the corresponding invoice in Sampro ERP.\
After completion Rpa bot  hits one of the Api-s success or failure.
Those Api routes and all others can be found on the controllers of this repository.

Tips:

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
