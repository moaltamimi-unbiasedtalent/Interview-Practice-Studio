"""Streamlit entry point for Interview Practice Studio.

This file renders the interface only. All behaviour lives in ``src``: the
session state machine (`session_manager`), the interview services, the security
layer, pricing and the OpenRouter client. The app is a single page that routes
on the explicit session state, so a Streamlit rerun always shows a consistent
view and never fires a duplicate API call.
"""

from __future__ import annotations

import json
import logging

import streamlit as st
import streamlit.components.v1 as components
from pydantic import ValidationError

import dataclasses
import os

from src import auth, constants, security, timing, ui_helpers
from src.avatar import LocalAvatarRenderer
from src.persistence import init_db, make_engine, make_session_factory
from src.repository import InterviewRepository
from src.config import AppConfig, load_config
from src.evaluation_service import EvaluationService
from src.interview_service import InterviewService, QuestionHistory, ServiceError
from src.models import InterviewConfiguration, ModelSettings
from src.openrouter_client import OpenRouterClient, OpenRouterError
from src.pricing_service import PricingService
from src.report_service import ReportService
from src.session_manager import SessionManager, SessionState
from src.speech_service import (
    SpeechError,
    build_speech_service,
    transcribe_recording,
)
from src.live_interview import (
    GeminiLiveTokenService,
    LiveInterviewError,
    LiveInterviewService,
)
from components.live_interviewer import is_available as live_component_available
from components.live_interviewer import live_interviewer
from src.integration import handoff  # career → interview preparation handoff
from src.interview import prompt_lab  # developer Prompt Lab (Advanced view)

logger = logging.getLogger(__name__)

_METADATA_CACHE_KEY = "_model_supported_params"

# A future realtime digital-human provider can replace this without touching any
# interview-domain logic (see src/avatar.AvatarRenderer).
_AVATAR = LocalAvatarRenderer()


# =============================================================================
# Resource wiring (no network on import or first render)
# =============================================================================


def get_session() -> SessionManager:
    """Session manager over Streamlit's namespaced session_state."""
    return SessionManager(st.session_state)


def get_pricing_service() -> PricingService:
    """A pricing service kept in session so its metadata cache persists.

    After a code hot-reload the cached instance can predate the current
    ``PricingService`` class (a stale instance keeps referencing the old class
    object). The ``isinstance`` check detects that and rebuilds it, so newly
    added accessors are always available instead of raising ``AttributeError``.
    """
    cached = st.session_state.get("_pricing_service")
    if not isinstance(cached, PricingService):
        cached = PricingService()
        st.session_state["_pricing_service"] = cached
    return cached


def build_services(
    config: AppConfig, pricing: PricingService
) -> tuple[InterviewService, EvaluationService, ReportService, OpenRouterClient]:
    """Create fresh services wrapping a client built from the current config."""
    client = OpenRouterClient(config)
    return (
        InterviewService(client, pricing),
        EvaluationService(client, pricing),
        ReportService(client, pricing),
        client,
    )


def require_configured(config: AppConfig) -> bool:
    """Show a clear missing-key message and return False when unconfigured."""
    if config.is_configured:
        return True
    st.error(
        "No OpenRouter API key is configured. Add `OPENROUTER_API_KEY` to "
        "`.streamlit/secrets.toml` or your environment, then reload."
    )
    return False


# =============================================================================
# A. Header
# =============================================================================


def render_header() -> None:
    st.title(constants.APP_NAME)
    st.markdown(f"**{constants.APP_TAGLINE}**")
    st.caption(
        "Practice feedback only — not an assessment, and not a guarantee of "
        "any hiring outcome."
    )
    with st.expander("Privacy & limitations", expanded=False):
        for notice in security.privacy_notices():
            st.markdown(f"- {notice}")


# =============================================================================
# C. Developer settings (sidebar)
# =============================================================================


def render_developer_settings(config: AppConfig) -> dict:
    """Render the sidebar developer settings and return the chosen values."""
    with st.sidebar.expander("Developer settings", expanded=False):
        model = st.selectbox(
            "Model",
            ui_helpers.MODELS,
            index=0,
            help="Approved OpenRouter models only.",
        )

        technique_options = ui_helpers.technique_options()
        technique_ids = [tid for tid, _ in technique_options]
        technique_labels = {tid: name for tid, name in technique_options}
        technique = st.selectbox(
            "Prompt technique",
            technique_ids,
            index=technique_ids.index("rubric_json")
            if "rubric_json" in technique_ids
            else 0,
            format_func=lambda tid: technique_labels.get(tid, tid),
        )

        # Capability gating. Live OpenRouter metadata (populated by "Test
        # connection") takes precedence; otherwise a static per-model default is
        # used so the slider is gated correctly on first render without a network
        # call. Reasoning models (the GPT-5 family) reject a custom temperature.
        supported = st.session_state.get(_METADATA_CACHE_KEY, {}).get(model)
        temperature_supported = ui_helpers.model_supports_temperature(model, supported)

        if temperature_supported:
            temperature = st.slider(
                "Temperature",
                min_value=constants.MIN_TEMPERATURE,
                max_value=constants.MAX_TEMPERATURE,
                value=constants.DEFAULT_TEMPERATURE,
                step=0.1,
            )
        else:
            temperature = constants.DEFAULT_TEMPERATURE
            st.caption(
                f"⚙️ `{model}` does not support a temperature setting, so the "
                "slider is disabled and no temperature is sent."
            )
        max_tokens = st.number_input(
            "Maximum output tokens",
            min_value=constants.MIN_OUTPUT_TOKENS,
            max_value=constants.MAX_OUTPUT_TOKENS_LIMIT,
            value=constants.DEFAULT_MAX_OUTPUT_TOKENS,
            step=64,
        )
        show_usage = st.checkbox("Show usage details", value=False)

        # Explain structured-output support only from cached metadata.
        if supported is not None:
            if constants.STRUCTURED_OUTPUT_PARAMETER in supported:
                st.caption(
                    "This model enforces strict JSON Schema (structured "
                    "outputs); repair is not needed."
                )
            elif "response_format" in supported:
                st.caption(
                    "This model supports a JSON response hint; the app validates "
                    "and repairs once if needed."
                )
            else:
                st.caption(
                    "This model has no JSON mode; the app relies on a prompt-only "
                    "JSON contract with one repair."
                )
        else:
            st.caption("Use 'Test connection' to check model capabilities.")

        if st.button("Test OpenRouter connection"):
            _test_connection(config, model)

    return {
        "model": model,
        "prompt_technique": technique,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "show_usage": show_usage,
    }


def _test_connection(config: AppConfig, model: str) -> None:
    if not require_configured(config):
        return
    pricing = get_pricing_service()
    client = OpenRouterClient(config)
    try:
        with st.spinner("Contacting OpenRouter…"):
            # Fetch capabilities first so the test can send a minimal-reasoning
            # request only when the model supports it (best-effort).
            supported = None
            try:
                supported = list(pricing.supported_parameters(model))
                st.session_state.setdefault(_METADATA_CACHE_KEY, {})[model] = supported
            except Exception:  # noqa: BLE001 - metadata is best-effort
                supported = None
            client.test_connection(supported_parameters=supported)
        st.success("Connection OK.")
    except OpenRouterError as exc:
        st.error(exc.message)
    finally:
        client.close()


# =============================================================================
# B. Interview setup form
# =============================================================================


