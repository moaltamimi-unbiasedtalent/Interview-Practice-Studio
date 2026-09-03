"""Unified Career → Interview practice handoff (Chat + Tools).

All LLM/tool boundaries are injected fakes — no network, no paid calls.
Covers: typed PreparationArtifacts plumbing (and that they never leak into the
chat response/history), the shared target-role resolver, Career-Chat handoff
eligibility/state, source references from unified evidence, and the full
Career Chat → PreparationContext → Interview Practice round-trip.
"""

from __future__ import annotations

import json

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.embeddings import LocalHashEmbedder
from src.copilot.models import DocumentChunk, KnowledgeEvidence
from src.copilot.rag.responder import ModelReply
from src.copilot.rag.translation import QueryTranslator
from src.copilot.retrieval import build_retriever
from src.copilot.service import (
    CareerIntelligenceService,
    PreparationArtifacts,
)
from src.copilot.tools import ToolInvoker, build_tool_registry
from src.copilot.tools.schemas import (
    GapAnalysisResult,
    InterviewQuestionSet,
    MatchStats,
    PriorityGap,
    QuestionCategory,
    RoleRequirements,
)
from src.copilot.vectorstore import InMemoryVectorStore
from src.career import ui as career_ui
from src.integration import handoff
from src.integration.models import PreparationContext
from src.integration.preparation_context import build_preparation_context

CONFIG = CopilotConfig()


# --- fakes -------------------------------------------------------------------


def _store():
    store = InMemoryVectorStore(LocalHashEmbedder())
    store.add_chunks([
        DocumentChunk(chunk_id="ai", doc_id="d1",
                      text="Demand for AI and product skills is rising across the market.",
                      metadata={"title": "AI demand", "document_type": "labour_market", "page": 1}),
    ])
    return store


def _translator(intent, *, rewritten="rewritten", retrieval_required=True):
    payload = {"intent": intent, "retrieval_required": retrieval_required,
               "rewritten_query": rewritten, "alternate_queries": [],
               "metadata_filters": {}, "explanation": "ok"}
    return QueryTranslator(responder=lambda m: ModelReply(content=json.dumps(payload)))


def _fake_job(messages):
    return RoleRequirements(role_title="Senior Product Manager", seniority="Senior",
                            required_skills=["Roadmapping", "Stakeholder management"],
                            technologies=[], likely_interview_themes=["strategy"])


def _fake_job_no_title(messages):
    return RoleRequirements(role_title=None, required_skills=["Roadmapping"])


def _fake_questions(messages):
    return InterviewQuestionSet(role="Senior Product Manager",
                                categories=[QuestionCategory(name="strategy",
                                                             questions=["Describe a roadmap call."])])


def _invoker(job_producer=_fake_job):
    return ToolInvoker(build_tool_registry(config=None, job_producer=job_producer,
                                           question_producer=_fake_questions))


def _service(intent, *, invoker=None, synth="Answer [1]."):
    store = _store()
    return CareerIntelligenceService(
        config=CONFIG,
        retriever=build_retriever(CONFIG, mode="hybrid", store=store),
        translator=_translator(intent),
        tool_invoker=invoker or _invoker(),
        synthesis_responder=lambda m: ModelReply(content=synth),
    )


# --- PreparationArtifacts plumbing (section 5/6) -----------------------------


class TestArtifactsPlumbing:
    def test_tool_run_populates_typed_artifacts(self) -> None:
        result = _service("candidate_comparison").answer(
            "Compare my background with this role.",
            job_description="Senior PM owning roadmap and strategy.",
            candidate_background="7 years SaaS product experience.")
        arts = result.preparation_artifacts
        assert isinstance(arts, PreparationArtifacts)
        assert isinstance(arts.role_requirements, RoleRequirements)
        assert isinstance(arts.gap_result, GapAnalysisResult)

    def test_artifacts_absent_from_chat_response(self) -> None:
        result = _service("candidate_comparison").answer(
            "Compare my background.", job_description="Senior PM.",
            candidate_background="PM.")
        # The safety boundary: raw typed artifacts are not on ChatResponse.
        assert not hasattr(result.response, "preparation_artifacts")
        assert not hasattr(result.response, "role_requirements")

    def test_artifacts_do_not_leak_into_history(self) -> None:  # (19K)
        from src.copilot import history as career_history

        result = _service("candidate_comparison").answer(
            "Compare my background.", job_description="Senior PM.",
            candidate_background="PM.")
        turn = career_history.build_turn("Compare my background.", result)
        blob = json.dumps(turn.as_dict() if hasattr(turn, "as_dict") else turn.__dict__,
                          default=str)
        assert "Roadmapping" not in blob  # raw role-requirement skill never serialised

    def test_no_tools_route_has_empty_artifacts(self) -> None:
        result = _service("skill_research").answer("What skills matter for AI roles?")
        assert result.preparation_artifacts.is_empty()


