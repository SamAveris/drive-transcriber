"""Append daily summaries to a single Drive markdown log."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime

from drive_client import (
    file_view_link,
    find_or_create_folder,
    get_drive_service,
    read_file_text,
    update_file_content,
    upload_transcript,
)

CACHE_FILENAME = "daily_summaries_drive.json"


def _cache_path(cfg: dict) -> str:
    base = os.path.dirname(os.path.abspath(cfg.get("_config_path", "config.json")))
    return os.path.join(base, CACHE_FILENAME)


def _analysis_folder_id(cfg: dict, service) -> str:
    transcripts_id = find_or_create_folder(service, "Transcripts", cfg["output_folder_id"])
    return find_or_create_folder(service, "Analysis", transcripts_id)


def _load_cached_file_id(cfg: dict) -> str:
    path = _cache_path(cfg)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("file_id") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def _save_cached_file_id(cfg: dict, file_id: str) -> None:
    with open(_cache_path(cfg), "w", encoding="utf-8") as f:
        json.dump({"file_id": file_id}, f)


def append_daily_summary_section(
    cfg: dict,
    *,
    date_str: str,
    summary: str,
    log_filename: str,
) -> str:
    """Append a dated section to the Drive log file. Returns view link."""
    service = get_drive_service(cfg)
    folder_id = _analysis_folder_id(cfg, service)
    file_id = _load_cached_file_id(cfg)
    section = f"## {date_str}\n\n{summary.strip()}\n\n---\n"

    existing = ""
    if file_id:
        try:
            existing = read_file_text(service, file_id)
        except Exception:
            file_id = ""

    content = (existing.rstrip() + "\n\n" if existing.strip() else "") + section
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if file_id:
            update_file_content(service, file_id, tmp_path)
        else:
            file_id = upload_transcript(service, tmp_path, log_filename, folder_id)
            _save_cached_file_id(cfg, file_id)
    finally:
        os.unlink(tmp_path)

    return file_view_link(file_id)
