"""Parse transcript markdown and align key moments for Browse tab."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TIMESTAMP_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.+)$")
_MOMENT_TS_RE = re.compile(r"\[(\d{2}:\d{2}:\d{2})\]")


def _clock_to_seconds(label: str) -> float:
    hours, minutes, seconds = (int(p) for p in label.split(":"))
    return hours * 3600 + minutes * 60 + seconds


@dataclass
class KeyMoment:
    seconds: float
    label: str
    description: str


@dataclass
class TranscriptLine:
    seconds: float
    label: str
    text: str


@dataclass
class BrowseRow:
    time_label: str
    transcript: str
    moment: KeyMoment | None = None


def parse_transcript_md(md: str) -> dict[str, str]:
    """Split markdown into key_moments preamble section and body below ---."""
    parts = re.split(r"\n---\n", md, maxsplit=1)
    preamble = parts[0]
    body = parts[1].strip() if len(parts) > 1 else ""

    key_moments = ""
    if "## Key moments" in preamble:
        _, _, rest = preamble.partition("## Key moments")
        key_moments = rest.strip()
        if "## Summary" in key_moments:
            key_moments = key_moments.split("## Summary")[0].strip()

    return {"key_moments": key_moments, "body": body}


def parse_key_moments(text: str) -> list[KeyMoment]:
    """Extract [HH:MM:SS] moments and descriptions from key moments block."""
    if not text.strip():
        return []

    moments: list[KeyMoment] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*•]\s*", "", line)
        line = re.sub(r"^\d+[.)]\s*", "", line)
        match = _MOMENT_TS_RE.search(line)
        if not match:
            continue
        label = match.group(1)
        description = line[match.end() :].strip()
        description = re.sub(r"^[-–—:]\s*", "", description).strip()
        if not description:
            continue
        moments.append(
            KeyMoment(
                seconds=_clock_to_seconds(label),
                label=label,
                description=description,
            )
        )
    return moments


def parse_timestamped_body(body: str) -> list[TranscriptLine]:
    """Parse [HH:MM:SS] transcript lines; empty if legacy plain text."""
    lines: list[TranscriptLine] = []
    for raw in body.splitlines():
        match = _TIMESTAMP_RE.match(raw.strip())
        if not match:
            if lines:
                lines[-1] = TranscriptLine(
                    seconds=lines[-1].seconds,
                    label=lines[-1].label,
                    text=f"{lines[-1].text} {raw.strip()}".strip(),
                )
            continue
        label, text = match.group(1), match.group(2).strip()
        if text:
            lines.append(
                TranscriptLine(
                    seconds=_clock_to_seconds(label),
                    label=label,
                    text=text,
                )
            )
    return lines


def is_timestamped_body(body: str) -> bool:
    return bool(parse_timestamped_body(body))


def align_moments_with_lines(
    lines: list[TranscriptLine],
    moments: list[KeyMoment],
    *,
    tolerance_seconds: float = 5.0,
) -> list[BrowseRow]:
    """Row-sync transcript lines with nearest key moment per timestamp."""
    if not lines:
        return []

    rows = [
        BrowseRow(time_label=line.label, transcript=line.text, moment=None)
        for line in lines
    ]
    used_rows: set[int] = set()

    for moment in sorted(moments, key=lambda m: m.seconds):
        best_idx = -1
        best_delta = tolerance_seconds + 1
        for idx, line in enumerate(lines):
            if idx in used_rows:
                continue
            delta = abs(moment.seconds - line.seconds)
            if delta > tolerance_seconds:
                continue
            if delta < best_delta or (
                delta == best_delta
                and best_idx >= 0
                and line.seconds >= moment.seconds
                and lines[best_idx].seconds < moment.seconds
            ):
                best_delta = delta
                best_idx = idx
        if best_idx >= 0:
            rows[best_idx] = BrowseRow(
                time_label=rows[best_idx].time_label,
                transcript=rows[best_idx].transcript,
                moment=moment,
            )
            used_rows.add(best_idx)
        else:
            rows.append(BrowseRow(time_label="", transcript="", moment=moment))

    return rows
