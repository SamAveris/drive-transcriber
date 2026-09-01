"""Stable ID for linking video, transcripts, and catalog rows."""

import uuid


def get_confessional_id(file_info: dict) -> str:
    """Reuse existing ID on the video, or assign a new UUID for this confessional."""
    props = file_info.get("appProperties") or {}
    existing = props.get("confessional_id")
    if existing:
        return str(existing)
    return str(uuid.uuid4())