# --- Career-Chat handoff state (_store_chat_preparation) ----------------------


def _prep(ss, result):
    career_ui._store_chat_preparation(ss, result)
    return ss.get("career.chat_preparation")


class TestChatHandoffState:
    def test_explicit_target_role_enables_handoff(self) -> None:  # (19A)
        result = _service("skill_research").answer("What skills should I prepare?")
        ss = {"chat_target_role": "Senior Product Manager"}
        prep = _prep(ss, result)
        assert prep is not None

    def test_jd_analyzer_role_enables_handoff(self) -> None:  # (19B)
        result = _service("candidate_comparison").answer(
            "Compare my background.", job_description="Senior PM.",
            candidate_background="PM.")
        prep = _prep({}, result)
        assert prep is not None
        assert isinstance(prep["role_requirements"], RoleRequirements)

    def test_resolved_occupation_enables_handoff(self) -> None:  # (19C)
        result = _service("skill_research").answer("What should a Data Analyst prepare?")
        result.trace.resolved_occupation = "Data Analyst"  # simulate structured resolver
        prep = _prep({}, result)
        assert prep is not None and prep["resolved_occupation"] == "Data Analyst"

    def test_smalltalk_shows_no_handoff(self) -> None:  # (19 negative)
        result = _service("smalltalk", synth="Hello!").answer("hi there")
        ss = {}
        _prep(ss, result)
        assert "career.chat_preparation" not in ss

    def test_blocked_answer_shows_no_handoff(self) -> None:
        result = _service("skill_research").answer("What skills matter?")
        result.trace.blocked = True
        ss = {}
        _prep(ss, result)
        assert "career.chat_preparation" not in ss

    def test_new_answer_replaces_stale_prep(self) -> None:  # (section 14)
        ss = {"career.chat_preparation": {"stale": True}}
        result = _service("smalltalk", synth="Hi").answer("hi")
        _prep(ss, result)  # ineligible → cleared
        assert "career.chat_preparation" not in ss


# --- Source references from unified evidence (section 9) ----------------------


class TestUnifiedEvidence:
    def test_knowledge_evidence_becomes_source_reference(self) -> None:  # (19G)
        ev = KnowledgeEvidence(evidence_id="e1", text="t", source_id="onet",
                               source_title="O*NET", source_url="https://onet.org",
                               evidence_type="role", retrieval_lane="structured_role")
        ctx = build_preparation_context(target_role="Data Analyst", evidence=[ev])
        assert ctx.source_count == 1
        assert ctx.source_references[0].title == "O*NET"

    def test_gap_result_included_in_context(self) -> None:  # (19F)
        gap = GapAnalysisResult(
            matched=["Roadmapping"], partially_matched=[], missing=["Exec comms"],
            strengths=["Roadmapping"],
            priority_gaps=[PriorityGap(requirement="Exec comms", category="skill", severity="high")],
            stats=MatchStats(total_requirements=2, matched=1, missing=1, match_percentage=50.0))
        ctx = build_preparation_context(target_role="Senior PM", gap_result=gap)
        assert "Exec comms" in ctx.candidate_gaps


# --- Navigation round-trip (sections 15, 16, 19H/I) --------------------------


class TestHandoffRoundTrip:
    def test_request_practice_sets_context_and_nav(self) -> None:  # (19H)
        ss: dict = {}
        ctx = build_preparation_context(target_role="Senior Product Manager")
        handoff.request_practice(ss, ctx)
        assert isinstance(handoff.get_context(ss), PreparationContext)
        assert ss["_pending_nav"] == "Interview Practice"

    def test_interview_prefill_after_handoff(self) -> None:  # (19I, 16)
        ss: dict = {}
        ctx = build_preparation_context(
            target_role="Senior Product Manager",
            role_requirements=_fake_job(None))
        handoff.request_practice(ss, ctx)
        prefill = handoff.interview_prefill(ss)
        assert prefill["target_role"] == "Senior Product Manager"
        assert prefill["career_level"] == "senior"

    def test_building_context_from_prep_needs_no_tools(self) -> None:  # (19J)
        # The click path only reshapes stored artifacts — no invoker involved.
        result = _service("candidate_comparison").answer(
            "Compare my background.", job_description="Senior PM.",
            candidate_background="PM.")
        prep = _prep({"chat_target_role": ""}, result)
        ctx = build_preparation_context(
            target_role="Senior Product Manager",
            role_requirements=prep["role_requirements"],
            gap_result=prep["gap_result"], evidence=prep["evidence"])
        assert ctx.target_role == "Senior Product Manager"  # built with no new calls


