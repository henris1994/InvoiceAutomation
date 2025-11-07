import requests
from utils.utilfunctions import _get_env
def send_email(emailcontent: str):
    # === STEP 1: CONFIGURATION from environment ===
    tenant_id    = _get_env("AZURE_TENANT_ID")
    client_id    = _get_env("AZURE_CLIENT_ID")
    client_secret= _get_env("AZURE_CLIENT_SECRET")
    user_email   = _get_env("AZURE_GRAPH_USER_EMAIL")  # mailbox to send-as

    # === STEP 2: AUTHENTICATE AND GET TOKEN ===
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default"
    }

    try:
        token_response = requests.post(token_url, data=token_data, timeout=20)
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]
        print("Authenticated successfully.")
    except Exception as e:
        raise RuntimeError(f"Failed to authenticate: {e}")

    # === STEP 3: SET AUTH HEADER ===
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # === STEP 4: BUILD EMAIL PAYLOAD ===
    email_payload = {
        "message": {
            "subject": "INV19",
            "body": {"contentType": "Text", "content": emailcontent},
            "toRecipients": [{"emailAddress": {"address": user_email}}],  # change if needed
        },
        "saveToSentItems": "true",
    }

    # === STEP 5: SEND THE EMAIL ===
    send_url = f"https://graph.microsoft.com/v1.0/users/{user_email}/sendMail"
    try:
        send_response = requests.post(send_url, headers=headers, json=email_payload, timeout=20)
        if send_response.status_code == 202:
            print("Email sent successfully.")
        else:
            raise RuntimeError(f"Failed to send email: {send_response.status_code} - {send_response.text}")
    except Exception as e:
        raise RuntimeError(f"Error sending email: {e}")