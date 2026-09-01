import os
from datetime import datetime, timezone

_INVALID_CHARS = '<>:"/\\|?*'


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a Windows filename stem."""
    for ch in _INVALID_CHARS:
        name = name.replace(ch, "-")
    name = name.strip().rstrip(".")
    return name or "transcript"


def safe_local_filename(name: str) -> str:
    """Sanitize a full filename while preserving the extension."""
    base, ext = os.path.splitext(os.path.basename(name))
    return sanitize_filename(base) + ext.lower()


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if "T" in value:
        try:
            iso = value.replace("Z", "+00:00") if value.endswith("Z") else value
            return datetime.fromisoformat(iso)
        except ValueError:
            pass
    for fmt in (
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def format_display_datetime(submitted_at: str, fallback_created: str = "") -> str:
    """Human-readable date/time for transcript headers."""
    dt = _parse_datetime(submitted_at) or _parse_datetime(fallback_created)
    if not dt:
        return submitted_at or "Unknown date"
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    else:
        dt = dt.replace(tzinfo=timezone.utc).astimezone()
    hour = dt.hour % 12 or 12
    return f"{dt.day} {dt.strftime('%B %Y')}, {hour}:{dt.strftime('%M')} {dt.strftime('%p').lower()}"


def format_submitted_stamp(submitted_at: str, fallback_created: str = "") -> str:
    """Compact timestamp for filenames: YYYYMMDDHHMM (local time)."""
    dt = _parse_datetime(submitted_at) or _parse_datetime(fallback_created)
    if not dt:
        return "unknown"
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    else:
        dt = dt.replace(tzinfo=timezone.utc).astimezone()
    return dt.strftime("%Y%m%d%H%M")


def build_transcript_basename(
    contestant: str,
    submitted_at: str,
    *,
    fallback_created: str = "",
    fallback_video_name: str = "",
) -> str:
    """Build transcript filename stem: Contestant_YYYYMMDDHHMM."""
    stamp = format_submitted_stamp(submitted_at, fallback_created)
    if contestant:
        who = sanitize_filename(contestant)
    else:
        who = sanitize_filename(os.path.splitext(fallback_video_name)[0]) or "Unknown"
    return f"{who}_{stamp}"