def _live_enabled() -> bool:
    """Whether the experimental Live interviewer is exposed in the product.

    Live is OFF by default: its realtime browser lifecycle (barge-in, reconnect,
    token expiry) is not yet verified end-to-end, so it is hidden from normal
    navigation to avoid presenting an unreliable feature as production-ready. Set
    ``INTERVIEW_LIVE_ENABLED=true`` to opt in for experimentation. Type and Record
    are always available.
    """
    return os.environ.get("INTERVIEW_LIVE_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on"}


def _answer_methods() -> list[str]:
    return ["Type", "Record", "Live"] if _live_enabled() else ["Type", "Record"]


def _render_mode_cards() -> None:
    """Friendly practice-mode cards (no technical/provider concepts shown).

    Selecting one sets the default answer method for the interview; the candidate
    can still switch per question. Camera coaching and models stay out of sight.
    The experimental Live card is hidden unless INTERVIEW_LIVE_ENABLED is set.
    """
    st.markdown("#### How would you like to practise?")
    chosen = st.session_state.get("_practice_mode", "Type")
    allowed = set(_answer_methods())
    cards = [c for c in constants.PRACTICE_MODE_CARDS if c["id"] in allowed]
    if chosen not in allowed:  # a stale/hidden mode falls back to Type
        chosen = "Type"
    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        with column:
            selected = card["id"] == chosen
            st.markdown(f"**{card['title']}**")
            st.caption(card["tagline"])
            st.caption(card["description"])
            if st.button(
                "Selected ✓" if selected else "Choose",
                key=f"mode_card_{card['id']}",
                type="primary" if selected else "secondary",
                use_container_width=True,
            ):
                st.session_state["_practice_mode"] = card["id"]
                # Pre-select this mode for main and Deep Dive answers.
                st.session_state["main_answer_method"] = card["id"]
                st.session_state["branch_answer_method"] = card["id"]
                st.rerun()


def _label_index(pairs, domain_id, default: int = 0) -> int:
    """Index of a domain id within a label list, or ``default`` if absent."""
    if not domain_id:
        return default
    try:
        return ui_helpers.labels(pairs).index(ui_helpers.label_for_id(pairs, domain_id))
    except (ValueError, KeyError):
        return default


def render_setup(session: SessionManager, config: AppConfig, dev: dict) -> None:
    st.subheader("Practice Interview")
    _render_mode_cards()
    st.divider()

    # Career → Interview handoff: pre-fill (defaults only; fully editable).
    prefill = handoff.interview_prefill(st.session_state)
    if prefill:
        context = handoff.get_context(st.session_state)
        with st.container(border=True):
            st.markdown("✅ **Prepared with Career Intelligence**")
            if context is not None:
                st.caption(f"Role: {context.target_role}")
                themes = context.likely_interview_topics[:3]
                if themes:
                    st.caption("Top themes: " + ", ".join(themes))
                focus = context.priority_competencies[:3]
                if focus:
                    st.caption("Preparation focus: " + ", ".join(focus))
            st.caption(
                f"{prefill.get('source_count', 0)} source(s) informed this "
                "preparation. Review and edit the setup below, then generate your "
                "strategy — provenance only, not a score."
            )

    st.markdown("#### Set up your interview")
    with st.form("interview_setup"):
        target_role = st.text_input(
            "Target role *", value=prefill.get("target_role", ""), help="Required."
        )
        industry = st.text_input("Industry or sector", value=prefill.get("industry", ""))
        career_label = st.selectbox(
            "Career level",
            ui_helpers.labels(ui_helpers.CAREER_LEVELS),
            index=_label_index(ui_helpers.CAREER_LEVELS, prefill.get("career_level")),
        )
        company_context = st.text_area(
            "Company context", height=80, value=prefill.get("company_context", "")
        )
        job_description = st.text_area(
            "Job description (recommended)",
            height=140,
            value=prefill.get("job_description", ""),
        )
        candidate_background = st.text_area(
            "Your background", height=100, value=prefill.get("candidate_background", "")
        )
        interview_type_labels = st.multiselect(
            "Interview types",
            ui_helpers.labels(ui_helpers.INTERVIEW_TYPES),
            default=["Behavioural"],
        )
        persona_label = st.selectbox(
            "Interviewer persona", ui_helpers.labels(ui_helpers.PERSONAS)
        )
        difficulty_label = st.selectbox(
            "Difficulty",
            ui_helpers.labels(ui_helpers.DIFFICULTIES),
            index=_label_index(
                ui_helpers.DIFFICULTIES,
                prefill.get("difficulty"),
                default=ui_helpers.difficulty_default_index(),
            ),
        )
        number_of_questions = st.slider(
            "Number of questions",
            min_value=constants.MIN_QUESTIONS,
            max_value=constants.MAX_QUESTIONS,
            value=constants.DEFAULT_NUMBER_OF_QUESTIONS,
        )
        detail_label = st.selectbox(
            "Response detail",
            ui_helpers.labels(ui_helpers.RESPONSE_DETAILS),
            index=1,
        )
        submitted = st.form_submit_button("Generate strategy")

    if not submitted:
        return

    if not interview_type_labels:
        st.error("Please choose at least one interview type.")
        return
    if not require_configured(config):
        return

    try:
        cfg = _build_configuration(
            target_role=target_role,
            industry=industry,
            career_label=career_label,
            company_context=company_context,
            job_description=job_description,
            candidate_background=candidate_background,
            interview_type_labels=interview_type_labels,
            persona_label=persona_label,
            difficulty_label=difficulty_label,
            number_of_questions=number_of_questions,
            detail_label=detail_label,
        )
    except security.InputValidationError as exc:
        st.error(exc.message)
        return
    except ValidationError:
        st.error("Some inputs were invalid. Please review the form and retry.")
        return

    settings = ModelSettings(
        model=dev["model"],
        prompt_technique=dev["prompt_technique"],
        temperature=dev["temperature"],
        max_tokens=dev["max_tokens"],
    )
    session.start_new_interview(cfg, settings)
    _generate_strategy(session, config)
    st.rerun()


def _build_configuration(**raw) -> InterviewConfiguration:
    """Validate free text and map UI labels to domain ids."""
    target_role = security.validate_field(raw["target_role"], "target_role")
    industry = security.sanitize_text(raw["industry"]) or "unspecified"
    company_context = security.validate_field(
        raw["company_context"], "company_context"
    )
    job_description = security.validate_field(
        raw["job_description"], "job_description"
    )
    candidate_background = security.validate_field(
        raw["candidate_background"], "candidate_background"
    )
    return InterviewConfiguration(
        target_role=target_role,
        industry_or_sector=industry,
        career_level=ui_helpers.id_for_label(
            ui_helpers.CAREER_LEVELS, raw["career_label"]
        ),
        company_context=company_context,
        job_description=job_description,
        candidate_background=candidate_background,
        interview_types=[
            ui_helpers.id_for_label(ui_helpers.INTERVIEW_TYPES, label)
            for label in raw["interview_type_labels"]
        ],
        interviewer_persona=ui_helpers.id_for_label(
            ui_helpers.PERSONAS, raw["persona_label"]
        ),
        difficulty=ui_helpers.id_for_label(
            ui_helpers.DIFFICULTIES, raw["difficulty_label"]
        ),
        number_of_questions=raw["number_of_questions"],
        response_detail=ui_helpers.id_for_label(
            ui_helpers.RESPONSE_DETAILS, raw["detail_label"]
        ),
    )


# =============================================================================
# D. Role analysis (strategy)
# =============================================================================


