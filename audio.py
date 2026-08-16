"""ffmpeg audio extraction and chunking for transcription."""

import os
import subprocess


def extract_audio(video_path: str, out_path: str):
    """Extract audio as mono 16kHz mp3 at 64kbps -- small, speech-quality-sufficient."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def split_audio(audio_path: str, chunk_minutes: int, out_dir: str) -> list[str]:
    """Split into fixed-length chunks. Returns sorted chunk paths."""
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, "chunk_%04d.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-f", "segment", "-segment_time", str(chunk_minutes * 60),
        "-c", "copy", pattern,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("chunk_")
    )
