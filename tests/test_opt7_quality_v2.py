"""OPT-7: held-out quality evaluation harness (deterministic, offline)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "eval_quality_v2", ROOT / "scripts" / "eval_quality_v2.py")
evq = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(evq)


def test_held_out_dataset_is_distinct_from_training_set() -> None:
    held = json.loads((ROOT / "evaluations/quality_v2/held_out_relevance.json").read_text())
    train = json.loads((ROOT / "evaluations/rag_dataset.json").read_text())
    held_q = {r["question"] for r in held["relevance"]}
    train_q = {c["question"] for c in train["cases"]}
    assert not (held_q & train_q)  # no shared questions → genuinely held out


def _run_to_tmp(tmp_path) -> dict:
    """Run the evaluator into an isolated dir (never the committed artifacts)."""
    assert evq.main(out_dir=tmp_path) == 0
    return json.loads((tmp_path / "results.json").read_text())


def test_harness_runs_and_reports_expected_structure(tmp_path) -> None:
    report = _run_to_tmp(tmp_path)
    assert report["retrieval"]["hybrid"]["cases"] == 12
    assert report["tool_selection_accuracy"] == 1.0  # deterministic route table
    assert report["out_of_domain"]["ood_leaks_at_in_domain_min"] == 0
    assert report["llm_judge"]["status"] == "NOT RUN"  # never paid in CI


def test_ood_overlap_is_below_in_domain(tmp_path) -> None:
    ood = _run_to_tmp(tmp_path)["out_of_domain"]
    assert ood["ood_overlap_mean"] < ood["in_domain_overlap_min"]


def test_running_evaluator_does_not_touch_committed_artifacts(tmp_path) -> None:
    # Phase 8: pytest must not mutate the git-tracked evaluation artifacts.
    committed = ROOT / "evaluations/quality_v2/results.json"
    before = committed.read_text() if committed.exists() else None
    evq.main(out_dir=tmp_path)
    after = committed.read_text() if committed.exists() else None
    assert before == after  # committed artifact unchanged
