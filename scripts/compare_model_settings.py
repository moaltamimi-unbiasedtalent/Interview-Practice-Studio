"""Model-setting experiment.

Sweeps temperature (0.1, 0.5, 0.9) and two maximum-token settings (concise vs
detailed) on the fixed profession-neutral scenario, holding the model and
prompt technique constant. Like the prompt comparison, it is chargeable and
never runs automatically:

* ``python scripts/compare_model_settings.py`` — dry run (placeholders, no
  network).
* ``python scripts/compare_model_settings.py --run --confirm`` — live run.

Only parameters the selected model supports are swept: if the model does not
list ``temperature`` in its metadata, the temperature sweep collapses to a
single default value and the report says so.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow direct invocation by ensuring the repository root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.compare_prompts import build_scenario
from src import constants
from src.models import ModelSettings

EVAL_DIR = Path(__file__).resolve().parent.parent / "evaluations"
JSON_PATH = EVAL_DIR / "model_settings_comparison.json"
MD_PATH = EVAL_DIR / "model_settings_comparison.md"

FIXED_MODEL = constants.DEFAULT_MODEL
FIXED_TECHNIQUE = "rubric_json"

TEMPERATURES = [0.1, 0.5, 0.9]
# (label, max_tokens) — both within the constant bounds. The lower value uses
# MIN_OUTPUT_TOKENS so the "concise" setting is the smallest budget the app
# permits (a smaller budget truncates structured JSON and cannot be parsed).
TOKEN_SETTINGS = [("concise", constants.MIN_OUTPUT_TOKENS), ("detailed", 1024)]

# Dimensions recorded per combination (several scored manually).
DIMENSIONS = [
    "completeness",
    "specificity",
    "consistency",
    "structured_output_validity",
]

CAVEATS = [
    "Model and prompt technique are held constant; only temperature and the "
    "token limit vary.",
    "Identical input across every combination.",
    "Only parameters the model supports are swept (see 'temperature supported').",
    "Costs are USD; reported where available, otherwise estimated — not a bill.",
    "Completeness, specificity and consistency are scored manually after review.",
]


def supported_temperatures(supported_parameters) -> list[float]:
    """Return the temperature sweep, collapsed if the model lacks temperature."""
    if "temperature" in set(supported_parameters):
        return list(TEMPERATURES)
    return [constants.DEFAULT_TEMPERATURE]


def combinations(temperatures: list[float]) -> list[tuple[float, str, int]]:
    """Return the (temperature, token_label, max_tokens) grid."""
    grid = []
    for temperature in temperatures:
        for label, max_tokens in TOKEN_SETTINGS:
            grid.append((temperature, label, max_tokens))
    return grid


def planned_request_count(temperatures: list[float] | None = None) -> int:
    temps = TEMPERATURES if temperatures is None else temperatures
    return len(combinations(temps))


def _blank_dimensions() -> dict:
    return {dimension: "PENDING" for dimension in DIMENSIONS}


def placeholder_rows(temperatures: list[float] | None = None) -> list[dict]:
    temps = TEMPERATURES if temperatures is None else temperatures
    rows = []
    for temperature, label, max_tokens in combinations(temps):
        rows.append(
            {
                "temperature": temperature,
                "token_setting": label,
                "max_tokens": max_tokens,
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
                "dimensions": _blank_dimensions(),
            }
        )
    return rows


def build_report(
    rows: list[dict], *, live: bool, temperature_supported: bool = True
) -> dict:
    config, question, answer = build_scenario()
    return {
        "experiment": "model_settings_comparison",
        "status": "completed" if live else "pending",
        "fixed_settings": {
            "model": FIXED_MODEL,
            "prompt_technique": FIXED_TECHNIQUE,
        },
        "swept": {
            "temperatures": TEMPERATURES,
            "token_settings": [
                {"label": label, "max_tokens": tokens}
                for label, tokens in TOKEN_SETTINGS
            ],
            "temperature_supported": temperature_supported,
        },
        "scenario": {
            "target_role": config.target_role,
            "question": question,
            "candidate_answer": answer,
        },
        "dimensions": DIMENSIONS,
        "combinations": rows,
        "notes": CAVEATS,
    }


def _cell(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.6f}" if 0 < value < 1 else f"{value:.3f}"
    return str(value)


def report_to_markdown(report: dict) -> str:
    fixed = report["fixed_settings"]
    scenario = report["scenario"]
    lines = [
        "# Model-setting comparison",
        "",
        f"**Status:** {report['status']}",
        "",
        "## Method",
        "",
        "Temperature and the token limit are swept while the model and prompt "
        "technique stay constant, so their effects can be compared in isolation.",
        "",
        f"- **Model:** `{fixed['model']}`",
        f"- **Prompt technique:** {fixed['prompt_technique']}",
        f"- **Temperatures:** {report['swept']['temperatures']}",
        "- **Token settings:** "
        + ", ".join(
            f"{s['label']} ({s['max_tokens']})" for s in report["swept"]["token_settings"]
        ),
        f"- **Temperature supported by model:** {report['swept']['temperature_supported']}",
        "",
        "## Fixed scenario (profession-neutral)",
        "",
        f"- **Target role:** {scenario['target_role']}",
        f"- **Question:** {scenario['question']}",
        f"- **Candidate answer:** {scenario['candidate_answer']}",
        "",
        "## Recorded metrics",
        "",
        "| Temp | Tokens | Valid JSON | Prompt tok | Completion tok | Cost (USD) "
        "| Latency (s) | Overall |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in report["combinations"]:
        lines.append(
            "| {t} | {label} ({mt}) | {valid} | {p} | {c} | {cost} | {lat} | "
            "{overall} |".format(
                t=row["temperature"],
                label=row["token_setting"],
                mt=row["max_tokens"],
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
        "## Qualitative dimensions (scored manually)",
        "",
        "| Temp | Tokens | "
        + " | ".join(d.replace("_", " ") for d in report["dimensions"])
        + " | Observations |",
        "|" + "---|" * (len(report["dimensions"]) + 3),
    ]
    for row in report["combinations"]:
        cells = [_cell(row["dimensions"][d]) for d in report["dimensions"]]
        lines.append(
            f"| {row['temperature']} | {row['token_setting']} | "
            + " | ".join(cells)
            + f" | {row['manual_observations']} |"
        )

    lines += ["", "## Notes"]
    lines += [f"- {note}" for note in report["notes"]]
    lines.append("")
    return "\n".join(lines)


def run_model_settings_comparison(
    evaluation_service,
    supported_parameters,
    *,
    model: str = FIXED_MODEL,
    technique: str = FIXED_TECHNIQUE,
) -> tuple[list[dict], bool]:
    """Execute the live sweep. Returns (rows, temperature_supported)."""
    config, question, answer = build_scenario()
    temperature_supported = "temperature" in set(supported_parameters)
    temps = supported_temperatures(supported_parameters)
    rows = placeholder_rows(temps)
    for row in rows:
        settings = ModelSettings(
            model=model,
            prompt_technique=technique,
            temperature=row["temperature"],
            max_tokens=row["max_tokens"],
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
                output_summary=f"overall {evaluation.overall_score}/100",
            )
        except Exception as exc:  # noqa: BLE001
            row.update(status="error", valid_json=False, output_summary=f"error: {type(exc).__name__}")
    return rows, temperature_supported


def _write(report: dict, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(report_to_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Model-setting experiment.")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--confirm", action="store_true")
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
            f"No requests made. Use --run --confirm to send up to {count} "
            "chargeable requests."
        )
        return 0

    if not args.confirm:
        print(
            f"Refusing to run: this sends up to {count} chargeable requests. "
            "Re-run with --run --confirm to proceed."
        )
        return 1

    from src.config import load_config
    from src.evaluation_service import EvaluationService
    from src.openrouter_client import OpenRouterClient
    from src.pricing_service import PricingService

    config = load_config()
    if not config.is_configured:
        print("No OpenRouter API key configured; cannot run the live sweep.")
        return 1

    pricing = PricingService()
    supported = pricing.supported_parameters(FIXED_MODEL)
    client = OpenRouterClient(config)
    try:
        service = EvaluationService(client, pricing)
        rows, temperature_supported = run_model_settings_comparison(
            service, supported
        )
    finally:
        client.close()

    report = build_report(rows, live=True, temperature_supported=temperature_supported)
    _write(report, json_path, md_path)
    print(f"Live run complete: wrote {json_path} and {md_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
