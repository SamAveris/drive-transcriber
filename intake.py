"""Match Google Form responses (linked Sheet tab) to Drive inbox files."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_DRIVE_ID_PATTERNS = (
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
    re.compile(r"/file/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"/open\?id=([a-zA-Z0-9_-]+)"),
)


@dataclass
class FormMatch:
    contestant: str
    note: str
    submitted_at: str
    form_timestamp: str
    row_index: int | None = None


def extract_drive_file_id(cell: str) -> str | None:
    if not cell:
        return None
    for pattern in _DRIVE_ID_PATTERNS:
        match = pattern.search(cell)
        if match:
            return match.group(1)
    return None


def _column_index(headers: list[str], name: str) -> int | None:
    if not name:
        return None
    target = name.strip().lower()
    for i, header in enumerate(headers):
        if header.strip().lower() == target:
            return i
    return None


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in (
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%d/%m/%Y %H:%M",
    ):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _filename_from_file_cell(cell: str) -> str:
    if not cell:
        return ""
    cell = cell.strip()
    if "drive.google.com" in cell:
        part = cell.rstrip("/").split("/")[-1]
        return part.split("?")[0] or cell
    return cell


def _filenames_match(form_name: str, drive_name: str) -> bool:
    if not form_name or not drive_name:
        return False
    form_name = form_name.strip().lower()
    drive_name = drive_name.strip().lower()
    return form_name == drive_name or form_name in drive_name or drive_name in form_name


def load_form_responses(
    sheets_service,
    spreadsheet_id: str,
    tab: str,
    contestant_column: str,
    note_column: str,
    file_column: str,
    timestamp_column: str = "Timestamp",
) -> list[dict[str, Any]]:
    """Read form response rows from a Sheet tab."""
    range_name = f"'{tab}'!A:Z" if " " in tab else f"{tab}!A:Z"
    result = (
        sheets_service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )
    values = result.get("values", [])
    if len(values) < 2:
        return []

    headers = [h.strip().lower() for h in values[0]]
    ts_idx = _column_index(headers, timestamp_column)
    contestant_idx = _column_index(headers, contestant_column)
    note_idx = _column_index(headers, note_column)
    file_idx = _column_index(headers, file_column)

    hyperlinks: list[str] = []
    try:
        grid = (
            sheets_service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                ranges=[range_name],
                fields="sheets.data.rowData.values.hyperlink",
            )
            .execute()
        )
        row_data = grid["sheets"][0]["data"][0].get("rowData", [])
        for row_idx, _row in enumerate(values[1:], start=1):
            link = ""
            if row_idx < len(row_data):
                cells = row_data[row_idx].get("values", [])
                if file_idx is not None and file_idx < len(cells):
                    link = cells[file_idx].get("hyperlink", "") or ""
            hyperlinks.append(link)
    except Exception:
        hyperlinks = [""] * (len(values) - 1)

    rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(values[1:]):
        file_cell = _cell(row, file_idx)
        hyperlink = hyperlinks[row_index] if row_index < len(hyperlinks) else ""
        file_id = extract_drive_file_id(file_cell) or extract_drive_file_id(hyperlink)
        rows.append(
            {
                "row_index": row_index,
                "file_id": file_id,
                "filename": _filename_from_file_cell(file_cell) or _filename_from_file_cell(hyperlink),
                "contestant": _cell(row, contestant_idx),
                "note": _cell(row, note_idx),
                "form_timestamp": _cell(row, ts_idx),
            }
        )
    return rows


def match_file_to_form(
    file_info: dict,
    form_rows: list[dict[str, Any]],
    match_window_minutes: int = 120,
    used_row_indices: set[int] | None = None,
) -> FormMatch | None:
    """Find the form response that belongs to this Drive file."""
    used = used_row_indices or set()
    file_id = file_info["id"]
    file_name = file_info.get("name", "")
    created_raw = file_info.get("createdTime", "")

    for row in form_rows:
        idx = row.get("row_index")
        if idx in used:
            continue
        if row.get("file_id") and row["file_id"] == file_id:
            return _form_match_from_row(row, created_raw)

    for row in form_rows:
        idx = row.get("row_index")
        if idx in used:
            continue
        if _filenames_match(row.get("filename", ""), file_name):
            return _form_match_from_row(row, created_raw)

    created_dt = _parse_drive_time(created_raw)
    if not created_dt:
        return None

    created_cmp = _to_naive_local(created_dt)
    best_row = None
    best_delta = None
    for row in form_rows:
        idx = row.get("row_index")
        if idx in used:
            continue
        if row.get("file_id"):
            continue
        form_dt = _parse_timestamp(row.get("form_timestamp", ""))
        if not form_dt:
            continue
        form_cmp = _to_naive_local(form_dt)
        delta = abs((created_cmp - form_cmp).total_seconds())
        if delta > match_window_minutes * 60:
            continue
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_row = row

    if best_row:
        return _form_match_from_row(best_row, created_raw)

    return None


def _form_match_from_row(row: dict[str, Any], created_raw: str) -> FormMatch:
    submitted = row.get("form_timestamp") or _format_drive_time(created_raw)
    return FormMatch(
        contestant=row.get("contestant", ""),
        note=row.get("note", ""),
        submitted_at=submitted,
        form_timestamp=row.get("form_timestamp", ""),
        row_index=row.get("row_index"),
    )


def _to_naive_local(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def _parse_drive_time(iso_value: str) -> datetime | None:
    if not iso_value:
        return None
    try:
        if iso_value.endswith("Z"):
            iso_value = iso_value[:-1] + "+00:00"
        return datetime.fromisoformat(iso_value)
    except ValueError:
        return None


def _format_drive_time(iso_value: str) -> str:
    dt = _parse_drive_time(iso_value)
    if not dt:
        return iso_value
    local = dt.astimezone() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def guess_contestant_from_filename(filename: str, known_names: list[str]) -> str:
    """Last-resort: match a known contestant name appearing in the filename."""
    lower = filename.lower()
    for name in known_names:
        if name and name.lower() in lower:
            return name
    return ""
