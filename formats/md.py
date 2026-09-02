"""Markdown transcript export for human reading."""


def build_markdown_transcript(
    text: str,
    *,
    contestant: str,
    display_datetime: str,
    video_link: str,
    confessional_id: str,
    note: str = "",
    summary: str = "",
    key_moments: str = "",
) -> str:
    name = contestant or "Unknown"
    lines = [
        f"# {name} — {display_datetime}",
        "",
        f"**Confessional ID:** `{confessional_id}`",
        "",
    ]
    if note.strip():
        lines.extend([f"**Note:** {note.strip()}", ""])
    if video_link:
        lines.extend([f"**Video:** [Watch confessional]({video_link})", ""])

    if summary.strip():
        lines.extend(["## Summary", "", summary.strip(), ""])
    if key_moments.strip():
        lines.extend(["## Key moments", "", key_moments.strip(), ""])

    lines.extend(["---", "", text.strip(), ""])
    return "\n".join(lines)
