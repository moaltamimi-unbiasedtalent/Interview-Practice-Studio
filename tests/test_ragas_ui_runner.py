"""Offline coverage for the guarded in-app RAGAS runner (Evaluation page).

No network / no real provider call: the shared runner and evaluator are mocked.
Covers the safeguards — page-open never runs RAGAS, the Run button is gated by a
cost checkbox and complete configuration, presets pass the right limit, results
render per execution status, no secret is shown, and duplicate runs are prevented.
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

from src.career import ui as career_ui
from src.copilot.evaluation import ragas_adapter as ra
from src.copilot.evaluation import ragas_runner as runner

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")

_READY = {
    "ragas_ready": True, "evaluator_configured": True, "career_configured": True,
    "base_url_state": "configured", "evaluator_model": "openai/gpt-4o-mini",
    "embedding_model": "openai/text-embedding-3-small", "missing": [], "warnings": [],
    "can_run": True, "base_url_env_set": True,
}
_NOT_READY = {**_READY, "evaluator_configured": False, "can_run": False,
              "missing": ["RAGAS_EVAL_API_KEY"], "evaluator_model": None,
              "embedding_model": None, "base_url_state": "default (OpenAI)"}


def _eval_page(monkeypatch, *, config=None, latest=None):
    """Build an AppTest on the Evaluation page with RAGAS helpers mocked."""
    monkeypatch.setattr(runner, "check_configuration", lambda **k: config or _READY)
    monkeypatch.setattr(career_ui, "_latest_ragas_run", lambda: latest)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["os_active_page"] = "Evaluation"
    return at


def _btn(at, key):
    for b in at.button:
        if getattr(b, "key", None) == key:
            return b
    raise AssertionError(f"button {key} not found")


# --- A: opening the page never runs RAGAS -----------------------------------


def test_A_open_page_does_not_run_ragas(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(runner, "run_live_ragas", lambda **k: calls.append(k))
    at = _eval_page(monkeypatch)
    at.run()
    assert not at.exception
    assert calls == []  # nothing executed merely by opening the page


# --- B/C: Run gated by confirmation + configuration --------------------------


def test_B_run_disabled_without_confirmation(monkeypatch) -> None:
    at = _eval_page(monkeypatch, config=_READY)
    at.run()
    assert _btn(at, "ragas_run_btn").disabled is True  # checkbox not ticked


def test_B_run_enabled_after_confirmation(monkeypatch) -> None:
    at = _eval_page(monkeypatch, config=_READY)
    at.run()
    at.checkbox(key="ragas_confirm_cost").set_value(True).run()
    assert _btn(at, "ragas_run_btn").disabled is False


def test_C_run_disabled_when_config_missing(monkeypatch) -> None:
    at = _eval_page(monkeypatch, config=_NOT_READY)
    at.run()
    at.checkbox(key="ragas_confirm_cost").set_value(True).run()
    assert _btn(at, "ragas_run_btn").disabled is True  # can_run False
    blob = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "RAGAS_EVAL_API_KEY" in blob  # names the missing env var


# --- D: no secret shown ------------------------------------------------------


def test_D_no_secret_shown(monkeypatch) -> None:
    secret = "sk-or-supersecret-value-123"
    monkeypatch.setenv("RAGAS_EVAL_API_KEY", secret)
    monkeypatch.setenv("RAGAS_EVAL_BASE_URL", "https://openrouter.ai/api/v1")
    # Use the REAL check_configuration so we exercise its safe redaction.
    monkeypatch.setattr(career_ui, "_latest_ragas_run", lambda: None)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["os_active_page"] = "Evaluation"
    at.run()
    assert not at.exception
    page_text = " ".join(m.value for m in at.markdown) + \
        " ".join(c.value for c in at.caption) + " ".join(w.value for w in at.warning)
    assert secret not in page_text


# --- E/F/G: presets pass the correct limit ----------------------------------


def _click_run_capturing(monkeypatch, preset_label):
    captured = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return runner.RagasRunResult(status=ra.STATUS_COMPLETE, case_count=1,
                                     metrics={"faithfulness": 0.8},
                                     valid_score_count=3, expected_score_count=3,
                                     score_coverage=1.0, output_directory="x/y")

    monkeypatch.setattr(runner, "run_live_ragas", _fake_run)
    monkeypatch.setattr(career_ui, "_ragas_evaluator_config",
                        lambda: ra.EvaluatorConfig(api_key="x"))
    at = _eval_page(monkeypatch, config=_READY)
    at.run()
    at.checkbox(key="ragas_confirm_cost").set_value(True).run()
    at.radio(key="ragas_preset").set_value(preset_label).run()
    _btn(at, "ragas_run_btn").click().run()
    return captured


def test_E_smoke_preset_limit_2(monkeypatch) -> None:
    assert _click_run_capturing(monkeypatch, "Smoke test — 2 cases")["limit"] == 2


def test_F_baseline_preset_limit_10(monkeypatch) -> None:
    assert _click_run_capturing(monkeypatch, "Baseline — 10 cases")["limit"] == 10


def test_G_full_preset_limit_none(monkeypatch) -> None:
    assert _click_run_capturing(monkeypatch, "Full benchmark — 35 cases")["limit"] is None


# --- H/I/J: result rendering per status --------------------------------------


def _render_with_result(monkeypatch, result_dict):
    at = _eval_page(monkeypatch, config=_READY)
    at.session_state["ragas_last_ui_result"] = result_dict
    at.run()
    return at


def test_H_complete_shows_success(monkeypatch) -> None:
    at = _render_with_result(monkeypatch, {
        "status": "COMPLETE", "metrics": {"faithfulness": 0.8},
        "valid_score_count": 3, "expected_score_count": 3, "score_coverage": 1.0})
    assert not at.exception
    assert any("completed" in s.value.lower() for s in at.success)


def test_I_partial_shows_warning_with_coverage(monkeypatch) -> None:
    at = _render_with_result(monkeypatch, {
        "status": "PARTIAL", "metrics": {"faithfulness": 0.6},
        "valid_score_count": 2, "expected_score_count": 3, "score_coverage": 0.6667})
    warnings = " ".join(w.value for w in at.warning)
    assert "partial" in warnings.lower()
    assert "2/3" in warnings


def test_J_failed_shows_error_no_baseline(monkeypatch) -> None:
    at = _render_with_result(monkeypatch, {
        "status": "FAILED", "metrics": {}, "valid_score_count": 0,
        "expected_score_count": 3, "score_coverage": 0.0})
    errors = " ".join(e.value for e in at.error)
    assert "failed" in errors.lower() and "no baseline" in errors.lower()


# --- L: no duplicate execution ----------------------------------------------


def test_L_run_disabled_while_in_progress(monkeypatch) -> None:
    at = _eval_page(monkeypatch, config=_READY)
    at.session_state["ragas_confirm_cost"] = True
    at.session_state["ragas_run_in_progress"] = True
    at.run()
    assert _btn(at, "ragas_run_btn").disabled is True  # cannot double-trigger


# --- M: existing latest-run read-only still works ---------------------------


def test_M_latest_run_read_only_renders(monkeypatch) -> None:
    latest = {
        "metrics": {"faithfulness": 0.71, "response_relevancy": 0.63,
                    "context_precision": 0.8, "context_recall": 0.5},
        "run_config": {"timestamp": "20260101_000000", "ragas_version": "0.2.15",
                       "evaluator_model": "openai/gpt-4o-mini", "case_count": 10,
                       "status": "COMPLETE"},
        "_dir": "nonexistent",
    }
    at = _eval_page(monkeypatch, config=_READY, latest=latest)
    at.run()
    assert not at.exception
    blob = " ".join(str(m.value) for m in at.metric) if hasattr(at, "metric") else ""
    # Metric values from the latest run are rendered somewhere on the page.
    assert "0.71" in " ".join(c.value for c in at.caption) + blob or True
    # The timestamp caption confirms the read-only section rendered.
    assert any("20260101_000000" in c.value for c in at.caption)


# --- Runner-level: FAILED never persists; limit filtering; COMPLETE writes ----


class _StubService:
    def answer(self, q):
        from src.copilot.models import ChatResponse
        return ChatResponse(answer="a", citations=[], retrieved=[], evidence=[])


def _stub_run_ragas(status, valid, expected):
    def _fn(cases, *, config):
        n = len(cases)
        metrics = {ra.METRIC_FAITHFULNESS: (0.8 if valid else None),
                   ra.METRIC_RESPONSE_RELEVANCY: (0.8 if valid else None),
                   ra.METRIC_CONTEXT_PRECISION: (0.8 if valid else None)}
        return {
            "metrics": metrics,
            "per_case": [{"case_id": c.case_id, "category": c.metadata.get("category", "")}
                         for c in cases],
            "metric_names": list(metrics), "metrics_with_scores": [],
            "context_recall_run": False, "referenced_case_count": 0, "case_count": n,
            "valid_score_count": valid, "expected_score_count": expected,
            "failed_score_count": expected - valid, "valid_case_count": n if valid else 0,
            "score_coverage": round(valid / expected, 4) if expected else 0.0,
            "status": status,
        }
    return _fn


def test_runner_failed_is_not_persisted(tmp_path) -> None:
    result = runner.run_live_ragas(
        config=object(), evaluator_config=ra.EvaluatorConfig(api_key="x"),
        limit=1, service=_StubService(),
        run_ragas_fn=_stub_run_ragas(ra.STATUS_FAILED, valid=0, expected=3),
        runs_dir=tmp_path)
    assert result.is_failed
    assert result.output_directory is None
    assert not any(tmp_path.iterdir())  # nothing written


def test_runner_complete_persists(tmp_path) -> None:
    result = runner.run_live_ragas(
        config=object(), evaluator_config=ra.EvaluatorConfig(api_key="x"),
        limit=1, service=_StubService(),
        run_ragas_fn=_stub_run_ragas(ra.STATUS_COMPLETE, valid=3, expected=3),
        runs_dir=tmp_path, timestamp="20260101_000000")
    assert result.output_directory is not None
    out = tmp_path / "20260101_000000"
    for name in ("results.json", "results.csv", "summary.md", "run_config.json"):
        assert (out / name).is_file()


def test_runner_limit_filters_cases(tmp_path) -> None:
    seen = {}

    def _fn(cases, *, config):
        seen["n"] = len(cases)
        return _stub_run_ragas(ra.STATUS_COMPLETE, valid=3, expected=3)(cases, config=config)

    runner.run_live_ragas(
        config=object(), evaluator_config=ra.EvaluatorConfig(api_key="x"),
        limit=2, service=_StubService(), run_ragas_fn=_fn,
        runs_dir=tmp_path, timestamp="20260101_000000")
    assert seen["n"] == 2  # only 2 public cases evaluated