def _generate_strategy(session: SessionManager, config: AppConfig) -> None:
    if not session.begin_operation("strategy"):
        return
    pricing = get_pricing_service()
    interview_service, _, _, client = build_services(config, pricing)
    try:
        with st.spinner("Analysing the role…"):
            strategy, usage = interview_service.generate_strategy(
                session.data.config, session.data.settings
            )
        session.save_strategy(strategy)
        session.record_usage(usage)
    except ServiceError as exc:
        session.enter_error(exc.message, recover_to=SessionState.SETUP)
    finally:
        session.end_operation()
        client.close()


def render_strategy(session: SessionManager) -> None:
    strategy = session.data.strategy
    st.subheader("Role analysis")
    st.write(strategy.role_summary)

    left, right = st.columns(2)
    with left:
        _bullet_block("Likely interview stages", strategy.likely_interview_stages)
        _bullet_block("Critical competencies", strategy.critical_competencies)
        _bullet_block("Question themes", strategy.likely_question_themes)
        _bullet_block(
            "Technical or functional topics",
            strategy.technical_or_functional_topics,
        )
    with right:
        _bullet_block("Behavioural topics", strategy.behavioural_topics)
        _bullet_block("Evidence to prepare", strategy.evidence_to_prepare)
        _bullet_block("Preparation priorities", strategy.preparation_priorities)
        _bullet_block(
            "Questions for the interviewer", strategy.questions_for_interviewer
        )

    st.divider()
    if st.button("Start mock interview", type="primary"):
        _generate_next_question(session, first=True)
        st.rerun()


def _bullet_block(title: str, items: list[str]) -> None:
    st.markdown(f"**{title}**")
    for item in items:
        st.markdown(f"- {item}")


# =============================================================================
# E. Mock interview (chatbot)
# =============================================================================


def _generate_next_question(session: SessionManager, *, first: bool = False) -> None:
    operation = "first_question" if first else "next_question"
    if not session.begin_operation(operation):
        return
    # The delivery/visual notes belong to the previous answer; clear before next.
    st.session_state.pop("_delivery_notes", None)
    st.session_state.pop("_visual_notes", None)
    config = load_config()
    if not config.is_configured:
        session.end_operation()
        st.error("No OpenRouter API key is configured; cannot generate a question.")
        return
    pricing = get_pricing_service()
    interview_service, _, _, client = build_services(config, pricing)
    data = session.data
    history = QuestionHistory(
        questions=list(data.questions),
        answers=list(data.answers),
        evaluations=list(data.evaluations),
    )
    recover = (
        SessionState.STRATEGY_READY if first else SessionState.INTERVIEW_IN_PROGRESS
    )
    try:
        with st.spinner("Preparing the next question…"):
            question, usage = interview_service.generate_next_question(
                data.config,
                data.settings,
                current_question_number=len(data.questions) + 1,
                history=history,
            )
        session.add_question(question)
        session.record_usage(usage)
        session.add_chat_message(
            "assistant",
            f"**Question {len(session.data.questions)}** "
            f"({session.data.questions[-1].competency})\n\n{question.question}",
        )
    except ServiceError as exc:
        session.enter_error(exc.message, recover_to=recover)
    finally:
        session.end_operation()
        client.close()


def _handle_answer(session: SessionManager, answer: str) -> None:
    try:
        answer = security.validate_field(answer, "candidate_answer")
    except security.InputValidationError as exc:
        st.error(str(exc))
        return
    if not session.begin_operation("evaluate"):
        return
    config = load_config()
    if not config.is_configured:
        session.end_operation()
        st.error("No OpenRouter API key is configured; cannot evaluate.")
        return
    pricing = get_pricing_service()
    _, evaluation_service, _, client = build_services(config, pricing)
    data = session.data
    current_question = data.questions[-1].question
    try:
        session.add_candidate_answer(answer)
        session.add_chat_message("user", answer)
        with st.spinner("Evaluating your answer…"):
            evaluation, usage = evaluation_service.evaluate_answer(
                data.config, current_question, answer, data.settings
            )
        session.add_evaluation(evaluation)
        session.record_usage(usage)
        session.add_chat_message(
            "assistant",
            f"Recorded — overall score **{evaluation.overall_score}/100**. "
            "Detailed feedback is shown below.",
        )
    except ServiceError as exc:
        session.enter_error(exc.message, recover_to=SessionState.AWAITING_ANSWER)
    finally:
        session.end_operation()
        client.close()


def _run_branch_generation(session: SessionManager) -> None:
    """Generate the next deep-dive question (level 1 or deeper)."""
    if not session.begin_operation("branch_question"):
        return
    st.session_state.pop("_delivery_notes", None)
    st.session_state.pop("_visual_notes", None)
    config = load_config()
    if not config.is_configured:
        session.end_operation()
        st.error("No OpenRouter API key is configured; cannot deep-dive.")
        return
    pricing = get_pricing_service()
    interview_service, _, _, client = build_services(config, pricing)
    data = session.data
    depth = len(data.branch_questions) + 1
    try:
        with st.spinner("Preparing a deeper question…"):
            branch_question, usage = interview_service.generate_branch_question(
                data.config,
                data.settings,
                parent_question=data.questions[-1],
                candidate_answer=data.answers[-1],
                evaluation=data.evaluations[-1],
                branch_mode=data.branch_mode,
                depth=depth,
                branch_id=session.next_branch_id(),
                previous_branch_questions=[q.question for q in data.branch_questions],
                previous_branch_answers=list(data.branch_answers),
            )
        session.add_branch_question(branch_question)
        session.record_usage(usage)
        mode_label = ui_helpers.label_for_id(
            ui_helpers.BRANCH_MODES, data.branch_mode
        )
        session.add_chat_message(
            "assistant",
            f"🔎 **Deep Dive — Level {branch_question.depth} of "
            f"{constants.MAX_BRANCH_DEPTH}** · {mode_label}\n\n"
            f"{branch_question.question}",
        )
    except ServiceError as exc:
        session.enter_error(
            exc.message, recover_to=SessionState.INTERVIEW_IN_PROGRESS
        )
    finally:
        session.end_operation()
        client.close()


def _handle_start_branch(session: SessionManager, mode: str) -> None:
    session.start_branch(mode)
    _run_branch_generation(session)


def _handle_branch_answer(session: SessionManager, answer: str) -> None:
    try:
        answer = security.validate_field(answer, "candidate_answer")
    except security.InputValidationError as exc:
        st.error(str(exc))
        return
    if not session.begin_operation("branch_evaluate"):
        return
    config = load_config()
    if not config.is_configured:
        session.end_operation()
        st.error("No OpenRouter API key is configured; cannot evaluate.")
        return
    pricing = get_pricing_service()
    _, evaluation_service, _, client = build_services(config, pricing)
    data = session.data
    branch_question = data.branch_questions[-1].question
    try:
        session.add_branch_answer(answer)
        session.add_chat_message("user", answer)
        with st.spinner("Evaluating your deep-dive answer…"):
            evaluation, usage = evaluation_service.evaluate_answer(
                data.config, branch_question, answer, data.settings
            )
        session.add_branch_evaluation(evaluation)
        session.record_usage(usage)
        session.add_chat_message(
            "assistant",
            f"Deep-dive feedback — overall score "
            f"**{evaluation.overall_score}/100**. See details below.",
        )
    except ServiceError as exc:
        session.enter_error(
            exc.message, recover_to=SessionState.BRANCH_AWAITING_ANSWER
        )
    finally:
        session.end_operation()
        client.close()


