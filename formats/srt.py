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
