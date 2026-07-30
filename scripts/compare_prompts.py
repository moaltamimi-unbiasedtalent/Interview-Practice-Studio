"""Prompt-comparison experiment.

Runs the *same* evaluation task with the *same* input and the *same* model,
temperature and token limit across all five prompt techniques, so the only
variable is the technique. The comparison is chargeable (one request per
technique), so it never runs automatically:

* ``python scripts/compare_prompts.py`` — a **dry run**: writes placeholder
  result files and makes no network request.
* ``python scripts/compare_prompts.py --run --confirm`` — executes the live,
  chargeable comparison and writes real results.

The pure functions here (scenario, plan, placeholders, serialization) are
imported by the Prompt Lab UI and by the tests, and never touch the network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow direct invocation (`python scripts/compare_prompts.py`) by ensuring the
# repository root is importable; harmless when imported as ``scripts.*``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import constants
from src import prompt_registry as registry
from src.models import InterviewConfiguration, ModelSettings

EVAL_DIR = Path(__file__).resolve().parent.parent / "evaluations"
JSON_PATH = EVAL_DIR / "prompt_comparison.json"
MD_PATH = EVAL_DIR / "prompt_comparison.md"

# Fixed settings held constant across every technique.
FIXED_MODEL = constants.DEFAULT_MODEL
FIXED_TEMPERATURE = 0.3
FIXED_MAX_TOKENS = 1024

# The seven evaluation dimensions (scored manually after a run).
EVALUATION_DIMENSIONS = [
    "relevance",
    "specificity",
    "role_adaptation",
    "structure",
    "actionability",
    "hallucination_risk",
    "json_reliability",
]

# One fixed, profession-neutral scenario used for every technique.
SCENARIO_QUESTION = "Tell me about a time you improved how your team worked."
SCENARIO_ANSWER = (
    "I noticed our weekly updates were slow, so I suggested a shorter format. "
    "People seemed to like it and things felt a bit smoother afterwards."
)

CAVEATS = [
    "Identical model, temperature and token limit across all techniques.",
    "Identical user input (question + candidate answer) across all techniques.",
    "Costs are in USD; reported where available, otherwise a calculated estimate "
    "— never a final bill.",
    "Do not treat the longest response as the best; judge on the evaluation "
    "dimensions.",
    "Manual dimensions are scored by a human after reviewing the outputs; they "
    "are not auto-generated.",
]


def build_scenario() -> tuple[InterviewConfiguration, str, str]:
    """Return the fixed (config, question, candidate_answer) scenario."""
    config = InterviewConfiguration(
        target_role="Project Coordinator",
        industry_or_sector="general business",
        career_level="mid",
        interview_types=["behavioural"],
        interviewer_persona="neutral",
        difficulty="moderate",
        response_detail="standard",
        number_of_questions=1,
    )
    return config, SCENARIO_QUESTION, SCENARIO_ANSWER


def technique_ids() -> list[str]:
    return list(constants.PROMPT_TECHNIQUES)


def planned_request_count() -> int:
    """Number of chargeable requests a live run would make (one per technique)."""
    return len(technique_ids())


def _blank_evaluation() -> dict:
    return {dimension: "PENDING" for dimension in EVALUATION_DIMENSIONS}


def placeholder_rows() -> list[dict]:
    """Rows with every metric marked pending — no fabricated results."""
    rows = []
    for technique_id in technique_ids():
        rows.append(
            {
                "technique": technique_id,
                "technique_name": registry.get_technique(technique_id).name,
                "status": "pending",
                "valid_json": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "cost_usd": None,
                "cost_source": None,
                "latency_seconds": None,
                "overall_score": None,
                "output": None,
                "output_summary": "PENDING — run the experiment",
                "manual_observations": "PENDING",
                "evaluation": _blank_evaluation(),
            }
        )
    return rows


def build_report(rows: list[dict], *, live: bool) -> dict:
    """Assemble the full report structure (JSON-serializable)."""
    config, question, answer = build_scenario()
    return {
        "experiment": "prompt_comparison",
        "status": "completed" if live else "pending",
        "fixed_settings": {
            "model": FIXED_MODEL,
            "temperature": FIXED_TEMPERATURE,
            "max_tokens": FIXED_MAX_TOKENS,
        },
        "scenario": {
            "target_role": config.target_role,
            "industry_or_sector": config.industry_or_sector,
            "career_level": config.career_level,
            "interview_type": config.interview_types[0],
            "question": question,
            "candidate_answer": answer,
        },
        "evaluation_dimensions": EVALUATION_DIMENSIONS,
        "techniques": rows,
        "notes": CAVEATS,
    }


def _cell(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.6f}" if value < 1 else f"{value:.3f}"
    return str(value)


def report_to_markdown(report: dict) -> str:
    """Render the report as readable Markdown."""
    scenario = report["scenario"]
    fixed = report["fixed_settings"]
    lines = [
        "# Prompt comparison",
        "",
        f"**Status:** {report['status']}",
        "",
        "## Method",
        "",
        "The same evaluation task is run across all five prompt techniques with "
        "identical input and identical model settings, so the only variable is "
        "the technique.",
        "",
        f"- **Model:** `{fixed['model']}`",
        f"- **Temperature:** {fixed['temperature']}",
        f"- **Max tokens:** {fixed['max_tokens']}",
        "",
        "## Fixed scenario (profession-neutral)",
        "",
        f"- **Target role:** {scenario['target_role']}",
        f"- **Sector:** {scenario['industry_or_sector']}",
        f"- **Career level:** {scenario['career_level']}",
        f"- **Interview type:** {scenario['interview_type']}",
        f"- **Question:** {scenario['question']}",
        f"- **Candidate answer:** {scenario['candidate_answer']}",
        "",
        "## Recorded metrics",
        "",
        "| Technique | Valid JSON | Prompt tok | Completion tok | Cost (USD) | "
        "Latency (s) | Overall |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report["techniques"]:
        lines.append(
            "| {name} | {valid} | {p} | {c} | {cost} | {lat} | {overall} |".format(
                name=row["technique_name"],
                valid=_cell(row["valid_json"]),
                p=_cell(row["prompt_tokens"]),
                c=_cell(row["completion_tokens"]),
                cost=_cell(row["cost_usd"]),
                lat=_cell(row["latency_seconds"]),
                overall=_cell(row["overall_score"]),
            )
        )

    lines += [
        "",
        "## Evaluation dimensions (scored manually)",
        "",
        "For each technique, score 1–5 and add observations:",
        "",
        "| Technique | "
        + " | ".join(d.replace("_", " ") for d in report["evaluation_dimensions"])
        + " | Observations |",
        "|" + "---|" * (len(report["evaluation_dimensions"]) + 2),
    ]
    for row in report["techniques"]:
        cells = [_cell(row["evaluation"][d]) for d in report["evaluation_dimensions"]]
        lines.append(
            f"| {row['technique_name']} | "
            + " | ".join(cells)
            + f" | {row['manual_observations']} |"
        )

    lines += ["", "## Notes"]
    lines += [f"- {note}" for note in report["notes"]]
    lines.append("")
    return "\n".join(lines)


def run_prompt_comparison(
    evaluation_service,
    *,
    model: str = FIXED_MODEL,
    temperature: float = FIXED_TEMPERATURE,
    max_tokens: int = FIXED_MAX_TOKENS,
) -> list[dict]:
    """Execute the live comparison. Requires a configured ``EvaluationService``.

    One chargeable request per technique. The seven manual dimensions stay
    ``PENDING`` for a human to fill in after reviewing the outputs.
    """
    config, question, answer = build_scenario()
    rows = placeholder_rows()
    for row in rows:
        settings = ModelSettings(
            model=model,
            prompt_technique=row["technique"],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            evaluation, usage = evaluation_service.evaluate_answer(
                config, question, answer, settings
            )
            cost = (
                usage.reported_cost
                if usage.reported_cost is not None
                else usage.calculated_cost
            )
            row.update(
                status="completed",
                valid_json=True,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                cost_usd=cost,
                cost_source=usage.cost_source,
                latency_seconds=usage.request_duration_seconds,
                overall_score=evaluation.overall_score,
                output=evaluation.model_dump(),
                output_summary=(
                    f"overall {evaluation.overall_score}/100; "
                    f"{len(evaluation.strengths)} strengths, "
                    f"{len(evaluation.improvement_areas)} improvements"
                ),
            )
        except Exception as exc:  # noqa: BLE001 - record failure, keep going
            row.update(status="error", valid_json=False, output_summary=f"error: {type(exc).__name__}")
    return rows


def _write(report: dict, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(report_to_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prompt-comparison experiment.")
    parser.add_argument("--run", action="store_true", help="Execute the live comparison.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required with --run to acknowledge chargeable requests.",
    )
    parser.add_argument("--out-json", default=str(JSON_PATH))
    parser.add_argument("--out-md", default=str(MD_PATH))
    args = parser.parse_args(argv)

    json_path = Path(args.out_json)
    md_path = Path(args.out_md)
    count = planned_request_count()

    if not args.run:
        report = build_report(placeholder_rows(), live=False)
        _write(report, json_path, md_path)
        print(
            f"Dry run: wrote placeholders to {json_path} and {md_path}. "
            f"No requests made. Use --run --confirm to send {count} chargeable "
            "requests."
        )
        return 0

    if not args.confirm:
        print(
            f"Refusing to run: this sends {count} chargeable requests. "
            "Re-run with --run --confirm to proceed."
        )
        return 1

    # Live path — imported here so a dry run never needs the client.
    from src.config import load_config
    from src.evaluation_service import EvaluationService
    from src.openrouter_client import OpenRouterClient
    from src.pricing_service import PricingService

    config = load_config()
    if not config.is_configured:
        print("No OpenRouter API key configured; cannot run the live comparison.")
        return 1

    client = OpenRouterClient(config)
    try:
        service = EvaluationService(client, PricingService())
        rows = run_prompt_comparison(service)
    finally:
        client.close()

    report = build_report(rows, live=True)
    _write(report, json_path, md_path)
    print(f"Live run complete: wrote {json_path} and {md_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
