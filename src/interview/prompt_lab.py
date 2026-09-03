"""Prompt Lab — developer-only prompt/model experimentation (Advanced view).

Extracted from ``src/interview/studio_app.py`` (behaviour unchanged) to keep that
module focused on the candidate interview flow. This is developer tooling: it runs
the fixed, profession-neutral comparison scenarios from ``scripts/`` and every
live run is gated behind an explicit "chargeable requests" confirmation.

Public entry point: :func:`render_prompt_lab`. The service builders live in
``studio_app`` and are imported lazily inside the run handlers so importing this
module never creates an import cycle.
"""

from __future__ import annotations

import json

import streamlit as st

from scripts import compare_model_settings as cm
from scripts import compare_prompts as cp
from src.config import AppConfig


def render_prompt_lab(config: AppConfig) -> None:
    st.subheader("Prompt Lab")
    st.caption(
        "Developer experimentation only. The candidate interview lives under "
        "the 'Interview' view."
    )
    _lab_scenario_summary()
    st.info(
        "Placeholder results live in `evaluations/`. No requests are made until "
        "you run a comparison below."
    )
    if not config.is_configured:
        st.warning("Add an OpenRouter API key to run live comparisons.")
    prompt_tab, settings_tab = st.tabs(["Prompt comparison", "Model settings"])
    with prompt_tab:
        _render_prompt_comparison_tab(config)
    with settings_tab:
        _render_model_settings_tab(config)


def _lab_scenario_summary() -> None:
    config, question, answer = cp.build_scenario()
    st.markdown("**Fixed scenario (profession-neutral)**")
    st.write(
        f"Role: {config.target_role} · Sector: {config.industry_or_sector} · "
        f"Level: {config.career_level} · Type: {config.interview_types[0]}"
    )
    st.write(f"Question: {question}")
    st.write(f"Candidate answer: {answer}")


def _results_table(rows: list[dict]) -> list[dict]:
    return [
        {
            "Variant": row.get("technique_name")
            or f"temp {row.get('temperature')} / {row.get('token_setting')}",
            "Valid JSON": row["valid_json"],
            "Prompt tok": row["prompt_tokens"],
            "Completion tok": row["completion_tokens"],
            "Cost USD": row["cost_usd"],
            "Latency s": row["latency_seconds"],
            "Overall": row["overall_score"],
        }
        for row in rows
    ]


def _render_prompt_comparison_tab(config: AppConfig) -> None:
    from src.interview.studio_app import build_services, get_pricing_service

    count = cp.planned_request_count()
    st.write(
        "Runs all five techniques on the fixed scenario with the model, "
        f"temperature and token limit held constant — **{count} chargeable "
        "requests**."
    )
    st.caption(
        f"Fixed: model `{cp.FIXED_MODEL}`, temperature {cp.FIXED_TEMPERATURE}, "
        f"max tokens {cp.FIXED_MAX_TOKENS}."
    )
    confirm = st.checkbox(
        f"I confirm sending {count} chargeable requests", key="pl_prompts_confirm"
    )
    if st.button(
        "Run prompt comparison",
        key="pl_prompts_run",
        disabled=not (confirm and config.is_configured),
    ):
        pricing = get_pricing_service()
        _, evaluation_service, _, client = build_services(config, pricing)
        try:
            with st.spinner("Running comparison…"):
                st.session_state["pl_prompt_rows"] = cp.run_prompt_comparison(
                    evaluation_service
                )
        finally:
            client.close()

    rows = st.session_state.get("pl_prompt_rows")
    if rows:
        st.dataframe(_results_table(rows))
        st.download_button(
            "Download JSON",
            data=json.dumps(cp.build_report(rows, live=True), indent=2),
            file_name="prompt_comparison.json",
            mime="application/json",
            key="pl_prompts_dl",
        )
        st.caption(
            "Longer output is not better — score the manual dimensions in "
            "`evaluations/prompt_comparison.md`."
        )


def _render_model_settings_tab(config: AppConfig) -> None:
    from src.interview.studio_app import build_services, get_pricing_service

    count = cm.planned_request_count()
    st.write(
        "Sweeps temperature (0.1, 0.5, 0.9) and concise/detailed token limits "
        f"with the model and technique held constant — up to **{count} "
        "chargeable requests** (fewer if the model lacks temperature support)."
    )
    st.caption(
        f"Fixed: model `{cm.FIXED_MODEL}`, technique {cm.FIXED_TECHNIQUE}."
    )
    confirm = st.checkbox(
        f"I confirm sending up to {count} chargeable requests",
        key="pl_settings_confirm",
    )
    if st.button(
        "Run model-setting sweep",
        key="pl_settings_run",
        disabled=not (confirm and config.is_configured),
    ):
        pricing = get_pricing_service()
        _, evaluation_service, _, client = build_services(config, pricing)
        try:
            with st.spinner("Running sweep…"):
                supported = pricing.supported_parameters(cm.FIXED_MODEL)
                rows, _ = cm.run_model_settings_comparison(
                    evaluation_service, supported
                )
                st.session_state["pl_settings_rows"] = rows
        finally:
            client.close()

    rows = st.session_state.get("pl_settings_rows")
    if rows:
        st.dataframe(_results_table(rows))
        st.caption(
            "Judge completeness, specificity and consistency manually in "
            "`evaluations/model_settings_comparison.md`."
        )