def _render_branch_controls(session: SessionManager) -> None:
    """The deep-dive hub between/after branch answers."""
    data = session.data
    mode_label = ui_helpers.label_for_id(ui_helpers.BRANCH_MODES, data.branch_mode)
    st.markdown(
        f"**🔎 Deep Dive — Level {data.branch_depth} of "
        f"{constants.MAX_BRANCH_DEPTH}** · {mode_label}"
    )
    if data.branch_evaluations:
        render_feedback(data.branch_evaluations[-1])
        _render_delivery_section()
    columns = st.columns(2)
    if session.can_go_deeper():
        if columns[0].button("Go deeper", type="primary", key="branch_deeper"):
            _run_branch_generation(session)
            st.rerun()
    else:
        columns[0].caption("Deep dive complete (maximum depth reached).")
    if columns[1].button("Return to main interview", key="branch_return"):
        session.return_to_main_interview()
        st.rerun()


def _render_answer_input(
    session, *, on_submit, ns: str, placeholder: str, question=None,
    is_deep_dive: bool = False,
) -> None:
    """Answer input offering three modes; typing is the default.

    Modes: **Type** (text), **Record** (recorded voice → transcript) and **Live**
    (experimental real-time interviewer). ``on_submit(text)`` is called with the
    final answer text, so every mode shares the one evaluation pipeline. Voice
    and live modes also show recommended answer-length guidance (never a limit).
    """
    guidance = timing.guidance_for_question(question, is_deep_dive=is_deep_dive) if question else None
    methods = _answer_methods()
    # A stale "Live" selection (feature since hidden) falls back to Type.
    if st.session_state.get(f"{ns}_method") not in methods:
        st.session_state.pop(f"{ns}_method", None)
    method = st.radio(
        "Answer method",
        methods,
        horizontal=True,
        key=f"{ns}_method",
        help="Type your answer" + (
            ", record a voice answer, or try the experimental live interviewer."
            if _live_enabled() else " or record a voice answer."),
    )
    if method == "Type":
        answer = st.chat_input(placeholder, max_chars=constants.MAX_ANSWER_CHARS)
        if answer:
            on_submit(answer)
            st.rerun()
        return
    if guidance is not None:
        st.caption(
            f"Recommended: ~{round(guidance.recommended_seconds / 60, 1)} min "
            f"(~{guidance.target_words} words). Guidance only — take the time you need."
        )
    if method == "Record":
        _render_voice_answer(session, on_submit=on_submit, ns=ns, guidance=guidance)
        return
    _render_live_answer(session, on_submit=on_submit, ns=ns, guidance=guidance)


def _record_delivery(session, *, ns: str, transcript: str, guidance) -> None:
    """Compute + store delivery metrics for a spoken answer (never a score).

    Uses voice-activity segments when the recorder/live client provided them;
    otherwise falls back to the recording duration. Stores plain-language
    delivery notes for display and aggregation. Typed answers never reach here.
    """
    pending = st.session_state.pop(f"{ns}_metrics", None) or {}
    word_count = len((transcript or "").split())
    metrics = timing.compute_delivery_metrics(
        word_count=word_count,
        segments=pending.get("segments"),
        total_duration_seconds=pending.get("duration_seconds"),
        response_start_latency_seconds=pending.get("response_start_latency_seconds"),
    )
    notes = timing.delivery_feedback(guidance, metrics) if guidance else []
    entry = metrics.as_dict()
    if guidance is not None:
        entry["recommended_seconds"] = guidance.recommended_seconds
    entry["feedback"] = notes
    session.record_voice_metrics(entry)
    st.session_state["_delivery_notes"] = notes


def _render_transcript_review(session, *, on_submit, ns: str, guidance=None) -> None:
    """Shared 'Review your transcript' block for voice and live answers.

    The final, candidate-edited transcript is what reaches the evaluator; a
    transcript is never auto-submitted.
    """
    transcript_key = f"{ns}_transcript"
    metrics_key = f"{ns}_metrics"
    if transcript_key not in st.session_state:
        return
    st.markdown("**Review your transcript**")
    edited = st.text_area(
        "Edit before submitting",
        value=st.session_state[transcript_key],
        key=f"{ns}_edit",
        height=140,
    )
    columns = st.columns(4)
    if columns[0].button("Submit answer", type="primary", key=f"{ns}_submit"):
        _record_delivery(session, ns=ns, transcript=edited, guidance=guidance)
        st.session_state.pop(transcript_key, None)
        on_submit(edited)
        st.rerun()
    if columns[1].button("Redo", key=f"{ns}_again"):
        st.session_state.pop(transcript_key, None)
        st.session_state.pop(metrics_key, None)
        st.rerun()
    if columns[2].button("Clear", key=f"{ns}_clear"):
        st.session_state.pop(transcript_key, None)
        st.session_state.pop(metrics_key, None)
        st.rerun()
    if columns[3].button("Switch to typing", key=f"{ns}_totype"):
        st.session_state.pop(transcript_key, None)
        st.session_state.pop(metrics_key, None)
        st.session_state[f"{ns}_method"] = "Type"
        st.rerun()


def _render_voice_answer(session, *, on_submit, ns: str, guidance=None) -> None:
    """Record → playback → transcribe → editable transcript → submit."""
    config = load_config()
    service = build_speech_service(config)
    transcript_key = f"{ns}_transcript"
    metrics_key = f"{ns}_metrics"

    if not service.is_available:
        st.info(
            "Voice answers are unavailable: speech-to-text is not configured. "
            "Please switch to **Type** to answer."
        )
        return

    st.caption(constants.SPEECH_PRIVACY_NOTICE)
    language_map = dict(constants.SPEECH_LANGUAGE_OPTIONS)
    language_label = st.selectbox(
        "Spoken language", list(language_map), key=f"{ns}_lang"
    )
    language_code = language_map[language_label]

    audio = st.audio_input("Record your answer", key=f"{ns}_audio")
    if audio is not None and st.button("Transcribe", key=f"{ns}_transcribe"):
        with st.spinner("Transcribing…"):
            try:
                result, metrics, usage = transcribe_recording(
                    service,
                    audio.getvalue(),
                    mime_type=audio.type,
                    language=language_code,
                )
            except SpeechError as exc:
                st.error(exc.message)
            else:
                # Store only text and metrics — never the raw audio bytes.
                st.session_state[transcript_key] = result.transcript
                st.session_state[metrics_key] = metrics
                session.record_transcription_usage(usage)
                st.rerun()

    _render_transcript_review(session, on_submit=on_submit, ns=ns, guidance=guidance)


def _live_fallback(ns: str) -> None:
    """Show the live-unavailable message and offer voice/text without data loss."""
    st.warning(constants.LIVE_FALLBACK_MESSAGE)
    columns = st.columns(2)
    if columns[0].button("Continue with recorded voice", key=f"{ns}_fb_voice"):
        st.session_state[f"{ns}_method"] = "Record"
        st.rerun()
    if columns[1].button("Continue with text", key=f"{ns}_fb_text"):
        st.session_state[f"{ns}_method"] = "Type"
        st.rerun()


