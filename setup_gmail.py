"""
setup_gmail.py — Run this ONCE to authorise Gmail access.
It opens a browser, asks you to sign in, then saves credentials/token.json.
"""

from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import json, os

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]

ROOT       = Path(__file__).parent
CREDS_DIR  = ROOT / "credentials"
TOKEN_FILE = CREDS_DIR / "token.json"
CLIENT_FILE = CREDS_DIR / "client_secret.json"


def main():
    CREDS_DIR.mkdir(exist_ok=True)

    if not CLIENT_FILE.exists():
        print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SETUP: You need a Google OAuth client secret first.

  1. Go to https://console.cloud.google.com/
  2. Create a new project (e.g. "hourglass-agent")
  3. Enable the Gmail API
  4. Go to APIs & Services → Credentials
  5. Create OAuth 2.0 Client ID → Desktop app
  6. Download JSON → save as:
         credentials/client_secret.json
  7. Re-run this script
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
        return

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    print(f"✅  Authorised! Token saved to {TOKEN_FILE}")
    print("    You can now run:  python src/agent.py")


if __name__ == "__main__":
    main()
