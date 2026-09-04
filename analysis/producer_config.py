"""Load and save producer.yaml for chat UI and daily summaries."""

import os
from typing import Any

import yaml

DEFAULT_PRODUCER = {
    "openai_model": "gpt-4o-mini",
    "persona": {"system": "You are a TV production assistant."},
    "daily_summary": {
        "enabled": True,
        "prompt": "Summarize confessionals from the last 24 hours.",
        "log_file": "daily_summaries.md",
        "email_on_empty": False,
    },
}


def producer_config_path(cfg: dict) -> str:
    path = cfg.get("producer_config_file", "producer.yaml")
    if os.path.isabs(path):
        return path
    base = os.path.dirname(os.path.abspath(cfg.get("_config_path", "config.json")))
    return os.path.join(base, path)


def load_producer_config(cfg: dict) -> dict[str, Any]:
    path = producer_config_path(cfg)
    if not os.path.isfile(path):
        return dict(DEFAULT_PRODUCER)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = dict(DEFAULT_PRODUCER)
    merged.update({k: v for k, v in data.items() if v is not None})
    if isinstance(data.get("persona"), dict):
        merged["persona"] = {**DEFAULT_PRODUCER["persona"], **data["persona"]}
    if isinstance(data.get("daily_summary"), dict):
        merged["daily_summary"] = {
            **DEFAULT_PRODUCER["daily_summary"],
            **data["daily_summary"],
        }
    return merged


def save_producer_config(cfg: dict, data: dict[str, Any]) -> None:
    path = producer_config_path(cfg)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def producer_model(cfg: dict, producer: dict | None = None) -> str:
    prod = producer or load_producer_config(cfg)
    return str(prod.get("openai_model") or cfg.get("openai_analysis_model", "gpt-4o-mini"))


def persona_system(cfg: dict, producer: dict | None = None) -> str:
    prod = producer or load_producer_config(cfg)
    return str((prod.get("persona") or {}).get("system") or "").strip()