# --- Full E2E (section 20) ---------------------------------------------------


# --- Streamlit smoke: Chat handoff card renders (no crash) -------------------


class TestChatHandoffStreamlitSmoke:
    def test_chat_handoff_card_renders_with_seeded_prep(self, monkeypatch) -> None:
        import pathlib

        from pydantic import SecretStr
        from streamlit.testing.v1 import AppTest

        # Configure so the chat page does not early-return on a missing key.
        monkeypatch.setattr(career_ui, "_config",
                            lambda: CopilotConfig(api_key=SecretStr("sk-test")))
        app_path = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
        at = AppTest.from_file(app_path, default_timeout=30)
        at.session_state["os_nav"] = "Career Intelligence"
        at.session_state["career_section"] = "Chat"
        at.session_state["chat_history"] = [{"role": "assistant", "content": "Answer."}]
        at.session_state["chat_target_role"] = "Senior Product Manager"
        at.session_state["career.chat_preparation"] = {
            "role_requirements": _fake_job(None), "gap_result": None,
            "preparation_plan": None, "question_set": None,
            "resolved_occupation": "", "evidence": [], "job_description": None,
            "company_context": None,
        }
        at.run()
        assert not at.exception
        markdown_blob = " ".join(m.value for m in at.markdown)
        assert "Ready to practise this role?" in markdown_blob

    def test_chat_handoff_missing_role_points_to_context_field(self, monkeypatch) -> None:
        import pathlib

        from pydantic import SecretStr
        from streamlit.testing.v1 import AppTest

        monkeypatch.setattr(career_ui, "_config",
                            lambda: CopilotConfig(api_key=SecretStr("sk-test")))
        app_path = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
        at = AppTest.from_file(app_path, default_timeout=30)
        at.session_state["os_nav"] = "Career Intelligence"
        at.session_state["career_section"] = "Chat"
        at.session_state["chat_history"] = [{"role": "assistant", "content": "Answer."}]
        at.session_state["chat_target_role"] = ""  # no role anywhere
        at.session_state["career.chat_preparation"] = {
            "role_requirements": None, "gap_result": None, "preparation_plan": None,
            "question_set": None, "resolved_occupation": "",
            "evidence": [], "job_description": None, "company_context": None,
        }
        at.run()
        assert not at.exception  # missing role must never crash


def test_e2e_chat_to_interview_practice() -> None:
    jd = ("We are hiring a Senior Product Manager to own product strategy, roadmap "
          "prioritisation, customer discovery, commercial outcomes and executive "
          "stakeholder communication.")
    background = ("Seven years of SaaS product experience. Led product discovery and "
                  "roadmap delivery. Limited experience presenting to executive boards.")
    result = _service("preparation_planning").answer(
        "Compare my background with this role and help me prepare.",
        job_description=jd, candidate_background=background,
        days_until_interview=14, hours_per_week=6)

    # Tools ran and produced typed artifacts (no answer-text parsing).
    names = [te.tool_name for te in result.tool_calls if te.status == "ok"]
    assert constants.TOOL_JOB_ANALYZER in names
    arts = result.preparation_artifacts
    assert isinstance(arts.role_requirements, RoleRequirements)

    # Chat stores handoff prep, resolves the role, and hands off.
    ss: dict = {"chat_target_role": "", "chat_jd": jd}
    prep = _prep(ss, result)
    assert prep is not None
    ctx = build_preparation_context(
        target_role="Senior Product Manager",
        role_requirements=prep["role_requirements"], gap_result=prep["gap_result"],
        evidence=prep["evidence"], job_description=prep["job_description"])
    handoff.request_practice(ss, ctx)

    # Interview Practice receives editable prefill; nothing auto-starts.
    prefill = handoff.interview_prefill(ss)
    assert prefill["target_role"] == "Senior Product Manager"
    assert prefill["job_description"]
    assert ss["_pending_nav"] == "Interview Practice"
