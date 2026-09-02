"""Offline coverage for the optional RAGAS evaluation layer.

These tests never make a network call — every RAGAS entry point is
injected/mocked. They are robust to RAGAS being installed OR absent: the
"missing package" paths are skipped when RAGAS is present, and an extra check
runs only when it is present. Evaluator credentials are always cleared so the
result never depends on the ambient environment.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.copilot.evaluation import ragas_adapter as ra
from src.copilot.models import ChatResponse, Citation, DocumentChunk, KnowledgeEvidence, RetrievalResult

ROOT = Path(__file__).resolve().parent.parent
_CLI_SPEC = importlib.util.spec_from_file_location(
    "eval_ragas", ROOT / "scripts" / "eval_ragas.py")
cli = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(cli)

_RAGAS_PRESENT = ra.ragas_available()


@pytest.fixture(autouse=True)
def _no_ambient_evaluator_creds(monkeypatch):
    """Credential-dependent behaviour must not depend on the ambient env."""
    for var in ("RAGAS_EVAL_API_KEY", "RAGAS_EVAL_BASE_URL", "RAGAS_EVAL_MODEL"):
        monkeypatch.delenv(var, raising=False)


# --- Fakes (no ragas import) -------------------------------------------------


def _fake_metrics(reference_free_only: bool):
    names = [ra.METRIC_FAITHFULNESS, ra.METRIC_RESPONSE_RELEVANCY, ra.METRIC_CONTEXT_PRECISION]
    if not reference_free_only:
        names.append(ra.METRIC_CONTEXT_RECALL)
    return [(n, None) for n in names]


def _fake_sample(case, *, with_reference: bool):
    return {"q": case.question, "ref": with_reference and case.has_reference}


def _fake_evaluate(samples, metrics, llm, embeddings):
    return {i: {name: 0.8 for name, _ in metrics} for i in range(len(samples))}


def _run(cases, **kw):
    return ra.run_ragas(
        cases, config=ra.EvaluatorConfig(api_key="x"),
        evaluate_fn=_fake_evaluate, build_metrics_fn=_fake_metrics,
        to_sample_fn=_fake_sample, **kw)


def _run_scores(cases, score_for):
    """Run with a custom per-index score generator (index -> value)."""
    def ev(samples, metrics, llm, embeddings):
        return {i: {name: score_for(i) for name, _ in metrics} for i in range(len(samples))}
    return ra.run_ragas(cases, config=ra.EvaluatorConfig(api_key="x"),
                        evaluate_fn=ev, build_metrics_fn=_fake_metrics,
                        to_sample_fn=_fake_sample)


def _service_result(answer="A data analyst interprets data [1].", *, with_evidence=True):
    evidence = [KnowledgeEvidence(
        evidence_id="e1", text="A data analyst collects and interprets data.",
        source_id="onet", source_title="O*NET", source_url="https://onet.org",
        evidence_type="role", retrieval_lane="structured_role")] if with_evidence else []
    retrieved = [RetrievalResult(
        chunk=DocumentChunk(chunk_id="c1", doc_id="d1", text="Analysts use SQL and dashboards.",
                            metadata={"title": "Skills"}), score=0.9)]
    return ChatResponse(
        answer=answer,
        citations=[Citation(marker="[1]", doc_id="onet", chunk_id="c1")],
        retrieved=retrieved, evidence=evidence)


# --- A/B: base app + lazy import --------------------------------------------


def test_A_base_app_imports_without_requiring_ragas() -> None:
    # The product runtime must import whether or not RAGAS is installed.
    import app  # noqa: F401
    from src.copilot.service import CareerIntelligenceService  # noqa: F401
    assert isinstance(ra.ragas_available(), bool)


def test_B_adapter_import_is_lazy() -> None:
    # A fresh interpreter importing only the adapter must NOT load ragas
    # (proves the imports are lazy regardless of whether ragas is installed).
    code = (
        "import sys; import src.copilot.evaluation.ragas_adapter as ra; "
        "print('ragas' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


@pytest.mark.skipif(_RAGAS_PRESENT, reason="ragas is installed in this environment")
def test_C_missing_package_raises_not_installed() -> None:
    with pytest.raises(ra.RagasNotInstalled):
        ra.run_ragas([ra.RagasEvalCase("c1", "q", "a")],
                     config=ra.EvaluatorConfig(api_key="x"))  # no evaluate_fn → real path


@pytest.mark.skipif(not _RAGAS_PRESENT, reason="requires ragas installed")
def test_C_installed_adapter_imports_work() -> None:
    # With the extra installed, the lazy RAGAS/LangChain imports resolve.
    llm, embeddings = ra._build_evaluator(ra.EvaluatorConfig(api_key="sk-test"))
    assert llm is not None and embeddings is not None
    metrics = ra._build_metrics(reference_free_only=False)
    assert {m[0] for m in metrics} == {
        ra.METRIC_FAITHFULNESS, ra.METRIC_RESPONSE_RELEVANCY,
        ra.METRIC_CONTEXT_PRECISION, ra.METRIC_CONTEXT_RECALL}


def test_C_cli_live_without_run_prerequisites_exits_zero() -> None:
    # No evaluator credentials (and, when absent, no package) → clean skip.
    assert cli.main(["--live"]) == 0


def test_D_missing_credentials_not_run() -> None:
    assert ra.evaluator_config_from_env() is None
    assert cli.main([]) == 0  # NOT RUN, exit 0
    assert cli.main(["--require-live"]) == 1  # explicit strict → non-zero


def test_D_run_ragas_without_config_raises() -> None:
    with pytest.raises(ra.RagasNotConfigured):
        ra.run_ragas([ra.RagasEvalCase("c1", "q", "a")], config=None,
                     evaluate_fn=_fake_evaluate)


def test_no_chat_fallback_unless_opted_in(monkeypatch) -> None:
    monkeypatch.delenv("RAGAS_EVAL_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-chat")
    assert ra.evaluator_config_from_env() is None  # chat key not reused by default
    assert ra.evaluator_config_from_env(allow_chat_fallback=True) is not None


# --- E/F/G: case conversion + privacy ---------------------------------------


def test_E_case_from_result_is_plain() -> None:
    case = ra.case_from_service_result("c1", "What does a data analyst do?",
                                       _service_result(), category="role")
    assert isinstance(case, ra.RagasEvalCase)
    assert case.question and case.answer
    json.dumps(case.as_dict())  # fully serialisable plain data


def test_F_private_fields_not_included() -> None:
    case = ra.case_from_service_result("c1", "q", _service_result(), category="role")
    blob = json.dumps(case.as_dict())
    assert "candidate_background" not in case.as_dict()
    assert "job_description" not in case.as_dict()
    assert set(case.metadata) <= {"category"}
    assert "candidate" not in blob.lower()


def test_G_contexts_from_response_evidence() -> None:
    case = ra.case_from_service_result("c1", "q", _service_result())
    assert any("collects and interprets" in c for c in case.retrieved_contexts)  # evidence
    assert any("SQL and dashboards" in c for c in case.retrieved_contexts)  # retrieved chunk
    assert "onet" in case.source_ids


# --- H/I/J: mocked metric parsing -------------------------------------------


def test_H_I_J_reference_free_metrics_parsed() -> None:
    cases = [ra.RagasEvalCase("c1", "q1", "a1", retrieved_contexts=["ctx"]),
             ra.RagasEvalCase("c2", "q2", "a2", retrieved_contexts=["ctx"])]
    run = _run(cases)
    assert run["metrics"][ra.METRIC_FAITHFULNESS] == 0.8
    assert run["metrics"][ra.METRIC_RESPONSE_RELEVANCY] == 0.8
    assert run["metrics"][ra.METRIC_CONTEXT_PRECISION] == 0.8
    assert run["per_case"][0][ra.METRIC_FAITHFULNESS] == 0.8


# --- K: context recall gating ------------------------------------------------


def test_K_context_recall_skipped_without_reference() -> None:
    cases = [ra.RagasEvalCase("c1", "q", "a", retrieved_contexts=["ctx"])]  # no reference
    run = _run(cases)
    assert run["context_recall_run"] is False
    assert ra.METRIC_CONTEXT_RECALL not in run["metric_names"]


def test_K_context_recall_runs_with_reference() -> None:
    cases = [ra.RagasEvalCase("c1", "q", "a", retrieved_contexts=["ctx"], reference="ref fact")]
    run = _run(cases)
    assert run["context_recall_run"] is True
    assert ra.METRIC_CONTEXT_RECALL in run["metric_names"]
    assert run["per_case"][0][ra.METRIC_CONTEXT_RECALL] == 0.8


# --- L/M: unique run directories, never overwrite ----------------------------


def _fake_run_dict():
    return {
        "metrics": {ra.METRIC_FAITHFULNESS: 0.8, ra.METRIC_RESPONSE_RELEVANCY: 0.7,
                    ra.METRIC_CONTEXT_PRECISION: 0.9},
        "per_case": [{"case_id": "c1", "category": "role",
                      ra.METRIC_FAITHFULNESS: 0.8, ra.METRIC_RESPONSE_RELEVANCY: 0.7,
                      ra.METRIC_CONTEXT_PRECISION: 0.9}],
        "metric_names": [ra.METRIC_FAITHFULNESS, ra.METRIC_RESPONSE_RELEVANCY,
                         ra.METRIC_CONTEXT_PRECISION],
        "metrics_with_scores": [ra.METRIC_FAITHFULNESS, ra.METRIC_RESPONSE_RELEVANCY,
                                ra.METRIC_CONTEXT_PRECISION],
        "context_recall_run": False, "referenced_case_count": 0, "case_count": 1,
        "valid_score_count": 3, "expected_score_count": 3, "failed_score_count": 0,
        "valid_case_count": 1, "score_coverage": 1.0, "status": ra.STATUS_COMPLETE,
    }


def test_L_run_writes_all_artifacts(tmp_path) -> None:
    from src.copilot.evaluation import ragas_runner as runner

    out = tmp_path / "20260101_000000"
    out.mkdir()
    runner.write_artifacts(out, _fake_run_dict(), ra.EvaluatorConfig(api_key="secret"),
                           "20260101_000000")
    for name in ("results.json", "results.csv", "summary.md", "run_config.json"):
        assert (out / name).is_file()
    # API key never written.
    assert "secret" not in (out / "run_config.json").read_text()
    assert "secret" not in (out / "results.json").read_text()


def test_M_second_run_does_not_overwrite_first(tmp_path) -> None:
    from src.copilot.evaluation import ragas_runner as runner

    a = tmp_path / "20260101_000000"; a.mkdir()
    b = tmp_path / "20260102_000000"; b.mkdir()
    runner.write_artifacts(a, _fake_run_dict(), ra.EvaluatorConfig(api_key="x"), "20260101_000000")
    before = (a / "results.json").read_text()
    runner.write_artifacts(b, _fake_run_dict(), ra.EvaluatorConfig(api_key="x"), "20260102_000000")
    assert (a / "results.json").read_text() == before  # first run untouched
    assert (b / "results.json").is_file()


# --- N/O: Evaluation UI helper (read-only) -----------------------------------


def test_N_ui_handles_no_ragas_runs(monkeypatch, tmp_path) -> None:
    from src.career import ui as career_ui

    monkeypatch.chdir(tmp_path)  # no evaluations/ragas/runs here
    assert career_ui._latest_ragas_run() is None


def test_O_ui_loads_latest_run(monkeypatch, tmp_path) -> None:
    from src.career import ui as career_ui

    runs = tmp_path / "evaluations" / "ragas" / "runs"
    (runs / "20260101_000000").mkdir(parents=True)
    (runs / "20260102_000000").mkdir(parents=True)
    (runs / "20260101_000000" / "results.json").write_text(
        json.dumps({"metrics": {"faithfulness": 0.5}, "run_config": {"timestamp": "old"}}))
    (runs / "20260102_000000" / "results.json").write_text(
        json.dumps({"metrics": {"faithfulness": 0.9}, "run_config": {"timestamp": "new"}}))
    monkeypatch.chdir(tmp_path)
    latest = career_ui._latest_ragas_run()
    assert latest is not None
    assert latest["run_config"]["timestamp"] == "new"  # newest by directory name


def test_O_evaluation_page_shows_not_run_state(monkeypatch) -> None:
    # The Evaluation page renders the RAGAS NOT-RUN state without executing RAGAS.
    # _latest_ragas_run is stubbed to None (no runs) — avoids depending on, or
    # mutating, the real CWD/store cache. (Its own logic is covered by test_N and
    # the skip-invalid tests.)
    import pathlib

    from streamlit.testing.v1 import AppTest

    from src.career import ui as career_ui

    monkeypatch.setattr(career_ui, "_latest_ragas_run", lambda: None)
    app_path = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
    at = AppTest.from_file(app_path, default_timeout=60)
    at.session_state["os_active_page"] = "Evaluation"
    at.run()
    assert not at.exception
    blob = " ".join(m.value for m in at.markdown) + " ".join(i.value for i in at.info)
    assert "RAGAS" in blob
    assert "No RAGAS run yet" in blob  # read-only NOT-RUN state, nothing executed


# --- Section 15: invalid-number handling (is_valid_score / aggregate / status) --


class TestInvalidScores:
    def test_is_valid_score_matrix(self) -> None:
        assert ra.is_valid_score(0.0) and ra.is_valid_score(1.0) and ra.is_valid_score(0.5)
        for bad in (float("nan"), float("inf"), float("-inf"), None, True, "0.5"):
            assert ra.is_valid_score(bad) is False

    def test_A_all_nan_aggregates_none_status_failed(self) -> None:
        cases = [ra.RagasEvalCase(f"c{i}", "q", "a", retrieved_contexts=["x"]) for i in range(3)]
        run = _run_scores(cases, lambda i: float("nan"))
        assert all(v is None for v in run["metrics"].values())
        assert run["valid_score_count"] == 0
        assert run["status"] == ra.STATUS_FAILED
        assert ra.has_usable_scores(run) is False

    def test_B_mixed_nan_and_finite_partial(self) -> None:
        cases = [ra.RagasEvalCase("c0", "q", "a", retrieved_contexts=["x"]),
                 ra.RagasEvalCase("c1", "q", "a", retrieved_contexts=["x"])]
        run = _run_scores(cases, lambda i: 0.6 if i == 0 else float("nan"))
        # NaN ignored; finite value averaged correctly.
        assert run["metrics"][ra.METRIC_FAITHFULNESS] == 0.6
        assert run["status"] == ra.STATUS_PARTIAL
        assert run["valid_score_count"] == 3 and run["expected_score_count"] == 6

    def test_C_positive_infinity_ignored(self) -> None:
        cases = [ra.RagasEvalCase("c0", "q", "a", retrieved_contexts=["x"])]
        run = _run_scores(cases, lambda i: float("inf"))
        assert all(v is None for v in run["metrics"].values())
        assert run["status"] == ra.STATUS_FAILED

    def test_D_negative_infinity_ignored(self) -> None:
        cases = [ra.RagasEvalCase("c0", "q", "a", retrieved_contexts=["x"])]
        run = _run_scores(cases, lambda i: float("-inf"))
        assert all(v is None for v in run["metrics"].values())

    def test_E_zero_is_valid(self) -> None:
        cases = [ra.RagasEvalCase("c0", "q", "a", retrieved_contexts=["x"])]
        run = _run_scores(cases, lambda i: 0.0)
        assert run["metrics"][ra.METRIC_FAITHFULNESS] == 0.0
        assert run["status"] == ra.STATUS_COMPLETE

    def test_F_one_is_valid(self) -> None:
        cases = [ra.RagasEvalCase("c0", "q", "a", retrieved_contexts=["x"])]
        run = _run_scores(cases, lambda i: 1.0)
        assert run["metrics"][ra.METRIC_FAITHFULNESS] == 1.0
        assert run["status"] == ra.STATUS_COMPLETE

    def test_G_none_ignored(self) -> None:
        cases = [ra.RagasEvalCase("c0", "q", "a", retrieved_contexts=["x"])]
        run = _run_scores(cases, lambda i: None)
        assert all(v is None for v in run["metrics"].values())
        assert run["status"] == ra.STATUS_FAILED


# --- Section 16: CLI guard (all-invalid → hard stop; partial/complete → write) --


def _mock_live(monkeypatch, run_dict):
    import src.copilot.config as cfgmod
    from src.copilot.evaluation import ragas_runner as runner

    class _Cfg:
        is_configured = True
        retrieval_mode = "hybrid"

    class _Svc:
        def answer(self, q):
            return _service_result()

    monkeypatch.setattr(ra, "ragas_available", lambda: True)
    monkeypatch.setattr(ra, "evaluator_config_from_env",
                        lambda **k: ra.EvaluatorConfig(api_key="x", base_url="https://x"))
    monkeypatch.setattr(cfgmod, "load_config", lambda: _Cfg())
    # The CLI delegates to the shared runner; mock its service builder + ra.run_ragas
    # so no real service or network is used.
    monkeypatch.setattr(runner, "_default_service", lambda config: _Svc())
    monkeypatch.setattr(ra, "run_ragas", lambda *a, **k: run_dict)


def _run_dict(status, metrics, *, valid, expected):
    return {
        "metrics": metrics,
        "per_case": [{"case_id": "c0", "category": "role", **{k: v for k, v in metrics.items()
                                                              if v is not None}}],
        "metric_names": list(metrics),
        "metrics_with_scores": [k for k, v in metrics.items() if v is not None],
        "context_recall_run": False, "referenced_case_count": 0, "case_count": 1,
        "valid_score_count": valid, "expected_score_count": expected,
        "failed_score_count": expected - valid,
        "valid_case_count": 1 if valid else 0,
        "score_coverage": round(valid / expected, 4) if expected else 0.0,
        "status": status,
    }


def test_cli_all_invalid_hard_stops(monkeypatch, tmp_path, capsys) -> None:
    failed = _run_dict(ra.STATUS_FAILED,
                       {"faithfulness": None, "response_relevancy": None,
                        "context_precision": None}, valid=0, expected=3)
    from src.copilot.evaluation import ragas_runner as runner

    _mock_live(monkeypatch, failed)
    called = {"write": False}
    monkeypatch.setattr(runner, "write_artifacts",
                        lambda *a, **k: called.__setitem__("write", True))
    out_dir = tmp_path / "run"
    rc = cli.main(["--live", "--limit", "1", "--output-dir", str(out_dir)])
    captured = capsys.readouterr().out
    assert rc == 2
    assert "RAGAS RUN FAILED" in captured
    assert called["write"] is False       # artifacts never written
    assert not out_dir.exists()           # directory never created


def test_cli_partial_writes_with_status(monkeypatch, tmp_path) -> None:
    partial = _run_dict(ra.STATUS_PARTIAL,
                        {"faithfulness": 0.6, "response_relevancy": 0.6,
                         "context_precision": 0.6}, valid=2, expected=3)
    _mock_live(monkeypatch, partial)
    out_dir = tmp_path / "run"
    rc = cli.main(["--live", "--limit", "1", "--output-dir", str(out_dir)])
    assert rc == 0
    for name in ("results.json", "results.csv", "summary.md", "run_config.json"):
        assert (out_dir / name).is_file()
    cfg = json.loads((out_dir / "run_config.json").read_text())
    assert cfg["status"] == ra.STATUS_PARTIAL and cfg["score_coverage"] > 0
    assert "PARTIAL" in (out_dir / "summary.md").read_text()


def test_cli_complete_writes_status_complete(monkeypatch, tmp_path) -> None:
    complete = _run_dict(ra.STATUS_COMPLETE,
                         {"faithfulness": 0.9, "response_relevancy": 0.8,
                          "context_precision": 0.7}, valid=3, expected=3)
    _mock_live(monkeypatch, complete)
    out_dir = tmp_path / "run"
    rc = cli.main(["--live", "--limit", "1", "--output-dir", str(out_dir)])
    assert rc == 0
    cfg = json.loads((out_dir / "run_config.json").read_text())
    assert cfg["status"] == ra.STATUS_COMPLETE


def test_cli_written_json_is_strict_no_nan(monkeypatch, tmp_path) -> None:
    # Even if a stray non-finite slipped through, allow_nan=False would fail loud.
    complete = _run_dict(ra.STATUS_COMPLETE,
                         {"faithfulness": 0.9, "response_relevancy": 0.8,
                          "context_precision": 0.7}, valid=3, expected=3)
    _mock_live(monkeypatch, complete)
    out_dir = tmp_path / "run"
    cli.main(["--live", "--limit", "1", "--output-dir", str(out_dir)])
    text = (out_dir / "results.json").read_text()
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)  # strict parse succeeds


# --- Section 17: UI skips invalid/legacy NaN runs ---------------------------


def test_ui_skips_all_nan_legacy_run(monkeypatch, tmp_path) -> None:
    from src.career import ui as career_ui

    runs = tmp_path / "evaluations" / "ragas" / "runs"
    (runs / "20260101_000000").mkdir(parents=True)   # older, valid
    (runs / "20260102_000000").mkdir(parents=True)   # newer, all-null (failed legacy)
    (runs / "20260101_000000" / "results.json").write_text(json.dumps(
        {"metrics": {"faithfulness": 0.7}, "run_config": {"timestamp": "valid"}}))
    (runs / "20260102_000000" / "results.json").write_text(json.dumps(
        {"metrics": {"faithfulness": None, "response_relevancy": None},
         "run_config": {"timestamp": "failed"}}))
    monkeypatch.chdir(tmp_path)
    latest = career_ui._latest_ragas_run()
    assert latest is not None
    assert latest["run_config"]["timestamp"] == "valid"  # skipped the newer invalid run
    assert latest["_invalid_ignored"] is True


def test_ui_returns_none_when_only_invalid_runs(monkeypatch, tmp_path) -> None:
    from src.career import ui as career_ui

    runs = tmp_path / "evaluations" / "ragas" / "runs"
    (runs / "20260101_000000").mkdir(parents=True)
    (runs / "20260101_000000" / "results.json").write_text(json.dumps(
        {"metrics": {"faithfulness": None}, "run_config": {"status": "FAILED"}}))
    monkeypatch.chdir(tmp_path)
    assert career_ui._latest_ragas_run() is None
