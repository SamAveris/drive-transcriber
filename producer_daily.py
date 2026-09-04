"""Daily confessional summary — append to Drive log and email producers."""

from __future__ import annotations

import sys
from datetime import datetime

from analysis.corpus import build_corpus_bundle, load_catalog_rows, rows_in_last_hours
from analysis.daily_log import append_daily_summary_section
from analysis.engine import run_chat
from analysis.producer_config import load_producer_config, persona_system, producer_model
from main import load_config
from notify import send_daily_summary_notification


def main() -> int:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    cfg = load_config(config_path)
    producer = load_producer_config(cfg)
    daily = producer.get("daily_summary") or {}

    if not daily.get("enabled", True):
        print("Daily summary disabled in producer.yaml")
        return 0

    rows = load_catalog_rows(cfg)
    recent = rows_in_last_hours(rows, hours=24)
    date_str = datetime.now().strftime("%Y-%m-%d")

    if not recent:
        print("No confessionals in the last 24 hours")
        if daily.get("email_on_empty"):
            send_daily_summary_notification(
                cfg,
                date_str=date_str,
                summary="No new confessionals in the last 24 hours.",
                log_link="",
            )
        return 0

    corpus, meta = build_corpus_bundle(
        cfg,
        "all_compact",
        rows=recent,
    )
    system = persona_system(cfg, producer)
    prompt = str(daily.get("prompt") or "").strip()
    user = f"{prompt}\n\n---\n\n{corpus}"
    model = producer_model(cfg, producer)
    summary = run_chat(system=system, user=user, model=model)

    log_file = str(daily.get("log_file") or "daily_summaries.md")
    log_link = append_daily_summary_section(
        cfg,
        date_str=date_str,
        summary=summary,
        log_filename=log_file,
    )
    send_daily_summary_notification(
        cfg,
        date_str=date_str,
        summary=summary,
        log_link=log_link,
    )
    print(f"Daily summary appended ({meta.get('count', 0)} confessionals)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
