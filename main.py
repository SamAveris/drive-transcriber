"""
Poll a Google Drive folder for new videos, transcribe each one, and
upload the transcript back to Drive.

Run this on a schedule (cron, Task Scheduler, Cloud Scheduler + Cloud
Run/Functions, etc.) -- see README.md for setup and scheduling options.

Usage:
    python main.py [path/to/config.json]
    python main.py --local-file path/to/video.mp4
    python main.py --auth
    python main.py --init-catalog
    python main.py --reanalyze --confessional-id <uuid>
"""

import json
import os
import shutil
import sys
import tempfile
import traceback

from confessional import get_confessional_id
from analysis.context import result_from_segments
from analysis.runner import (
    analysis_enabled,
    catalog_fields_from_outputs,
    run_auto_jobs,
)
from catalog import (
    build_whatsapp_message,
    catalog_enabled,
    catalog_row_for_file,
    find_catalog_row_by_confessional_id,
    get_sheets_service,
    init_catalog_headers,
    sync_catalog_headers,
    upsert_catalog_row,
)
from drive_client import (
    STATUS_DONE,
    STATUS_FAILED,
    analysis_already_done,
    authorize_oauth,
    clear_analysis_status,
    download_file,
    ensure_anyone_with_link_can_view,
    file_id_from_link,
    file_view_link,
    find_or_create_folder,
    get_drive_service,
    get_file_metadata,
    list_unprocessed_videos,
    mark_analysis_status,
    mark_status,
    read_file_text,
    update_file_content,
    upload_transcript,
)
from filenames import (
    build_transcript_basename,
    format_display_datetime,
    safe_local_filename,
    sanitize_filename,
)
from formats.md import build_markdown_transcript
from formats.srt import parse_srt, segments_to_srt
from intake import (
    guess_contestant_from_filename,
    load_form_responses,
    match_file_to_form,
)
from media_info import get_media_duration_seconds
from notify import notification_recipients, notifications_enabled, send_confessional_notification
from transcribe import transcribe_video


EXAMPLE_CONFIG_NAME = "config.example.json"


def load_config(path: str) -> dict:
    """Load config.example.json defaults, then overlay the user's config.json."""
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

    cfg["_config_path"] = os.path.abspath(path)
    return cfg


