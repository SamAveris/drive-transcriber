"""Streamlit producer chat — Tailscale-accessible prompting UI."""

from __future__ import annotations

import os
import sys

import streamlit as st

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

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
from analysis.engine import run_chat_conversation  # noqa: E402
from analysis.producer_config import (  # noqa: E402
    load_producer_config,
    persona_system,
    producer_model,
    save_producer_config,
)
from main import load_config  # noqa: E402


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


def _settings_tab(cfg: dict, producer: dict):
    st.subheader("Producer persona")
    st.caption("Changes apply to new conversations and daily summaries.")
    system = st.text_area(
        "System prompt",
        value=persona_system(cfg, producer),
        height=240,
    )
    model = st.text_input("OpenAI model", value=producer_model(cfg, producer))
    if st.button("Save settings"):
        data = load_producer_config(cfg)
        data.setdefault("persona", {})["system"] = system.strip()
        if model.strip():
            data["openai_model"] = model.strip()
        save_producer_config(cfg, data)
        st.success("Saved to producer.yaml")


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


def main():
    st.set_page_config(page_title="Producer chat", page_icon="🎬", layout="wide")
    cfg = _load_cfg()
    producer = load_producer_config(cfg)

    st.title("Producer chat")
    chat_tab, settings_tab, history_tab = st.tabs(["Chat", "Settings", "History"])
    with chat_tab:
        _chat_tab(cfg, producer)
    with settings_tab:
        _settings_tab(cfg, producer)
    with history_tab:
        _history_tab(cfg)


if __name__ == "__main__":
    main()
