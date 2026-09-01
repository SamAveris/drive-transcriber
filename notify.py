"""Email notifications when a confessional is ready (Gmail API via OAuth)."""

import base64
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from google_auth import load_credentials


def notifications_enabled(cfg: dict) -> bool:
    emails = cfg.get("notification_emails") or []
    return bool(emails)


def _gmail_service(cfg: dict):
    creds = load_credentials(cfg)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_confessional_notification(
    cfg: dict,
    *,
    contestant: str,
    whatsapp_message: str,
    note: str = "",
    transcript_md_link: str = "",
    confessional_id: str = "",
):
    recipients = cfg.get("notification_emails") or []
    if not recipients or not whatsapp_message:
        return

    name = contestant or "Unknown"
    subject = f"New confessional from {name}"

    lines = [
        "Copy the line below into WhatsApp:",
        "",
        whatsapp_message,
        "",
    ]
    if note.strip():
        lines.extend([f"Note: {note.strip()}", ""])
    if transcript_md_link:
        lines.extend([f"Transcript: {transcript_md_link}", ""])
    if confessional_id:
        lines.extend([f"Confessional ID: {confessional_id}", ""])

    body = "\n".join(lines).strip() + "\n"

    message = MIMEText(body)
    message["to"] = ", ".join(recipients)
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    _gmail_service(cfg).users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()
