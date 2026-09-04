"""Email notifications when a confessional is ready (Gmail API via OAuth)."""

import base64
import html
import re
from email import policy
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from google_auth import load_credentials

_EMAIL_POLICY = policy.default.clone(max_line_length=0)


def notifications_enabled(cfg: dict) -> bool:
    regular = cfg.get("notification_emails") or []
    production = cfg.get("production_notification_emails") or []
    return bool(regular or production)


def _is_production_contestant(contestant: str, cfg: dict) -> bool:
    names = cfg.get("production_contestant_names") or ["Production"]
    name = (contestant or "").strip().lower()
    return name in {n.strip().lower() for n in names if n.strip()}


def notification_recipients(cfg: dict, contestant: str) -> list[str]:
    """Pick email list based on contestant (e.g. Production vs players)."""
    if _is_production_contestant(contestant, cfg):
        emails = cfg.get("production_notification_emails") or []
        if emails:
            return list(emails)
    return list(cfg.get("notification_emails") or [])


def _gmail_service(cfg: dict):
    creds = load_credentials(cfg)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _normalize_copy_line(text: str) -> str:
    """Single-line copy text — no internal line breaks."""
    return re.sub(r"\s+", " ", text).strip()


def send_confessional_notification(
    cfg: dict,
    *,
    contestant: str,
    whatsapp_message: str,
    note: str = "",
    transcript_md_link: str = "",
    confessional_id: str = "",
):
    recipients = notification_recipients(cfg, contestant)
    if not recipients or not whatsapp_message:
        return

    name = contestant or "Unknown"
    subject = f"New confessional from {name}"
    copy_line = _normalize_copy_line(whatsapp_message)

    plain_lines = [
        "Copy the line below into WhatsApp:",
        "",
        copy_line,
        "",
    ]
    if note.strip():
        plain_lines.extend([f"Note: {note.strip()}", ""])
    if transcript_md_link:
        plain_lines.extend([f"Transcript: {transcript_md_link}", ""])
    if confessional_id:
        plain_lines.extend([f"Confessional ID: {confessional_id}", ""])
    plain_body = "\n".join(plain_lines).strip() + "\n"

    escaped = html.escape(copy_line)
    html_parts = [
        "<p>Copy the line below into WhatsApp:</p>",
        (
            '<div style="background:#f4f4f4;padding:12px;font-family:monospace;'
            f'font-size:13px;white-space:nowrap;overflow-x:auto;">{escaped}</div>'
        ),
    ]
    if note.strip():
        html_parts.append(f"<p><strong>Note:</strong> {html.escape(note.strip())}</p>")
    if transcript_md_link:
        html_parts.append(
            f'<p><strong>Transcript:</strong> '
            f'<a href="{html.escape(transcript_md_link)}">{html.escape(transcript_md_link)}</a></p>'
        )
    if confessional_id:
        html_parts.append(
            f"<p><strong>Confessional ID:</strong> {html.escape(confessional_id)}</p>"
        )
    html_body = "\n".join(html_parts)

    message = MIMEMultipart("alternative", policy=_EMAIL_POLICY)
    message.attach(MIMEText(plain_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))
    message["to"] = ", ".join(recipients)
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    _gmail_service(cfg).users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()


def send_daily_summary_notification(
    cfg: dict,
    *,
    date_str: str,
    summary: str,
    log_link: str = "",
):
    """Email daily summary to the main producer list (notification_emails)."""
    recipients = list(cfg.get("notification_emails") or [])
    if not recipients:
        return

    subject = f"Daily confessional summary — {date_str}"
    plain_lines = [summary.strip(), ""]
    if log_link:
        plain_lines.extend([f"Full log: {log_link}", ""])
    plain_body = "\n".join(plain_lines).strip() + "\n"

    html_parts = [f"<pre style='white-space:pre-wrap;font-family:inherit'>{html.escape(summary.strip())}</pre>"]
    if log_link:
        html_parts.append(
            f'<p><a href="{html.escape(log_link)}">View full daily log on Drive</a></p>'
        )
    html_body = "\n".join(html_parts)

    message = MIMEMultipart("alternative", policy=_EMAIL_POLICY)
    message.attach(MIMEText(plain_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))
    message["to"] = ", ".join(recipients)
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    _gmail_service(cfg).users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()
