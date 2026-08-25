"""Evaluate the injection scanner over a labelled case set.

Reports detection rate for attacks and the false-positive rate for benign
controls — so we can improve detection without breaking normal career queries.
Everything is deterministic and offline.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from src.copilot import constants
from src.copilot.security.injection import scan_text

__all__ = ["SecurityCase", "SecurityEvalReport", "evaluate_injection", "load_cases"]

_VERDICT_RANK = {
    constants.VERDICT_ALLOW: 0,
    constants.VERDICT_WARN: 1,
    constants.VERDICT_BLOCK: 2,
}


@dataclass
class SecurityCase:
    id: str
    surface: str
    kind: str  # "attack" | "control"
    text: str
    expected: str


@dataclass
class SecurityEvalReport:
    total: int = 0
    attacks: int = 0
    controls: int = 0
    detected: int = 0  # attacks flagged (warn or block)
    missed: int = 0  # attacks allowed through
    false_positives: int = 0  # controls flagged
    detection_rate: float = 0.0
    false_positive_rate: float = 0.0
    by_surface: dict = field(default_factory=dict)
    details: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def load_cases(path: str) -> list[SecurityCase]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    cases = data.get("cases", data) if isinstance(data, dict) else data
    return [
        SecurityCase(
            id=c["id"],
            surface=c.get("surface", "chat"),
            kind=c.get("kind", "attack"),
            text=c["text"],
            expected=c.get("expected", "block"),
        )
        for c in cases
    ]


def evaluate_injection(cases: list[SecurityCase]) -> SecurityEvalReport:
    """Scan every case and aggregate detection / false-positive metrics."""
    report = SecurityEvalReport(total=len(cases))
    surfaces: dict[str, dict] = {}
    for case in cases:
        scan = scan_text(case.text)
        flagged = scan.verdict != constants.VERDICT_ALLOW
        meets_expected = _VERDICT_RANK[scan.verdict] >= _VERDICT_RANK.get(case.expected, 0)

        surf = surfaces.setdefault(case.surface, {"attacks": 0, "detected": 0, "controls": 0, "false_positives": 0})
        if case.kind == "attack":
            report.attacks += 1
            surf["attacks"] += 1
            if flagged:
                report.detected += 1
                surf["detected"] += 1
            else:
                report.missed += 1
        else:
            report.controls += 1
            surf["controls"] += 1
            if flagged:
                report.false_positives += 1
                surf["false_positives"] += 1

        report.details.append(
            {
                "id": case.id,
                "surface": case.surface,
                "kind": case.kind,
                "expected": case.expected,
                "verdict": scan.verdict,
                "score": scan.score,
                "indicators": scan.indicators,
                "meets_expected": meets_expected,
            }
        )

    report.detection_rate = (report.detected / report.attacks) if report.attacks else 0.0
    report.false_positive_rate = (
        report.false_positives / report.controls
    ) if report.controls else 0.0
    report.by_surface = surfaces
    return report