def _live_session_config(ns: str, token_service) -> dict:
    """Return the browser session config, minting an ephemeral token only when
    needed (1E).

    A valid token is reused across unrelated Streamlit reruns instead of minting a
    new one every render. The config is held in bounded session state (never
    persisted, never logged), and carries a stable ``session_id`` so the frontend
    treats a rerun as the same session; a re-mint yields a new id (a controlled
    frontend restart).
    """
    import time
    import uuid

    from src.live_interview import token_needs_refresh

    key = f"{ns}_live_session_config"
    cached = st.session_state.get(key)
    if cached and not token_needs_refresh(cached.get("token_expires_at", 0), time.time()):
        return dict(cached)  # reuse the still-valid token; no re-mint
    _token, cfg = LiveInterviewService(token_service=token_service).start_session()
    cfg["session_id"] = uuid.uuid4().hex
    st.session_state[key] = cfg
    return dict(cfg)


def _render_live_answer(session, *, on_submit, ns: str, guidance=None) -> None:
    """Experimental live interviewer; falls back cleanly when unavailable."""
    config = load_config()
    st.caption(
        "**Live Interview — Experimental.** " + constants.SPEECH_PRIVACY_NOTICE
    )
    token_service = GeminiLiveTokenService(config)
    if not token_service.is_available or not live_component_available():
        _live_fallback(ns)
        return

    try:
        session_config = _live_session_config(ns, token_service)
    except LiveInterviewError:
        _live_fallback(ns)
        return

    question = (
        session.data.questions[-1].question if session.data.questions else ""
    )
    session_config["question"] = question
    if guidance is not None:
        # The live timer uses these to nudge (never to stop the candidate).
        session_config["recommended_seconds"] = guidance.recommended_seconds
        session_config["soft_warning_seconds"] = guidance.soft_warning_seconds
        session_config["hard_guidance_seconds"] = guidance.hard_guidance_seconds

    event = live_interviewer(session_config=session_config, key=f"{ns}_live")

    # The component reports a final candidate transcript (plus voice-activity
    # segments); the candidate reviews and edits it before it is submitted to the
    # existing evaluation pipeline.
    if isinstance(event, dict):
        if event.get("transcript_final"):
            text = (event.get("candidate_transcript") or "").strip()
            if text:
                st.session_state[f"{ns}_transcript"] = text
                st.session_state[f"{ns}_metrics"] = {
                    "segments": event.get("segments"),
                    "response_start_latency_seconds": event.get(
                        "response_start_latency"
                    ),
                }
    _render_transcript_review(session, on_submit=on_submit, ns=ns, guidance=guidance)


def _render_delivery_section() -> None:
    """Show 'Delivery & pacing' notes for the most recent spoken answer.

    Timing is coaching only: it never appears for typed answers and never
    affects the interview-content score.
    """
    notes = st.session_state.get("_delivery_notes")
    if not notes:
        return
    with st.expander("Delivery & pacing", expanded=False):
        for note in notes:
            st.markdown(f"- {note}")
        st.caption("Guidance on pacing only — it does not affect your score.")


def _avatar_state(session: SessionManager) -> str:
    """Map the session state to a tasteful interviewer avatar state."""
    if session.state in (
        SessionState.AWAITING_ANSWER,
        SessionState.BRANCH_AWAITING_ANSWER,
    ):
        return constants.AVATAR_LISTENING
    if session.state in (
        SessionState.EVALUATING,
        SessionState.BRANCH_EVALUATING,
    ):
        return constants.AVATAR_THINKING
    return constants.AVATAR_IDLE


def _current_question_text(session: SessionManager) -> str:
    data = session.data
    if data.branch_active and data.branch_questions:
        return data.branch_questions[-1].question
    if data.questions:
        return data.questions[-1].question
    return ""


def _render_interviewer_stage(session: SessionManager) -> None:
    """The 'remote interview' stage: interviewer avatar, progress and captions."""
    data = session.data
    persona = data.config.interviewer_persona if data.config else None
    planned = data.config.number_of_questions if data.config else 0

    left, right = st.columns([1, 2])
    with left:
        components.html(
            _AVATAR.render(persona=persona, state=_avatar_state(session)),
            height=220,
        )
    with right:
        if data.branch_active:
            st.markdown(
                f"**Deep Dive · Level {data.branch_depth} of "
                f"{constants.MAX_BRANCH_DEPTH}**"
            )
        else:
            current = min(max(data.current_question_number, 1), planned or 1)
            st.markdown(f"**Question {current} of {planned}**")
        answered = len(data.evaluations)
        st.progress(min(answered / planned, 1.0) if planned else 0.0)
        state_labels = {
            constants.AVATAR_LISTENING: constants.STATUS_LISTENING,
            constants.AVATAR_THINKING: constants.STATUS_PROCESSING_ANSWER,
        }
        st.caption(state_labels.get(_avatar_state(session), "In progress"))
        if st.session_state.get("_captions", True):
            question = _current_question_text(session)
            if question:
                st.markdown(f"> **Interviewer:** {question}")
    st.divider()


def render_interview(session: SessionManager) -> None:
    data = session.data
    planned = data.config.number_of_questions
    answered = len(data.evaluations)
    asked = len(data.questions)

    _render_interviewer_stage(session)

    # Captions toggle (accessibility): governs the interviewer caption + live
    # transcript. On by default.
    st.checkbox(
        "Show captions",
        value=st.session_state.get("_captions", True),
        key="_captions",
        help="Show the interviewer's question and your live transcript as text.",
    )

    with st.expander("Transcript", expanded=False):
        if not data.chat_messages:
            st.caption("The conversation will appear here.")
        for message in data.chat_messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    st.divider()

    # --- Deep Dive (branch) mode ---------------------------------------------
    if data.branch_active:
        if session.state is SessionState.BRANCH_AWAITING_ANSWER:
            _render_answer_input(
                session,
                on_submit=lambda text: _handle_branch_answer(session, text),
                ns="branch_answer",
                placeholder="Answer the deep-dive question…",
                question=(
                    data.branch_questions[-1] if data.branch_questions else None
                ),
                is_deep_dive=True,
            )
            st.caption("Deep-dive questions use additional AI requests.")
            if st.button("Return to main interview", key="branch_return_await"):
                session.return_to_main_interview()
                st.rerun()
        elif session.state is SessionState.BRANCH_EVALUATING:
            st.info("Evaluating your deep-dive answer…")
        else:  # INTERVIEW_IN_PROGRESS, inside an open branch
            _render_branch_controls(session)
        return

    # --- Normal main interview -----------------------------------------------
    if data.evaluations:
        render_feedback(data.evaluations[-1])
        _render_delivery_section()
        st.divider()

    if session.state is SessionState.AWAITING_ANSWER:
        _render_answer_input(
            session,
            on_submit=lambda text: _handle_answer(session, text),
            ns="main_answer",
            placeholder="Type your answer…",
            question=data.questions[-1] if data.questions else None,
            is_deep_dive=False,
        )
        if answered >= 1 and st.button("End interview early"):
            session.end_interview_early()
            st.rerun()
    elif session.state is SessionState.INTERVIEW_IN_PROGRESS:
        st.markdown("**Next actions**")
        columns = st.columns(2)
        if asked < planned:
            if columns[0].button("Next question", type="primary"):
                _generate_next_question(session)
                st.rerun()
        else:
            columns[0].info("You have answered all planned questions.")
        if columns[1].button("Finish & generate report"):
            session.complete_interview()
            st.rerun()

        # Explore this further (Deep Dive) — available once an answer exists.
        if answered >= 1:
            with st.expander("Explore this further (Deep Dive)"):
                mode_label = st.selectbox(
                    "Deep-dive focus",
                    ui_helpers.labels(ui_helpers.BRANCH_MODES),
                    index=0,
                    help="Explore the last question more deeply before continuing.",
                )
                st.caption("Deep-dive questions use additional AI requests.")
                if st.button("Explore this further", key="start_branch"):
                    _handle_start_branch(
                        session,
                        ui_helpers.id_for_label(ui_helpers.BRANCH_MODES, mode_label),
                    )
                    st.rerun()
    elif session.state is SessionState.EVALUATING:
        st.info("Evaluating your answer…")


