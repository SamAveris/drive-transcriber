import re

from transcript import Segment


def _format_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def segments_to_srt(segments: list[Segment]) -> str:
    lines = []
    for i, seg in enumerate(segments, start=1):
        if not seg.text.strip():
            continue
        lines.append(str(i))
        lines.append(
            f"{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}"
        )
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines)


def _parse_timestamp(ts: str) -> float:
    """Parse SRT timestamp HH:MM:SS,mmm to seconds."""
    time_part, _, ms_part = ts.strip().partition(",")
    if not ms_part and "." in time_part:
        time_part, _, ms_part = time_part.partition(".")
    parts = time_part.split(":")
    if len(parts) != 3:
        return 0.0
    hours, minutes, seconds = (int(p) for p in parts)
    millis = int(ms_part[:3].ljust(3, "0")) if ms_part else 0
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def parse_srt(content: str) -> list[Segment]:
    """Parse SRT content into segments."""
    segments: list[Segment] = []
    blocks = re.split(r"\n\s*\n", content.strip())
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        time_line = lines[1] if lines[0].isdigit() else lines[0]
        text_lines = lines[2:] if lines[0].isdigit() else lines[1:]
        if "-->" not in time_line:
            continue
        start_str, _, end_str = time_line.partition("-->")
        text = " ".join(text_lines).strip()
        if not text:
            continue
        segments.append(
            Segment(
                start=_parse_timestamp(start_str),
                end=_parse_timestamp(end_str),
                text=text,
            )
        )
    return segments
