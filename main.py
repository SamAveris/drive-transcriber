"""
Poll a Google Drive folder for new videos, transcribe each one, and
upload the transcript back to Drive.

Run this on a schedule (cron, Task Scheduler, Cloud Scheduler + Cloud
Run/Functions, etc.) -- see README.md for setup and scheduling options.

Usage:
    python main.py [path/to/config.json]
"""

import json
import os
import shutil
import sys
import tempfile
import traceback

from drive_client import (
    get_drive_service,
    list_unprocessed_videos,
    download_file,
    find_or_create_folder,
    upload_transcript,
    mark_status,
    STATUS_DONE,
    STATUS_FAILED,
)
from transcribe import transcribe_video


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def process_file(service, file_info: dict, output_folder_id: str, cfg: dict):
    file_id = file_info["id"]
    name = file_info["name"]
    print(f"[{name}] processing...")

    work_dir = tempfile.mkdtemp(prefix="drive_transcriber_")
    try:
        video_path = os.path.join(work_dir, name)
        download_file(service, file_id, video_path)

        transcript_text = transcribe_video(
            video_path,
            work_dir=work_dir,
            chunk_minutes=cfg.get("chunk_minutes", 20),
            model=cfg.get("openai_model", "whisper-1"),
        )

        transcript_path = os.path.join(work_dir, "transcript.txt")
        with open(transcript_path, "w") as f:
            f.write(transcript_text)

        base_name, _ = os.path.splitext(name)
        upload_transcript(
            service, transcript_path, f"{base_name}.txt", output_folder_id
        )

        mark_status(service, file_id, STATUS_DONE)
        print(f"[{name}] done.")

    except Exception:
        print(f"[{name}] FAILED:")
        traceback.print_exc()
        # Mark failed so it doesn't retry forever and silently burn API credits.
        # Delete this appProperty on the Drive file manually (or change status)
        # to force a retry once you've fixed the underlying issue.
        mark_status(service, file_id, STATUS_FAILED)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run(config_path: str):
    cfg = load_config(config_path)
    service = get_drive_service(cfg["service_account_file"])

    output_folder_id = find_or_create_folder(
        service, "Transcripts", cfg["output_folder_id"]
    )

    videos = list_unprocessed_videos(
        service,
        cfg["source_folder_id"],
        cfg.get("video_mime_prefixes", ["video/"]),
        cfg.get("poll_page_size", 25),
    )

    if not videos:
        print("No new videos to transcribe.")
        return

    print(f"Found {len(videos)} new video(s).")
    for file_info in videos:
        process_file(service, file_info, output_folder_id, cfg)


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    run(config_path)
