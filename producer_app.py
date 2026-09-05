"""Streamlit producer chat — Tailscale-accessible prompting UI."""

from __future__ import annotations

import os
import sys

import streamlit as st
import streamlit.components.v1 as components

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


def _local_code_digest() -> str:
    """Fingerprint mtimes of project modules Streamlit may cache across reruns."""
    import hashlib

    parts: list[str] = []
    analysis_dir = os.path.join(_REPO, "analysis")
    if os.path.isdir(analysis_dir):
        for name in sorted(os.listdir(analysis_dir)):
            if name.endswith(".py"):
                path = os.path.join(analysis_dir, name)
                parts.append(f"{path}:{os.path.getmtime(path):.6f}")
    for rel in ("drive_client.py", "main.py", "producer_app.py"):
        path = os.path.join(_REPO, rel)
        if os.path.isfile(path):
            parts.append(f"{path}:{os.path.getmtime(path):.6f}")
    formats_dir = os.path.join(_REPO, "formats")
    if os.path.isdir(formats_dir):
        for name in sorted(os.listdir(formats_dir)):
            if name.endswith(".py"):
                path = os.path.join(formats_dir, name)
                parts.append(f"{path}:{os.path.getmtime(path):.6f}")
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def _sync_local_modules() -> bool:
    """Drop cached project modules when tracked .py files change."""
    digest = _local_code_digest()
    prev = os.environ.get("PRODUCER_CODE_DIGEST")
    if prev == digest:
        return False
    for name in list(sys.modules):
        if name.startswith(("analysis.", "formats.")) or name in (
            "analysis",
            "formats",
            "drive_client",
            "main",
        ):
            del sys.modules[name]
    os.environ["PRODUCER_CODE_DIGEST"] = digest
    return True


_sync_local_modules()

from analysis.conversation_log import (  # noqa: E402
    list_conversations,
    log_turn,
    new_session_id,
    read_conversation,
)
from analysis.corpus import (  # noqa: E402
    SCOPE_ALL_COMPACT,
    SCOPE_ALL_FULL,
    SCOPE_ONE,
    build_corpus_bundle,
    format_first_user_message,
    load_catalog_rows,
)
from analysis.engine import (  # noqa: E402
    get_auto_job,
    load_prompts,
    run_chat_conversation,
    save_prompts,
)
from analysis.producer_config import (  # noqa: E402
    load_producer_config,
    persona_system,
    producer_model,
    save_producer_config,
)
from drive_client import (  # noqa: E402
    file_id_from_link,
    file_preview_embed_link,
    get_drive_service,
    read_file_text,
)
from formats.browse_view import (  # noqa: E402
    align_moments_with_lines,
    is_timestamped_body,
    parse_key_moments,
    parse_timestamped_body,
    parse_transcript_md,
)
from main import load_config  # noqa: E402


APP_TITLE = "32FRSFFL Producer Console"

PROMPT_TEMPLATE_VARS = (
    "{contestant}, {submitted_at}, {note}, {confessional_id}, "
    "{transcript_timestamps}, {transcript_text}, {video_link}"
)


def _load_cfg():
    config_path = os.environ.get("TRANSCRIBER_CONFIG", "config.json")
    return load_config(config_path)


