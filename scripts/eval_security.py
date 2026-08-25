"""Run the prompt-injection evaluation set and write a results artifact.

Offline and deterministic. Writes data/eval/security_results.json and prints a
summary (detection rate + false positives per surface).

Usage:
  python scripts/eval_security.py
  python scripts/eval_security.py --cases data/eval/injection_cases.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.evaluation.security_eval import evaluate_injection, load_cases  # noqa: E402

_DEFAULT_CASES = "data/eval/injection_cases.json"
_DEFAULT_OUT = "data/eval/security_results.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate prompt-injection detection.")
    parser.add_argument("--cases", default=_DEFAULT_CASES)
    parser.add_argument("--out", default=_DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not Path(args.cases).is_file():
        print(f"No cases file at {args.cases}.")
        return 1

    cases = load_cases(args.cases)
    report = evaluate_injection(cases)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report.as_dict(), handle, indent=2)

    print(f"\nPrompt-injection evaluation over {report.total} case(s)")
    print(f"  attacks detected : {report.detected}/{report.attacks} "
          f"(detection rate {report.detection_rate:.1%})")
    print(f"  false positives  : {report.false_positives}/{report.controls} "
          f"(FP rate {report.false_positive_rate:.1%})")
    print("  by surface:")
    for surface, stats in sorted(report.by_surface.items()):
        print(f"    {surface:<20} attacks {stats['detected']}/{stats['attacks']} "
              f"detected, FP {stats['false_positives']}/{stats['controls']}")
    print(f"\nWrote {args.out}.")
    print("Note: deterministic detection is best effort — not a guarantee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
