"""Optional RAGAS generation-quality adapter (isolated from production runtime).

RAGAS is an OPTIONAL secondary evaluation layer. This module:

* defines a plain, RAGAS-independent evaluation contract (:class:`RagasEvalCase`);
* converts a Career Intelligence result into that plain contract (no LangChain /
  Chroma / SQLite / Streamlit objects, and no private candidate/JD content);
* lazy-imports RAGAS and the evaluator model only when a live run is requested;
* normalises RAGAS output to plain dictionaries.

Nothing here is imported by the chat runtime — the app works identically when
RAGAS is not installed. Missing package or missing evaluator credentials degrade
to a clean, explicit skip, never a crash.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

__all__ = [
    "RagasEvalCase",
    "EvaluatorConfig",
    "RagasNotInstalled",
    "RagasNotConfigured",
    "ragas_available",
    "evaluator_config_from_env",
    "case_from_service_result",
    "load_cases",
    "run_ragas",
    "is_valid_score",
    "has_usable_scores",
    "STATUS_COMPLETE",
    "STATUS_PARTIAL",
    "STATUS_FAILED",
    "METRIC_FAITHFULNESS",
    "METRIC_RESPONSE_RELEVANCY",
    "METRIC_CONTEXT_PRECISION",
    "METRIC_CONTEXT_RECALL",
]

# Deterministic execution-status labels (technical validity, NOT model quality).
STATUS_COMPLETE = "COMPLETE"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"


def is_valid_score(value) -> bool:
    """A usable metric score is a finite real number (not bool, NaN, or inf)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def has_usable_scores(run: dict) -> bool:
    """True if the run produced at least one valid (finite) evaluator score."""
    return int(run.get("valid_score_count", 0)) > 0

# Project-facing metric names (stable; independent of RAGAS column renames).
METRIC_FAITHFULNESS = "faithfulness"
METRIC_RESPONSE_RELEVANCY = "response_relevancy"
METRIC_CONTEXT_PRECISION = "context_precision"
METRIC_CONTEXT_RECALL = "context_recall"

_MAX_CONTEXTS = 20
_MAX_CONTEXT_CHARS = 2000


class RagasNotInstalled(RuntimeError):
    """Raised when a live RAGAS run is requested but the package is absent."""


class RagasNotConfigured(RuntimeError):
    """Raised when a live RAGAS run is requested without evaluator credentials."""


@dataclass
class RagasEvalCase:
    """A plain, RAGAS-independent evaluation record (safe to serialise)."""

    case_id: str
    question: str
    answer: str
    retrieved_contexts: list[str] = field(default_factory=list)
    reference: str | None = None
    reference_contexts: list[str] | None = None
    source_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def has_reference(self) -> bool:
        return bool((self.reference or "").strip())

    def as_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "question": self.question,
            "answer": self.answer,
            "retrieved_contexts": list(self.retrieved_contexts),
            "reference": self.reference,
            "reference_contexts": self.reference_contexts,
            "source_ids": list(self.source_ids),
            "metadata": dict(self.metadata),
        }


@dataclass
class EvaluatorConfig:
    """Evaluator-model configuration, independent of production chat."""

    api_key: str
    model: str = "gpt-4o-mini"
    base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"

    def safe_dict(self) -> dict:
        """Config for run_config.json — NEVER includes the API key."""
        return {
            "evaluator_model": self.model,
            "evaluator_base_url": self.base_url or "default",
            "evaluator_embedding_model": self.embedding_model,
        }


def ragas_available() -> bool:
    """True if the RAGAS package can be imported (no side effects on the app)."""
    import importlib.util

    return importlib.util.find_spec("ragas") is not None


def evaluator_config_from_env(*, allow_chat_fallback: bool = False) -> EvaluatorConfig | None:
    """Build evaluator config from ``RAGAS_EVAL_*`` env vars, or ``None``.

    The production chat credential is only reused when ``allow_chat_fallback`` is
    explicitly set (the CLI exposes this behind an opt-in flag).
    """
    api_key = os.environ.get("RAGAS_EVAL_API_KEY")
    base_url = os.environ.get("RAGAS_EVAL_BASE_URL")
    model = os.environ.get("RAGAS_EVAL_MODEL", "gpt-4o-mini")
    embedding_model = os.environ.get("RAGAS_EVAL_EMBEDDING_MODEL", "text-embedding-3-small")
    if not api_key and allow_chat_fallback:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("COPILOT_API_KEY")
        base_url = base_url or os.environ.get("COPILOT_BASE_URL")
    if not api_key:
        return None
    return EvaluatorConfig(api_key=api_key, model=model, base_url=base_url,
                           embedding_model=embedding_model)


