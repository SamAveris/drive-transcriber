"""
Thin wrapper around the Google Drive API v3 for the transcriber.

Uses a service account (not interactive OAuth) so it can run unattended
on a schedule. Share your source/output Drive folders with the service
account's client_email (found inside the JSON key file) before running.

"Already processed" state lives on the file itself, as a Drive custom
property (appProperties). This means the script has no local state to
lose, and works the same whether you run it on a cron'd VM or as a
stateless Cloud Function invocation.
"""

import io
import os
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]

PROP_KEY = "transcript_status"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


def get_drive_service(service_account_file: str):
    creds = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


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
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def download_file(service, file_id: str, dest_path: str):
    request = service.files().get_media(fileId=file_id)
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
    resp = service.files().list(q=query, fields="files(id, name)", pageSize=1).execute()
    existing = resp.get("files", [])
    if existing:
        return existing[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(body=metadata, fields="id").execute()
    return created["id"]


def upload_transcript(service, local_path: str, filename: str, parent_id: str) -> str:
    metadata = {"name": filename, "parents": [parent_id]}
    media = MediaFileUpload(local_path, mimetype="text/plain", resumable=False)
    created = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return created["id"]


def mark_status(service, file_id: str, status: str, extra_props: Optional[dict] = None):
    props = {PROP_KEY: status}
    if extra_props:
        props.update(extra_props)
    service.files().update(fileId=file_id, body={"appProperties": props}).execute()
