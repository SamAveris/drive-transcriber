"""
Thin wrapper around the Google Drive API v3 for the transcriber.

Uses OAuth (your Google account) by default so transcripts can be uploaded to
personal Drive -- service accounts cannot create files there. Service account
auth remains available for Google Workspace shared-drive setups.

"Already processed" state lives on the file itself, as a Drive custom
property (appProperties). This means the script has no local state to lose.
"""

import io
import re
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

from google_auth import authorize_oauth, load_credentials

__all__ = [
    "authorize_oauth",
    "PROP_KEY",
    "STATUS_DONE",
    "STATUS_FAILED",
    "get_drive_service",
    "list_unprocessed_videos",
    "download_file",
    "find_or_create_folder",
    "upload_transcript",
    "update_file_content",
    "file_view_link",
    "file_preview_embed_link",
    "ensure_anyone_with_link_can_view",
    "mark_status",
    "clear_status",
    "ANALYSIS_PROP_KEY",
    "ANALYSIS_STATUS_DONE",
    "get_file_metadata",
    "file_id_from_link",
    "read_file_text",
    "mark_analysis_status",
    "clear_analysis_status",
    "analysis_already_done",
]

PROP_KEY = "transcript_status"
ANALYSIS_PROP_KEY = "analysis_status"
ANALYSIS_STATUS_DONE = "done"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

# Needed when accessing folders shared into the account from another user.
_DRIVE_KWARGS = {"supportsAllDrives": True}
_LIST_KWARGS = {"supportsAllDrives": True, "includeItemsFromAllDrives": True}


def get_drive_service(cfg: dict):
    creds = load_credentials(cfg)
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
            fields="nextPageToken, files(id, name, mimeType, size, createdTime, appProperties)",
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


def upload_transcript(
    service,
    local_path: str,
    filename: str,
    parent_id: str,
    app_properties: Optional[dict] = None,
) -> str:
    metadata: dict = {"name": filename, "parents": [parent_id]}
    if app_properties:
        metadata["appProperties"] = {
            k: str(v) for k, v in app_properties.items() if v is not None and str(v)
        }
    media = MediaFileUpload(local_path, mimetype="text/plain", resumable=False)
    created = service.files().create(
        body=metadata, media_body=media, fields="id", **_DRIVE_KWARGS
    ).execute()
    return created["id"]


def update_file_content(service, file_id: str, local_path: str):
    """Replace an existing Drive file's content."""
    media = MediaFileUpload(local_path, mimetype="text/plain", resumable=False)
    service.files().update(
        fileId=file_id, media_body=media, **_DRIVE_KWARGS
    ).execute()


def file_view_link(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def file_preview_embed_link(file_id: str) -> str:
    """Google Drive embed URL for iframe video preview."""
    if not file_id:
        return ""
    return f"https://drive.google.com/file/d/{file_id}/preview"


def ensure_anyone_with_link_can_view(service, file_id: str):
    """Allow WhatsApp viewers to open the link without signing in."""
    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            **_DRIVE_KWARGS,
        ).execute()
    except HttpError as err:
        if err.resp.status not in (400, 403, 409):
            raise


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


def get_file_metadata(service, file_id: str) -> dict:
    return (
        service.files()
        .get(
            fileId=file_id,
            fields="id, name, mimeType, size, createdTime, appProperties",
            **_DRIVE_KWARGS,
        )
        .execute()
    )


def file_id_from_link(link: str) -> str:
    if not link:
        return ""
    match = re.search(r"/file/d/([^/]+)", link)
    return match.group(1) if match else ""


def read_file_text(service, file_id: str) -> str:
    request = service.files().get_media(fileId=file_id, **_DRIVE_KWARGS)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8", errors="replace")


def analysis_already_done(file_info: dict) -> bool:
    props = file_info.get("appProperties") or {}
    return props.get(ANALYSIS_PROP_KEY) == ANALYSIS_STATUS_DONE


def mark_analysis_status(service, file_id: str, status: str = ANALYSIS_STATUS_DONE):
    service.files().update(
        fileId=file_id,
        body={"appProperties": {ANALYSIS_PROP_KEY: status}},
        **_DRIVE_KWARGS,
    ).execute()


def clear_analysis_status(service, file_id: str):
    service.files().update(
        fileId=file_id,
        body={"appProperties": {ANALYSIS_PROP_KEY: None}},
        **_DRIVE_KWARGS,
    ).execute()