def write_transcript_files(
    result,
    dest_dir: str,
    base_name: str,
    cfg: dict,
    meta: dict | None = None,
) -> dict[str, str]:
    """Write transcript files under dest_dir. Returns {format: path}."""
    os.makedirs(dest_dir, exist_ok=True)
    output_formats = cfg.get("output_formats", ["md", "srt"])
    paths: dict[str, str] = {}
    meta = meta or {}

    if "txt" in output_formats:
        txt_path = os.path.join(dest_dir, f"{base_name}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(result.text)
        paths["txt"] = txt_path

    if "md" in output_formats:
        md_path = os.path.join(dest_dir, f"{base_name}.md")
        body = build_markdown_transcript(
            result.text,
            contestant=meta.get("contestant", ""),
            display_datetime=meta.get("display_datetime", ""),
            video_link=meta.get("video_link", ""),
            confessional_id=meta.get("confessional_id", ""),
            note=meta.get("note", ""),
            summary=meta.get("summary", ""),
            key_moments=meta.get("key_moments", ""),
        )
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(body)
        paths["md"] = md_path

    if "srt" in output_formats:
        srt_path = os.path.join(dest_dir, f"{base_name}.srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(segments_to_srt(result.segments))
        paths["srt"] = srt_path

    return paths


def _load_form_rows(cfg: dict, sheets_service) -> list:
    form_sheet = cfg.get("form_response_sheet_id") or cfg.get("catalog_sheet_id")
    file_column = cfg.get("form_file_column")
    if not sheets_service or not form_sheet or not file_column:
        return []
    return load_form_responses(
        sheets_service,
        form_sheet,
        cfg.get("form_response_tab", "Form Responses 1"),
        cfg.get("form_contestant_column", "Name"),
        cfg.get("form_note_column", "Note"),
        file_column,
        cfg.get("form_timestamp_column", "Timestamp"),
    )


def _resolve_intake(
    file_info: dict,
    form_rows: list,
    cfg: dict,
    used_form_rows: set[int] | None = None,
) -> tuple[str, str, str]:
    used = used_form_rows if used_form_rows is not None else set()
    match = match_file_to_form(
        file_info,
        form_rows,
        cfg.get("form_match_window_minutes", 120),
        used_row_indices=used,
    )
    if match:
        if match.row_index is not None:
            used.add(match.row_index)
        return match.contestant, match.note, match.submitted_at

    known = cfg.get("contestant_names") or []
    contestant = guess_contestant_from_filename(file_info.get("name", ""), known)
    created = file_info.get("createdTime", "")
    submitted = created.replace("T", " ")[:16] if created else ""
    return contestant, "", submitted


def _write_catalog(
    sheets_service,
    cfg: dict,
    file_info: dict,
    **fields,
):
    if not sheets_service or not catalog_enabled(cfg):
        return
    tab = cfg.get("catalog_tab", "Catalog")
    row = catalog_row_for_file(file_info, **fields)
    upsert_catalog_row(sheets_service, cfg["catalog_sheet_id"], tab, row)


def _run_analysis(
    result,
    meta: dict,
    cfg: dict,
    file_info: dict | None = None,
    force: bool = False,
) -> tuple[dict[str, str], dict[str, str]]:
    """Run auto_jobs. Returns (job outputs, catalog fields)."""
    if not analysis_enabled(cfg):
        return {}, {}

    info = file_info or {}
    if not force and analysis_already_done(info):
        print("[analysis] skipped (already done)")
        return {}, {}

    try:
        outputs = run_auto_jobs(result, meta, cfg)
        if not outputs:
            return {}, {}
        return outputs, catalog_fields_from_outputs(outputs)
    except Exception as err:
        name = info.get("name", "unknown")
        print(f"[{name}] analysis failed: {err}")
        traceback.print_exc()
        return {}, {}


def process_file(
    service,
    file_info: dict,
    output_folder_id: str,
    cfg: dict,
    sheets_service=None,
    form_rows=None,
    used_form_rows: set[int] | None = None,
):
    file_id = file_info["id"]
    name = file_info["name"]
    form_rows = form_rows or []
    used_form_rows = used_form_rows if used_form_rows is not None else set()
    print(f"[{name}] processing...")

    contestant, note, submitted_at = _resolve_intake(
        file_info, form_rows, cfg, used_form_rows
    )
    confessional_id = get_confessional_id(file_info)
    if contestant:
        print(f"[{name}] contestant: {contestant}")
    print(f"[{name}] confessional_id: {confessional_id}")

    _write_catalog(
        sheets_service,
        cfg,
        file_info,
        status="processing",
        confessional_id=confessional_id,
        contestant=contestant,
        note=note,
        submitted_at=submitted_at,
    )

    work_dir = tempfile.mkdtemp(prefix="drive_transcriber_")
    try:
        video_path = os.path.join(work_dir, safe_local_filename(name))
        download_file(service, file_id, video_path)

        duration = get_media_duration_seconds(video_path)
        result = transcribe_video(video_path, work_dir=work_dir, cfg=cfg)

        ensure_anyone_with_link_can_view(service, file_id)
        video_link = file_view_link(file_id)

        base_name = build_transcript_basename(
            contestant,
            submitted_at,
            fallback_created=file_info.get("createdTime", ""),
            fallback_video_name=name,
        )
        display_datetime = format_display_datetime(
            submitted_at,
            file_info.get("createdTime", ""),
        )
        analysis_meta = {
            "contestant": contestant,
            "display_datetime": display_datetime,
            "video_link": video_link,
            "confessional_id": confessional_id,
            "note": note,
            "submitted_at": submitted_at,
        }
        analysis_outputs, analysis_fields = _run_analysis(
            result, analysis_meta, cfg, file_info=file_info
        )
        if analysis_outputs:
            mark_analysis_status(service, file_id)

        outputs = write_transcript_files(
            result,
            work_dir,
            base_name,
            cfg,
            meta={
                **analysis_meta,
                "summary": analysis_outputs.get("summary", ""),
                "key_moments": analysis_outputs.get("key_moments", ""),
            },
        )
        transcript_props = {
            "confessional_id": confessional_id,
            "contestant": contestant,
            "submitted_at": submitted_at or file_info.get("createdTime", ""),
            "source_video_id": file_id,
            "note": note,
        }
        transcript_ids: dict[str, str] = {}
        for fmt, path in outputs.items():
            props = {**transcript_props, "format": fmt}
            transcript_ids[fmt] = upload_transcript(
                service,
                path,
                os.path.basename(path),
                output_folder_id,
                app_properties=props,
            )
            print(f"[{name}] uploaded {fmt} as {os.path.basename(path)}")

        md_link = file_view_link(transcript_ids["md"]) if "md" in transcript_ids else ""
        srt_link = file_view_link(transcript_ids["srt"]) if "srt" in transcript_ids else ""

        extra = {"contestant": contestant, "confessional_id": confessional_id}
        mark_status(service, file_id, STATUS_DONE, extra_props=extra)

        _write_catalog(
            sheets_service,
            cfg,
            file_info,
            status="ready",
            confessional_id=confessional_id,
            contestant=contestant,
            note=note,
            submitted_at=submitted_at,
            duration_seconds=duration,
            video_link=video_link,
            transcript_md_link=md_link,
            transcript_srt_link=srt_link,
            **analysis_fields,
        )
        print(f"[{name}] done.")
        if catalog_enabled(cfg) and video_link:
            msg = build_whatsapp_message(
                contestant,
                submitted_at,
                video_link,
                analysis_fields.get("summary", ""),
            )
            print(f"[{name}] whatsapp: {msg}")
            if notifications_enabled(cfg):
                try:
                    send_confessional_notification(
                        cfg,
                        contestant=contestant,
                        whatsapp_message=msg,
                        note=note,
                        transcript_md_link=md_link,
                        confessional_id=confessional_id,
                    )
                    print(f"[{name}] emailed {len(notification_recipients(cfg, contestant))} recipient(s)")
                except Exception as err:
                    print(f"[{name}] email notification failed: {err}")

    except Exception:
        print(f"[{name}] FAILED:")
        traceback.print_exc()
        mark_status(service, file_id, STATUS_FAILED)
        _write_catalog(
            sheets_service,
            cfg,
            file_info,
            status="failed",
            confessional_id=confessional_id,
            contestant=contestant,
            note=note,
            submitted_at=submitted_at,
        )

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_local_file(video_path: str, config_path: str):
    """Transcribe a local video without touching Drive."""
    cfg = load_config(config_path)
    video_path = os.path.abspath(video_path)
    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)

    backend = cfg.get("transcription_backend", "openai")
    print(f"Backend: {backend}")
    print("Extracting audio locally, then transcribing...")

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


def run_reanalyze(confessional_id: str, config_path: str):
    """Re-run analysis auto_jobs for an existing confessional without re-transcribing."""
    cfg = load_config(config_path)
    if not analysis_enabled(cfg):
        raise ValueError("Set analysis_enabled: true and ensure prompts.yaml exists.")
    if not catalog_enabled(cfg):
        raise ValueError("catalog_sheet_id required for --reanalyze.")

    service = get_drive_service(cfg)
    sheets_service = get_sheets_service(cfg)
    tab = cfg.get("catalog_tab", "Catalog")

    row = find_catalog_row_by_confessional_id(
        sheets_service, cfg["catalog_sheet_id"], tab, confessional_id
    )
    if not row:
        raise ValueError(f"No catalog row for confessional_id: {confessional_id}")

    file_id = row.get("drive_file_id", "")
    if not file_id:
        raise ValueError("Catalog row missing drive_file_id")

    file_info = get_file_metadata(service, file_id)
    srt_id = file_id_from_link(row.get("transcript_srt_link", ""))
    if not srt_id:
        raise ValueError("Catalog row missing transcript_srt_link — re-transcribe first.")

    print(f"Re-analyzing confessional {confessional_id} ({file_info.get('name', file_id)})...")
    srt_content = read_file_text(service, srt_id)
    segments = parse_srt(srt_content)
    if not segments:
        raise ValueError("Could not parse SRT transcript.")

    result = result_from_segments(segments)
    submitted_at = row.get("submitted_at", "")
    display_datetime = format_display_datetime(
        submitted_at,
        file_info.get("createdTime", ""),
    )
    meta = {
        "contestant": row.get("contestant", ""),
        "note": row.get("note", ""),
        "submitted_at": row.get("submitted_at", ""),
        "confessional_id": confessional_id,
        "video_link": row.get("video_link", ""),
        "display_datetime": display_datetime,
    }
    base_name = build_transcript_basename(
        meta["contestant"],
        meta["submitted_at"],
        fallback_created=file_info.get("createdTime", ""),
        fallback_video_name=file_info.get("name", ""),
    )

    md_id = file_id_from_link(row.get("transcript_md_link", ""))
    if not md_id:
        raise ValueError("Catalog row missing transcript_md_link — re-transcribe first.")

    clear_analysis_status(service, file_id)

    work_dir = tempfile.mkdtemp(prefix="drive_transcriber_reanalyze_")
    try:
        analysis_outputs, analysis_fields = _run_analysis(
            result, meta, cfg, file_info=file_info, force=True
        )
        if analysis_outputs:
            mark_analysis_status(service, file_id)

        md_outputs = write_transcript_files(
            result,
            work_dir,
            base_name,
            cfg,
            meta={
                **meta,
                "summary": analysis_outputs.get("summary", ""),
                "key_moments": analysis_outputs.get("key_moments", ""),
            },
        )
        if "md" not in md_outputs:
            raise ValueError("Markdown output disabled in config.")
        update_file_content(service, md_id, md_outputs["md"])
        print(f"Updated transcript markdown on Drive.")

        _write_catalog(
            sheets_service,
            cfg,
            file_info,
            status=row.get("status", "ready") or "ready",
            confessional_id=confessional_id,
            contestant=meta["contestant"],
            note=meta["note"],
            submitted_at=meta["submitted_at"],
            video_link=row.get("video_link", ""),
            transcript_md_link=row.get("transcript_md_link", ""),
            transcript_srt_link=row.get("transcript_srt_link", ""),
            **analysis_fields,
        )
        print("Re-analysis complete.")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_init_catalog(config_path: str):
    cfg = load_config(config_path)
    if not catalog_enabled(cfg):
        raise ValueError("Set catalog_sheet_id in config.json first.")
    sheets_service = get_sheets_service(cfg)
    tab = cfg.get("catalog_tab", "Catalog")
    headers = sync_catalog_headers(sheets_service, cfg["catalog_sheet_id"], tab)
    print(f"Synced catalog headers on tab '{tab}': {', '.join(headers)}")


def run(config_path: str):
    cfg = load_config(config_path)
    service = get_drive_service(cfg)
    sheets_service = get_sheets_service(cfg) if catalog_enabled(cfg) else None
    form_rows = _load_form_rows(cfg, sheets_service) if sheets_service else []

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
    used_form_rows: set[int] = set()
    for file_info in videos:
        process_file(
            service,
            file_info,
            output_folder_id,
            cfg,
            sheets_service=sheets_service,
            form_rows=form_rows,
            used_form_rows=used_form_rows,
        )


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--auth":
        config_path = sys.argv[2] if len(sys.argv) > 2 else "config.json"
        cfg = load_config(config_path)
        authorize_oauth(cfg["credentials_file"], cfg["token_file"])
        print(f"Authorized. Token saved to {cfg['token_file']}")
    elif len(sys.argv) >= 2 and sys.argv[1] == "--init-catalog":
        config_path = sys.argv[2] if len(sys.argv) > 2 else "config.json"
        run_init_catalog(config_path)
    elif len(sys.argv) >= 2 and sys.argv[1] == "--reanalyze":
        confessional_id = ""
        config_path = "config.json"
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--confessional-id" and i + 1 < len(args):
                confessional_id = args[i + 1]
                i += 2
            else:
                config_path = args[i]
                i += 1
        if not confessional_id:
            print("Usage: python main.py --reanalyze --confessional-id <uuid> [config.json]")
            sys.exit(1)
        run_reanalyze(confessional_id, config_path)
    elif len(sys.argv) >= 3 and sys.argv[1] == "--local-file":
        video_path = sys.argv[2]
        config_path = sys.argv[3] if len(sys.argv) > 3 else "config.json"
        run_local_file(video_path, config_path)
    else:
        config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
        run(config_path)
