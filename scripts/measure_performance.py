"""Measure representative Career-lane latencies and write docs/performance_report.md.

Offline and deterministic (local embedder, heuristic translator, fake model), so
numbers are reproducible and free. Stages needing a live provider (real LLM
answer, interview generation/evaluation, speech, live) are marked not-measured
rather than invented. No latency targets are asserted.

Usage:  python scripts/measure_performance.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.config import CopilotConfig  # noqa: E402
from src.copilot.embeddings import LocalHashEmbedder  # noqa: E402
from src.copilot.knowledge import normalisers as norm  # noqa: E402
from src.copilot.knowledge.compensation import CompensationRecord, CompensationRepository  # noqa: E402
from src.copilot.knowledge.roles import RoleRepository  # noqa: E402
from src.copilot.knowledge.router import route_question  # noqa: E402
from src.copilot.models import DocumentChunk  # noqa: E402
from src.copilot.rag.responder import ModelReply  # noqa: E402
from src.copilot.rag.translation import QueryTranslator, heuristic_translation  # noqa: E402
from src.copilot.retrieval import build_retriever  # noqa: E402
from src.copilot.service import CareerIntelligenceService  # noqa: E402
from src.copilot.tools import ToolInvoker, build_tool_registry  # noqa: E402
from src.copilot.tools.gap_analyzer import analyze_gaps  # noqa: E402
from src.copilot.tools.prep_planner import build_plan  # noqa: E402
from src.copilot.tools.schemas import GapAnalyzerArgs, PrepPlanArgs, PriorityGap, RoleRequirements  # noqa: E402
from src.copilot.vectorstore import InMemoryVectorStore  # noqa: E402

CONFIG = CopilotConfig()


def _timeit(fn, iterations=200) -> tuple[float, float]:
    samples = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return round(statistics.mean(samples), 3), round(statistics.median(samples), 3)


def main() -> int:
    store = InMemoryVectorStore(LocalHashEmbedder())
    store.add_chunks([DocumentChunk(chunk_id=f"c{i}", doc_id="d",
                     text=f"AI and machine learning skills demand rises {i}.",
                     metadata={"title": f"Doc {i}", "document_type": "labour_market"}) for i in range(20)])
    vector = build_retriever(CONFIG, mode="vector", store=store)
    hybrid = build_retriever(CONFIG, mode="hybrid", store=store)

    role = RoleRepository(":memory:")
    for row in json.load(open("evaluations/knowledge_samples/roles_onet.json")):
        role.add_occupation(norm.normalise_onet(row))
    comp = CompensationRepository(":memory:")
    comp.add(CompensationRecord(source_id="bls_oews", occupation_title="Data Analyst",
                                country="US", geography="US", year=2023, currency="USD",
                                pay_period="annual", statistic_type="median", value=85000))

    invoker = ToolInvoker(build_tool_registry(config=None))
    reqs = RoleRequirements(required_skills=["Python", "SQL"], technologies=["AWS"])
    service = CareerIntelligenceService(
        config=CONFIG, retriever=hybrid,
        translator=QueryTranslator(enabled=False),
        tool_invoker=invoker,
        synthesis_responder=lambda m: ModelReply(content="AI skills matter [1]."),
    )

    q = "What skills matter for AI roles?"
    results = {
        "intent/router": _timeit(lambda: route_question(q)),
        "query translation (heuristic)": _timeit(lambda: heuristic_translation(q)),
        "structured role retrieval": _timeit(lambda: role.search("Data Analyst")),
        "vector retrieval": _timeit(lambda: vector.retrieve(q, top_k=5)),
        "hybrid retrieval": _timeit(lambda: hybrid.retrieve(q, top_k=5)),
        "compensation lookup": _timeit(lambda: comp.filter(country="US", year=2023, title="Data Analyst")),
        "tool: gap analyzer (deterministic)": _timeit(
            lambda: analyze_gaps(GapAnalyzerArgs(candidate_background="Python dev.", role_requirements=reqs))),
        "tool: preparation plan (deterministic)": _timeit(
            lambda: build_plan(PrepPlanArgs(priority_gaps=[PriorityGap(requirement="AWS", severity="high")],
                                            days_until_interview=14, hours_per_week=6))),
        "service.answer pipeline (excl. live model)": _timeit(lambda: service.answer(q), iterations=50),
    }

    lines = [
        "# Interview OS — Performance Report",
        "",
        "Representative latencies for the Career Intelligence lanes, measured offline "
        "(local hashing embedder, heuristic translator, fake model) so they are "
        "reproducible and free. Micro-stages: 200 iterations; full pipeline: 50. "
        "These are machine-dependent measurements, **not** targets.",
        "",
        "## Career stages",
        "",
        "| Stage | Mean (ms) | Median (ms) |",
        "|---|---|---|",
    ]
    for name, (mean, median) in results.items():
        lines.append(f"| {name} | {mean} | {median} |")
    lines += [
        "",
        "## Not measured offline (require a live provider)",
        "",
        "- **Career final answer (real LLM synthesis)** — dominated by the OpenRouter "
        "model round-trip; the pipeline row above excludes it (fake model).",
        "- **Interview**: question generation, answer evaluation, Deep Dive — each is a "
        "live OpenRouter call.",
        "- **Speech transcription** and **Gemini Live** — require Google credentials.",
        "",
        "These are excluded rather than estimated; measure them in a live session.",
        "",
        "## Cost",
        "",
        "- **Career LLM**: OpenRouter via LangChain — token usage tracked; provider "
        "cost is not surfaced on this path, so cost shows **unavailable** (never "
        "fabricated).",
        "- **Interview LLM**: OpenRouter via HTTPX — `PricingService` reports "
        "reported→calculated→none cost.",
        "- **Speech / Live**: usage not billed through the app; **unavailable** here.",
        "- Career and Interview usage are tracked separately (no merged totals).",
    ]
    Path("docs").mkdir(exist_ok=True)
    with open("docs/performance_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    for name, (mean, median) in results.items():
        print(f"  {name:<44} mean={mean}ms median={median}ms")
    print("\nWrote docs/performance_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
