"""Answer-timing guidance and conversational delivery coaching.

The goal is focused, interview-appropriate answers — **not** arbitrary time
limits. Nothing here ever stops the candidate or changes their interview-content
score; it only produces guidance and delivery feedback.

Recommended durations are derived from a target answer word count (which varies
by question type and difficulty) and a configurable professional speaking rate,
so every number is explainable rather than magic. Delivery metrics (speaking
time, pauses, longest uninterrupted segment, words per minute, response latency)
are computed from voice-activity segments supplied by the recorder/live client.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from src import constants

__all__ = [
    "AnswerTimingGuidance",
    "DeliveryMetrics",
    "recommended_seconds_from_words",
    "guidance_for_question_type",
    "guidance_for_question",
    "coaching_message_for_elapsed",
    "compute_delivery_metrics",
    "delivery_feedback",
    "aggregate_delivery",
]


# --- Timing guidance ---------------------------------------------------------


@dataclass(frozen=True)
class AnswerTimingGuidance:
    """How long a good answer to a question should take (guidance only)."""

    target_words: int
    recommended_seconds: float
    soft_warning_seconds: float
    hard_guidance_seconds: float

    @property
    def recommended_minutes(self) -> float:
        return self.recommended_seconds / 60.0


def recommended_seconds_from_words(
    target_words: int,
    *,
    wpm: int = constants.TARGET_SPEAKING_WPM,
    minimum: int = constants.MIN_RECOMMENDED_ANSWER_SECONDS,
    maximum: int = constants.MAX_RECOMMENDED_ANSWER_SECONDS,
) -> float:
    """Recommended speaking seconds for a word count, clamped to sane bounds."""
    if wpm <= 0:
        raise ValueError("wpm must be positive")
    seconds = (target_words / wpm) * 60.0
    return float(max(minimum, min(seconds, maximum)))


def guidance_for_question_type(
    question_type: str,
    *,
    difficulty: str = "moderate",
    is_deep_dive: bool = False,
) -> AnswerTimingGuidance:
    """Build timing guidance for a question type and difficulty.

    A deep-dive follow-up uses a shorter, focused target. Difficulty scales the
    target length so a harder question warrants a fuller answer.
    """
    if is_deep_dive:
        base_words = constants.DEEP_DIVE_TARGET_WORDS
    else:
        base_words = constants.ANSWER_TARGET_WORDS.get(
            question_type, constants.DEFAULT_ANSWER_TARGET_WORDS
        )
    multiplier = constants.DIFFICULTY_LENGTH_MULTIPLIER.get(difficulty, 1.0)
    target_words = max(1, round(base_words * multiplier))
    recommended = recommended_seconds_from_words(target_words)
    return AnswerTimingGuidance(
        target_words=target_words,
        recommended_seconds=recommended,
        soft_warning_seconds=recommended * constants.SOFT_WARNING_RATIO,
        hard_guidance_seconds=recommended * constants.HARD_GUIDANCE_RATIO,
    )


def guidance_for_question(question: object, *, is_deep_dive: bool = False):
    """Timing guidance derived from a question's type and difficulty.

    Works with :class:`InterviewQuestion` and :class:`BranchQuestion` (both
    expose ``question_type`` — a branch defaults to behavioural — and
    ``difficulty``). Computed locally, so the model output schema is untouched.
    """
    question_type = getattr(question, "question_type", "behavioural")
    difficulty = getattr(question, "difficulty", "moderate")
    return guidance_for_question_type(
        question_type, difficulty=difficulty, is_deep_dive=is_deep_dive
    )


def coaching_message_for_elapsed(
    elapsed_seconds: float, guidance: AnswerTimingGuidance
) -> str | None:
    """Live-timer coaching for elapsed speaking time (or None below ~100%).

    Never an examination countdown: below the recommended duration there is no
    warning; it only nudges once the answer passes the soft, then hard, marks.
    """
    if elapsed_seconds >= guidance.hard_guidance_seconds:
        return "Your answer is becoming long. Bring it to a conclusion."
    if elapsed_seconds >= guidance.soft_warning_seconds:
        return "Consider wrapping up your main point."
    return None


# --- Delivery metrics --------------------------------------------------------


@dataclass(frozen=True)
class DeliveryMetrics:
    """Measured delivery of one spoken answer (never a score input)."""

    total_speaking_seconds: float
    longest_segment_seconds: float
    words_per_minute: float | None
    word_count: int
    # None when segment-level voice-activity data was not available (e.g. a
    # single recorded blob without VAD): pauses cannot be inferred honestly.
    meaningful_pause_count: int | None = None
    average_pause_seconds: float | None = None
    response_start_latency_seconds: float | None = None

    def as_dict(self) -> dict:
        return {
            "total_speaking_seconds": self.total_speaking_seconds,
            "longest_segment_seconds": self.longest_segment_seconds,
            "words_per_minute": self.words_per_minute,
            "word_count": self.word_count,
            "meaningful_pause_count": self.meaningful_pause_count,
            "average_pause_seconds": self.average_pause_seconds,
            "response_start_latency_seconds": self.response_start_latency_seconds,
        }


def compute_delivery_metrics(
    *,
    word_count: int,
    segments: Sequence[tuple[float, float]] | None = None,
    total_duration_seconds: float | None = None,
    response_start_latency_seconds: float | None = None,
    pause_threshold: float = constants.MEANINGFUL_PAUSE_SECONDS,
) -> DeliveryMetrics:
    """Compute delivery metrics from voice-activity segments or a total duration.

    ``segments`` are (start, end) speech intervals in seconds (from live/VAD).
    When they are absent (a single recording without VAD), only duration-based
    metrics are produced and pause metrics stay ``None`` rather than guessed.
    """
    if segments:
        ordered = sorted((float(s), float(e)) for s, e in segments if e > s)
        speaking = sum(e - s for s, e in ordered)
        longest = max((e - s for s, e in ordered), default=0.0)
        pauses = [
            ordered[i][0] - ordered[i - 1][1]
            for i in range(1, len(ordered))
            if ordered[i][0] - ordered[i - 1][1] >= pause_threshold
        ]
        pause_count = len(pauses)
        avg_pause = sum(pauses) / len(pauses) if pauses else 0.0
        latency = (
            response_start_latency_seconds
            if response_start_latency_seconds is not None
            else (ordered[0][0] if ordered else None)
        )
        wpm = (word_count / (speaking / 60.0)) if speaking > 0 else None
        return DeliveryMetrics(
            total_speaking_seconds=round(speaking, 2),
            longest_segment_seconds=round(longest, 2),
            words_per_minute=round(wpm, 1) if wpm is not None else None,
            word_count=word_count,
            meaningful_pause_count=pause_count,
            average_pause_seconds=round(avg_pause, 2),
            response_start_latency_seconds=(
                round(latency, 2) if latency is not None else None
            ),
        )

    duration = float(total_duration_seconds or 0.0)
    wpm = (word_count / (duration / 60.0)) if duration > 0 else None
    return DeliveryMetrics(
        total_speaking_seconds=round(duration, 2),
        longest_segment_seconds=round(duration, 2),
        words_per_minute=round(wpm, 1) if wpm is not None else None,
        word_count=word_count,
        meaningful_pause_count=None,
        average_pause_seconds=None,
        response_start_latency_seconds=response_start_latency_seconds,
    )


# --- Coaching ----------------------------------------------------------------


def delivery_feedback(
    guidance: AnswerTimingGuidance, metrics: DeliveryMetrics
) -> list[str]:
    """Plain-language delivery notes (no medical or psychological language)."""
    notes: list[str] = []
    recommended = guidance.recommended_seconds
    speaking = metrics.total_speaking_seconds

    # Length relative to the recommended duration.
    if speaking <= 0:
        notes.append("No speaking time was detected for this answer.")
        return notes
    if speaking < recommended * 0.5:
        notes.append("Very brief — consider adding a concrete example or detail.")
    elif speaking <= recommended * 0.9:
        notes.append("Concise.")
    elif speaking <= guidance.hard_guidance_seconds:
        notes.append("Concise and appropriately paced.")
    elif speaking <= recommended * 1.5:
        notes.append("Slightly long — tighten to your main points next time.")
    else:
        notes.append("Ran long — aim to reach your conclusion sooner.")

    # Speaking rate.
    wpm = metrics.words_per_minute
    if wpm is not None:
        if wpm > 180:
            notes.append("Speaking pace is fast; slowing slightly aids clarity.")
        elif wpm < 90:
            notes.append("Speaking pace is quite measured; a little more energy helps.")

    # Pause / segmentation feedback (only when segment data is available).
    if metrics.meaningful_pause_count is not None:
        if metrics.meaningful_pause_count == 0 and speaking > 30:
            notes.append("Limited pauses — brief pauses help the listener follow.")
    if metrics.longest_segment_seconds > guidance.hard_guidance_seconds:
        notes.append(
            "One very long uninterrupted stretch — breaking it up improves clarity."
        )

    if notes and all(
        note in ("Concise.", "Concise and appropriately paced.") for note in notes
    ):
        notes.append("Healthy conversational pacing.")
    return notes


# --- Report aggregation ------------------------------------------------------


def aggregate_delivery(entries: Sequence[dict]) -> dict:
    """Aggregate per-answer delivery metrics for the final report.

    Each entry is expected to carry ``total_speaking_seconds``,
    ``recommended_seconds``, ``words_per_minute``, ``longest_segment_seconds``.
    Returns averages, counts substantially over/under target, and short
    actionable coaching. Returns an empty summary when there are no spoken
    answers (typed answers contribute nothing here).
    """
    spoken = [e for e in entries if e.get("total_speaking_seconds")]
    if not spoken:
        return {"spoken_answers": 0}

    def _avg(key: str) -> float | None:
        values = [e[key] for e in spoken if e.get(key) is not None]
        return round(sum(values) / len(values), 1) if values else None

    over = sum(
        1
        for e in spoken
        if e.get("recommended_seconds")
        and e["total_speaking_seconds"]
        > e["recommended_seconds"] * constants.OVER_TARGET_RATIO
    )
    under = sum(
        1
        for e in spoken
        if e.get("recommended_seconds")
        and e["total_speaking_seconds"]
        < e["recommended_seconds"] * constants.UNDER_TARGET_RATIO
    )
    longest = max((e.get("longest_segment_seconds") or 0.0) for e in spoken)

    coaching: list[str] = []
    if over > under and over:
        coaching.append(
            "Several answers ran over the recommended length — practise landing "
            "your main point sooner."
        )
    elif under > over and under:
        coaching.append(
            "Several answers were quite short — add a concrete example to round "
            "them out."
        )
    else:
        coaching.append("Answer lengths were generally well matched to each question.")

    return {
        "spoken_answers": len(spoken),
        "average_answer_seconds": _avg("total_speaking_seconds"),
        "average_recommended_seconds": _avg("recommended_seconds"),
        "average_words_per_minute": _avg("words_per_minute"),
        "longest_uninterrupted_seconds": round(longest, 1),
        "answers_substantially_over_target": over,
        "answers_substantially_under_target": under,
        "coaching": coaching,
    }