# =============================================================================
# F. Feedback presentation
# =============================================================================


def render_feedback(evaluation) -> None:
    st.markdown("#### Feedback")
    st.metric("Overall score", f"{evaluation.overall_score}/100")

    columns = st.columns(len(ui_helpers.RUBRIC_CRITERIA))
    for column, (field_name, label) in zip(columns, ui_helpers.RUBRIC_CRITERIA):
        column.metric(label, f"{getattr(evaluation, field_name)}/10")

    left, right = st.columns(2)
    with left:
        _bullet_block("Strengths", evaluation.strengths)
        _bullet_block("Missing evidence", evaluation.missing_evidence)
    with right:
        _bullet_block("Improvement areas", evaluation.improvement_areas)

    st.markdown("**Stronger answer structure**")
    st.write(evaluation.stronger_answer_structure)

    with st.expander("Improved example answer (personalise before using)"):
        st.write(evaluation.improved_example_answer)

    st.markdown("**Follow-up question**")
    st.write(evaluation.follow_up_question)


# =============================================================================
# G. Final report
# =============================================================================


def _generate_report(session: SessionManager) -> None:
    if not session.begin_operation("report"):
        return
    config = load_config()
    if not config.is_configured:
        session.end_operation()
        st.error("No OpenRouter API key is configured; cannot generate a report.")
        return
    pricing = get_pricing_service()
    _, _, report_service, client = build_services(config, pricing)
    data = session.data
    try:
        with st.spinner("Compiling your report…"):
            report, usage = report_service.generate_report(
                data.config,
                list(data.questions[: len(data.evaluations)]),
                list(data.answers),
                list(data.evaluations),
                data.settings,
            )
        session.save_final_report(report)
        session.record_usage(usage)
    except ServiceError as exc:
        session.enter_error(
            exc.message, recover_to=SessionState.INTERVIEW_COMPLETE
        )
    finally:
        session.end_operation()
        client.close()


def render_complete(session: SessionManager) -> None:
    st.subheader("Interview complete")
    st.write(
        f"You answered {len(session.data.evaluations)} question(s). "
        "Generate a readiness report to see your summary and next steps."
    )
    if st.button("Generate final report", type="primary"):
        _generate_report(session)
        st.rerun()


def _render_delivery_summary(session: SessionManager) -> None:
    """Aggregated delivery/pacing metrics across spoken answers (report only).

    Typed answers contribute nothing here; when there were no spoken answers the
    section is omitted entirely (no fabricated speech metrics).
    """
    summary = timing.aggregate_delivery(session.data.voice_metrics)
    if not summary.get("spoken_answers"):
        return
    st.divider()
    st.markdown("**Delivery & pacing (spoken answers)**")

    def _fmt(seconds) -> str:
        return f"{seconds:.0f}s" if seconds is not None else "—"

    cols = st.columns(3)
    cols[0].metric("Avg answer", _fmt(summary["average_answer_seconds"]))
    cols[1].metric("Avg recommended", _fmt(summary["average_recommended_seconds"]))
    wpm = summary["average_words_per_minute"]
    cols[2].metric("Avg pace", f"{wpm:.0f} wpm" if wpm is not None else "—")
    st.caption(
        f"Longest uninterrupted: {_fmt(summary['longest_uninterrupted_seconds'])} · "
        f"Over target: {summary['answers_substantially_over_target']} · "
        f"Under target: {summary['answers_substantially_under_target']}"
    )
    for note in summary.get("coaching", []):
        st.markdown(f"- {note}")
    st.caption("Delivery guidance only — it does not affect the readiness score.")


def render_report(session: SessionManager) -> None:
    report = session.data.report
    # Publish a plain summary to the integration channel (for combined export).
    try:
        handoff.store_interview_summary(
            st.session_state,
            {
                "target_role": session.data.config.target_role if session.data.config else None,
                "overall_readiness_score": report.overall_readiness_score,
                "performance_summary": report.performance_summary,
                "development_priorities": list(report.development_priorities),
            },
        )
    except Exception:  # pragma: no cover - export channel must never break the UI
        pass
    st.subheader("Interview readiness report")
    # If saving to history failed, warn (safely) and offer a retry — the report
    # itself stays fully usable.
    if session.data.save_failed and not session.data.saved_report_id:
        st.warning(
            "Your report was generated, but it could not be saved to Interview "
            "History. Please try again."
        )
        if st.button("Retry saving to history", key="retry_save_history"):
            session.data.save_failed = False
            _persist_if_new(session, load_config())
            st.rerun()
    st.metric("Readiness score", f"{report.overall_readiness_score}/100")
    st.caption("Practice guidance only — not an employment decision.")

    st.markdown("**Performance summary**")
    st.write(report.performance_summary)

    left, right = st.columns(2)
    with left:
        _bullet_block("Strongest competencies", report.strongest_competencies)
        _bullet_block("Development priorities", report.development_priorities)
        _bullet_block("Recurring patterns", report.recurring_answer_patterns)
        _bullet_block("Evidence gaps", report.evidence_gaps)
    with right:
        _bullet_block("Highest-risk questions", report.highest_risk_questions)
        _bullet_block("Practice actions", report.recommended_practice_actions)
        _bullet_block("Final checklist", report.final_interview_checklist)

    _render_delivery_summary(session)

    st.divider()
    columns = st.columns(2)
    columns[0].download_button(
        "Download JSON",
        data=ui_helpers.report_to_json(report),
        file_name="interview_report.json",
        mime="application/json",
    )
    columns[1].download_button(
        "Download Markdown",
        data=ui_helpers.report_to_markdown(report, session.data.config),
        file_name="interview_report.md",
        mime="text/markdown",
    )

    # Reverse navigation back to Career Intelligence (context is preserved).
    if handoff.has_context(st.session_state):
        st.divider()
        if st.button("Return to preparation"):
            handoff.request_return_to_preparation(st.session_state)
            st.rerun()


# =============================================================================
# H. Usage panel  &  I. Reset  &  J. Error view
# =============================================================================


def render_usage(session: SessionManager) -> None:
    st.sidebar.divider()
    st.sidebar.markdown("### Usage")
    data = session.data
    if not data.usage_records:
        st.sidebar.caption("No requests yet this session.")
        return
    latest = data.usage_records[-1]
    st.sidebar.write(f"Model: `{latest.model}`")
    st.sidebar.write(f"Input tokens: {latest.prompt_tokens}")
    st.sidebar.write(f"Output tokens: {latest.completion_tokens}")
    st.sidebar.write(f"Total tokens: {latest.total_tokens}")
    current = (
        latest.reported_cost
        if latest.reported_cost is not None
        else (latest.calculated_cost if latest.cost_source != "unavailable" else None)
    )
    st.sidebar.write(f"Current request cost: {ui_helpers.format_usd(current)}")
    st.sidebar.caption(f"Cost source: {latest.cost_source}")

    # Speech-to-text usage is tracked and displayed separately from LLM cost.
    if data.transcription_usage:
        total_seconds = sum(u.units for u in data.transcription_usage)
        known_costs = [
            u.cost_usd for u in data.transcription_usage if u.cost_usd is not None
        ]
        st.sidebar.write(
            f"Transcribed audio: {total_seconds:.0f}s "
            f"({len(data.transcription_usage)} recording(s))"
        )
        if known_costs:
            st.sidebar.write(
                f"Transcription cost: {ui_helpers.format_usd(sum(known_costs))}"
            )
        else:
            st.sidebar.caption(
                "Transcription cost: not calculated (no rate configured)."
            )

    st.sidebar.write(
        f"Total session cost: {ui_helpers.format_usd(data.cumulative_cost_usd)}"
    )


