"""Tests for the conversational interview session manager.

The manager is tested with a plain ``dict`` store, so no Streamlit run is
required and nothing touches disk.
"""

import pytest

from src.models import (
    AnswerEvaluation,
    FinalInterviewReport,
    InterviewConfiguration,
    InterviewQuestion,
    InterviewStrategy,
    ModelSettings,
    UsageRecord,
)
from src.session_manager import (
    NAMESPACE,
    DuplicateSubmissionError,
    InvalidStateTransitionError,
    SessionData,
    SessionManager,
    SessionState,
)


# --- Fixtures / builders -----------------------------------------------------


def _config(number_of_questions: int = 2) -> InterviewConfiguration:
    return InterviewConfiguration(
        target_role="Registered Nurse",
        industry_or_sector="healthcare",
        career_level="senior",
        interview_types=["behavioural"],
        interviewer_persona="neutral",
        difficulty="moderate",
        response_detail="standard",
        number_of_questions=number_of_questions,
    )


def _settings() -> ModelSettings:
    return ModelSettings(model="openai/gpt-5-mini", prompt_technique="rubric_json")


def _strategy() -> InterviewStrategy:
    section = ["item"]
    return InterviewStrategy(
        role_summary="A summary.",
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


def _question(qid: int) -> InterviewQuestion:
    return InterviewQuestion(
        question_id=qid,
        question=f"Question {qid}?",
        question_type="behavioural",
        competency="teamwork",
        difficulty="moderate",
        interviewer_intent="Assess collaboration.",
        expected_answer_elements=["situation", "action", "result"],
    )


def _evaluation(score: int = 70) -> AnswerEvaluation:
    return AnswerEvaluation(
        overall_score=score,
        relevance=7,
        structure=7,
        evidence=6,
        role_knowledge=7,
        problem_solving=7,
        communication=7,
        credibility=7,
        strengths=["clear"],
        improvement_areas=["add detail"],
        missing_evidence=["metrics"],
        stronger_answer_structure="STAR",
        improved_example_answer="Example.",
        follow_up_question="What changed?",
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


def _usage(reported: float | None = 0.001, calculated: float = 0.0) -> UsageRecord:
    return UsageRecord(
        model="openai/gpt-5-mini",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        reported_cost=reported,
        calculated_cost=calculated,
        cost_source="reported" if reported is not None else "calculated",
        request_duration_seconds=0.5,
    )


def _manager(store: dict | None = None) -> SessionManager:
    return SessionManager(store if store is not None else {}, clock=lambda: 1000.0)


def _run_to_awaiting(sm: SessionManager, qid: int = 1) -> None:
    """Drive a fresh manager to AWAITING_ANSWER for question ``qid``."""
    if sm.state is SessionState.SETUP:
        sm.start_new_interview(_config(), _settings())
        sm.save_strategy(_strategy())
    sm.add_question(_question(qid))


# --- Initialisation ----------------------------------------------------------


class TestInitialisation:
    def test_starts_in_setup(self) -> None:
        assert _manager().state is SessionState.SETUP

    def test_creates_namespaced_structure(self) -> None:
        store: dict = {}
        _manager(store)
        assert NAMESPACE in store
        assert isinstance(store[NAMESPACE], SessionData)

    def test_does_not_clobber_existing_session_on_reinit(self) -> None:
        store: dict = {}
        sm1 = _manager(store)
        sm1.start_new_interview(_config(), _settings())
        sm1.add_chat_message("assistant", "hello")
        # A second manager over the same store simulates a Streamlit rerun.
        sm2 = SessionManager(store, clock=lambda: 1.0)
        assert sm2.data.chat_messages == [{"role": "assistant", "content": "hello"}]
        assert sm2.data.config is not None

    def test_leaves_other_store_keys_untouched(self) -> None:
        store: dict = {"_widget_text_input": "typed", "theme": "dark"}
        _manager(store)
        assert store["_widget_text_input"] == "typed"
        assert store["theme"] == "dark"


# --- Happy-path transitions --------------------------------------------------


class TestValidTransitions:
    def test_full_interview_flow(self) -> None:
        sm = _manager()
        sm.start_new_interview(_config(number_of_questions=2), _settings())
        assert sm.state is SessionState.SETUP
        assert sm.data.interview_start_time == 1000.0
        assert sm.data.prompt_technique == "rubric_json"

        sm.save_strategy(_strategy())
        assert sm.state is SessionState.STRATEGY_READY

        # Question 1
        sm.add_question(_question(1))
        assert sm.state is SessionState.AWAITING_ANSWER
        assert sm.data.current_question_number == 1
        sm.add_candidate_answer("My first answer.")
        assert sm.state is SessionState.EVALUATING
        sm.add_evaluation(_evaluation())
        assert sm.state is SessionState.INTERVIEW_IN_PROGRESS
        assert sm.advance_interview() is True  # one more to go

        # Question 2
        sm.add_question(_question(2))
        assert sm.state is SessionState.AWAITING_ANSWER
        sm.add_candidate_answer("My second answer.")
        sm.add_evaluation(_evaluation(80))
        assert sm.advance_interview() is False  # planned count reached
        assert sm.state is SessionState.INTERVIEW_COMPLETE

        sm.save_final_report(_report())
        assert sm.state is SessionState.REPORT_READY
        assert sm.data.report is not None

    def test_complete_interview_operation(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        sm.add_candidate_answer("answer")
        sm.add_evaluation(_evaluation())
        sm.complete_interview()
        assert sm.state is SessionState.INTERVIEW_COMPLETE

    def test_end_interview_early_from_awaiting(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        sm.end_interview_early()
        assert sm.state is SessionState.INTERVIEW_COMPLETE


# --- Invalid transitions -----------------------------------------------------


class TestInvalidTransitions:
    def test_cannot_add_question_from_setup(self) -> None:
        sm = _manager()
        with pytest.raises(InvalidStateTransitionError):
            sm.add_question(_question(1))

    def test_cannot_save_strategy_twice(self) -> None:
        sm = _manager()
        sm.start_new_interview(_config(), _settings())
        sm.save_strategy(_strategy())
        with pytest.raises(InvalidStateTransitionError):
            sm.save_strategy(_strategy())

    def test_cannot_answer_before_question(self) -> None:
        sm = _manager()
        sm.start_new_interview(_config(), _settings())
        sm.save_strategy(_strategy())
        with pytest.raises(InvalidStateTransitionError):
            sm.add_candidate_answer("too early")

    def test_cannot_evaluate_before_answer(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        with pytest.raises(InvalidStateTransitionError):
            sm.add_evaluation(_evaluation())

    def test_cannot_save_report_before_complete(self) -> None:
        sm = _manager()
        with pytest.raises(InvalidStateTransitionError):
            sm.save_final_report(_report())

    def test_cannot_start_new_interview_mid_interview(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        with pytest.raises(InvalidStateTransitionError):
            sm.start_new_interview(_config(), _settings())


# --- Duplicate-submission protection -----------------------------------------


class TestDuplicateProtection:
    def test_double_answer_is_blocked_by_state(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        sm.add_candidate_answer("first")
        # A Streamlit rerun re-calling submit hits EVALUATING now.
        with pytest.raises(InvalidStateTransitionError):
            sm.add_candidate_answer("duplicate")

    def test_begin_operation_prevents_duplicate_calls(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        assert sm.begin_operation("evaluate") is True
        # A rerun tries to start the same operation again → refused.
        assert sm.begin_operation("evaluate") is False
        assert sm.is_processing is True
        sm.end_operation()
        assert sm.is_processing is False
        assert sm.begin_operation("evaluate") is True

    def test_duplicate_answer_length_guard(self) -> None:
        # Directly exercise the per-question idempotency guard.
        sm = _manager()
        _run_to_awaiting(sm)
        sm.add_candidate_answer("first")
        sm.data.state = SessionState.AWAITING_ANSWER  # force the guard path
        with pytest.raises(DuplicateSubmissionError):
            sm.add_candidate_answer("second for same question")


# --- Error recovery ----------------------------------------------------------


class TestErrorRecovery:
    def test_enter_and_recover_returns_to_previous_state(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        sm.add_candidate_answer("answer")  # now EVALUATING
        sm.enter_error("model timed out")
        assert sm.state is SessionState.ERROR
        assert sm.data.error == "model timed out"
        sm.recover_from_error()
        assert sm.state is SessionState.EVALUATING
        assert sm.data.error is None

    def test_recover_to_explicit_target(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        sm.add_candidate_answer("answer")
        sm.enter_error("bad", recover_to=SessionState.AWAITING_ANSWER)
        sm.recover_from_error()
        assert sm.state is SessionState.AWAITING_ANSWER

    def test_error_releases_processing_guard(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        sm.begin_operation("evaluate")
        sm.enter_error("boom")
        assert sm.is_processing is False

    def test_cannot_recover_when_not_in_error(self) -> None:
        sm = _manager()
        with pytest.raises(InvalidStateTransitionError):
            sm.recover_from_error()


# --- Reset -------------------------------------------------------------------


class TestReset:
    def test_reset_clears_interview_data(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        sm.add_candidate_answer("answer")
        sm.add_evaluation(_evaluation())
        sm.reset_interview()
        assert sm.state is SessionState.SETUP
        assert sm.data.questions == []
        assert sm.data.answers == []
        assert sm.data.evaluations == []
        assert sm.data.config is None
        assert sm.data.strategy is None
        assert sm.data.current_question_number == 0

    def test_reset_keeps_developer_preferences(self) -> None:
        sm = _manager()
        sm.set_preference("debug", True)
        sm.set_preference("preferred_model", "openai/gpt-5-nano")
        _run_to_awaiting(sm)
        sm.reset_interview()
        assert sm.get_preference("debug") is True
        assert sm.get_preference("preferred_model") == "openai/gpt-5-nano"

    def test_reset_then_start_again(self) -> None:
        sm = _manager()
        _run_to_awaiting(sm)
        sm.reset_interview()
        # A fresh interview can be started after reset.
        sm.start_new_interview(_config(), _settings())
        sm.save_strategy(_strategy())
        assert sm.state is SessionState.STRATEGY_READY


# --- Usage / cost / chat -----------------------------------------------------


class TestUsageAndChat:
    def test_cumulative_cost_uses_reported_then_calculated(self) -> None:
        sm = _manager()
        sm.start_new_interview(_config(), _settings())
        sm.record_usage(_usage(reported=0.002))
        sm.record_usage(_usage(reported=None, calculated=0.0015))
        assert sm.data.cumulative_cost_usd == pytest.approx(0.0035)
        assert len(sm.data.usage_records) == 2

    def test_chat_history_accumulates(self) -> None:
        sm = _manager()
        sm.add_chat_message("assistant", "Question 1?")
        sm.add_chat_message("user", "My answer.")
        assert [m["role"] for m in sm.data.chat_messages] == ["assistant", "user"]