def _init_chat_state():
    defaults = {
        "messages": [],
        "corpus_injected": False,
        "session_id": new_session_id(),
        "scope": SCOPE_ALL_COMPACT,
        "confessional_id": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _new_conversation():
    st.session_state.messages = []
    st.session_state.corpus_injected = False
    st.session_state.session_id = new_session_id()


def _chat_tab(cfg: dict, producer: dict):
    _init_chat_state()
    rows = load_catalog_rows(cfg)
    model = producer_model(cfg, producer)

    with st.sidebar:
        st.subheader("Scope")
        scope_labels = {
            SCOPE_ONE: "One confessional (full transcript)",
            SCOPE_ALL_COMPACT: "All confessionals (compact)",
            SCOPE_ALL_FULL: "All confessionals (full transcripts)",
        }
        scope = st.selectbox(
            "Context",
            options=list(scope_labels.keys()),
            format_func=lambda k: scope_labels[k],
            key="scope",
        )
        confessional_id = ""
        if scope == SCOPE_ONE:
            options = [
                (r.get("confessional_id", ""), r)
                for r in rows
                if r.get("confessional_id")
            ]
            if not options:
                st.warning("No ready confessionals in catalog")
            else:
                labels = [
                    f"{r.get('contestant', '?')} — {r.get('submitted_at', '')[:16]}"
                    for _, r in options
                ]
                idx = st.selectbox("Confessional", range(len(options)), format_func=lambda i: labels[i])
                confessional_id = options[idx][0]
                st.session_state.confessional_id = confessional_id

        st.caption(f"Model: `{model}`")
        if st.button("New conversation"):
            _new_conversation()
            st.rerun()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask about confessionals…")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    system = persona_system(cfg, producer)
    api_messages: list[dict[str, str]] = []
    if system:
        api_messages.append({"role": "system", "content": system})

    turn_meta = {"scope": scope}
    user_for_api = prompt
    if not st.session_state.corpus_injected:
        try:
            bundle, meta = build_corpus_bundle(
                cfg,
                scope,
                confessional_id=st.session_state.get("confessional_id") or confessional_id,
            )
            user_for_api = format_first_user_message(bundle, prompt, meta)
            turn_meta.update(meta)
            st.session_state.corpus_injected = True
        except ValueError as err:
            st.error(str(err))
            st.session_state.messages.pop()
            return

    history = st.session_state.messages[:-1]
    for msg in history:
        api_messages.append({"role": msg["role"], "content": msg["content"]})
    api_messages.append({"role": "user", "content": user_for_api})

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                reply = run_chat_conversation(api_messages, model=model)
            except Exception as err:
                st.error(f"Chat failed: {err}")
                st.session_state.messages.pop()
                return
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
    log_turn(
        cfg,
        session_id=st.session_state.session_id,
        scope=scope,
        user=prompt,
        assistant=reply,
        meta=turn_meta,
    )


def _pipeline_job_editor(job_id: str, label: str, job: dict | None) -> dict | None:
    """Render system/user/enabled fields; return updated job dict or None if missing."""
    if job is None:
        st.warning(f"No `{job_id}` job found in prompts.yaml auto_jobs.")
        return None
    enabled = st.checkbox(f"Enable {label}", value=bool(job.get("enabled", True)), key=f"job_{job_id}_enabled")
    system = st.text_area(
        "System prompt",
        value=str(job.get("system") or ""),
        height=120,
        key=f"job_{job_id}_system",
    )
    user = st.text_area(
        "User prompt template",
        value=str(job.get("user") or ""),
        height=220,
        key=f"job_{job_id}_user",
    )
    return {
        **job,
        "id": job_id,
        "enabled": enabled,
        "system": system,
        "user": user,
    }


def _settings_tab(cfg: dict, producer: dict):
    st.caption("Saving rewrites YAML files; inline comments in those files are not preserved.")

    with st.expander("Chat persona (producer.yaml)", expanded=True):
        st.caption("Applies to new chat conversations and daily summaries.")
        persona_system_val = st.text_area(
            "System prompt",
            value=persona_system(cfg, producer),
            height=200,
            key="settings_persona_system",
        )
        chat_model = st.text_input("OpenAI model", value=producer_model(cfg, producer), key="settings_chat_model")

    prompts_data = None
    prompts_error = ""
    try:
        prompts_data = load_prompts(cfg)
    except (FileNotFoundError, ValueError) as err:
        prompts_error = str(err)

    summary_job = None
    key_moments_job = None
    if prompts_data is not None:
        with st.expander("Summary prompt (prompts.yaml)", expanded=False):
            st.caption(f"Template variables: {PROMPT_TEMPLATE_VARS}")
            st.caption("Applies to the next confessional processed and --reanalyze runs.")
            summary_job = _pipeline_job_editor(
                "summary",
                "summary",
                get_auto_job(prompts_data, "summary"),
            )

        with st.expander("Key moments prompt (prompts.yaml)", expanded=False):
            st.caption(f"Template variables: {PROMPT_TEMPLATE_VARS}")
            st.caption("Applies to the next confessional processed and --reanalyze runs.")
            key_moments_job = _pipeline_job_editor(
                "key_moments",
                "key moments",
                get_auto_job(prompts_data, "key_moments"),
            )
    elif prompts_error:
        st.error(f"Could not load prompts.yaml: {prompts_error}")

    if st.button("Save settings", type="primary"):
        prod_data = load_producer_config(cfg)
        prod_data.setdefault("persona", {})["system"] = persona_system_val.strip()
        if chat_model.strip():
            prod_data["openai_model"] = chat_model.strip()
        save_producer_config(cfg, prod_data)

        if prompts_data is not None:
            updated = dict(prompts_data)
            jobs = list(updated.get("auto_jobs") or [])
            patches = {j["id"]: j for j in (summary_job, key_moments_job) if j}
            new_jobs = []
            for job in jobs:
                job_id = job.get("id")
                if job_id in patches:
                    merged = dict(job)
                    merged.update(patches[job_id])
                    new_jobs.append(merged)
                else:
                    new_jobs.append(job)
            updated["auto_jobs"] = new_jobs
            save_prompts(cfg, updated)

        st.success("Saved — chat persona updated; pipeline prompts apply to the next confessional and re-analyze runs.")


def _history_tab(cfg: dict):
    st.subheader("Recent conversations")
    entries = list_conversations(cfg)
    if not entries:
        st.info("No saved conversations yet.")
        return
    for entry in entries:
        label = f"{entry['day']} — {entry['preview'] or entry['session_id'][:8]}"
        with st.expander(label):
            turns = read_conversation(entry["path"])
            for turn in turns:
                st.markdown(f"**You** ({turn.get('ts', '')})")
                st.markdown(turn.get("user", ""))
                st.markdown("**Assistant**")
                st.markdown(turn.get("assistant", ""))
                st.divider()


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_transcript_md(file_id: str) -> str:
    cfg = _load_cfg()
    service = get_drive_service(cfg)
    return read_file_text(service, file_id)


def _video_file_id(row: dict[str, str]) -> str:
    return file_id_from_link(row.get("video_link", "")) or row.get("drive_file_id", "").strip()


def _render_browse_transcript(body: str, key_moments_text: str) -> None:
    moments = parse_key_moments(key_moments_text)

    if is_timestamped_body(body):
        lines = parse_timestamped_body(body)
        aligned = align_moments_with_lines(lines, moments)
        for browse_row in aligned:
            left, right = st.columns([3, 2])
            with left:
                if browse_row.transcript:
                    st.markdown(f"`{browse_row.time_label}` {browse_row.transcript}")
            with right:
                if browse_row.moment:
                    m = browse_row.moment
                    st.markdown(f"**{m.label}** — {m.description}")
        return

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Transcript**")
        st.markdown(body)
    with right:
        st.markdown("**Key moments**")
        if moments:
            for m in moments:
                st.markdown(f"**{m.label}** — {m.description}")
        else:
            st.caption("No key moments for this confessional.")


def _browse_tab(cfg: dict):
    st.subheader("Transcripts")
    rows = load_catalog_rows(cfg)
    if not rows:
        st.info("No ready confessionals in the catalog yet.")
        return

    rows = sorted(rows, key=lambda r: r.get("submitted_at", ""), reverse=True)
    contestants = sorted({r.get("contestant") or "Unknown" for r in rows})
    filter_name = st.selectbox("Filter by contestant", ["All"] + contestants, key="browse_contestant")
    if filter_name != "All":
        rows = [r for r in rows if (r.get("contestant") or "Unknown") == filter_name]
    if not rows:
        st.info("No confessionals for this contestant.")
        return

    labels = [
        f"{r.get('contestant', '?')} — {r.get('submitted_at', '')[:16]}"
        for r in rows
    ]
    idx = st.selectbox("Confessional", range(len(rows)), format_func=lambda i: labels[i], key="browse_pick")
    row = rows[idx]

    meta_col, links_col = st.columns(2)
    with meta_col:
        st.markdown(f"**Contestant:** {row.get('contestant') or 'Unknown'}")
        st.markdown(f"**Submitted:** {row.get('submitted_at', '')}")
        st.markdown(f"**Duration:** {row.get('duration', '')}")
        if row.get("note", "").strip():
            st.markdown(f"**Note:** {row.get('note', '').strip()}")
        if row.get("summary", "").strip():
            st.markdown(f"**Summary:** {row.get('summary', '').strip()}")
    with links_col:
        if row.get("video_link"):
            st.markdown(f"[Open video on Drive]({row['video_link']})")
        if row.get("transcript_md_link"):
            st.markdown(f"[Open transcript on Drive]({row['transcript_md_link']})")

    video_id = _video_file_id(row)
    embed_url = file_preview_embed_link(video_id)
    if embed_url:
        st.markdown("**Confessional video**")
        components.iframe(embed_url, height=480, scrolling=False)
    elif row.get("video_link") or row.get("drive_file_id"):
        st.caption("Video link present but could not build embed URL.")

    file_id = file_id_from_link(row.get("transcript_md_link", ""))
    if not file_id:
        st.warning("No transcript markdown link in catalog for this confessional.")
        return

    with st.spinner("Loading transcript…"):
        try:
            md = _fetch_transcript_md(file_id)
        except Exception as err:
            st.error(f"Could not load transcript: {err}")
            return

    if not md.strip():
        st.warning("Transcript file is empty.")
        return

    parsed = parse_transcript_md(md)
    st.divider()
    _render_browse_transcript(parsed["body"], parsed["key_moments"])


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🎬", layout="wide")
    cfg = _load_cfg()
    producer = load_producer_config(cfg)

    st.title(APP_TITLE)
    chat_tab, browse_tab, settings_tab, history_tab = st.tabs(["Chat", "Browse", "Settings", "History"])
    with chat_tab:
        _chat_tab(cfg, producer)
    with browse_tab:
        _browse_tab(cfg)
    with settings_tab:
        _settings_tab(cfg, producer)
    with history_tab:
        _history_tab(cfg)


if __name__ == "__main__":
    main()
