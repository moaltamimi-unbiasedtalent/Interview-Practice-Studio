"""Conversational interview session state.

This module owns the interview's explicit state machine and all per-session
data. It is the only place that talks to Streamlit's ``session_state``, and it
does so through an injected store (a ``MutableMapping``), so:

* the state machine is fully testable with a plain ``dict`` — no Streamlit run
  is needed;
* everything lives under a single namespace key, isolated from Streamlit widget
  keys and other session values;
* nothing is written to disk — interview content is in memory only, for the
  duration of the browser session.

The manager enforces valid transitions between the explicit states and guards
against duplicate API calls caused by Streamlit reruns. Button presses are
never stored as state; only domain facts (what has been asked, answered,
evaluated and which state we are in) drive behaviour.
"""

from __future__ import annotations

import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src import constants
from src.models import (
    AnswerEvaluation,
    BranchQuestion,
    FinalInterviewReport,
    InterviewConfiguration,
    InterviewQuestion,
    InterviewStrategy,
    ModelSettings,
    UsageRecord,
)

__all__ = [
    "SessionState",
    "SessionError",
    "InvalidStateTransitionError",
    "DuplicateSubmissionError",
    "BranchError",
    "SessionData",
    "SessionManager",
    "NAMESPACE",
]

# Single namespaced key under which all session data lives in the store.
NAMESPACE = "interview_practice_studio_session"


class SessionState(str, Enum):
    """The explicit states an interview session can be in."""

    SETUP = "SETUP"
    STRATEGY_READY = "STRATEGY_READY"
    INTERVIEW_IN_PROGRESS = "INTERVIEW_IN_PROGRESS"
    AWAITING_ANSWER = "AWAITING_ANSWER"
    EVALUATING = "EVALUATING"
    INTERVIEW_COMPLETE = "INTERVIEW_COMPLETE"
    REPORT_READY = "REPORT_READY"
    ERROR = "ERROR"
    # Interview Deep Dive (branching) sub-states.
    BRANCH_AWAITING_ANSWER = "BRANCH_AWAITING_ANSWER"
    BRANCH_EVALUATING = "BRANCH_EVALUATING"


# --- Errors ------------------------------------------------------------------


class SessionError(Exception):
    """Base class for controlled session errors (safe to show to a user)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidStateTransitionError(SessionError):
    """Raised when an operation is not allowed from the current state."""


class DuplicateSubmissionError(SessionError):
    """Raised when the same submission is made twice (e.g., a Streamlit rerun)."""


class BranchError(SessionError):
    """Raised for invalid Deep Dive branching operations."""


# --- Session data ------------------------------------------------------------


@dataclass
class SessionData:
    """All data for one interview session, held in memory only."""

    state: SessionState = SessionState.SETUP

    # Configuration and settings.
    config: InterviewConfiguration | None = None
    settings: ModelSettings | None = None
    prompt_technique: str | None = None

    # Interview content.
    strategy: InterviewStrategy | None = None
    chat_messages: list[dict[str, str]] = field(default_factory=list)
    questions: list[InterviewQuestion] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    evaluations: list[AnswerEvaluation] = field(default_factory=list)
    report: FinalInterviewReport | None = None
    current_question_number: int = 0

    # Usage and cost.
    usage_records: list[UsageRecord] = field(default_factory=list)
    cumulative_cost_usd: float = 0.0

    # Interview Deep Dive (branching) — tracked separately from main progress so
    # a branch can never move the main interview forward.
    branch_active: bool = False
    active_branch_id: str | None = None
    branch_parent_question_id: int | None = None
    branch_mode: str | None = None
    branch_depth: int = 0
    branch_questions: list[BranchQuestion] = field(default_factory=list)
    branch_answers: list[str] = field(default_factory=list)
    branch_evaluations: list[AnswerEvaluation] = field(default_factory=list)
    branch_started_at: float | None = None
    # Completed branches, archived for history and the final report.
    branches: list[dict[str, Any]] = field(default_factory=list)

    # Control fields.
    error: str | None = None
    previous_state: SessionState | None = None
    interview_start_time: float | None = None
    active_operation: str | None = None

    # Harmless developer preferences (survive a reset).
    preferences: dict[str, Any] = field(default_factory=dict)


def _default_store() -> MutableMapping[str, Any]:
    """Return Streamlit's session_state (imported lazily so tests stay free of it)."""
    import streamlit as st

    return st.session_state


