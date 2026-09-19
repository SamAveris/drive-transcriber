"""Quick notification setup diagnostic (no secrets printed)."""
import json
import os
import sys

from catalog import catalog_enabled
from google_auth import SCOPES
from main import load_config
from notify import notification_recipients, notifications_enabled


def main() -> int:
    cfg_path = os.environ.get("TRANSCRIBER_CONFIG", "config.json")
    if not os.path.isfile(cfg_path):
        print(f"FAIL: {cfg_path} not found")
        return 1

    cfg = load_config(cfg_path)
    print(f"notifications_enabled: {notifications_enabled(cfg)}")
    print(f"notification_emails: {len(cfg.get('notification_emails') or [])} address(es)")
    print(f"production_notification_emails: {len(cfg.get('production_notification_emails') or [])} address(es)")
    print(f"catalog_enabled: {catalog_enabled(cfg)}")
    print(f"recipients (player): {len(notification_recipients(cfg, 'Alice'))}")
    print(f"recipients (Production): {len(notification_recipients(cfg, 'Production'))}")

    token_file = cfg.get("token_file", "token.json")
    if not os.path.isfile(token_file):
        print(f"FAIL: {token_file} missing — run: python main.py --auth")
        return 1

    token = json.load(open(token_file, encoding="utf-8"))
    scopes = token.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    has_gmail = "https://www.googleapis.com/auth/gmail.send" in scopes
    print(f"gmail.send in token: {has_gmail}")
    if not has_gmail:
        print("FIX: delete token.json and run: python main.py --auth (enable Gmail API in Cloud Console)")
        return 1

    try:
        from google_auth import load_credentials
        from googleapiclient.discovery import build

        creds = load_credentials(cfg)
        if not creds.valid:
            print("FAIL: OAuth token invalid or expired")
            return 1
        build("gmail", "v1", credentials=creds, cache_discovery=False)
        print("Gmail API client: OK")
    except Exception as err:
        print(f"Gmail API client: FAIL — {err}")
        if "invalid_grant" in str(err).lower():
            print("FIX: delete token.json, then run: python main.py --auth")
        return 1

    print("Config looks OK for notifications. If emails still missing, check transcriber.log for 'email notification failed'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
