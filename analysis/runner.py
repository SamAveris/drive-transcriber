"""Run configured auto_jobs against a transcript."""

from analysis.context import build_transcript_context
from analysis.engine import (
    default_analysis_model,
    load_prompts,
    one_sentence_summary,
    render_template,
    run_chat,
)
from transcript import TranscriptResult


def analysis_enabled(cfg: dict) -> bool:
    if not cfg.get("analysis_enabled", False):
        return False
    try:
        load_prompts(cfg)
    except (FileNotFoundError, ValueError):
        return False
    return True


def _job_model(job: dict, cfg: dict, prompts: dict) -> str:
    if job.get("model"):
        return str(job["model"])
    return default_analysis_model(cfg, prompts)


def run_auto_jobs(
    result: TranscriptResult,
    meta: dict,
    cfg: dict,
) -> dict[str, str]:
    """Run enabled auto_jobs. Returns {job_id: raw markdown/text content}."""
    prompts = load_prompts(cfg)
    context = build_transcript_context(result, meta)
    outputs: dict[str, str] = {}

    for job in prompts.get("auto_jobs", []):
        if not job.get("enabled", True):
            continue
        job_id = job.get("id")
        if not job_id:
            continue

        user_tpl = job.get("user", "")
        if not user_tpl.strip():
            continue

        system = render_template(job.get("system", ""), context)
        user = render_template(user_tpl, context)
        model = _job_model(job, cfg, prompts)

        print(f"[analysis] running job '{job_id}' ({model})...")
        outputs[job_id] = run_chat(system=system, user=user, model=model)

    return outputs


def catalog_fields_from_outputs(outputs: dict[str, str]) -> dict[str, str]:
    """Map analysis job outputs to catalog column values."""
    fields: dict[str, str] = {}
    if "summary" in outputs:
        fields["summary"] = one_sentence_summary(outputs["summary"])
    return fields