# --- Session manager ---------------------------------------------------------


class SessionManager:
    """Owns the interview state machine over a namespaced session store."""

    def __init__(
        self,
        store: MutableMapping[str, Any] | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store if store is not None else _default_store()
        self._clock = clock
        self.initialise_session()

    # -- accessors ------------------------------------------------------------

    @property
    def data(self) -> SessionData:
        return self._store[NAMESPACE]

    @property
    def state(self) -> SessionState:
        return self.data.state

    @property
    def is_processing(self) -> bool:
        """True while an operation (e.g., an API call) is in flight."""
        return self.data.active_operation is not None

    # -- transition helper ----------------------------------------------------

    def _require(self, allowed: set[SessionState], action: str) -> None:
        if self.data.state not in allowed:
            allowed_names = ", ".join(sorted(s.value for s in allowed))
            raise InvalidStateTransitionError(
                f"Cannot {action} from state {self.data.state.value}. "
                f"Allowed only from: {allowed_names}."
            )

    def _require_no_active_branch(self, action: str) -> None:
        """Main-interview progress operations are blocked while a branch is open."""
        if self.data.branch_active:
            raise InvalidStateTransitionError(
                f"Cannot {action} while a Deep Dive is active. Return to the main "
                "interview first."
            )

    # -- 1. initialise --------------------------------------------------------

    def initialise_session(self) -> SessionData:
        """Ensure a session exists in the store without clobbering an existing one.

        Safe to call on every Streamlit rerun: it only creates fresh data the
        first time, so chat history and interview state persist across reruns.
        """
        existing = self._store.get(NAMESPACE)
        if not isinstance(existing, SessionData):
            self._store[NAMESPACE] = SessionData()
        return self.data

    # -- 2. start a new interview ---------------------------------------------

    def start_new_interview(
        self, config: InterviewConfiguration, settings: ModelSettings
    ) -> None:
        """Store configuration and begin a fresh interview (still in SETUP)."""
        self._require({SessionState.SETUP}, "start a new interview")
        data = self.data
        data.config = config
        data.settings = settings
        data.prompt_technique = settings.prompt_technique
        data.interview_start_time = self._clock()
        # Clear any prior interview content (defensive; SETUP is normally clean).
        data.strategy = None
        data.chat_messages = []
        data.questions = []
        data.answers = []
        data.evaluations = []
        data.report = None
        data.current_question_number = 0
        data.usage_records = []
        data.cumulative_cost_usd = 0.0
        data.error = None
        data.previous_state = None
        data.active_operation = None

    # -- 3. save strategy -----------------------------------------------------

    def save_strategy(self, strategy: InterviewStrategy) -> None:
        self._require({SessionState.SETUP}, "save a strategy")
        self.data.strategy = strategy
        self.data.state = SessionState.STRATEGY_READY

    # -- 4. add question ------------------------------------------------------

    def add_question(self, question: InterviewQuestion) -> None:
        self._require(
            {SessionState.STRATEGY_READY, SessionState.INTERVIEW_IN_PROGRESS},
            "add a question",
        )
        self._require_no_active_branch("add a main question")
        self.data.questions.append(question)
        self.data.current_question_number = len(self.data.questions)
        self.data.state = SessionState.AWAITING_ANSWER

    # -- 5. add candidate answer ----------------------------------------------

    def add_candidate_answer(self, answer: str) -> None:
        """Record the candidate's answer to the current question.

        Guards against duplicate submission: exactly one answer may be recorded
        per asked question.
        """
        self._require({SessionState.AWAITING_ANSWER}, "submit an answer")
        if len(self.data.answers) >= len(self.data.questions):
            raise DuplicateSubmissionError(
                "An answer for this question has already been submitted."
            )
        self.data.answers.append(answer)
        self.data.state = SessionState.EVALUATING

    # -- 6. add evaluation ----------------------------------------------------

    def add_evaluation(self, evaluation: AnswerEvaluation) -> None:
        self._require({SessionState.EVALUATING}, "add an evaluation")
        self.data.evaluations.append(evaluation)
        self.data.state = SessionState.INTERVIEW_IN_PROGRESS

    # -- 7. advance interview -------------------------------------------------

    def advance_interview(self) -> bool:
        """Move toward the next question.

        Returns ``True`` if more questions remain (stay in progress, ready for
        the next question) or ``False`` if the planned number has been reached
        (transition to INTERVIEW_COMPLETE).
        """
        self._require({SessionState.INTERVIEW_IN_PROGRESS}, "advance the interview")
        self._require_no_active_branch("advance the interview")
        planned = (
            self.data.config.number_of_questions
            if self.data.config is not None
            else self.data.current_question_number
        )
        has_more = self.data.current_question_number < planned
        if not has_more:
            self.data.state = SessionState.INTERVIEW_COMPLETE
        return has_more

    # -- 8. end interview early -----------------------------------------------

    def end_interview_early(self) -> None:
        self._require(
            {
                SessionState.STRATEGY_READY,
                SessionState.INTERVIEW_IN_PROGRESS,
                SessionState.AWAITING_ANSWER,
                SessionState.EVALUATING,
            },
            "end the interview early",
        )
        self._require_no_active_branch("end the interview early")
        self.data.state = SessionState.INTERVIEW_COMPLETE

    # -- 9. complete interview ------------------------------------------------

    def complete_interview(self) -> None:
        self._require(
            {SessionState.INTERVIEW_IN_PROGRESS}, "complete the interview"
        )
        self._require_no_active_branch("complete the interview")
        self.data.state = SessionState.INTERVIEW_COMPLETE

    # -- Interview Deep Dive (branching) --------------------------------------

    def start_branch(self, mode: str) -> None:
        """Open a Deep Dive from the most recently evaluated main answer.

        Only allowed once a main answer has been evaluated. Does not touch the
        main question counter or lists.
        """
        self._require({SessionState.INTERVIEW_IN_PROGRESS}, "start a deep dive")
        if self.data.branch_active:
            raise BranchError("A Deep Dive is already active.")
        if not self.data.evaluations or not self.data.questions:
            raise BranchError(
                "A Deep Dive can only start after an answer has been evaluated."
            )
        if mode not in constants.BRANCH_MODES:
            raise BranchError(
                f"Unknown deep-dive mode {mode!r}; supported: "
                f"{list(constants.BRANCH_MODES)}."
            )
        data = self.data
        data.branch_active = True
        data.branch_mode = mode
        data.branch_parent_question_id = data.questions[-1].question_id
        data.active_branch_id = f"branch-{data.branch_parent_question_id}-{len(data.branches) + 1}"
        data.branch_depth = 0
        data.branch_questions = []
        data.branch_answers = []
        data.branch_evaluations = []
        data.branch_started_at = self._clock()
        # State stays INTERVIEW_IN_PROGRESS; branch_active marks the deep dive.

    def next_branch_id(self) -> str:
        """The branch id for the next branch turn (used by the app before adding)."""
        return f"{self.data.active_branch_id}-q{len(self.data.branch_questions) + 1}"

    def add_branch_question(self, question: BranchQuestion) -> None:
        """Record a generated branch question and await its answer."""
        self._require(
            {SessionState.INTERVIEW_IN_PROGRESS}, "add a deep-dive question"
        )
        if not self.data.branch_active:
            raise BranchError("No Deep Dive is active.")
        if len(self.data.branch_questions) >= constants.MAX_BRANCH_DEPTH:
            raise BranchError(
                f"Maximum deep-dive depth ({constants.MAX_BRANCH_DEPTH}) reached."
            )
        self.data.branch_questions.append(question)
        self.data.branch_depth = len(self.data.branch_questions)
        self.data.state = SessionState.BRANCH_AWAITING_ANSWER

    def add_branch_answer(self, answer: str) -> None:
        """Record the candidate's answer to the current branch question."""
        self._require(
            {SessionState.BRANCH_AWAITING_ANSWER}, "submit a deep-dive answer"
        )
        if len(self.data.branch_answers) >= len(self.data.branch_questions):
            raise DuplicateSubmissionError(
                "An answer for this deep-dive question has already been submitted."
            )
        self.data.branch_answers.append(answer)
        self.data.state = SessionState.BRANCH_EVALUATING

    def add_branch_evaluation(self, evaluation: AnswerEvaluation) -> None:
        """Record the evaluation of a branch answer and return to the deep-dive hub."""
        self._require(
            {SessionState.BRANCH_EVALUATING}, "add a deep-dive evaluation"
        )
        self.data.branch_evaluations.append(evaluation)
        # Back to the in-progress hub, still inside the branch (go deeper / return).
        self.data.state = SessionState.INTERVIEW_IN_PROGRESS

    def can_go_deeper(self) -> bool:
        """Whether another branch level is available."""
        return (
            self.data.branch_active
            and len(self.data.branch_questions) < constants.MAX_BRANCH_DEPTH
            and len(self.data.branch_answers) == len(self.data.branch_questions)
            and len(self.data.branch_evaluations) == len(self.data.branch_questions)
        )

    def return_to_main_interview(self) -> None:
        """Close the active Deep Dive, archiving it, and resume the main interview.

        Never changes the main question counter, so the main interview continues
        from exactly where it paused.
        """
        if not self.data.branch_active:
            raise BranchError("No Deep Dive is active.")
        self._require(
            {
                SessionState.INTERVIEW_IN_PROGRESS,
                SessionState.BRANCH_AWAITING_ANSWER,
                SessionState.BRANCH_EVALUATING,
            },
            "return to the main interview",
        )
        data = self.data
        if data.branch_questions:
            data.branches.append(
                {
                    "branch_id": data.active_branch_id,
                    "parent_question_id": data.branch_parent_question_id,
                    "mode": data.branch_mode,
                    "questions": list(data.branch_questions),
                    "answers": list(data.branch_answers),
                    "evaluations": list(data.branch_evaluations),
                }
            )
        # Clear the active branch; main progress is untouched.
        data.branch_active = False
        data.active_branch_id = None
        data.branch_parent_question_id = None
        data.branch_mode = None
        data.branch_depth = 0
        data.branch_questions = []
        data.branch_answers = []
        data.branch_evaluations = []
        data.branch_started_at = None
        data.state = SessionState.INTERVIEW_IN_PROGRESS

    # -- 10. save final report ------------------------------------------------

    def save_final_report(self, report: FinalInterviewReport) -> None:
        self._require({SessionState.INTERVIEW_COMPLETE}, "save the final report")
        self.data.report = report
        self.data.state = SessionState.REPORT_READY

    # -- 11. error handling & recovery ----------------------------------------

    def enter_error(
        self, message: str, *, recover_to: SessionState | None = None
    ) -> None:
        """Record a controlled, recoverable error and move to ERROR.

        ``recover_to`` sets the state :meth:`recover_from_error` will return to;
        it defaults to the state we were in when the error occurred.
        """
        data = self.data
        if data.state is not SessionState.ERROR:
            data.previous_state = recover_to or data.state
        elif recover_to is not None:
            data.previous_state = recover_to
        data.error = message
        data.active_operation = None  # release any in-flight guard
        data.state = SessionState.ERROR

    def recover_from_error(self) -> None:
        self._require({SessionState.ERROR}, "recover from an error")
        target = self.data.previous_state or SessionState.SETUP
        self.data.state = target
        self.data.error = None
        self.data.previous_state = None

    # -- 12. reset ------------------------------------------------------------

    def reset_interview(self) -> None:
        """Clear all interview data safely, keeping harmless developer prefs."""
        preferences = dict(self.data.preferences)
        self._store[NAMESPACE] = SessionData(preferences=preferences)

    # -- usage / chat helpers -------------------------------------------------

    def record_usage(self, usage: UsageRecord) -> None:
        """Append a usage record and update cumulative session cost (USD)."""
        self.data.usage_records.append(usage)
        best_effort = (
            usage.reported_cost
            if usage.reported_cost is not None
            else usage.calculated_cost
        )
        self.data.cumulative_cost_usd += float(best_effort)

    def add_chat_message(self, role: str, content: str) -> None:
        """Append a message to the persistent chat history."""
        self.data.chat_messages.append({"role": role, "content": content})

    # -- duplicate-call protection --------------------------------------------

    def begin_operation(self, name: str) -> bool:
        """Claim an in-flight operation slot; return False if one is already active.

        Wrap each model call in ``begin_operation``/``end_operation`` so a
        Streamlit rerun that re-executes the script does not fire a duplicate
        API call.
        """
        if self.data.active_operation is not None:
            return False
        self.data.active_operation = name
        return True

    def end_operation(self) -> None:
        self.data.active_operation = None

    # -- preferences ----------------------------------------------------------

    def set_preference(self, key: str, value: Any) -> None:
        self.data.preferences[key] = value

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self.data.preferences.get(key, default)
