import os

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
