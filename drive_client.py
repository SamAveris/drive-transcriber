"""
Thin wrapper around the Google Drive API v3 for the transcriber.

Uses OAuth (your Google account) by default so transcripts can be uploaded to
personal Drive -- service accounts cannot create files there. Service account
auth remains available for Google Workspace shared-drive setups.

"Already processed" state lives on the file itself, as a Drive custom
property (appProperties). This means the script has no local state to lose.
"""

import io
import os
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]

PROP_KEY = "transcript_status"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

# Needed when accessing folders shared into the account from another user.
_DRIVE_KWARGS = {"supportsAllDrives": True}
_LIST_KWARGS = {"supportsAllDrives": True, "includeItemsFromAllDrives": True}


def get_drive_service(cfg: dict):
    auth = cfg.get("auth", "oauth")
    if auth == "service_account":
        creds = service_account.Credentials.from_service_account_file(
            cfg["service_account_file"], scopes=SCOPES
        )
    else:
        creds = _load_oauth_credentials(
            cfg["credentials_file"], cfg["token_file"]
        )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def authorize_oauth(credentials_file: str, token_file: str):
    """Run the browser OAuth flow and save token_file. Call once during setup."""
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_file, "w") as f:
        f.write(creds.to_json())


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


def list_unprocessed_videos(service, folder_id: str, mime_prefixes, page_size: int):
    """Return video files in folder_id that don't yet have a transcript_status property."""
    mime_clause = " or ".join(f"mimeType contains '{p}'" for p in mime_prefixes)
    query = (
        f"'{folder_id}' in parents and trashed = false and ({mime_clause}) "
        f"and not appProperties has {{ key='{PROP_KEY}' and value='{STATUS_DONE}' }} "
        f"and not appProperties has {{ key='{PROP_KEY}' and value='{STATUS_FAILED}' }}"
    )
    files = []
    page_token = None
    while True:
        resp = service.files().list(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType, size, appProperties)",
            pageSize=page_size,
            pageToken=page_token,
            **_LIST_KWARGS,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def download_file(service, file_id: str, dest_path: str):
    request = service.files().get_media(fileId=file_id, **_DRIVE_KWARGS)
    with io.FileIO(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return dest_path


def find_or_create_folder(service, name: str, parent_id: str) -> str:
    query = (
        f"'{parent_id}' in parents and trashed = false "
        f"and mimeType = 'application/vnd.google-apps.folder' and name = '{name}'"
    )
    resp = service.files().list(
        q=query, fields="files(id, name)", pageSize=1, **_LIST_KWARGS
    ).execute()
    existing = resp.get("files", [])
    if existing:
        return existing[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(
        body=metadata, fields="id", **_DRIVE_KWARGS
    ).execute()
    return created["id"]


def upload_transcript(service, local_path: str, filename: str, parent_id: str) -> str:
    metadata = {"name": filename, "parents": [parent_id]}
    media = MediaFileUpload(local_path, mimetype="text/plain", resumable=False)
    created = service.files().create(
        body=metadata, media_body=media, fields="id", **_DRIVE_KWARGS
    ).execute()
    return created["id"]


def mark_status(service, file_id: str, status: str, extra_props: Optional[dict] = None):
    props = {PROP_KEY: status}
    if extra_props:
        props.update(extra_props)
    service.files().update(
        fileId=file_id, body={"appProperties": props}, **_DRIVE_KWARGS
    ).execute()


def clear_status(service, file_id: str):
    """Remove transcript_status so a file can be reprocessed."""
    service.files().update(
        fileId=file_id,
        body={"appProperties": {PROP_KEY: None}},
        **_DRIVE_KWARGS,
    ).execute()
