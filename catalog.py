"""Google Sheets production catalog for confessionals."""

from typing import Any

from googleapiclient.discovery import build

from google_auth import load_credentials
from media_info import format_duration

CATALOG_HEADERS = [
    "confessional_id",
    "drive_file_id",
    "filename",
    "contestant",
    "submitted_at",
    "duration",
    "status",
    "video_link",
    "transcript_md_link",
    "transcript_srt_link",
    "note",
    "whatsapp_message",
]

# Old header name before markdown output replaced plain text.
_LEGACY_TXT_HEADER = "transcript_txt_link"


def get_sheets_service(cfg: dict):
    creds = load_credentials(cfg)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def catalog_enabled(cfg: dict) -> bool:
    sheet_id = (cfg.get("catalog_sheet_id") or "").strip()
    if not sheet_id or sheet_id.startswith("PUT_YOUR"):
        return False
    return True


def _tab_range(tab: str, cell_range: str) -> str:
    if " " in tab or "'" in tab:
        return f"'{tab}'!{cell_range}"
    return f"{tab}!{cell_range}"


def ensure_catalog_tab(sheets_service, sheet_id: str, tab: str):
    """Create the catalog worksheet tab if it does not exist."""
    meta = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    for sheet in meta.get("sheets", []):
        if sheet["properties"]["title"] == tab:
            return
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
    ).execute()


def init_catalog_headers(sheets_service, sheet_id: str, tab: str = "Catalog"):
    ensure_catalog_tab(sheets_service, sheet_id, tab)
    sync_catalog_headers(sheets_service, sheet_id, tab)


def sync_catalog_headers(sheets_service, sheet_id: str, tab: str = "Catalog") -> list[str]:
    """Align header row with CATALOG_HEADERS; rename legacy transcript_txt_link."""
    ensure_catalog_tab(sheets_service, sheet_id, tab)
    values = _read_sheet(sheets_service, sheet_id, tab)
    if not values:
        sheets_service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=_tab_range(tab, "A1"),
            valueInputOption="RAW",
            body={"values": [CATALOG_HEADERS]},
        ).execute()
        return list(CATALOG_HEADERS)

    headers = list(values[0])
    changed = False

    for i, header in enumerate(headers):
        if header.strip().lower() == _LEGACY_TXT_HEADER.lower():
            headers[i] = "transcript_md_link"
            changed = True

    existing = _header_map(headers)
    for col in CATALOG_HEADERS:
        if col.lower() not in existing:
            headers.append(col)
            changed = True

    if changed:
        sheets_service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=_tab_range(tab, "A1"),
            valueInputOption="RAW",
            body={"values": [headers]},
        ).execute()

    return headers


def _read_sheet(sheets_service, sheet_id: str, tab: str) -> list[list[str]]:
    result = (
        sheets_service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=_tab_range(tab, "A:Z"))
        .execute()
    )
    return result.get("values", [])


def _header_map(headers: list[str]) -> dict[str, int]:
    return {h.strip().lower(): i for i, h in enumerate(headers)}


def _row_to_dict(headers: list[str], row: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for i, key in enumerate(headers):
        key = key.strip().lower()
        data[key] = row[i].strip() if i < len(row) else ""
    return data


def _build_row_values(headers: list[str], data: dict[str, Any]) -> list[str]:
    row = [""] * len(headers)
    for key, value in data.items():
        idx = _header_map(headers).get(key.strip().lower())
        if idx is not None:
            row[idx] = "" if value is None else str(value)
    return row


def build_whatsapp_message(contestant: str, submitted_at: str, video_link: str) -> str:
    name = contestant or "Unknown"
    date_part = ""
    if submitted_at:
        date_part = submitted_at.strip()[:10]
    if date_part:
        return f"New confessional from {name} ({date_part}): {video_link}"
    return f"New confessional from {name}: {video_link}"


def upsert_catalog_row(
    sheets_service,
    sheet_id: str,
    tab: str,
    row_data: dict[str, Any],
):
    """Insert or update a catalog row keyed by drive_file_id."""
    headers = sync_catalog_headers(sheets_service, sheet_id, tab)
    values = _read_sheet(sheets_service, sheet_id, tab)
    if not values:
        values = [headers]
    header_lookup = _header_map(headers)
    file_id_key = "drive_file_id"
    file_id = str(row_data.get(file_id_key, ""))
    if not file_id:
        raise ValueError("row_data must include drive_file_id")

    row_values = _build_row_values(headers, row_data)
    file_id_col = header_lookup.get(file_id_key)

    target_row = None
    if file_id_col is not None:
        for i, row in enumerate(values[1:], start=2):
            if file_id_col < len(row) and row[file_id_col].strip() == file_id:
                target_row = i
                break

    if target_row:
        sheets_service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=_tab_range(tab, f"A{target_row}"),
            valueInputOption="USER_ENTERED",
            body={"values": [row_values]},
        ).execute()
    else:
        sheets_service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=_tab_range(tab, "A1"),
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row_values]},
        ).execute()


def catalog_row_for_file(
    file_info: dict,
    *,
    status: str,
    confessional_id: str = "",
    video_link: str = "",
    transcript_md_link: str = "",
    transcript_srt_link: str = "",
    contestant: str = "",
    note: str = "",
    submitted_at: str = "",
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    submitted = submitted_at or file_info.get("createdTime", "")
    if "T" in submitted:
        submitted = submitted.replace("T", " ")[:16]

    row = {
        "confessional_id": confessional_id,
        "drive_file_id": file_info["id"],
        "filename": file_info.get("name", ""),
        "contestant": contestant,
        "submitted_at": submitted,
        "duration": format_duration(duration_seconds),
        "status": status,
        "video_link": video_link,
        "transcript_md_link": transcript_md_link,
        "transcript_srt_link": transcript_srt_link,
        "note": note,
        "whatsapp_message": "",
    }
    if video_link:
        row["whatsapp_message"] = build_whatsapp_message(
            contestant, submitted, video_link
        )
    return row
