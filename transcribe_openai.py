"""Transcribe extracted audio via the OpenAI Whisper API."""

import os

from openai import OpenAI

from audio import split_audio
from formats.text import segments_to_readable_text
from transcript import Segment, TranscriptResult

# Stay under OpenAI's 25MB upload limit (~20MB safety margin).
_MAX_CHUNK_BYTES = 20 * 1024 * 1024

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()  # OPENAI_API_KEY from environment
    return _client


def _transcribe_file(audio_path: str, model: str) -> TranscriptResult:
    client = _get_client()
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model=model,
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments = [
        Segment(start=s.start, end=s.end, text=s.text.strip())
        for s in (result.segments or [])
        if s.text.strip()
    ]
    text = segments_to_readable_text(segments) if segments else (result.text or "").strip()
    return TranscriptResult(text=text, segments=segments)


def transcribe_audio(
    audio_path: str,
    work_dir: str,
    model: str = "whisper-1",
    chunk_minutes: int = 20,
) -> TranscriptResult:
    if os.path.getsize(audio_path) <= _MAX_CHUNK_BYTES:
        return _transcribe_file(audio_path, model)

    chunks_dir = os.path.join(work_dir, "chunks")
    chunk_paths = split_audio(audio_path, chunk_minutes, chunks_dir)
    chunk_seconds = chunk_minutes * 60

    all_segments: list[Segment] = []
    for i, chunk_path in enumerate(chunk_paths):
        offset = i * chunk_seconds
        chunk_result = _transcribe_file(chunk_path, model)
        for seg in chunk_result.segments:
            all_segments.append(
                Segment(
                    start=seg.start + offset,
                    end=seg.end + offset,
                    text=seg.text,
                )
            )

    return TranscriptResult(
        text=segments_to_readable_text(all_segments),
        segments=all_segments,
    )
