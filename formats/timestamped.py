"""Timestamped plain text for LLM prompts."""

from transcript import Segment


def _format_clock(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def segments_to_timestamped_text(segments: list[Segment]) -> str:
    """One line per segment: [HH:MM:SS] spoken text."""
    lines = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        lines.append(f"[{_format_clock(seg.start)}] {text}")
    return "\n".join(lines)
