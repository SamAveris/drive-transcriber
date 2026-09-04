"""Load transcript corpus from catalog + Drive for producer chat."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from catalog import catalog_enabled, get_sheets_service, list_catalog_rows
from drive_client import file_id_from_link, get_drive_service, read_file_text

SCOPE_ONE = "one"
SCOPE_ALL_COMPACT = "all_compact"
SCOPE_ALL_FULL = "all_full"

MAX_CORPUS_CHARS = 100_000


def _parse_submitted_at(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %H",
        "%m/%d/%Y",
    )
    for fmt in formats:
        for candidate in (text, text[:19], text[:16], text[:10]):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    if "T" in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")[:19])
        except ValueError:
            pass
    return None


def rows_in_last_hours(rows: list[dict[str, str]], hours: float = 24) -> list[dict[str, str]]:
    cutoff = datetime.now() - timedelta(hours=hours)
    matched: list[dict[str, str]] = []
    for row in rows:
        submitted = _parse_submitted_at(row.get("submitted_at", ""))
        if submitted is not None and submitted >= cutoff:
            matched.append(row)
    return matched


def load_catalog_rows(cfg: dict, *, status: str | None = "ready") -> list[dict[str, str]]:
    if not catalog_enabled(cfg):
        return []
    sheets = get_sheets_service(cfg)
    return list_catalog_rows(
        sheets,
        cfg["catalog_sheet_id"],
        cfg.get("catalog_tab", "Catalog"),
        status=status,
    )


def load_transcript_md(service, row: dict[str, str]) -> str:
    link = row.get("transcript_md_link", "")
    file_id = file_id_from_link(link)
    if not file_id:
        return ""
    return read_file_text(service, file_id)


def _row_preamble(row: dict[str, str]) -> str:
    parts = [
        f"confessional_id: {row.get('confessional_id', '')}",
        f"contestant: {row.get('contestant', '')}",
        f"submitted_at: {row.get('submitted_at', '')}",
        f"duration: {row.get('duration', '')}",
    ]
    note = row.get("note", "").strip()
    if note:
        parts.append(f"note: {note}")
    return "\n".join(parts)


def _strip_md_boilerplate(text: str) -> str:
    """Drop leading title block when concatenating many transcripts."""
    lines = text.splitlines()
    if not lines:
        return text
    if lines[0].startswith("#"):
        idx = 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        return "\n".join(lines[idx:]).strip()
    return text.strip()


def _compact_row_block(row: dict[str, str]) -> str:
    summary = re.sub(r"\s+", " ", row.get("summary", "")).strip()
    block = _row_preamble(row)
    if summary:
        block += f"\nsummary: {summary}"
    return block


def _cap_text(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_CORPUS_CHARS:
        return text, False
    trimmed = text[:MAX_CORPUS_CHARS]
    trimmed += (
        "\n\n[Context truncated — estimated size exceeded model safety limit. "
        "Try one confessional or all compact scope.]"
    )
    return trimmed, True


def build_corpus_bundle(
    cfg: dict,
    scope: str,
    *,
    confessional_id: str | None = None,
    rows: list[dict[str, str]] | None = None,
    drive_service=None,
) -> tuple[str, dict[str, Any]]:
    """Build LLM context text and metadata (count, truncated, warning)."""
    all_rows = rows if rows is not None else load_catalog_rows(cfg)
    meta: dict[str, Any] = {"scope": scope, "count": 0, "truncated": False}

    if scope == SCOPE_ONE:
        if not confessional_id:
            raise ValueError("confessional_id required for one-confessional scope")
        target = None
        for row in all_rows:
            if row.get("confessional_id") == confessional_id:
                target = row
                break
        if target is None:
            raise ValueError(f"Confessional not found: {confessional_id}")
        service = drive_service or get_drive_service(cfg)
        md = load_transcript_md(service, target)
        bundle = f"### {_row_preamble(target)}\n\n{md.strip()}"
        meta["count"] = 1
        bundle, truncated = _cap_text(bundle)
        meta["truncated"] = truncated
        return bundle, meta

    if scope == SCOPE_ALL_COMPACT:
        blocks = [_compact_row_block(row) for row in all_rows]
        bundle = "\n\n---\n\n".join(blocks)
        meta["count"] = len(all_rows)
        bundle, truncated = _cap_text(bundle)
        meta["truncated"] = truncated
        return bundle, meta

    if scope == SCOPE_ALL_FULL:
        service = drive_service or get_drive_service(cfg)
        sections: list[str] = []
        for row in all_rows:
            md = load_transcript_md(service, row)
            if not md.strip():
                md = _compact_row_block(row)
            else:
                md = _strip_md_boilerplate(md)
            sections.append(f"### {_row_preamble(row)}\n\n{md}")
        bundle = "\n\n---\n\n".join(sections)
        meta["count"] = len(all_rows)
        bundle, truncated = _cap_text(bundle)
        meta["truncated"] = truncated
        return bundle, meta

    raise ValueError(f"Unknown scope: {scope}")


def format_first_user_message(corpus: str, question: str, meta: dict[str, Any]) -> str:
    header = (
        f"[Context: {meta.get('count', 0)} confessionals, scope={meta.get('scope', '')}]"
    )
    if meta.get("truncated"):
        header += " (truncated)"
    return f"{header}\n{corpus}\n\n---\n{question.strip()}"
