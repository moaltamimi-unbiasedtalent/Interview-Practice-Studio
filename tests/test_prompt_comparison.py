"""Offline tests for the experimentation scripts and the Prompt Lab.

No chargeable comparison is ever executed here: the live runners are exercised
with a fake evaluation service, and the CLIs are only invoked in their dry-run /
refusal paths. Nothing touches the network.
"""

import json
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

from scripts import compare_model_settings as cm
from scripts import compare_prompts as cp
from src import constants
from src.models import AnswerEvaluation, InterviewConfiguration, UsageRecord

# Absolute path so AppTest resolves app.py across Streamlit versions.
APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


# --- A fake evaluation service (mocked model result) ------------------------


class FakeEvaluationService:
    """Returns a canned evaluation; records the inputs it was called with."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def evaluate_answer(self, config, question, answer, settings):
        self.calls.append((question, answer, settings.prompt_technique, settings.temperature, settings.max_tokens))
        evaluation = AnswerEvaluation(
            overall_score=70,
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
        usage = UsageRecord(
            model=settings.model,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            reported_cost=0.001,
            calculated_cost=0.0,
            cost_source="reported",
            request_duration_seconds=0.5,
        )
        return evaluation, usage


# --- Prompt comparison: pure pieces -----------------------------------------


class TestPromptComparisonPure:
    def test_scenario_is_valid_and_profession_neutral(self) -> None:
        config, question, answer = cp.build_scenario()
        assert isinstance(config, InterviewConfiguration)
        blob = f"{config.target_role} {config.industry_or_sector} {question} {answer}".lower()
        for biased in ("software", "engineer", "nurse", "lawyer", "doctor", "sales"):
            assert biased not in blob

    def test_planned_requests_is_five(self) -> None:
        assert cp.planned_request_count() == 5
        assert cp.planned_request_count() == len(constants.PROMPT_TECHNIQUES)

    def test_placeholder_rows_have_no_fabricated_metrics(self) -> None:
        rows = cp.placeholder_rows()
        assert len(rows) == 5
        for row in rows:
            assert row["status"] == "pending"
            assert row["valid_json"] is None
            assert row["prompt_tokens"] is None
            assert row["cost_usd"] is None
            assert all(v == "PENDING" for v in row["evaluation"].values())

    def test_report_lists_all_seven_dimensions(self) -> None:
        report = cp.build_report(cp.placeholder_rows(), live=False)
        assert report["status"] == "pending"
        assert report["evaluation_dimensions"] == [
            "relevance",
            "specificity",
            "role_adaptation",
            "structure",
            "actionability",
            "hallucination_risk",
            "json_reliability",
        ]

    def test_report_includes_longest_is_not_best_caveat(self) -> None:
        report = cp.build_report(cp.placeholder_rows(), live=False)
        assert any("longest response" in note.lower() for note in report["notes"])

    def test_markdown_renders_scenario_techniques_and_caveat(self) -> None:
        md = cp.report_to_markdown(cp.build_report(cp.placeholder_rows(), live=False))
        assert "Fixed scenario" in md
        assert "Project Coordinator" in md
        for technique_id in constants.PROMPT_TECHNIQUES:
            name = cp.registry.get_technique(technique_id).name
            assert name in md
        assert "Do not treat the longest response as the best" in md

    def test_json_round_trips(self) -> None:
        report = cp.build_report(cp.placeholder_rows(), live=False)
        assert json.loads(json.dumps(report)) == report


# --- Prompt comparison: live runner with a fake service ---------------------


class TestPromptComparisonRunner:
    def test_runner_fills_metrics_and_keeps_manual_pending(self) -> None:
        service = FakeEvaluationService()
        rows = cp.run_prompt_comparison(service)
        assert len(rows) == 5
        for row in rows:
            assert row["status"] == "completed"
            assert row["valid_json"] is True
            assert row["prompt_tokens"] == 100
            assert row["overall_score"] == 70
            # Manual dimensions are never auto-filled.
            assert all(v == "PENDING" for v in row["evaluation"].values())

    def test_runner_sends_identical_input_to_every_technique(self) -> None:
        service = FakeEvaluationService()
        cp.run_prompt_comparison(service)
        questions = {call[0] for call in service.calls}
        answers = {call[1] for call in service.calls}
        techniques = [call[2] for call in service.calls]
        temps = {call[3] for call in service.calls}
        tokens = {call[4] for call in service.calls}
        assert len(questions) == 1 and len(answers) == 1  # identical input
        assert temps == {cp.FIXED_TEMPERATURE} and tokens == {cp.FIXED_MAX_TOKENS}
        assert techniques == list(constants.PROMPT_TECHNIQUES)  # all five


# --- Model-setting comparison -----------------------------------------------


class TestModelSettingsComparison:
    def test_temperatures_and_token_settings(self) -> None:
        assert cm.TEMPERATURES == [0.1, 0.5, 0.9]
        labels = [label for label, _ in cm.TOKEN_SETTINGS]
        assert labels == ["concise", "detailed"]

    def test_grid_size_is_six(self) -> None:
        assert cm.planned_request_count() == 6
        assert len(cm.placeholder_rows()) == 6

    def test_supported_temperatures_filters_when_unsupported(self) -> None:
        assert cm.supported_temperatures(["temperature", "max_tokens"]) == [0.1, 0.5, 0.9]
        collapsed = cm.supported_temperatures(["max_tokens"])
        assert collapsed == [constants.DEFAULT_TEMPERATURE]

    def test_runner_respects_unsupported_temperature(self) -> None:
        service = FakeEvaluationService()
        rows, temperature_supported = cm.run_model_settings_comparison(
            service, ["max_tokens"]
        )
        assert temperature_supported is False
        # Only the two token settings at the single default temperature.
        assert len(rows) == 2
        assert {r["temperature"] for r in rows} == {constants.DEFAULT_TEMPERATURE}

    def test_runner_full_grid_when_supported(self) -> None:
        service = FakeEvaluationService()
        rows, temperature_supported = cm.run_model_settings_comparison(
            service, ["temperature", "max_tokens"]
        )
        assert temperature_supported is True
        assert len(rows) == 6
        for row in rows:
            assert row["valid_json"] is True
            assert all(v == "PENDING" for v in row["dimensions"].values())

    def test_markdown_has_caveats(self) -> None:
        md = cm.report_to_markdown(cm.build_report(cm.placeholder_rows(), live=False))
        assert "Model-setting comparison" in md
        assert "held constant" in md.lower()


# --- CLIs never run chargeable work automatically ---------------------------


class TestClisAreSafe:
    def test_prompt_dry_run_writes_placeholders_offline(self, tmp_path) -> None:
        out_json = tmp_path / "p.json"
        out_md = tmp_path / "p.md"
        code = cp.main(["--out-json", str(out_json), "--out-md", str(out_md)])
        assert code == 0
        data = json.loads(out_json.read_text())
        assert data["status"] == "pending"
        assert out_md.read_text().startswith("# Prompt comparison")

    def test_prompt_run_without_confirm_refuses(self) -> None:
        # No files/network: --run alone must refuse with a non-zero code.
        assert cp.main(["--run"]) == 1

    def test_settings_dry_run_writes_placeholders_offline(self, tmp_path) -> None:
        out_json = tmp_path / "m.json"
        out_md = tmp_path / "m.md"
        code = cm.main(["--out-json", str(out_json), "--out-md", str(out_md)])
        assert code == 0
        assert json.loads(out_json.read_text())["status"] == "pending"

    def test_settings_run_without_confirm_refuses(self) -> None:
        assert cm.main(["--run"]) == 1


# --- Prompt Lab renders offline, with runs gated ----------------------------


class TestPromptLabUI:
    def test_prompt_lab_renders_without_network(self) -> None:
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.radio(key="nav_page").set_value("Advanced").run()
        assert not at.exception
        assert any("Prompt Lab" in s.value for s in at.subheader)

    def test_run_buttons_are_disabled_until_confirmed(self) -> None:
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.radio(key="nav_page").set_value("Advanced").run()
        run_buttons = [
            b for b in at.button if "Run prompt comparison" in b.label or "Run model-setting" in b.label
        ]
        assert run_buttons  # present
        assert all(b.disabled for b in run_buttons)  # gated until confirmation
