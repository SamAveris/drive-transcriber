"""Build template context for analysis prompts."""

from formats.text import segments_to_readable_text
from formats.timestamped import segments_to_timestamped_text
from transcript import Segment, TranscriptResult


def build_transcript_context(
    result: TranscriptResult,
    meta: dict,
) -> dict[str, str]:
    """Variables available in prompts.yaml templates."""
    segments = result.segments or []
    return {
        "contestant": meta.get("contestant") or "Unknown",
        "note": meta.get("note") or "",
        "submitted_at": meta.get("submitted_at") or meta.get("display_datetime") or "",
        "confessional_id": meta.get("confessional_id") or "",
        "video_link": meta.get("video_link") or "",
        "transcript_text": result.text or segments_to_readable_text(segments),
        "transcript_timestamps": segments_to_timestamped_text(segments),
    }


def result_from_segments(segments: list[Segment], text: str = "") -> TranscriptResult:
    body = text or segments_to_readable_text(segments)
    return TranscriptResult(text=body, segments=segments)
