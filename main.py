"""
Poll a Google Drive folder for new videos, transcribe each one, and
upload the transcript back to Drive.

Run this on a schedule (cron, Task Scheduler, Cloud Scheduler + Cloud
Run/Functions, etc.) -- see README.md for setup and scheduling options.

Usage:
    python main.py [path/to/config.json]
    python main.py --local-file path/to/video.mp4
    python main.py --auth
"""

import json
import os
import shutil
import sys
import tempfile
import traceback

from drive_client import (
    authorize_oauth,
    get_drive_service,
    list_unprocessed_videos,
    download_file,
    find_or_create_folder,
    upload_transcript,
    mark_status,
    STATUS_DONE,
    STATUS_FAILED,
)
from filenames import safe_local_filename, sanitize_filename
from formats.srt import segments_to_srt
from transcribe import transcribe_video


EXAMPLE_CONFIG_NAME = "config.example.json"


def load_config(path: str) -> dict:
    """Load config.example.json defaults, then overlay the user's config.json.

    Your config.json only needs the values you want to override (folder IDs,
    etc.) -- new keys added to config.example.json in future updates are picked
    up automatically without editing config.json.
    """
    base_dir = os.path.dirname(os.path.abspath(path)) or os.getcwd()
    example_path = os.path.join(base_dir, EXAMPLE_CONFIG_NAME)

    cfg = {}
    if os.path.isfile(example_path):
        with open(example_path) as f:
            cfg = json.load(f)

    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"{path} not found. Create it with your folder IDs "
            f"(see {EXAMPLE_CONFIG_NAME} for all available options)."
        )

    with open(path) as f:
        cfg.update(json.load(f))

    return cfg


def write_transcript_files(result, dest_dir: str, base_name: str, cfg: dict) -> dict[str, str]:
    """Write transcript files under dest_dir. Returns {format: path}."""
    os.makedirs(dest_dir, exist_ok=True)
    output_formats = cfg.get("output_formats", ["txt"])
    paths: dict[str, str] = {}

    if "txt" in output_formats:
        txt_path = os.path.join(dest_dir, f"{base_name}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(result.text)
        paths["txt"] = txt_path

    if "srt" in output_formats:
        srt_path = os.path.join(dest_dir, f"{base_name}.srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(segments_to_srt(result.segments))
        paths["srt"] = srt_path

    return paths


def process_file(service, file_info: dict, output_folder_id: str, cfg: dict):
    file_id = file_info["id"]
    name = file_info["name"]
    print(f"[{name}] processing...")

    work_dir = tempfile.mkdtemp(prefix="drive_transcriber_")
    try:
        video_path = os.path.join(work_dir, safe_local_filename(name))
        download_file(service, file_id, video_path)

        result = transcribe_video(video_path, work_dir=work_dir, cfg=cfg)

        base_name = sanitize_filename(os.path.splitext(name)[0])
        outputs = write_transcript_files(result, work_dir, base_name, cfg)
        for fmt, path in outputs.items():
            upload_transcript(
                service, path, os.path.basename(path), output_folder_id
            )
            print(f"[{name}] uploaded {fmt}")

        mark_status(service, file_id, STATUS_DONE)
        print(f"[{name}] done.")

    except Exception:
        print(f"[{name}] FAILED:")
        traceback.print_exc()
        mark_status(service, file_id, STATUS_FAILED)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_local_file(video_path: str, config_path: str):
    """Pilot mode: transcribe a local video without touching Drive."""
    cfg = load_config(config_path)
    video_path = os.path.abspath(video_path)
    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)

    backend = cfg.get("transcription_backend", "openai")
    print(f"Backend: {backend}")
    print(f"Extracting audio locally, then transcribing...")

    work_dir = tempfile.mkdtemp(prefix="drive_transcriber_pilot_")
    try:
        result = transcribe_video(video_path, work_dir=work_dir, cfg=cfg)

        out_dir = cfg.get("local_output_dir") or os.path.join(
            os.path.dirname(os.path.abspath(config_path)), "pilot_output"
        )
        base_name = sanitize_filename(os.path.splitext(os.path.basename(video_path))[0])
        outputs = write_transcript_files(result, out_dir, base_name, cfg)
        for fmt, path in outputs.items():
            print(f"Wrote {path}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run(config_path: str):
    cfg = load_config(config_path)
    service = get_drive_service(cfg)

    output_folder_id = find_or_create_folder(
        service, "Transcripts", cfg["output_folder_id"]
    )

    videos = list_unprocessed_videos(
        service,
        cfg["source_folder_id"],
        cfg["video_mime_prefixes"],
        cfg["poll_page_size"],
    )

    if not videos:
        print("No new videos to transcribe.")
        return

    print(f"Found {len(videos)} new video(s).")
    for file_info in videos:
        process_file(service, file_info, output_folder_id, cfg)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--auth":
        config_path = sys.argv[2] if len(sys.argv) > 2 else "config.json"
        cfg = load_config(config_path)
        authorize_oauth(cfg["credentials_file"], cfg["token_file"])
        print(f"Authorized. Token saved to {cfg['token_file']}")
    elif len(sys.argv) >= 3 and sys.argv[1] == "--local-file":
        video_path = sys.argv[2]
        config_path = sys.argv[3] if len(sys.argv) > 3 else "config.json"
        run_local_file(video_path, config_path)
    else:
        config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
        run(config_path)