def _dedupe_bounded(texts) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for text in texts:
        cleaned = (str(text) or "").strip()[:_MAX_CONTEXT_CHARS]
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
        if len(out) >= _MAX_CONTEXTS:
            break
    return out


def case_from_service_result(
    case_id: str,
    question: str,
    result,
    *,
    category: str | None = None,
    reference: str | None = None,
    reference_contexts: list[str] | None = None,
) -> RagasEvalCase:
    """Convert a Career Intelligence result into a plain :class:`RagasEvalCase`.

    Only the question, the generated answer, and the answer's evidence/citation
    text are used. Private inputs (candidate background, raw job description,
    transcripts, uploaded company files) are never read here.
    """
    response = getattr(result, "response", result)
    answer = getattr(result, "answer", None) or getattr(response, "answer", "")

    contexts: list[str] = []
    for ev in getattr(response, "evidence", None) or []:
        text = getattr(ev, "text", None)
        if text:
            contexts.append(text)
    for r in getattr(response, "retrieved", None) or getattr(result, "retrieved", None) or []:
        text = getattr(getattr(r, "chunk", None), "text", None)
        if text:
            contexts.append(text)

    source_ids: list[str] = []
    for ev in getattr(response, "evidence", None) or []:
        sid = getattr(ev, "source_id", None)
        if sid and sid not in source_ids:
            source_ids.append(sid)
    for c in getattr(response, "citations", None) or getattr(result, "citations", None) or []:
        sid = getattr(c, "doc_id", None) or getattr(c, "source", None)
        if sid and sid not in source_ids:
            source_ids.append(sid)

    metadata = {"category": category} if category else {}
    return RagasEvalCase(
        case_id=case_id,
        question=question,
        answer=answer,
        retrieved_contexts=_dedupe_bounded(contexts),
        reference=reference,
        reference_contexts=reference_contexts,
        source_ids=source_ids,
        metadata=metadata,
    )


def load_cases(path: str) -> list[RagasEvalCase]:
    """Load public evaluation cases from a cases.json file."""
    import json

    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    rows = data.get("cases", data) if isinstance(data, dict) else data
    cases: list[RagasEvalCase] = []
    for row in rows:
        cases.append(RagasEvalCase(
            case_id=row["case_id"],
            question=row["question"],
            answer=row.get("answer", ""),
            retrieved_contexts=list(row.get("retrieved_contexts", [])),
            reference=row.get("reference"),
            reference_contexts=row.get("reference_contexts"),
            source_ids=list(row.get("source_ids", [])),
            metadata={k: row[k] for k in ("category", "geography", "expected_source_family")
                      if k in row},
        ))
    return cases


# --- Live run (lazy RAGAS import) -------------------------------------------


def _build_evaluator(config: EvaluatorConfig):
    """Build LangChain-wrapped evaluator LLM + embeddings for RAGAS."""
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper

    chat = ChatOpenAI(model=config.model, api_key=config.api_key,
                      base_url=config.base_url, temperature=0.0)
    emb = OpenAIEmbeddings(model=config.embedding_model, api_key=config.api_key,
                           base_url=config.base_url)
    return LangchainLLMWrapper(chat), LangchainEmbeddingsWrapper(emb)


def _build_metrics(reference_free_only: bool):
    """Instantiate the RAGAS metric objects for this run."""
    from ragas.metrics import (
        Faithfulness,
        LLMContextPrecisionWithoutReference,
        ResponseRelevancy,
    )

    metrics = [
        (METRIC_FAITHFULNESS, Faithfulness()),
        (METRIC_RESPONSE_RELEVANCY, ResponseRelevancy()),
        (METRIC_CONTEXT_PRECISION, LLMContextPrecisionWithoutReference()),
    ]
    if not reference_free_only:
        from ragas.metrics import LLMContextRecall

        metrics.append((METRIC_CONTEXT_RECALL, LLMContextRecall()))
    return metrics


def _to_sample(case: RagasEvalCase, *, with_reference: bool):
    from ragas.dataset_schema import SingleTurnSample

    kwargs = dict(
        user_input=case.question,
        response=case.answer,
        retrieved_contexts=case.retrieved_contexts or [""],
    )
    if with_reference and case.has_reference:
        kwargs["reference"] = case.reference
    return SingleTurnSample(**kwargs)


