"""Plain-text formatting from transcript segments."""

from transcript import Segment


def segments_to_readable_text(segments: list[Segment]) -> str:
    """Join segment text with a blank line between each segment."""
    parts = [s.text.strip() for s in segments if s.text.strip()]
    return "\n\n".join(parts)
