"""Regression: 'Practise this role' must validate a target role before building
a PreparationContext (fix/practise-role-handoff-validation).

The domain contract stays strict — target_role is mandatory and never fabricated
— but the UI now resolves/validates the role first so the page never crashes.
"""

from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from src.career.ui import _resolve_handoff_target_role
from src.integration import handoff
from src.integration.models import PreparationContext
from src.integration.preparation_context import build_preparation_context
from src.copilot.tools.schemas import RoleRequirements

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


# --- Target-role resolver (deterministic, no Streamlit) ----------------------


class TestResolveTargetRole:
    def test_none_role_req_no_manual_returns_empty(self) -> None:  # (A)
        assert _resolve_handoff_target_role(None, {}) == ""

    def test_empty_role_title_no_manual_returns_empty(self) -> None:  # (B)
        assert _resolve_handoff_target_role(RoleRequirements(role_title=""), {}) == ""

    def test_none_role_title_uses_manual(self) -> None:  # (C)
        role = RoleRequirements(role_title=None)
        assert _resolve_handoff_target_role(role, {"handoff_target_role": "Senior Product Manager"}) \
            == "Senior Product Manager"

    def test_analyser_role_wins_over_manual(self) -> None:  # (D)
        role = RoleRequirements(role_title="Data Analyst")
        got = _resolve_handoff_target_role(role, {"handoff_target_role": "Ignored"})
        assert got == "Data Analyst"

    def test_analyser_role_is_trimmed(self) -> None:  # (E)
        assert _resolve_handoff_target_role(RoleRequirements(role_title="  Nurse  "), {}) == "Nurse"

    def test_manual_role_is_trimmed(self) -> None:  # (E)
        role = RoleRequirements(role_title="")
        assert _resolve_handoff_target_role(role, {"handoff_target_role": "  Chef "}) == "Chef"


# --- Context build recovery + contract preservation --------------------------


class TestBuildRecovery:
    def test_manual_role_recovers_missing_role_title(self) -> None:  # (C)
        ctx = build_preparation_context(
            target_role="Senior Product Manager",
            role_requirements=RoleRequirements(role_title=None, required_skills=["Roadmapping"]),
        )
        assert ctx.target_role == "Senior Product Manager"
        assert ctx.required_skills == ["Roadmapping"]  # other analyser data preserved

    def test_contract_still_rejects_empty_role(self) -> None:  # (G) contract intact
        with pytest.raises(ValueError):
            build_preparation_context(role_requirements=RoleRequirements(role_title=""))
        with pytest.raises(ValueError):
            build_preparation_context(target_role="   ", role_requirements=RoleRequirements())

    def test_no_placeholder_is_substituted(self) -> None:
        # Nothing fabricates "Unknown"/"N/A"/etc — a missing role raises instead.
        with pytest.raises(ValueError):
            build_preparation_context()


# --- Streamlit smoke: Career Tools with an unidentified role -----------------


def _run_tools_page(**session) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["os_nav"] = "Career Intelligence"
    at.session_state["career_section"] = "Career Tools"
    for key, value in session.items():
        at.session_state[key] = value
    at.run()
    return at


class TestCareerToolsSmoke:
    def test_empty_role_title_does_not_crash(self) -> None:  # (B, G, §12)
        at = _run_tools_page(role_requirements=RoleRequirements(role_title=""))
        assert not at.exception
        warnings = " ".join(w.value for w in at.warning)
        assert "Target role needed" in warnings

    def test_none_role_title_does_not_crash(self) -> None:  # (§12)
        at = _run_tools_page(role_requirements=RoleRequirements(role_title=None))
        assert not at.exception

    def test_valid_role_renders_handoff(self) -> None:  # (F)
        at = _run_tools_page(
            role_requirements=RoleRequirements(role_title="Data Analyst",
                                               required_skills=["SQL"]))
        assert not at.exception
        # The handoff button is present (not blocked by a missing role).
        assert any("Practise this role" in b.label for b in at.button)

    def test_manual_role_enables_handoff(self) -> None:  # (C via UI)
        at = _run_tools_page(
            role_requirements=RoleRequirements(role_title=None),
            handoff_target_role="Senior Product Manager")
        assert not at.exception


# --- Stale-state invalidation (H) --------------------------------------------


class TestStaleStateInvalidation:
    def test_new_analysis_drops_stale_downstream_state(self) -> None:  # (H)
        from src.career.ui import _invalidate_downstream_role_state

        ss: dict = {
            "gap_result": object(),
            "prep_plan": object(),
            "question_set": object(),
            "handoff_target_role": "Old Role",
            handoff.PREP_CONTEXT_KEY: build_preparation_context(target_role="Old Role"),
            "chat_history": [{"role": "user", "content": "keep me"}],  # unrelated
        }
        _invalidate_downstream_role_state(ss)
        for key in ("gap_result", "prep_plan", "question_set", "handoff_target_role"):
            assert key not in ss
        assert handoff.has_context(ss) is False
        # Unrelated Career chat/history is preserved.
        assert ss["chat_history"] == [{"role": "user", "content": "keep me"}]


# --- Full Career → Practise → Interview integration still works (I) ----------


class TestIntegrationStillWorks:
    def test_request_practice_roundtrip(self) -> None:
        ss: dict = {}
        ctx = build_preparation_context(
            target_role="Data Analyst",
            role_requirements=RoleRequirements(role_title="Data Analyst",
                                               required_skills=["SQL"]))
        handoff.request_practice(ss, ctx)
        assert handoff.has_context(ss) is True
        prefill = handoff.interview_prefill(ss)
        assert prefill["target_role"] == "Data Analyst"
        assert isinstance(handoff.get_context(ss), PreparationContext)


def test_validationerror_is_importable() -> None:
    # The defensive UI path catches both ValueError and pydantic ValidationError.
    assert ValidationError is not None