def run_ragas(
    cases: list[RagasEvalCase],
    *,
    config: EvaluatorConfig,
    evaluate_fn=None,
    build_evaluator_fn=None,
    build_metrics_fn=None,
    to_sample_fn=None,
) -> dict:
    """Run RAGAS over ``cases`` and return plain, normalised results.

    The ``*_fn`` hooks are injection points for offline tests; in production they
    default to the real RAGAS entry points. Raises :class:`RagasNotInstalled` if
    the package is missing and :class:`RagasNotConfigured` if ``config`` is falsy.
    """
    if not ragas_available() and evaluate_fn is None:
        raise RagasNotInstalled(
            "RAGAS is not installed. Install with: pip install -e \".[evaluation]\"")
    if config is None:
        raise RagasNotConfigured("Evaluator credentials are not configured.")

    _evaluate = evaluate_fn or _default_evaluate
    _make_metrics = build_metrics_fn or _build_metrics
    _make_sample = to_sample_fn or _to_sample
    llm, embeddings = (build_evaluator_fn or _build_evaluator)(config) if evaluate_fn is None \
        else (None, None)

    with_ref = [c for c in cases if c.has_reference]
    no_ref = [c for c in cases if not c.has_reference]

    per_case: dict[str, dict] = {c.case_id: {"case_id": c.case_id,
                                             "category": c.metadata.get("category", "")}
                                 for c in cases}
    context_recall_run = bool(with_ref)

    # Reference-free metrics run on every case.
    rf_metrics = _make_metrics(reference_free_only=True)
    rf_scores = _evaluate(
        [_make_sample(c, with_reference=False) for c in cases],
        rf_metrics, llm, embeddings)
    _merge_scores(per_case, cases, rf_scores, [m[0] for m in rf_metrics])

    # Context Recall runs only on the referenced subset.
    if with_ref:
        cr_metrics = [m for m in _make_metrics(reference_free_only=False)
                      if m[0] == METRIC_CONTEXT_RECALL]
        cr_scores = _evaluate(
            [_make_sample(c, with_reference=True) for c in with_ref],
            cr_metrics, llm, embeddings)
        _merge_scores(per_case, with_ref, cr_scores, [METRIC_CONTEXT_RECALL])

    metric_names = [METRIC_FAITHFULNESS, METRIC_RESPONSE_RELEVANCY, METRIC_CONTEXT_PRECISION]
    if context_recall_run:
        metric_names.append(METRIC_CONTEXT_RECALL)

    rows = list(per_case.values())
    aggregates = _aggregate(rows, metric_names)

    # Execution validity (technical coverage, NOT model quality). Only finite
    # scores count; a failed evaluator job leaves its score absent.
    reference_free = [METRIC_FAITHFULNESS, METRIC_RESPONSE_RELEVANCY, METRIC_CONTEXT_PRECISION]
    expected = len(reference_free) * len(cases) + (len(with_ref) if context_recall_run else 0)
    valid = sum(1 for r in rows for name in metric_names if is_valid_score(r.get(name)))
    valid_case_count = sum(1 for r in rows
                           if any(is_valid_score(r.get(name)) for name in metric_names))
    metrics_with_scores = [name for name in metric_names if aggregates.get(name) is not None]
    if valid == 0:
        status = STATUS_FAILED
    elif valid >= expected:
        status = STATUS_COMPLETE
    else:
        status = STATUS_PARTIAL

    return {
        "metrics": aggregates,
        "per_case": rows,
        "metric_names": metric_names,
        "metrics_with_scores": metrics_with_scores,
        "context_recall_run": context_recall_run,
        "referenced_case_count": len(with_ref),
        "case_count": len(cases),
        "valid_score_count": valid,
        "expected_score_count": expected,
        "failed_score_count": max(0, expected - valid),
        "valid_case_count": valid_case_count,
        "score_coverage": round(valid / expected, 4) if expected else 0.0,
        "status": status,
    }


def _default_evaluate(samples, metrics, llm, embeddings):
    """Call ragas.evaluate and return {case_index: {metric_name: score}}."""
    from ragas import evaluate
    from ragas.dataset_schema import EvaluationDataset

    dataset = EvaluationDataset(samples=samples)
    result = evaluate(dataset=dataset, metrics=[m[1] for m in metrics],
                      llm=llm, embeddings=embeddings)
    frame = result.to_pandas()
    out: dict[int, dict] = {}
    for idx in range(len(frame)):
        row = frame.iloc[idx]
        scores = {}
        for name, metric in metrics:
            col = getattr(metric, "name", name)
            if col in frame.columns:
                scores[name] = float(row[col])
        out[idx] = scores
    return out


def _merge_scores(per_case, cases, scores_by_index, metric_names) -> None:
    for idx, case in enumerate(cases):
        scores = scores_by_index.get(idx, {})
        for name in metric_names:
            # Only store finite scores; a failed evaluator job (NaN/inf/None)
            # stays absent rather than becoming a misleading numeric value.
            if is_valid_score(scores.get(name)):
                per_case[case.case_id][name] = round(float(scores[name]), 4)


def _aggregate(rows, metric_names) -> dict:
    agg: dict[str, float | None] = {}
    for name in metric_names:
        values = [float(r[name]) for r in rows if is_valid_score(r.get(name))]
        agg[name] = round(sum(values) / len(values), 4) if values else None
    return agg