def render_reset(session: SessionManager) -> None:
    st.sidebar.divider()
    st.sidebar.markdown("### Reset")
    confirm = st.sidebar.checkbox("Confirm: clear this interview")
    if st.sidebar.button("Reset current interview", disabled=not confirm):
        session.reset_interview()
        st.rerun()


def render_error(session: SessionManager) -> None:
    st.error(session.data.error or "Something went wrong. Please try again.")
    # Every failure offers a useful next step and keeps completed results. We
    # never send the candidate back to the start because one attempt failed.
    st.caption("Your completed answers and feedback so far are kept.")
    columns = st.columns(3)
    if columns[0].button("Try again", type="primary"):
        session.recover_from_error()
        st.rerun()
    if columns[1].button("Switch to text & continue"):
        # Recover and prefer the most robust input mode for the next attempt.
        st.session_state["main_answer_method"] = "Type"
        st.session_state["branch_answer_method"] = "Type"
        session.recover_from_error()
        st.rerun()
    if columns[2].button("Switch to voice & continue"):
        st.session_state["main_answer_method"] = "Record"
        st.session_state["branch_answer_method"] = "Record"
        session.recover_from_error()
        st.rerun()
    st.divider()
    if st.button("Reset interview"):
        session.reset_interview()
        st.rerun()


