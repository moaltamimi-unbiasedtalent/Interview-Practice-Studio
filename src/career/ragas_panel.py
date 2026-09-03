"""RAGAS panel for the Career Intelligence Evaluation page.

Extracted from ``src/career/ui.py`` (behaviour unchanged) to keep that module
focused. RAGAS is an *optional* live generation-quality layer: this panel shows
the latest saved run read-only and hosts the guarded, user-triggered runner. It
never executes RAGAS on page open and never makes a provider call in CI.

Public entry point: :func:`render_ragas_section`. Everything else is private and
imported lazily so the panel adds no import cost when RAGAS is not used.
"""

from __future__ import annotations

import streamlit as st

__all__ = ["render_ragas_section"]


def render_ragas_section() -> None:
    """Show the latest RAGAS run (read-only). RAGAS is never executed from the UI."""
    st.caption(
        "Retrieval metrics tell us whether the system found relevant evidence. "
        "RAGAS evaluates whether the generated answer used that evidence "
        "faithfully and answered the question. RAGAS is an optional live layer "
        "(LLM-judged, with cost) and does not run in CI or from this page."
    )
    run = _latest_ragas_run()
    if run is None:
        st.info(
            "No RAGAS run yet. RAGAS is an optional live evaluation layer and does "
            "not run in CI. Run one below, or with "
            "`python scripts/eval_ragas.py --live` (needs evaluator credentials)."
        )
    else:
        _render_latest_ragas_run(run)

    _render_ragas_metric_legend()
    _render_ragas_runner()


def _ragas_run_usable(data: dict) -> bool:
    """A usable RAGAS run has at least one finite aggregate metric.

    New runs also carry an explicit status; a FAILED status is never usable.
    Legacy runs (no status) are judged purely on metric finiteness, so an
    all-NaN/null legacy run is correctly rejected as a baseline.
    """
    from src.copilot.evaluation.ragas_adapter import STATUS_FAILED, is_valid_score

    if (data.get("run_config", {}) or {}).get("status") == STATUS_FAILED:
        return False
    return any(is_valid_score(v) for v in (data.get("metrics") or {}).values())


