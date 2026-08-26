"""OS-4 tests: Career → Interview handoff via PreparationContext (offline)."""

import subprocess
import sys

import pytest

from src.integration import handoff
from src.integration.models import PreparationContext, SourceReference
from src.integration.preparation_context import build_preparation_context
from src.copilot.models import DocumentChunk, RetrievalResult
from src.copilot.tools.schemas import (
    GapAnalysisResult,
    MatchStats,
    PriorityGap,
    RoleRequirements,
)


def _role() -> RoleRequirements:
    return RoleRequirements(
        role_title="Data Engineer",
        seniority="Senior",
        required_skills=["Python", "SQL"],
        key_responsibilities=["Build data pipelines"],
        leadership_expectations=["Mentor juniors"],
        technologies=["AWS"],
        likely_interview_themes=["data modelling", "reliability"],
    )


def _gap() -> GapAnalysisResult:
    return GapAnalysisResult(
        matched=["Python"],
        partially_matched=[],
        missing=["AWS"],
        strengths=["Python"],
        priority_gaps=[PriorityGap(requirement="AWS", category="technology", severity="high")],
        stats=MatchStats(total_requirements=3, matched=1, missing=1, match_percentage=33.3),
    )


def _evidence() -> list[RetrievalResult]:
    chunk = DocumentChunk(
        chunk_id="c1", doc_id="d1", text="Cloud demand is rising.",
        metadata={"title": "Labour report", "source": "wef.pdf", "page": 14},
    )
    return [RetrievalResult(chunk=chunk, score=0.9)]


# --- Context generation ------------------------------------------------------


class TestBuild:
    def test_full_context(self) -> None:
        ctx = build_preparation_context(
            role_requirements=_role(), gap_result=_gap(), evidence=_evidence(),
            job_description="JD text", industry="Tech",
        )
        assert ctx.target_role == "Data Engineer"
        assert ctx.seniority == "Senior"
        assert ctx.required_skills == ["Python", "SQL"]
        assert ctx.candidate_strengths == ["Python"]
        assert ctx.candidate_gaps == ["AWS"]
        assert "AWS" in ctx.priority_competencies  # high-severity gap first
        assert ctx.source_references[0].page == 14
        assert ctx.source_count == 1

    def test_partial_missing_fields(self) -> None:
        # Only a role — no gap, no evidence, no JD.
        ctx = build_preparation_context(role_requirements=_role())
        assert ctx.candidate_strengths == [] and ctx.candidate_gaps == []
        assert ctx.source_references == []
        assert ctx.job_description is None

    def test_target_role_required(self) -> None:
        with pytest.raises(ValueError):
            build_preparation_context(role_requirements=RoleRequirements())

    def test_explicit_target_role_overrides(self) -> None:
        ctx = build_preparation_context(target_role="Nurse")
        assert ctx.target_role == "Nurse"


# --- Handoff state -----------------------------------------------------------


class TestState:
    def test_store_get_has_clear(self) -> None:
        ss: dict = {}
        ctx = build_preparation_context(target_role="Analyst")
        assert handoff.has_context(ss) is False
        handoff.store_context(ss, ctx)
        assert handoff.has_context(ss) is True
        assert handoff.get_context(ss).target_role == "Analyst"
        handoff.clear_context(ss)
        assert handoff.has_context(ss) is False

    def test_request_practice_sets_nav_and_context(self) -> None:
        ss: dict = {}
        ctx = build_preparation_context(target_role="Analyst")
        handoff.request_practice(ss, ctx)
        assert ss["_pending_nav"] == "Interview Practice"
        assert handoff.has_context(ss)

    def test_request_return_sets_nav(self) -> None:
        ss: dict = {}
        handoff.request_return_to_preparation(ss)
        assert ss["_pending_nav"] == "Career Intelligence"


# --- Setup pre-population ----------------------------------------------------


class TestPrefill:
    def test_prefill_maps_fields(self) -> None:
        ss: dict = {}
        handoff.store_context(
            ss,
            build_preparation_context(
                role_requirements=_role(), gap_result=_gap(), job_description="JD"
            ),
        )
        prefill = handoff.interview_prefill(ss)
        assert prefill["target_role"] == "Data Engineer"
        assert prefill["career_level"] == "senior"  # from seniority "Senior"
        assert prefill["difficulty"] == "hard"  # senior → hard
        assert "Strengths:" in prefill["candidate_background"]
        assert "Development areas:" in prefill["candidate_background"]
        assert prefill["job_description"] == "JD"
        assert isinstance(prefill, dict)  # plain data only (candidate can edit)

    def test_prefill_empty_without_context(self) -> None:
        assert handoff.interview_prefill({}) == {}

    def test_seniority_mapping(self) -> None:
        assert handoff.seniority_to_career_level("Entry level") == "entry"
        assert handoff.seniority_to_career_level("VP of Engineering") == "executive"
        assert handoff.seniority_to_career_level("Manager") == "manager"
        assert handoff.seniority_to_career_level(None) is None


# --- Session boundaries ------------------------------------------------------


class TestBoundaries:
    def test_interview_reset_does_not_erase_context(self) -> None:
        # Simulate an interview reset clearing only its own namespaced state.
        ss: dict = {"copilot_x": 1}
        handoff.store_context(ss, build_preparation_context(target_role="R"))
        ss["interview_namespace"] = {"state": "SETUP"}
        del ss["interview_namespace"]  # interview reset touches only its key
        assert handoff.has_context(ss) is True

    def test_new_career_session_can_clear(self) -> None:
        ss: dict = {}
        handoff.store_context(ss, build_preparation_context(target_role="R"))
        handoff.clear_context(ss)
        assert handoff.has_context(ss) is False


# --- Provenance & data purity ------------------------------------------------


class TestPurity:
    def test_context_is_json_serialisable_plain_data(self) -> None:
        ctx = build_preparation_context(
            role_requirements=_role(), gap_result=_gap(), evidence=_evidence()
        )
        # Round-trips through JSON => no Chroma/LangChain/retriever objects.
        restored = PreparationContext.model_validate_json(ctx.model_dump_json())
        assert restored == ctx
        assert all(isinstance(r, SourceReference) for r in restored.source_references)

    def test_preview_is_safe_summary(self) -> None:
        ctx = build_preparation_context(role_requirements=_role(), gap_result=_gap())
        prev = handoff.preview(ctx)
        assert prev["role"] == "Data Engineer"
        assert len(prev["top_competencies"]) <= 5


# --- Module isolation --------------------------------------------------------


def test_integration_does_not_import_career_internals() -> None:
    """Importing the handoff must not pull retrievers / chains / Chroma."""
    script = (
        "import sys;"
        "import src.integration.handoff, src.integration.preparation_context;"
        "bad=[m for m in sys.modules if m.startswith('src.copilot.retrieval')"
        " or m.startswith('src.copilot.rag') or m in ('chromadb','langchain')"
        " or m.startswith('src.copilot.vectorstore')"
        " or m.startswith('src.interview')];"
        "print('BAD' if bad else 'OK', bad)"
    )
    out = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd="."
    )
    assert out.stdout.startswith("OK"), out.stdout + out.stderr