# =============================================================================
# Accounts & persistence (data-access via the repository only)
# =============================================================================


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a SQLite file URL if needed."""
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = database_url[len(prefix):]
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)


def get_repository(config: AppConfig) -> InterviewRepository:
    """A per-session repository over the configured database (lazily built)."""
    key = f"_repo::{config.database_url}"
    if key not in st.session_state:
        _ensure_sqlite_dir(config.database_url)
        engine = make_engine(config.database_url)
        init_db(engine)  # dev/tests; production applies Alembic migrations
        st.session_state[key] = InterviewRepository(make_session_factory(engine))
    return st.session_state[key]


def _current_user_id(config: AppConfig, repo: InterviewRepository) -> int | None:
    """Resolve the signed-in (or anonymous dev) user to an internal id."""
    user = auth.current_user(config)
    if user is None:
        return None
    return repo.get_or_create_user(
        subject=user.subject,
        provider=user.provider,
        display_name=user.display_name,
        email=user.email,
    )


def _interview_payload(data) -> dict:
    """Assemble a persistence payload from the session (appropriate data only)."""
    questions: list[dict] = []
    for i, question in enumerate(data.questions):
        answer_text = data.answers[i] if i < len(data.answers) else ""
        evaluation = (
            data.evaluations[i].model_dump() if i < len(data.evaluations) else None
        )
        guidance = timing.guidance_for_question(question)
        timing_metrics = (
            data.voice_metrics[i] if i < len(data.voice_metrics) else None
        )
        visual_metrics = (
            data.visual_metrics[i] if i < len(data.visual_metrics) else None
        )
        questions.append(
            {
                "position": i,
                "canonical_question": question.question,
                "question_type": question.question_type,
                "difficulty": question.difficulty,
                "timing_guidance": dataclasses.asdict(guidance),
                "is_deep_dive": False,
                "parent_position": None,
                "answer": (
                    {
                        "text": answer_text,
                        "evaluation": evaluation,
                        "timing_metrics": timing_metrics,
                        "visual_metrics": visual_metrics,
                    }
                    if (answer_text or evaluation)
                    else None
                ),
            }
        )
    # Deep Dive branches. Completed branches are archived into ``data.branches``
    # (and the active lists cleared) when the candidate returns to the main
    # interview, so serialise BOTH the archived branches and any still-active one
    # — otherwise finished Deep Dives are silently dropped from history.
    base = len(data.questions)
    default_parent = base - 1 if base else None
    position = base

    def _branch_records(questions_list, answers, evaluations, parent_id):
        nonlocal position
        parent_pos = parent_id if isinstance(parent_id, int) else default_parent
        for j, branch in enumerate(questions_list):
            answer_text = answers[j] if j < len(answers) else ""
            evaluation = evaluations[j] if j < len(evaluations) else None
            evaluation = evaluation.model_dump() if evaluation is not None else None
            questions.append(
                {
                    "position": position,
                    "canonical_question": branch.question,
                    "question_type": getattr(branch, "question_type", "behavioural"),
                    "difficulty": branch.difficulty,
                    "timing_guidance": None,
                    "is_deep_dive": True,
                    "parent_position": parent_pos,
                    "answer": (
                        {"text": answer_text, "evaluation": evaluation}
                        if (answer_text or evaluation)
                        else None
                    ),
                }
            )
            position += 1

    for archived in getattr(data, "branches", []):
        _branch_records(
            archived.get("questions", []), archived.get("answers", []),
            archived.get("evaluations", []), archived.get("parent_question_id"))
    # Any branch still active at completion (not yet returned to main).
    _branch_records(
        data.branch_questions, data.branch_answers, data.branch_evaluations,
        data.branch_parent_question_id)
    report = None
    if data.report is not None:
        report = {
            "report": data.report.model_dump(),
            "usage": {
                "total_tokens": sum(r.total_tokens for r in data.usage_records),
                "requests": len(data.usage_records),
            },
            "cost_usd": round(data.cumulative_cost_usd, 6),
        }
    return {
        "configuration": data.config.model_dump() if data.config else {},
        "mode": st.session_state.get("_practice_mode"),
        "status": "completed",
        "questions": questions,
        "report": report,
    }


def _persist_if_new(session: SessionManager, config: AppConfig) -> None:
    """Save a completed interview once per interview.

    The saved-report id lives on the session data (not a top-level Streamlit
    key), so ``reset_interview`` clears it and a *second* interview saves too.
    A save failure never breaks the report page: it records a bounded, safe flag
    so the page can show a friendly warning and offer a retry — the raw DB error
    is never surfaced.
    """
    data = session.data
    if data.saved_report_id:
        return
    try:
        repo = get_repository(config)
        user_id = _current_user_id(config, repo)
        if user_id is None:
            return
        interview_id = repo.save_interview(user_id, _interview_payload(data))
        data.saved_report_id = interview_id
        data.save_failed = False
    except Exception:  # noqa: BLE001 - persistence must not break the report
        # Record the failure safely (no DB/SQL/credential/stacktrace detail) so
        # the report page can warn and offer a retry.
        data.save_failed = True
        logger.warning("Interview persistence failed", exc_info=True)


# =============================================================================
# Candidate pages (Dashboard / History / Progress / Settings)
# =============================================================================


def _render_login(config: AppConfig) -> None:
    st.subheader("Sign in to practise")
    st.write(
        "Signing in keeps your interview history and progress across sessions."
    )
    st.caption(constants.DATA_RETENTION_NOTE)
    if st.button("Log in", type="primary"):
        try:
            auth.login()
        except Exception:  # noqa: BLE001 - no OIDC configured
            st.error(
                "Login is not configured. Set up an OIDC provider in "
                "`.streamlit/secrets.toml` under `[auth]`."
            )


def _page_dashboard(config: AppConfig) -> None:
    st.subheader("Dashboard")
    repo = get_repository(config)
    user_id = _current_user_id(config, repo)
    metrics = repo.dashboard_metrics(user_id) if user_id is not None else {}
    if not metrics.get("interviews_completed"):
        st.info("No practice interviews yet — start one from **New Practice**.")
        return
    columns = st.columns(3)
    columns[0].metric("Interviews completed", metrics["interviews_completed"])
    score = metrics.get("average_practice_score")
    columns[1].metric("Avg practice score", f"{score}/100" if score else "—")
    secs = metrics.get("average_answer_seconds")
    columns[2].metric("Avg answer length", f"{secs:.0f}s" if secs else "—")
    if metrics.get("most_common_improvement_area"):
        st.caption(
            f"Most common area to work on: **{metrics['most_common_improvement_area']}**"
        )
    st.caption("Practice guidance only — not an objective hiring probability.")
    st.markdown("#### Recent interviews")
    for row in metrics.get("recent_interviews", []):
        st.write(
            f"- #{row['id']} · {row.get('target_role') or 'Interview'} · "
            f"{row.get('questions')} questions · {(row.get('created_at') or '')[:10]}"
        )


def _page_history(config: AppConfig) -> None:
    st.subheader("Interview History")
    repo = get_repository(config)
    user_id = _current_user_id(config, repo)
    interviews = repo.list_interviews(user_id) if user_id is not None else []
    if not interviews:
        st.info("No saved interviews yet.")
        return
    labels = {
        f"#{row['id']} · {row.get('target_role') or 'Interview'} · "
        f"{(row.get('created_at') or '')[:16]}": row["id"]
        for row in interviews
    }
    choice = st.selectbox("Choose an interview", list(labels))
    interview_id = labels[choice]
    detail = repo.get_interview(user_id, interview_id)
    if detail is None:
        st.error("That interview could not be found.")
        return

    columns = st.columns(2)
    columns[0].download_button(
        "Download report (JSON)",
        data=json.dumps(detail, indent=2, default=str),
        file_name=f"interview_{interview_id}.json",
        mime="application/json",
    )
    if columns[1].button("Delete this interview", type="secondary"):
        repo.delete_interview(user_id, interview_id)
        st.rerun()

    for q in detail["questions"]:
        tag = "🔎 Deep Dive" if q["is_deep_dive"] else f"Q{q['position'] + 1}"
        with st.expander(f"{tag}: {q['canonical_question'][:80]}"):
            answer = q.get("answer") or {}
            st.markdown(f"**Your answer:** {answer.get('text') or '—'}")
            evaluation = answer.get("evaluation")
            if evaluation:
                st.markdown(
                    f"**Score:** {evaluation.get('overall_score')}/100"
                )
                for area in evaluation.get("improvement_areas", []) or []:
                    st.markdown(f"- Improve: {area}")
            if answer.get("timing_metrics"):
                st.caption(f"Delivery: {answer['timing_metrics']}")
            if answer.get("visual_metrics"):
                st.caption(f"Visual (aggregated): {answer['visual_metrics']}")
    if detail.get("report"):
        with st.expander("Final report"):
            st.json(detail["report"]["report"])


def _page_progress(config: AppConfig) -> None:
    st.subheader("Progress")
    repo = get_repository(config)
    user_id = _current_user_id(config, repo)
    export = repo.export_user_data(user_id) if user_id is not None else {"interviews": []}
    scores: list[float] = []
    durations: list[float] = []
    for interview in export.get("interviews", []):
        for q in interview.get("questions", []):
            answer = q.get("answer") or {}
            evaluation = answer.get("evaluation") or {}
            if evaluation.get("overall_score") is not None:
                scores.append(evaluation["overall_score"])
            timing_metrics = answer.get("timing_metrics") or {}
            if timing_metrics.get("total_speaking_seconds"):
                durations.append(timing_metrics["total_speaking_seconds"])
    if not scores:
        st.info("Complete a few interviews to see your progress trend.")
        return
    st.markdown("**Practice score trend** (guidance only)")
    st.line_chart(scores)
    if durations:
        st.markdown("**Answer length trend (seconds)**")
        st.line_chart(durations)


def _page_settings(config: AppConfig) -> None:
    st.subheader("Settings")
    user = auth.current_user(config)
    if user is not None:
        who = user.display_name or user.email or user.subject
        st.write(f"Signed in as **{who}**" + (" (local dev)" if user.is_anonymous else ""))
        if not user.is_anonymous and st.button("Log out"):
            try:
                auth.logout()
            except Exception:  # noqa: BLE001
                pass

    st.markdown("#### Your data")
    st.caption(constants.DATA_RETENTION_NOTE)
    repo = get_repository(config)
    user_id = _current_user_id(config, repo)
    if user_id is None:
        return
    export = repo.export_user_data(user_id)
    st.download_button(
        "Export my data (JSON)",
        data=json.dumps(export, indent=2, default=str),
        file_name="my_interview_data.json",
        mime="application/json",
    )
    st.divider()
    st.markdown("#### Danger zone")
    confirm = st.checkbox("I understand this permanently deletes all my interviews")
    if st.button("Delete all my interview data", disabled=not confirm):
        removed = repo.delete_all_for_user(user_id)
        st.success(f"Deleted {removed} interview(s).")


# =============================================================================
# Main router
# =============================================================================


def _render_practice_page(session: SessionManager, config: AppConfig, dev: dict) -> None:
    if not config.is_configured:
        st.warning(
            "Add an OpenRouter API key to start. You can still explore the "
            "setup form below."
        )
    state = session.state
    if state is SessionState.SETUP:
        render_setup(session, config, dev)
    elif state is SessionState.STRATEGY_READY:
        render_strategy(session)
    elif state in (
        SessionState.AWAITING_ANSWER,
        SessionState.EVALUATING,
        SessionState.INTERVIEW_IN_PROGRESS,
        SessionState.BRANCH_AWAITING_ANSWER,
        SessionState.BRANCH_EVALUATING,
    ):
        render_interview(session)
    elif state is SessionState.INTERVIEW_COMPLETE:
        render_complete(session)
    elif state is SessionState.REPORT_READY:
        _persist_if_new(session, config)  # save history once, best-effort
        render_report(session)
    elif state is SessionState.ERROR:
        render_error(session)


def render_studio() -> None:
    """Render the Interview Practice module inside the Interview OS shell.

    The unified ``app.py`` owns ``st.set_page_config`` and the top-level nav; this
    renders the full Interview Practice experience (its own sub-menu intact).
    """
    session = get_session()
    config = load_config()

    render_header()
    dev = render_developer_settings(config)

    # Auth gate: required in production, optional (anonymous) for local dev.
    if auth.current_user(config) is None:
        _render_login(config)
        return

    page = st.sidebar.radio(
        "Menu",
        ["New Practice", "Dashboard", "Interview History", "Progress", "Settings", "Advanced"],
        key="nav_page",
    )

    if page == "New Practice":
        _render_practice_page(session, config, dev)
    elif page == "Dashboard":
        _page_dashboard(config)
    elif page == "Interview History":
        _page_history(config)
    elif page == "Progress":
        _page_progress(config)
    elif page == "Settings":
        _page_settings(config)
    elif page == "Advanced":
        prompt_lab.render_prompt_lab(config)

    if dev["show_usage"]:
        render_usage(session)
    render_reset(session)
