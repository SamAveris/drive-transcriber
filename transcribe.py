"""
Video -> audio -> transcript.

Extracts a compressed mono audio track from the video with ffmpeg, splits
it into chunks so no single file exceeds OpenAI's 25MB upload limit, sends
each chunk to the Whisper API, and stitches the pieces back into one
transcript.
"""

import os
import subprocess
from openai import OpenAI

client = OpenAI()  # reads OPENAI_API_KEY from the environment


def extract_audio(video_path: str, out_path: str):
    """Extract audio as mono 16kHz mp3 at 64kbps -- small, speech-quality-sufficient."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def split_audio(audio_path: str, chunk_minutes: int, out_dir: str) -> list[str]:
    """Split into fixed-length chunks using ffmpeg's segment muxer. Returns sorted chunk paths."""
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, "chunk_%04d.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-f", "segment", "-segment_time", str(chunk_minutes * 60),
        "-c", "copy", pattern,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    chunks = sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("chunk_")
    )
    return chunks


def transcribe_chunk(chunk_path: str, model: str) -> str:
    with open(chunk_path, "rb") as f:
        result = client.audio.transcriptions.create(model=model, file=f)
    return result.text.strip()


def transcribe_video(video_path: str, work_dir: str, chunk_minutes: int, model: str) -> str:
    os.makedirs(work_dir, exist_ok=True)
    audio_path = os.path.join(work_dir, "audio.mp3")
    extract_audio(video_path, audio_path)

    # Skip chunking if the whole file is already comfortably under the limit (~20MB safety margin).
    if os.path.getsize(audio_path) <= 20 * 1024 * 1024:
        return transcribe_chunk(audio_path, model)

    chunks_dir = os.path.join(work_dir, "chunks")
    chunk_paths = split_audio(audio_path, chunk_minutes, chunks_dir)

    texts = []
    for i, chunk_path in enumerate(chunk_paths, start=1):
        texts.append(transcribe_chunk(chunk_path, model))

    return "\n\n".join(texts)
