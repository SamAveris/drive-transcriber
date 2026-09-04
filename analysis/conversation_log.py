"""Append-only JSONL conversation logs for producer chat."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

LOG_DIR = "conversations"


def _repo_root(cfg: dict) -> str:
    return os.path.dirname(os.path.abspath(cfg.get("_config_path", "config.json")))


def conversations_dir(cfg: dict) -> str:
    return os.path.join(_repo_root(cfg), LOG_DIR)


def new_session_id() -> str:
    return str(uuid.uuid4())


def session_path(cfg: dict, session_id: str, day: str | None = None) -> str:
    day = day or datetime.now().strftime("%Y-%m-%d")
    folder = os.path.join(conversations_dir(cfg), day)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{session_id}.jsonl")


def log_turn(
    cfg: dict,
    *,
    session_id: str,
    scope: str,
    user: str,
    assistant: str,
    meta: dict[str, Any] | None = None,
) -> None:
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "scope": scope,
        "user": user,
        "assistant": assistant,
        "meta": meta or {},
    }
    path = session_path(cfg, session_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def list_conversations(cfg: dict, limit: int = 50) -> list[dict[str, str]]:
    root = conversations_dir(cfg)
    if not os.path.isdir(root):
        return []
    entries: list[tuple[str, str, float]] = []
    for day in os.listdir(root):
        day_dir = os.path.join(root, day)
        if not os.path.isdir(day_dir):
            continue
        for name in os.listdir(day_dir):
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(day_dir, name)
            entries.append((day, path, os.path.getmtime(path)))
    entries.sort(key=lambda item: item[2], reverse=True)
    results: list[dict[str, str]] = []
    for day, path, _ in entries[:limit]:
        session_id = os.path.splitext(os.path.basename(path))[0]
        preview = ""
        try:
            with open(path, encoding="utf-8") as f:
                first = f.readline().strip()
            if first:
                data = json.loads(first)
                preview = (data.get("user") or "")[:120]
        except (OSError, json.JSONDecodeError):
            pass
        results.append(
            {
                "day": day,
                "session_id": session_id,
                "path": path,
                "preview": preview,
            }
        )
    return results


def read_conversation(path: str) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    if not os.path.isfile(path):
        return turns
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                turns.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return turns
