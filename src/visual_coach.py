"""Optional Visual Engagement Coach — coaching only, never a judgement.

This module turns *aggregated, local* camera metrics (produced entirely in the
browser by MediaPipe Face Landmarker) into plain-language practice feedback. It
deliberately does **not**:

* decide whether a candidate is attentive, truthful, or suitable for a job;
* contribute to any interview-content / hiring score;
* make psychological, medical or personality judgements.

No camera frames, screenshots, face landmarks or biometric templates ever reach
Python — only the small aggregated metrics below. When landmark quality is poor,
feedback is withheld rather than invented.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src import constants

__all__ = [
    "VisualEngagementMetrics",
    "is_confident",
    "build_metrics",
    "coaching_from_metrics",
    "aggregate_visual",
]


def _clamp_percent(value: float) -> float:
    return float(max(0.0, min(100.0, value)))


@dataclass(frozen=True)
class VisualEngagementMetrics:
    """Aggregated, bounded camera-facing metrics for one answer.

    ``gaze_direction_proxy`` is exactly that — a rough directional proxy, never
    an "attention score". ``confident`` is False when landmark quality was too
    low to give useful feedback.
    """

    face_present_percentage: float
    screen_facing_percentage: float
    longest_away_interval_seconds: float
    number_of_extended_away_periods: int
    excessive_head_turn_count: int
    gaze_direction_proxy: str | None = None
    confident: bool = True

    def as_dict(self) -> dict:
        return {
            "face_present_percentage": self.face_present_percentage,
            "screen_facing_percentage": self.screen_facing_percentage,
            "longest_away_interval_seconds": self.longest_away_interval_seconds,
            "number_of_extended_away_periods": self.number_of_extended_away_periods,
            "excessive_head_turn_count": self.excessive_head_turn_count,
            "gaze_direction_proxy": self.gaze_direction_proxy,
            "confident": self.confident,
        }


def is_confident(
    *,
    face_present_percentage: float,
    landmark_confidence: float | None = None,
    multiple_faces: bool = False,
) -> bool:
    """Whether the camera signal is good enough to coach on.

    Low confidence comes from poor lighting / distance (low landmark
    confidence), the face being out of frame much of the time, or more than one
    face in view.
    """
    if multiple_faces:
        return False
    if face_present_percentage < constants.VISUAL_MIN_FACE_PRESENT_PERCENT:
        return False
    if (
        landmark_confidence is not None
        and landmark_confidence < constants.VISUAL_MIN_LANDMARK_CONFIDENCE
    ):
        return False
    return True


def build_metrics(raw: dict) -> VisualEngagementMetrics:
    """Validate/clamp browser-supplied metrics into a bounded record.

    Determines ``confident`` from face presence, landmark confidence and
    multiple-face detection. Values are clamped so a malformed payload can never
    produce out-of-range coaching numbers.
    """
    face_present = _clamp_percent(raw.get("face_present_percentage", 0.0))
    screen_facing = _clamp_percent(raw.get("screen_facing_percentage", 0.0))
    longest_away = max(0.0, float(raw.get("longest_away_interval_seconds", 0.0)))
    extended_periods = max(0, int(raw.get("number_of_extended_away_periods", 0)))
    head_turns = max(0, int(raw.get("excessive_head_turn_count", 0)))
    gaze = raw.get("gaze_direction_proxy")
    if gaze is not None and gaze not in constants.GAZE_DIRECTION_PROXY_VALUES:
        gaze = "unknown"
    confident = is_confident(
        face_present_percentage=face_present,
        landmark_confidence=raw.get("landmark_confidence"),
        multiple_faces=bool(raw.get("multiple_faces", False)),
    )
    return VisualEngagementMetrics(
        face_present_percentage=round(face_present, 1),
        screen_facing_percentage=round(screen_facing, 1),
        longest_away_interval_seconds=round(longest_away, 1),
        number_of_extended_away_periods=extended_periods,
        excessive_head_turn_count=head_turns,
        gaze_direction_proxy=gaze,
        confident=confident,
    )


def coaching_from_metrics(metrics: VisualEngagementMetrics) -> list[str]:
    """Plain-language 'Visual delivery' notes — never a judgement of attention.

    Deliberately avoids "distracted" / "not paying attention" and any medical or
    psychological framing.
    """
    if not metrics.confident:
        return [constants.VISUAL_LOW_CONFIDENCE_MESSAGE]

    notes: list[str] = []
    facing = metrics.screen_facing_percentage
    if facing >= 80:
        notes.append(
            "You stayed oriented toward the interview window for most of your answer."
        )
    elif facing >= 50:
        notes.append(
            "You were oriented toward the interview window for much of your answer, "
            "with some time looking elsewhere."
        )
    else:
        notes.append(
            "For a good deal of the answer your head and eyes were directed away "
            "from the interview window."
        )

    periods = metrics.number_of_extended_away_periods
    if periods > 0:
        longest = metrics.longest_away_interval_seconds
        plural = "period" if periods == 1 else "periods"
        notes.append(
            f"There were {periods} extended {plural} where your head/eyes were "
            f"directed elsewhere for more than "
            f"{int(constants.VISUAL_EXTENDED_AWAY_SECONDS)} seconds "
            f"(longest about {longest:.0f}s)."
        )
    if metrics.excessive_head_turn_count >= 3:
        notes.append(
            "Frequent large head turns — steadier orientation can read as more "
            "engaged on video."
        )
    return notes


def aggregate_visual(entries: Sequence[dict]) -> dict:
    """Aggregate confident per-answer visual metrics for the session report.

    Kept clearly separate from answer-content scoring. Returns an empty summary
    when there are no confident entries (no fabricated metrics).
    """
    usable = [e for e in entries if e.get("confident")]
    if not usable:
        return {"visual_answers": 0}

    facing = [e["screen_facing_percentage"] for e in usable]
    longest = max(e.get("longest_away_interval_seconds", 0.0) for e in usable)
    total_periods = sum(e.get("number_of_extended_away_periods", 0) for e in usable)

    avg_facing = round(sum(facing) / len(facing), 1)
    coaching: list[str] = []
    if avg_facing >= 80:
        coaching.append(
            "You generally kept good orientation toward the interview window."
        )
    else:
        coaching.append(
            "Practising steadier orientation toward the interview window can help "
            "you come across as engaged on video."
        )

    return {
        "visual_answers": len(usable),
        "average_screen_facing_percentage": avg_facing,
        "longest_extended_away_seconds": round(longest, 1),
        "total_extended_away_periods": total_periods,
        "coaching": coaching,
    }
