"""
Video -> audio -> transcript via faster-whisper (local, GPU-accelerated).

Extracts a compressed mono audio track from the video with ffmpeg, then
transcribes it locally with faster-whisper. No API key or per-minute cost.
"""

import os
import site
import subprocess
import sys
from pathlib import Path

_model = None
_model_config = None


def _register_cuda_dlls():
    """Make pip-installed CUDA runtime DLLs visible on Windows."""
    if sys.platform != "win32":
        return
    for sp in site.getsitepackages():
        nvidia_dir = Path(sp) / "nvidia"
        if not nvidia_dir.is_dir():
            continue
        for bin_dir in nvidia_dir.glob("*/bin"):
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


_register_cuda_dlls()


def _get_model(model_size: str, device: str, compute_type: str):
    global _model, _model_config
    config = (model_size, device, compute_type)
    if _model is None or _model_config != config:
        from faster_whisper import WhisperModel

        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _model_config = config
    return _model


def extract_audio(video_path: str, out_path: str):
    """Extract audio as mono 16kHz mp3 at 64kbps -- small, speech-quality-sufficient."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def transcribe_video(
    video_path: str,
    work_dir: str,
    model: str = "medium",
    device: str = "cuda",
    compute_type: str = "float16",
) -> str:
    os.makedirs(work_dir, exist_ok=True)
    audio_path = os.path.join(work_dir, "audio.mp3")
    extract_audio(video_path, audio_path)

    whisper = _get_model(model, device, compute_type)
    segments, _ = whisper.transcribe(audio_path)
    return " ".join(segment.text.strip() for segment in segments)
