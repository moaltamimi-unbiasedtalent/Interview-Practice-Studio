"""Shared orchestration for optional live RAGAS runs (CLI + Evaluation UI).

One place owns: loading the PUBLIC cases, filtering, building Career Intelligence,
generating answers, converting to plain eval cases, running RAGAS, validating the
result (COMPLETE / PARTIAL / FAILED via the finite-score guard), and persisting
artifacts to a unique timestamp directory. Both ``scripts/eval_ragas.py`` and the
Streamlit Evaluation page call :func:`run_live_ragas` — no duplicated logic, and
RAGAS never runs unless a caller explicitly asks.

Security: only ``evaluations/ragas/cases.json`` is evaluated (public benchmark).
No private candidate/JD/transcript/company data is ever read. API keys are never
returned, logged, or written.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.copilot.evaluation import ragas_adapter as ra

__all__ = [
    "CASES_PATH",
    "RUNS_DIR",
    "PRESETS",
    "RagasRunResult",
    "check_configuration",
    "run_live_ragas",
    "write_artifacts",
    "summary_markdown",
]

CASES_PATH = "evaluations/ragas/cases.json"
RUNS_DIR = Path("evaluations/ragas/runs")

# The ONLY case-count choices exposed in the UI (no free-form counts).
# label -> limit (None = full benchmark).
PRESETS: dict[str, int | None] = {
    "Smoke test — 2 cases": 2,
    "Baseline — 10 cases": 10,
    "Full benchmark — 35 cases": None,
}


@dataclass
class RagasRunResult:
    """Plain, safe result of a live RAGAS run (never contains keys/prompts)."""

    status: str  # COMPLETE | PARTIAL | FAILED
    case_count: int = 0
    metrics: dict = field(default_factory=dict)
    metric_names: list = field(default_factory=list)
    per_case: list = field(default_factory=list)
    valid_score_count: int = 0
    expected_score_count: int = 0
    failed_score_count: int = 0
    score_coverage: float = 0.0
    referenced_case_count: int = 0
    context_recall_run: bool = False
    output_directory: str | None = None
    error_category: str | None = None
    safe_message: str | None = None

    @property
    def is_failed(self) -> bool:
        return self.status == ra.STATUS_FAILED

    @property
    def persisted(self) -> bool:
        return self.output_directory is not None


# --- Safe configuration inspection ------------------------------------------


def check_configuration(*, allow_chat_fallback: bool = False) -> dict:
    """Return a SAFE view of RAGAS run readiness — never any secret value.

    Reports package availability, whether the evaluator credential and the Career
    Intelligence chat credential are configured, the (non-secret) evaluator model
    / embedding / base-URL disposition, the names of any missing env vars, and any
    configuration warnings (e.g. an OpenRouter-looking key with a default base URL).
    """
    import os

    ragas_ready = ra.ragas_available()
    evaluator = ra.evaluator_config_from_env(allow_chat_fallback=allow_chat_fallback)

    try:
        from src.copilot.config import load_config
        career_configured = bool(load_config().is_configured)
    except Exception:  # noqa: BLE001 - config must never crash the page
        career_configured = False

    missing: list[str] = []
    warnings: list[str] = []
    if not ragas_ready:
        missing.append("ragas package (pip install -e \".[evaluation]\")")
    if evaluator is None:
        missing.append("RAGAS_EVAL_API_KEY")
    if not career_configured:
        missing.append("Career Intelligence chat credential (e.g. COPILOT_API_KEY)")

    base_url_state = "default (OpenAI)"
    evaluator_model = None
    embedding_model = None
    if evaluator is not None:
        base_url_state = "configured" if evaluator.base_url else "default (OpenAI)"
        evaluator_model = evaluator.model
        embedding_model = evaluator.embedding_model
        # Safe heuristic (never exposes the key): an OpenRouter-style key sent to
        # the default OpenAI endpoint is the known all-NaN misconfiguration.
        looks_openrouter = (evaluator.api_key or "").startswith("sk-or-")
        if looks_openrouter and not evaluator.base_url:
            warnings.append(
                "The evaluator key looks like an OpenRouter key but no base URL is "
                "set. Set RAGAS_EVAL_BASE_URL=https://openrouter.ai/api/v1, or the "
                "evaluator will fail to authenticate.")

    return {
        "ragas_ready": ragas_ready,
        "evaluator_configured": evaluator is not None,
        "career_configured": career_configured,
        "base_url_state": base_url_state,
        "evaluator_model": evaluator_model,
        "embedding_model": embedding_model,
        "missing": missing,
        "warnings": warnings,
        "can_run": ragas_ready and evaluator is not None and career_configured,
        # RAGAS_EVAL_BASE_URL presence (name only; never the value).
        "base_url_env_set": bool(os.environ.get("RAGAS_EVAL_BASE_URL")),
    }


# --- Live run ----------------------------------------------------------------


def _load_filtered_cases(cases_path: str, category: str | None, limit: int | None):
    cases = ra.load_cases(cases_path)
    if category:
        cases = [c for c in cases if c.metadata.get("category") == category]
    if limit:
        cases = cases[:limit]
    return cases


def _default_service(config):
    from src.copilot.embeddings import build_embedder
    from src.copilot.knowledge.retrieval import build_default_coordinator
    from src.copilot.retrieval import build_retriever
    from src.copilot.service import CareerIntelligenceService
    from src.copilot.vectorstore import build_vector_store

    store = build_vector_store(config, embedder=build_embedder(config))
    retriever = build_retriever(config, mode=config.retrieval_mode, store=store)
    coordinator = build_default_coordinator(config)
    return CareerIntelligenceService(
        config=config, retriever=retriever, knowledge_coordinator=coordinator)


def run_live_ragas(
    *,
    config,
    evaluator_config,
    limit: int | None = None,
    category: str | None = None,
    persist: bool = True,
    cases_path: str = CASES_PATH,
    runs_dir: Path | str = RUNS_DIR,
    output_dir: str | None = None,
    service=None,
    service_factory=None,
    run_ragas_fn=None,
    timestamp: str | None = None,
) -> RagasRunResult:
    """Generate answers over the public cases and score them with RAGAS.

    Returns a plain :class:`RagasRunResult`. A FAILED run (no valid evaluator
    scores) is NEVER persisted — no directory or artifacts are created. The
    ``*_fn`` / ``service`` / ``timestamp`` hooks are injection points for offline
    tests; production uses the real defaults.
    """
    cases = _load_filtered_cases(cases_path, category, limit)
    if not cases:
        return RagasRunResult(status=ra.STATUS_FAILED, error_category="no_cases",
                              safe_message="No matching cases to evaluate.")

    if service is None:
        service = (service_factory or _default_service)(config)

    eval_cases = []
    for qc in cases:
        result = service.answer(qc.question)
        eval_cases.append(ra.case_from_service_result(
            qc.case_id, qc.question, result,
            category=qc.metadata.get("category"), reference=qc.reference))

    run = (run_ragas_fn or ra.run_ragas)(eval_cases, config=evaluator_config)

    base = RagasRunResult(
        status=run["status"],
        case_count=run["case_count"],
        metrics=run["metrics"],
        metric_names=run["metric_names"],
        per_case=run["per_case"],
        valid_score_count=run["valid_score_count"],
        expected_score_count=run["expected_score_count"],
        failed_score_count=run["failed_score_count"],
        score_coverage=run["score_coverage"],
        referenced_case_count=run["referenced_case_count"],
        context_recall_run=run["context_recall_run"],
    )

    # HARD STOP: an all-invalid run must not be persisted as a normal result.
    if not ra.has_usable_scores(run):
        base.error_category = "no_valid_scores"
        base.safe_message = (
            "Evaluator returned no valid scores. Check RAGAS_EVAL_API_KEY, "
            "RAGAS_EVAL_BASE_URL, RAGAS_EVAL_MODEL and RAGAS_EVAL_EMBEDDING_MODEL.")
        return base

    if persist:
        if timestamp is None:
            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = Path(output_dir) if output_dir else Path(runs_dir) / timestamp
        out.mkdir(parents=True, exist_ok=True)
        write_artifacts(out, run, evaluator_config, timestamp)
        base.output_directory = str(out)
    return base


# --- Artifact persistence (shared) ------------------------------------------


def _git_sha() -> str | None:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001 - git optional
        return None


def write_artifacts(out: Path, run: dict, evaluator, stamp: str) -> None:
    """Write results.csv/json, summary.md and run_config.json (strict JSON)."""
    import csv

    try:
        import ragas
        ragas_version = getattr(ragas, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        ragas_version = "unknown"

    run_config = {
        "timestamp": stamp,
        "ragas_version": ragas_version,
        "status": run["status"],
        "case_count": run["case_count"],
        "referenced_case_count": run["referenced_case_count"],
        "context_recall_run": run["context_recall_run"],
        "valid_score_count": run["valid_score_count"],
        "expected_score_count": run["expected_score_count"],
        "failed_score_count": run["failed_score_count"],
        "score_coverage": run["score_coverage"],
        "metric_names": run["metric_names"],
        "git_commit": _git_sha(),
        **evaluator.safe_dict(),  # never includes the API key
    }
    # allow_nan=False is a fail-loud backstop: no NaN/inf can reach JSON.
    (out / "run_config.json").write_text(
        json.dumps(run_config, indent=2, allow_nan=False), encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps({"metrics": run["metrics"], "per_case": run["per_case"],
                    "run_config": run_config}, indent=2, allow_nan=False),
        encoding="utf-8")

    fieldnames = ["case_id", "category", *run["metric_names"]]
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in run["per_case"]:
            writer.writerow(row)

    (out / "summary.md").write_text(summary_markdown(run, run_config), encoding="utf-8")


def _fmt(value) -> str:
    return f"{value}" if ra.is_valid_score(value) else "n/a"


def _avg(rows, name) -> str:
    vals = [float(r[name]) for r in rows if ra.is_valid_score(r.get(name))]
    return f"{round(sum(vals) / len(vals), 3)}" if vals else "n/a"


def summary_markdown(run: dict, run_config: dict) -> str:
    m = run["metrics"]
    lines = [
        "# RAGAS — generation quality\n",
        f"Run {run_config['timestamp']} · RAGAS {run_config['ragas_version']} · "
        f"evaluator `{run_config['evaluator_model']}` · {run['case_count']} case(s).",
        "Measured values (baseline — not pass/fail). Optional secondary layer; the "
        "deterministic retrieval evaluations remain the primary gate.\n",
        "## Execution status\n",
        f"Status: **{run['status']}**",
        f"Valid scores: {run['valid_score_count']} / {run['expected_score_count']}",
        f"Score coverage: {round(run['score_coverage'] * 100, 1)}%",
        ("\n_Some evaluator jobs did not return valid numeric scores. Metrics below "
         "are aggregated only from valid scores. This is technical evaluation "
         "coverage, not model quality._" if run["status"] == ra.STATUS_PARTIAL else ""),
        "",
        "## Overall\n",
        f"- Faithfulness: **{_fmt(m.get(ra.METRIC_FAITHFULNESS))}**",
        f"- Response Relevancy: **{_fmt(m.get(ra.METRIC_RESPONSE_RELEVANCY))}**",
        f"- Context Precision: **{_fmt(m.get(ra.METRIC_CONTEXT_PRECISION))}**",
        f"- Context Recall: **{_fmt(m.get(ra.METRIC_CONTEXT_RECALL))}** "
        f"({run['referenced_case_count']} referenced case(s))"
        if run["context_recall_run"] else
        "- Context Recall: not run (no referenced cases in this selection)",
        "",
        "## By category\n",
        "| Category | n | Faithfulness | Response Relevancy | Context Precision |",
        "|---|---|---|---|---|",
    ]
    by_cat: dict[str, list] = {}
    for row in run["per_case"]:
        by_cat.setdefault(row.get("category", ""), []).append(row)
    for cat in sorted(by_cat):
        rows = by_cat[cat]
        lines.append(
            f"| {cat or '—'} | {len(rows)} | "
            f"{_avg(rows, ra.METRIC_FAITHFULNESS)} | "
            f"{_avg(rows, ra.METRIC_RESPONSE_RELEVANCY)} | "
            f"{_avg(rows, ra.METRIC_CONTEXT_PRECISION)} |")

    lowest = sorted(
        (r for r in run["per_case"] if ra.is_valid_score(r.get(ra.METRIC_FAITHFULNESS))),
        key=lambda r: r[ra.METRIC_FAITHFULNESS])[:5]
    if lowest:
        lines += ["", "## Lowest-faithfulness cases (review, not automatic failures)\n"]
        for r in lowest:
            lines.append(f"- `{r['case_id']}` — faithfulness {r[ra.METRIC_FAITHFULNESS]}")
    return "\n".join(lines) + "\n"