def _latest_ragas_run() -> dict | None:
    """Load the most recent USABLE RAGAS run's results.json, or None.

    Never executes RAGAS. Invalid runs (all-NaN/null legacy runs, or FAILED runs)
    are skipped in favour of the newest usable prior run; ``_invalid_ignored`` on
    the returned dict flags that at least one newer invalid run was skipped.
    """
    import json
    import os

    runs_dir = "evaluations/ragas/runs"
    if not os.path.isdir(runs_dir):
        return None
    run_dirs = sorted(
        (d for d in os.listdir(runs_dir) if os.path.isdir(os.path.join(runs_dir, d))),
        reverse=True,
    )
    skipped_invalid = False
    for name in run_dirs:
        path = os.path.join(runs_dir, name, "results.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)  # strict JSON; NaN would raise here
        except (OSError, ValueError):
            skipped_invalid = True  # unreadable / non-standard JSON (e.g. NaN)
            continue
        if not _ragas_run_usable(data):
            skipped_invalid = True
            continue
        data["_dir"] = os.path.join(runs_dir, name)
        data["_invalid_ignored"] = skipped_invalid
        return data
    return None


def _render_latest_ragas_run(run: dict) -> None:
    """Read-only view of the latest usable RAGAS run."""
    import os

    if run.get("_invalid_ignored"):
        st.warning("A more recent RAGAS run was invalid (no valid evaluator scores) "
                   "and is not used as a baseline. Showing the latest usable run.")
    metrics = run.get("metrics", {})
    cfg = run.get("run_config", {})
    status = cfg.get("status")
    st.caption(
        f"Last run: {cfg.get('timestamp', '—')} · RAGAS {cfg.get('ragas_version', '—')} · "
        f"evaluator `{cfg.get('evaluator_model', '—')}` · {cfg.get('case_count', '—')} case(s)."
    )
    if status == "PARTIAL":
        st.warning(
            "This RAGAS run completed with partial evaluator coverage "
            f"({cfg.get('valid_score_count', '?')}/{cfg.get('expected_score_count', '?')} "
            "valid scores). Metrics aggregate only valid scores — this is technical "
            "coverage, not model quality."
        )
    cols = st.columns(4)
    cols[0].metric("Faithfulness", _ragas_val(metrics.get("faithfulness")))
    cols[1].metric("Response Relevancy", _ragas_val(metrics.get("response_relevancy")))
    cols[2].metric("Context Precision", _ragas_val(metrics.get("context_precision")))
    cols[3].metric("Context Recall", _ragas_val(metrics.get("context_recall")))
    st.caption("Measured baseline values (not pass/fail). The deterministic "
               "retrieval evaluations above remain the primary quality gate.")

    summary_path = os.path.join(run.get("_dir", ""), "summary.md")
    if os.path.isfile(summary_path):
        with st.expander("View latest RAGAS report"):
            with open(summary_path, encoding="utf-8") as handle:
                st.markdown(handle.read())


def _render_ragas_metric_legend() -> None:
    """Plain-language metric meanings + the execution-status explainer."""
    with st.expander("What do the RAGAS metrics mean?"):
        st.markdown(
            "- **Faithfulness** — are the answer's claims supported by the "
            "retrieved evidence?\n"
            "- **Response Relevancy** — did the answer directly address the "
            "user's question?\n"
            "- **Context Precision** — was the retrieved evidence useful rather "
            "than noisy?\n"
            "- **Context Recall** — did retrieval capture enough evidence for the "
            "reference answer? (only cases with a reference)\n\n"
            "Higher is generally better. Scores are benchmark signals, not "
            "percentages of factual accuracy, and there are no pass/fail thresholds."
        )
    with st.expander("What do COMPLETE / PARTIAL / FAILED mean?"):
        st.markdown(
            "- **COMPLETE** — every expected evaluator metric produced a finite "
            "score.\n"
            "- **PARTIAL** — at least one valid score exists, but some evaluator "
            "jobs did not produce a valid score.\n"
            "- **FAILED** — no valid evaluator scores were returned; the run is "
            "not saved as a baseline.\n\n"
            "Score coverage measures evaluator execution completeness, not answer "
            "quality."
        )


def _render_ragas_runner() -> None:
    """Guarded, user-triggered RAGAS run controls. Never runs on page open."""
    from src.copilot.evaluation import ragas_runner as runner

    st.markdown("**Run a new RAGAS evaluation**")
    st.caption(
        "RAGAS uses evaluator LLM and embedding calls and may incur provider cost. "
        "It never runs automatically. Only the public benchmark set "
        "(`evaluations/ragas/cases.json`) is evaluated — never your chat, "
        "candidate background, job description, or company files."
    )

    status = runner.check_configuration()
    _render_ragas_config_status(status)
    for warning in status["warnings"]:
        st.warning(warning)

    preset_label = st.radio("Scope", list(runner.PRESETS), index=0,
                            key="ragas_preset", horizontal=True)
    confirmed = st.checkbox("I understand this evaluation makes live provider calls.",
                            key="ragas_confirm_cost")

    disabled = not (status["can_run"] and confirmed) or st.session_state.get(
        "ragas_run_in_progress", False)
    if not status["can_run"]:
        st.caption("Run is disabled until configuration is complete (see above).")

    if st.button("Run RAGAS evaluation", type="primary", disabled=disabled,
                 key="ragas_run_btn"):
        _execute_ragas_run(runner, preset_label)

    _render_last_ui_run_result()


def _render_ragas_config_status(status: dict) -> None:
    """Show SAFE configuration status — never any secret value."""
    def _tick(ok: bool) -> str:
        return "✅" if ok else "❌"

    cols = st.columns(3)
    cols[0].caption(f"{_tick(status['ragas_ready'])} RAGAS package")
    cols[1].caption(f"{_tick(status['evaluator_configured'])} Evaluator credential")
    cols[2].caption(f"{_tick(status['career_configured'])} Career model")
    if status["evaluator_configured"]:
        st.caption(
            f"Base URL: {status['base_url_state']} · "
            f"Evaluator model: `{status['evaluator_model']}` · "
            f"Embedding model: `{status['embedding_model']}`"
        )
    if status["missing"]:
        st.caption("Missing: " + ", ".join(status["missing"]))


def _execute_ragas_run(runner, preset_label: str) -> None:
    """Run RAGAS once, guarding against duplicate execution within a rerun."""
    if st.session_state.get("ragas_run_in_progress"):
        return
    st.session_state["ragas_run_in_progress"] = True
    limit = runner.PRESETS[preset_label]
    try:
        from src.copilot.config import load_config

        evaluator = _ragas_evaluator_config()
        scope = "full benchmark" if limit is None else f"{limit}-case"
        with st.spinner(f"Running {scope} RAGAS evaluation. This may take several "
                        "minutes and makes live provider calls…"):
            result = runner.run_live_ragas(
                config=load_config(), evaluator_config=evaluator, limit=limit)
        st.session_state["ragas_last_ui_result"] = _safe_ui_result(result)
    except Exception:  # noqa: BLE001 - never surface a raw traceback / secret
        st.session_state["ragas_last_ui_result"] = {
            "status": "ERROR",
            "message": "The RAGAS run could not be completed. Check the evaluator "
                       "configuration and try again.",
        }
    finally:
        st.session_state["ragas_run_in_progress"] = False
    st.rerun()


def _ragas_evaluator_config():
    from src.copilot.evaluation import ragas_adapter as ra

    return ra.evaluator_config_from_env()


def _safe_ui_result(result) -> dict:
    """Bounded, secret-free snapshot of a run result for session state."""
    return {
        "status": result.status,
        "metrics": dict(result.metrics),
        "valid_score_count": result.valid_score_count,
        "expected_score_count": result.expected_score_count,
        "score_coverage": result.score_coverage,
        "output_directory": result.output_directory,
        "safe_message": result.safe_message,
    }


def _render_last_ui_run_result() -> None:
    """Render the outcome of the last UI-triggered run (from session state)."""
    res = st.session_state.get("ragas_last_ui_result")
    if not res:
        return
    status = res.get("status")
    if status == "COMPLETE":
        st.success("RAGAS evaluation completed.")
    elif status == "PARTIAL":
        st.warning(
            "RAGAS evaluation completed with partial evaluator coverage. Metrics "
            f"use valid scores only ({res.get('valid_score_count')}/"
            f"{res.get('expected_score_count')}, "
            f"{round(res.get('score_coverage', 0) * 100, 1)}% coverage).")
    elif status == "FAILED":
        st.error(
            "RAGAS evaluation failed. No valid evaluator scores were returned. "
            "No baseline was saved.")
        st.caption("Check RAGAS_EVAL_API_KEY, RAGAS_EVAL_BASE_URL, RAGAS_EVAL_MODEL "
                   "and RAGAS_EVAL_EMBEDDING_MODEL.")
        return
    else:  # ERROR
        st.error(res.get("message", "The RAGAS run could not be completed."))
        return

    metrics = res.get("metrics", {})
    cols = st.columns(4)
    cols[0].metric("Faithfulness", _ragas_val(metrics.get("faithfulness")))
    cols[1].metric("Response Relevancy", _ragas_val(metrics.get("response_relevancy")))
    cols[2].metric("Context Precision", _ragas_val(metrics.get("context_precision")))
    cols[3].metric("Context Recall", _ragas_val(metrics.get("context_recall")))


def _ragas_val(value) -> str:
    from src.copilot.evaluation.ragas_adapter import is_valid_score

    return f"{value}" if is_valid_score(value) else "n/a"
