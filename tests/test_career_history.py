"""Phase 9R tests: Career usage, RAG metrics, history and export (offline)."""

import json
import subprocess
import sys
from types import SimpleNamespace

from src.copilot import history as ch
from src.core.usage import Operation, UsageLedger, UsageRecord
from src.copilot.models import Citation, ToolExecution, UsageRecord as CopilotUsage
from src.integration.export import combined_session_export
from src.integration.models import PreparationContext


def _result():
    trace = SimpleNamespace(
        retrieval_strategy="hybrid",
        translated_query_count=2,
        vector_results=[1, 2, 3],
        keyword_results=[1],
        fused_results=[1, 2, 3],
        context_count=3,
        retrieval_latency_ms=12.5,
    )
    return SimpleNamespace(
        answer="AI skills are rising [1].",
        citations=[Citation(marker="[1]", doc_id="d", chunk_id="c", title="WEF", page=14)],
        tool_calls=[
            ToolExecution(
                tool_name="job_description_analyzer",
                status="ok",
                duration_seconds=0.02,
                safe_argument_summary="job_description (1200 chars)",
                safe_result_summary="role=DE; 3 skills",
            )
        ],
        trace=trace,
        response=SimpleNamespace(
            usage=CopilotUsage(model="m", prompt_tokens=100, completion_tokens=50, total_tokens=150)
        ),
    )


# --- Usage / cost ------------------------------------------------------------


class TestUsage:
    def test_final_generation_recorded_with_tokens(self) -> None:
        ss: dict = {}
        ch.record_final_generation(ss, _result().response.usage)
        ledger = ch.get_ledger(ss)
        assert ledger.total_tokens == 150
        assert ledger.tokens_by_source()["career_final_generation"] == 150

    def test_missing_usage_records_nothing(self) -> None:
        ss: dict = {}
        ch.record_final_generation(ss, None)
        assert ch.get_ledger(ss).total_tokens == 0

    def test_cost_unavailable_when_no_reported_cost(self) -> None:
        ledger = UsageLedger()
        ledger.add(UsageRecord(operation=Operation.CAREER_FINAL_GENERATION, total_tokens=10))
        assert all(r.cost_usd is None for r in ledger.records)  # no fabricated cost

    def test_cost_aggregates_when_present(self) -> None:
        ledger = UsageLedger()
        ledger.add(UsageRecord(operation=Operation.CAREER_TOOLS, total_tokens=5, cost_usd=0.01, id="a"))
        ledger.add(UsageRecord(operation=Operation.CAREER_FINAL_GENERATION, total_tokens=5, cost_usd=0.02, id="b"))
        assert round(ledger.total_cost_usd, 4) == 0.03


# --- RAG + tool stats via build_turn -----------------------------------------


class TestTurn:
    def test_rag_metrics_captured(self) -> None:
        turn = ch.build_turn("What skills matter?", _result())
        assert turn.rag.retrieval_strategy == "hybrid"
        assert turn.rag.translated_query_count == 2
        assert turn.rag.vector_count == 3 and turn.rag.keyword_count == 1
        assert turn.rag.context_count == 3
        assert turn.rag.retrieval_latency_ms == 12.5

    def test_tool_stats_are_safe(self) -> None:
        turn = ch.build_turn("q", _result())
        tool = turn.tools[0]
        assert tool["tool_name"] == "job_description_analyzer"
        assert tool["status"] == "ok"
        # No sensitive arguments — only safe summaries are kept.
        assert "candidate" not in json.dumps(turn.tools).lower()

    def test_citations_captured(self) -> None:
        turn = ch.build_turn("q", _result())
        assert turn.citations[0]["marker"] == "[1]"
        assert turn.citations[0]["page"] == 14


# --- History + reset ---------------------------------------------------------


class TestHistory:
    def test_append_get_clear(self) -> None:
        ss: dict = {}
        ch.append_turn(ss, ch.build_turn("q1", _result()))
        ch.append_turn(ss, ch.build_turn("q2", _result()))
        assert len(ch.get_history(ss).turns) == 2
        ch.record_final_generation(ss, _result().response.usage)
        ch.clear_history(ss)
        assert ch.get_history(ss).turns == []
        assert ch.get_ledger(ss).total_tokens == 0  # ledger cleared too


# --- Export ------------------------------------------------------------------


class TestExport:
    def test_history_json_and_csv(self) -> None:
        ss: dict = {}
        ch.append_turn(ss, ch.build_turn("What skills matter?", _result()))
        hist = ch.get_history(ss)
        parsed = json.loads(hist.to_json())
        assert parsed["turns"][0]["question"] == "What skills matter?"
        csv_text = hist.to_csv()
        assert "question,answer,citations" in csv_text
        assert "hybrid" in csv_text

    def test_combined_session_export(self) -> None:
        ss: dict = {}
        ch.append_turn(ss, ch.build_turn("q", _result()))
        prep = PreparationContext(target_role="Data Engineer", seniority="Senior",
                                  priority_competencies=["Python"])
        combined = combined_session_export(
            preparation=prep,
            career_history=ch.get_history(ss),
            interview_report={"overall_readiness_score": 72},
        )
        assert combined["preparation_summary"]["target_role"] == "Data Engineer"
        assert combined["career_sources"][0]["title"] == "WEF"
        assert combined["interview_report"]["overall_readiness_score"] == 72
        assert combined["career_conversation"][0]["question"] == "q"

    def test_combined_export_no_prompts_or_secrets(self) -> None:
        ss: dict = {}
        ch.append_turn(ss, ch.build_turn("q", _result()))
        text = json.dumps(
            combined_session_export(career_history=ch.get_history(ss))
        ).lower()
        for forbidden in ("system prompt", "api_key", "sk-", "openrouter_api_key"):
            assert forbidden not in text


# --- Module isolation --------------------------------------------------------


def test_combined_export_is_standalone() -> None:
    script = (
        "import sys, src.integration.export;"
        "bad=[m for m in sys.modules if m.startswith('src.copilot') "
        "or m.startswith('src.interview')];"
        "print('OK' if not bad else 'BAD', bad)"
    )
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert out.stdout.startswith("OK"), out.stdout + out.stderr
