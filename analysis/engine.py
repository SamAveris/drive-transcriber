"""Load prompts and call OpenAI Chat Completions."""

import os
import re
from typing import Any

import yaml
from openai import OpenAI

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def _prompts_path(cfg: dict) -> str:
    path = cfg.get("prompts_file", "prompts.yaml")
    if os.path.isabs(path):
        return path
    base = os.path.dirname(os.path.abspath(cfg.get("_config_path", "config.json")))
    return os.path.join(base, path)


def load_prompts(cfg: dict) -> dict[str, Any]:
    path = _prompts_path(cfg)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Prompts file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data.get("auto_jobs"), list):
        raise ValueError(f"{path}: auto_jobs must be a list")
    return data


def render_template(template: str, context: dict[str, str]) -> str:
    """Replace {key} placeholders; leave unknown keys as-is."""

    def repl(match: re.Match) -> str:
        key = match.group(1)
        return context.get(key, match.group(0))

    return re.sub(r"\{(\w+)\}", repl, template)


def default_analysis_model(cfg: dict, prompts: dict | None = None) -> str:
    if prompts and prompts.get("openai_analysis_model"):
        return str(prompts["openai_analysis_model"])
    return cfg.get("openai_analysis_model", "gpt-4o-mini")


def run_chat(
    *,
    system: str,
    user: str,
    model: str,
) -> str:
    client = _get_client()
    messages = []
    if system.strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.append({"role": "user", "content": user.strip()})

    response = client.chat.completions.create(model=model, messages=messages)
    content = response.choices[0].message.content or ""
    return content.strip()


def one_sentence_summary(text: str) -> str:
    """Normalize model output to a single line (no truncation)."""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^#+\s*", "", text).strip()
    return text
