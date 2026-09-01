"""
Video -> audio -> transcript.

Supports local faster-whisper (default) or OpenAI Whisper API (pilot).
Audio is always extracted locally with ffmpeg before transcription.
"""

import os
import site
import sys
from pathlib import Path

from audio import extract_audio
from formats.text import segments_to_readable_text
from transcript import Segment, TranscriptResult

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


def _get_local_model(model_size: str, device: str, compute_type: str):
    global _model, _model_config
    _register_cuda_dlls()
    config = (model_size, device, compute_type)
    if _model is None or _model_config != config:
        from faster_whisper import WhisperModel

        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _model_config = config
    return _model


def _transcribe_local(
    audio_path: str,
    model: str,
    device: str,
    compute_type: str,
) -> TranscriptResult:
    whisper = _get_local_model(model, device, compute_type)
    segments, _ = whisper.transcribe(audio_path)
    segment_list = [
        Segment(start=s.start, end=s.end, text=s.text.strip())
        for s in segments
        if s.text.strip()
    ]
    text = segments_to_readable_text(segment_list)
    return TranscriptResult(text=text, segments=segment_list)


def transcribe_video(video_path: str, work_dir: str, cfg: dict) -> TranscriptResult:
    os.makedirs(work_dir, exist_ok=True)
    audio_path = os.path.join(work_dir, "audio.mp3")
    extract_audio(video_path, audio_path)

    backend = cfg.get("transcription_backend", "local")
    if backend == "openai":
        from transcribe_openai import transcribe_audio

        return transcribe_audio(
            audio_path,
            work_dir=work_dir,
            model=cfg.get("openai_model", "whisper-1"),
            chunk_minutes=cfg.get("chunk_minutes", 20),
        )

    return _transcribe_local(
        audio_path,
        model=cfg["whisper_model"],
        device=cfg["device"],
        compute_type=cfg["compute_type"],
    )
