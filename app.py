"""Streamlit entry point for Interview Practice Studio.

This file renders the interface only. All behaviour lives in ``src``: the
session state machine (`session_manager`), the interview services, the security
layer, pricing and the OpenRouter client. The app is a single page that routes
on the explicit session state, so a Streamlit rerun always shows a consistent
view and never fires a duplicate API call.
"""

from __future__ import annotations

import json

import streamlit as st
from pydantic import ValidationError

from scripts import compare_model_settings as cm
from scripts import compare_prompts as cp
from src import constants, security, ui_helpers
from src.config import AppConfig, load_config
from src.evaluation_service import EvaluationService
from src.interview_service import InterviewService, QuestionHistory, ServiceError
from src.models import InterviewConfiguration, ModelSettings
from src.openrouter_client import OpenRouterClient, OpenRouterError
from src.pricing_service import PricingService
from src.report_service import ReportService
from src.session_manager import SessionManager, SessionState

_METADATA_CACHE_KEY = "_model_supported_params"


# =============================================================================
# Resource wiring (no network on import or first render)
# =============================================================================


def get_session() -> SessionManager:
    """Session manager over Streamlit's namespaced session_state."""
    return SessionManager(st.session_state)


def get_pricing_service() -> PricingService:
    """A pricing service kept in session so its metadata cache persists."""
    if "_pricing_service" not in st.session_state:
        st.session_state["_pricing_service"] = PricingService()
    return st.session_state["_pricing_service"]


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

        temperature = st.slider(
            "Temperature",
            min_value=constants.MIN_TEMPERATURE,
            max_value=constants.MAX_TEMPERATURE,
            value=constants.DEFAULT_TEMPERATURE,
            step=0.1,
        )
        max_tokens = st.number_input(
            "Maximum output tokens",
            min_value=constants.MIN_OUTPUT_TOKENS,
            max_value=constants.MAX_OUTPUT_TOKENS_LIMIT,
            value=constants.DEFAULT_MAX_OUTPUT_TOKENS,
            step=64,
        )
        show_usage = st.checkbox("Show usage details", value=False)

        # Explain structured-output support only from cached metadata (no
        # network on a normal render).
        supported = st.session_state.get(_METADATA_CACHE_KEY, {}).get(model)
        if supported is not None:
            if "response_format" in supported:
                st.caption("This model supports strict JSON (response_format).")
            else:
                st.caption(
                    "This model does not support strict JSON mode; the app "
                    "relies on a prompt-only JSON contract."
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
            client.test_connection()
            cache = st.session_state.setdefault(_METADATA_CACHE_KEY, {})
            try:
                cache[model] = list(pricing.supported_parameters(model))
            except Exception:  # noqa: BLE001 - metadata is best-effort
                pass
        st.success("Connection OK.")
    except OpenRouterError as exc:
        st.error(exc.message)
    finally:
        client.close()


# =============================================================================
# B. Interview setup form
# =============================================================================


def render_setup(session: SessionManager, config: AppConfig, dev: dict) -> None:
    st.subheader("Set up your interview")
    with st.form("interview_setup"):
        target_role = st.text_input("Target role *", help="Required.")
        industry = st.text_input("Industry or sector")
        career_label = st.selectbox(
            "Career level", ui_helpers.labels(ui_helpers.CAREER_LEVELS)
        )
        company_context = st.text_area("Company context", height=80)
        job_description = st.text_area("Job description (recommended)", height=140)
        candidate_background = st.text_area("Your background", height=100)
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
            index=ui_helpers.difficulty_default_index(),
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


def render_interview(session: SessionManager) -> None:
    data = session.data
    planned = data.config.number_of_questions
    answered = len(data.evaluations)
    asked = len(data.questions)

    st.subheader("Mock interview")
    st.progress(min(answered / planned, 1.0) if planned else 0.0)
    st.caption(f"Answered {answered} of {planned} planned questions.")

    for message in data.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if data.evaluations:
        st.divider()
        render_feedback(data.evaluations[-1])

    st.divider()
    if session.state is SessionState.AWAITING_ANSWER:
        answer = st.chat_input("Type your answer…")
        if answer:
            _handle_answer(session, answer)
            st.rerun()
        if answered >= 1 and st.button("End interview early"):
            session.end_interview_early()
            st.rerun()
    elif session.state is SessionState.INTERVIEW_IN_PROGRESS:
        columns = st.columns(2)
        if asked < planned:
            if columns[0].button("Next question", type="primary"):
                _generate_next_question(session)
                st.rerun()
        else:
            st.info("You have answered all planned questions.")
        if columns[1].button("Finish & generate report"):
            session.complete_interview()
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


def render_report(session: SessionManager) -> None:
    report = session.data.report
    st.subheader("Interview readiness report")
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
    st.sidebar.write(
        f"Cumulative session cost: {ui_helpers.format_usd(data.cumulative_cost_usd)}"
    )
    st.sidebar.caption(f"Cost source: {latest.cost_source}")


def render_reset(session: SessionManager) -> None:
    st.sidebar.divider()
    st.sidebar.markdown("### Reset")
    confirm = st.sidebar.checkbox("Confirm: clear this interview")
    if st.sidebar.button("Reset current interview", disabled=not confirm):
        session.reset_interview()
        st.rerun()


def render_error(session: SessionManager) -> None:
    st.error(session.data.error or "Something went wrong. Please try again.")
    columns = st.columns(2)
    if columns[0].button("Try again"):
        session.recover_from_error()
        st.rerun()
    if columns[1].button("Reset interview"):
        session.reset_interview()
        st.rerun()


# =============================================================================
# Prompt Lab (developer experimentation — clearly separated)
# =============================================================================


def _lab_scenario_summary() -> None:
    config, question, answer = cp.build_scenario()
    st.markdown("**Fixed scenario (profession-neutral)**")
    st.write(
        f"Role: {config.target_role} · Sector: {config.industry_or_sector} · "
        f"Level: {config.career_level} · Type: {config.interview_types[0]}"
    )
    st.write(f"Question: {question}")
    st.write(f"Candidate answer: {answer}")


def _results_table(rows: list[dict]) -> list[dict]:
    return [
        {
            "Variant": row.get("technique_name")
            or f"temp {row.get('temperature')} / {row.get('token_setting')}",
            "Valid JSON": row["valid_json"],
            "Prompt tok": row["prompt_tokens"],
            "Completion tok": row["completion_tokens"],
            "Cost USD": row["cost_usd"],
            "Latency s": row["latency_seconds"],
            "Overall": row["overall_score"],
        }
        for row in rows
    ]


def _render_prompt_comparison_tab(config: AppConfig) -> None:
    count = cp.planned_request_count()
    st.write(
        "Runs all five techniques on the fixed scenario with the model, "
        f"temperature and token limit held constant — **{count} chargeable "
        "requests**."
    )
    st.caption(
        f"Fixed: model `{cp.FIXED_MODEL}`, temperature {cp.FIXED_TEMPERATURE}, "
        f"max tokens {cp.FIXED_MAX_TOKENS}."
    )
    confirm = st.checkbox(
        f"I confirm sending {count} chargeable requests", key="pl_prompts_confirm"
    )
    if st.button(
        "Run prompt comparison",
        key="pl_prompts_run",
        disabled=not (confirm and config.is_configured),
    ):
        pricing = get_pricing_service()
        _, evaluation_service, _, client = build_services(config, pricing)
        try:
            with st.spinner("Running comparison…"):
                st.session_state["pl_prompt_rows"] = cp.run_prompt_comparison(
                    evaluation_service
                )
        finally:
            client.close()

    rows = st.session_state.get("pl_prompt_rows")
    if rows:
        st.dataframe(_results_table(rows))
        st.download_button(
            "Download JSON",
            data=json.dumps(cp.build_report(rows, live=True), indent=2),
            file_name="prompt_comparison.json",
            mime="application/json",
            key="pl_prompts_dl",
        )
        st.caption(
            "Longer output is not better — score the manual dimensions in "
            "`evaluations/prompt_comparison.md`."
        )


def _render_model_settings_tab(config: AppConfig) -> None:
    count = cm.planned_request_count()
    st.write(
        "Sweeps temperature (0.1, 0.5, 0.9) and concise/detailed token limits "
        f"with the model and technique held constant — up to **{count} "
        "chargeable requests** (fewer if the model lacks temperature support)."
    )
    st.caption(
        f"Fixed: model `{cm.FIXED_MODEL}`, technique {cm.FIXED_TECHNIQUE}."
    )
    confirm = st.checkbox(
        f"I confirm sending up to {count} chargeable requests",
        key="pl_settings_confirm",
    )
    if st.button(
        "Run model-setting sweep",
        key="pl_settings_run",
        disabled=not (confirm and config.is_configured),
    ):
        pricing = get_pricing_service()
        _, evaluation_service, _, client = build_services(config, pricing)
        try:
            with st.spinner("Running sweep…"):
                supported = pricing.supported_parameters(cm.FIXED_MODEL)
                rows, _ = cm.run_model_settings_comparison(
                    evaluation_service, supported
                )
                st.session_state["pl_settings_rows"] = rows
        finally:
            client.close()

    rows = st.session_state.get("pl_settings_rows")
    if rows:
        st.dataframe(_results_table(rows))
        st.caption(
            "Judge completeness, specificity and consistency manually in "
            "`evaluations/model_settings_comparison.md`."
        )


def render_prompt_lab(config: AppConfig) -> None:
    st.subheader("Prompt Lab")
    st.caption(
        "Developer experimentation only. The candidate interview lives under "
        "the 'Interview' view."
    )
    _lab_scenario_summary()
    st.info(
        "Placeholder results live in `evaluations/`. No requests are made until "
        "you run a comparison below."
    )
    if not config.is_configured:
        st.warning("Add an OpenRouter API key to run live comparisons.")
    prompt_tab, settings_tab = st.tabs(["Prompt comparison", "Model settings"])
    with prompt_tab:
        _render_prompt_comparison_tab(config)
    with settings_tab:
        _render_model_settings_tab(config)


# =============================================================================
# Main router
# =============================================================================


def main() -> None:
    st.set_page_config(page_title=constants.APP_NAME, layout="wide")
    session = get_session()
    config = load_config()

    render_header()
    dev = render_developer_settings(config)

    view = st.sidebar.radio("View", ["Interview", "Prompt Lab"], key="view_mode")
    if view == "Prompt Lab":
        render_prompt_lab(config)
        if dev["show_usage"]:
            render_usage(session)
        render_reset(session)
        return

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
    ):
        render_interview(session)
    elif state is SessionState.INTERVIEW_COMPLETE:
        render_complete(session)
    elif state is SessionState.REPORT_READY:
        render_report(session)
    elif state is SessionState.ERROR:
        render_error(session)

    if dev["show_usage"]:
        render_usage(session)
    render_reset(session)


if __name__ == "__main__":
    main()
