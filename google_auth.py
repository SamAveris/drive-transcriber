"""Shared Google OAuth / service-account credentials for Drive and Sheets."""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow

# Drive + Sheets + Gmail send (re-run `python main.py --auth` after scope changes).
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.send",
]


def authorize_oauth(credentials_file: str, token_file: str):
    """Run the browser OAuth flow and save token_file. Call once during setup."""
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_file, "w") as f:
        f.write(creds.to_json())


def load_credentials(cfg: dict) -> Credentials:
    auth = cfg.get("auth", "oauth")
    if auth == "service_account":
        return service_account.Credentials.from_service_account_file(
            cfg["service_account_file"], scopes=SCOPES
        )
    return _load_oauth_credentials(cfg["credentials_file"], cfg["token_file"])


def _load_oauth_credentials(credentials_file: str, token_file: str) -> Credentials:
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    if creds and creds.valid:
        return creds
    raise RuntimeError(
        f"No valid OAuth token in {token_file}. Run: python main.py --auth"
    )
