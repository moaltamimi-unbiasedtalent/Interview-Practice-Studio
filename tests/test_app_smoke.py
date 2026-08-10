"""Smoke tests for the Streamlit app and its UI helpers.

The app is exercised with ``streamlit.testing.v1.AppTest``, which runs the
script in-process without a browser and without any network calls (the app
makes no API request until the user submits). Later states are pre-seeded into
session_state so their rendering is covered offline too. Pure helpers are
unit-tested directly.
"""

import pathlib

import app
import pytest
from streamlit.testing.v1 import AppTest

from src import constants, ui_helpers
from src.models import (
    FinalInterviewReport,
    InterviewConfiguration,
    InterviewStrategy,
)
from src.session_manager import NAMESPACE, SessionData, SessionState

# Absolute path so AppTest.from_file resolves correctly across Streamlit
# versions (>=1.61 resolves relative paths against the calling test file's
# directory rather than the working directory).
APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _config() -> InterviewConfiguration:
    return InterviewConfiguration(
        target_role="Registered Nurse",
        industry_or_sector="healthcare",
        career_level="senior",
        interview_types=["behavioural"],
        interviewer_persona="neutral",
        difficulty="moderate",
        response_detail="standard",
    )


def _strategy() -> InterviewStrategy:
    section = ["item"]
    return InterviewStrategy(
        role_summary="A profession-neutral summary.",
        likely_interview_stages=section,
        critical_competencies=section,
        likely_question_themes=section,
        probable_challenges=section,
        evidence_to_prepare=section,
        technical_or_functional_topics=section,
        behavioural_topics=section,
        questions_for_interviewer=section,
        preparation_priorities=section,
    )


def _report() -> FinalInterviewReport:
    section = ["item"]
    return FinalInterviewReport(
        overall_readiness_score=68,
        performance_summary="Solid overall.",
        strongest_competencies=section,
        development_priorities=section,
        recurring_answer_patterns=section,
        highest_risk_questions=section,
        evidence_gaps=section,
        recommended_practice_actions=section,
        final_interview_checklist=section,
    )


def _seed(state: SessionData) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state[NAMESPACE] = state
    return at


# --- Startup & per-state rendering (AppTest, no network) --------------------


class TestAppRenders:
    def test_startup_has_no_exception_and_shows_title(self) -> None:
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        assert not at.exception
        assert any(constants.APP_NAME in t.value for t in at.title)

    def test_setup_form_is_present_on_startup(self) -> None:
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        assert not at.exception
        # The setup form's submit button exists.
        labels = [b.label for b in at.button]
        assert any("Generate strategy" in label for label in labels)

    def test_strategy_state_renders_role_analysis(self) -> None:
        at = _seed(
            SessionData(
                state=SessionState.STRATEGY_READY,
                config=_config(),
                strategy=_strategy(),
            )
        )
        at.run()
        assert not at.exception
        assert any("Role analysis" in s.value for s in at.subheader)

    def test_report_state_renders_report_and_downloads(self) -> None:
        at = _seed(
            SessionData(
                state=SessionState.REPORT_READY,
                config=_config(),
                report=_report(),
            )
        )
        at.run()
        assert not at.exception
        assert any("readiness report" in s.value.lower() for s in at.subheader)
        # JSON + Markdown download buttons.
        assert len(at.get("download_button")) == 2

    def test_error_state_renders_controlled_message(self) -> None:
        at = _seed(
            SessionData(
                state=SessionState.ERROR,
                error="A controlled, safe error message.",
                previous_state=SessionState.SETUP,
            )
        )
        at.run()
        assert not at.exception
        assert any("controlled, safe error" in e.value for e in at.error)

    def test_missing_key_warning_when_unconfigured(self, monkeypatch) -> None:
        # Force load_config to resolve no key by neutralising its secret
        # readers on the shared src.config module (AppTest runs in-process).
        monkeypatch.setattr("src.config._read_streamlit_secret", lambda: None)
        monkeypatch.setattr("src.config._read_environment_secret", lambda: None)
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        assert not at.exception
        assert any("API key" in w.value for w in at.warning)


# --- UI helper unit tests ----------------------------------------------------


class TestUiHelpers:
    def test_all_option_ids_are_valid_domain_values(self) -> None:
        assert ui_helpers.all_option_ids_valid() is True

    def test_label_id_roundtrip(self) -> None:
        for pairs in (
            ui_helpers.CAREER_LEVELS,
            ui_helpers.INTERVIEW_TYPES,
            ui_helpers.PERSONAS,
            ui_helpers.DIFFICULTIES,
            ui_helpers.RESPONSE_DETAILS,
        ):
            for label, domain_id in pairs:
                assert ui_helpers.id_for_label(pairs, label) == domain_id
                assert ui_helpers.label_for_id(pairs, domain_id) == label

    def test_models_are_approved(self) -> None:
        for model in ui_helpers.MODELS:
            assert model in constants.APPROVED_MODELS

    def test_format_usd(self) -> None:
        assert ui_helpers.format_usd(None) == "—"
        assert ui_helpers.format_usd(0.0015).startswith("$")

    def test_report_json_and_markdown(self) -> None:
        report = _report()
        as_json = ui_helpers.report_to_json(report)
        assert '"overall_readiness_score": 68' in as_json
        as_md = ui_helpers.report_to_markdown(report, _config())
        assert as_md.startswith("# Interview readiness report")
        assert "Development priorities" in as_md
        assert "not an employment decision" in as_md

    def test_technique_options_come_from_registry(self) -> None:
        options = ui_helpers.technique_options()
        ids = [tid for tid, _ in options]
        assert set(ids) == set(constants.PROMPT_TECHNIQUES)


# --- Build-configuration mapping (no Streamlit runtime needed) ---------------


class TestBuildConfiguration:
    def test_maps_labels_to_domain_ids(self) -> None:
        cfg = app._build_configuration(
            target_role="  Registered Nurse  ",
            industry="Healthcare",
            career_label="Senior professional",
            company_context="",
            job_description="",
            candidate_background="",
            interview_type_labels=["Behavioural", "Leadership"],
            persona_label="Sceptical executive",
            difficulty_label="Hard",
            number_of_questions=5,
            detail_label="Detailed",
        )
        assert cfg.target_role == "Registered Nurse"  # sanitised
        assert cfg.career_level == "senior"
        assert cfg.interview_types == ["behavioural", "leadership"]
        assert cfg.interviewer_persona == "sceptical_executive"
        assert cfg.difficulty == "hard"
        assert cfg.response_detail == "detailed"
        assert cfg.number_of_questions == 5

    def test_empty_target_role_is_rejected(self) -> None:
        from src.security import InputValidationError

        with pytest.raises(InputValidationError):
            app._build_configuration(
                target_role="   ",
                industry="",
                career_label="Professional",
                company_context="",
                job_description="",
                candidate_background="",
                interview_type_labels=["Behavioural"],
                persona_label="Neutral hiring manager",
                difficulty_label="Moderate",
                number_of_questions=3,
                detail_label="Balanced",
            )

    def test_oversized_job_description_is_rejected(self) -> None:
        from src.security import InputValidationError

        with pytest.raises(InputValidationError):
            app._build_configuration(
                target_role="Engineer",
                industry="",
                career_label="Professional",
                company_context="",
                job_description="x" * (constants.MAX_JOB_DESCRIPTION_CHARS + 1),
                candidate_background="",
                interview_type_labels=["Behavioural"],
                persona_label="Neutral hiring manager",
                difficulty_label="Moderate",
                number_of_questions=3,
                detail_label="Balanced",
            )
