"""Tests for answer-timing guidance and delivery coaching.

Timing is guidance only — these assert varied per-type durations, correct metric
maths, plain-language coaching, and that nothing here produces a score.
"""

from types import SimpleNamespace

import pytest

from src import constants, timing


# --- Recommended duration ----------------------------------------------------


class TestRecommendedDuration:
    def test_duration_from_words_uses_speaking_rate(self) -> None:
        # 130 words at 130 wpm == 60 seconds.
        assert timing.recommended_seconds_from_words(130, wpm=130) == 60.0

    def test_duration_is_clamped_to_minimum(self) -> None:
        assert (
            timing.recommended_seconds_from_words(5)
            == constants.MIN_RECOMMENDED_ANSWER_SECONDS
        )

    def test_duration_is_clamped_to_maximum(self) -> None:
        assert (
            timing.recommended_seconds_from_words(100_000)
            == constants.MAX_RECOMMENDED_ANSWER_SECONDS
        )

    def test_zero_wpm_rejected(self) -> None:
        with pytest.raises(ValueError):
            timing.recommended_seconds_from_words(100, wpm=0)


# --- Per-question-type guidance ----------------------------------------------


class TestGuidanceByType:
    def test_types_differ(self) -> None:
        screening = timing.guidance_for_question_type("screening")
        case_study = timing.guidance_for_question_type("case_study")
        # A screening reply should be shorter than a case-study answer.
        assert screening.recommended_seconds < case_study.recommended_seconds

    def test_not_every_question_is_120_seconds(self) -> None:
        seconds = {
            timing.guidance_for_question_type(t).recommended_seconds
            for t in constants.ANSWER_TARGET_WORDS
        }
        assert len(seconds) > 1  # genuinely varied

    def test_difficulty_scales_length(self) -> None:
        easy = timing.guidance_for_question_type("technical", difficulty="easy")
        hard = timing.guidance_for_question_type("technical", difficulty="hard")
        assert hard.target_words > easy.target_words

    def test_deep_dive_is_focused(self) -> None:
        guidance = timing.guidance_for_question_type(
            "behavioural", is_deep_dive=True
        )
        assert guidance.target_words == constants.DEEP_DIVE_TARGET_WORDS

    def test_soft_and_hard_thresholds(self) -> None:
        g = timing.guidance_for_question_type("behavioural")
        assert g.soft_warning_seconds == pytest.approx(g.recommended_seconds)
        assert g.hard_guidance_seconds > g.soft_warning_seconds

    def test_guidance_for_question_reads_attributes(self) -> None:
        question = SimpleNamespace(question_type="technical", difficulty="hard")
        g = timing.guidance_for_question(question)
        assert g.target_words == timing.guidance_for_question_type(
            "technical", difficulty="hard"
        ).target_words


# --- Live-timer coaching -----------------------------------------------------


class TestLiveCoaching:
    def test_no_warning_below_recommended(self) -> None:
        g = timing.guidance_for_question_type("behavioural")
        assert timing.coaching_message_for_elapsed(g.recommended_seconds * 0.85, g) is None

    def test_soft_warning_around_100_percent(self) -> None:
        g = timing.guidance_for_question_type("behavioural")
        message = timing.coaching_message_for_elapsed(g.soft_warning_seconds + 1, g)
        assert message == "Consider wrapping up your main point."

    def test_hard_warning_past_120_percent(self) -> None:
        g = timing.guidance_for_question_type("behavioural")
        message = timing.coaching_message_for_elapsed(g.hard_guidance_seconds + 1, g)
        assert "conclusion" in message


# --- Delivery metrics --------------------------------------------------------


class TestDeliveryMetrics:
    def test_wpm_from_segments(self) -> None:
        # 30 words over two 30 s segments == 60 s speaking == 30 wpm.
        metrics = timing.compute_delivery_metrics(
            word_count=30, segments=[(0.0, 30.0), (32.0, 62.0)]
        )
        assert metrics.total_speaking_seconds == 60.0
        assert metrics.words_per_minute == 30.0

    def test_pause_segmentation_counts_only_meaningful_gaps(self) -> None:
        # Gaps of 0.5 s (ignored) and 2.0 s (counted, >= 1.2 s threshold).
        metrics = timing.compute_delivery_metrics(
            word_count=20,
            segments=[(0.0, 5.0), (5.5, 8.0), (10.0, 12.0)],
        )
        assert metrics.meaningful_pause_count == 1
        assert metrics.average_pause_seconds == 2.0

    def test_longest_uninterrupted_segment(self) -> None:
        metrics = timing.compute_delivery_metrics(
            word_count=10, segments=[(0.0, 3.0), (5.0, 20.0), (22.0, 25.0)]
        )
        assert metrics.longest_segment_seconds == 15.0

    def test_response_start_latency_from_first_segment(self) -> None:
        metrics = timing.compute_delivery_metrics(
            word_count=5, segments=[(2.5, 7.5)]
        )
        assert metrics.response_start_latency_seconds == 2.5

    def test_duration_fallback_without_segments(self) -> None:
        # Recorded blob (no VAD): duration-based only; pauses unknown, not guessed.
        metrics = timing.compute_delivery_metrics(
            word_count=100, total_duration_seconds=60.0
        )
        assert metrics.total_speaking_seconds == 60.0
        assert metrics.words_per_minute == 100.0
        assert metrics.meaningful_pause_count is None

    def test_silence_yields_zero_and_no_wpm(self) -> None:
        metrics = timing.compute_delivery_metrics(
            word_count=0, total_duration_seconds=0.0
        )
        assert metrics.total_speaking_seconds == 0.0
        assert metrics.words_per_minute is None


# --- Coaching feedback -------------------------------------------------------


class TestDeliveryFeedback:
    def test_long_answer_is_flagged(self) -> None:
        g = timing.guidance_for_question_type("screening")  # short recommended
        metrics = timing.compute_delivery_metrics(
            word_count=600, total_duration_seconds=g.recommended_seconds * 2
        )
        notes = timing.delivery_feedback(g, metrics)
        assert any("long" in n.lower() for n in notes)

    def test_short_answer_is_flagged(self) -> None:
        g = timing.guidance_for_question_type("case_study")  # long recommended
        metrics = timing.compute_delivery_metrics(
            word_count=5, total_duration_seconds=g.recommended_seconds * 0.2
        )
        notes = timing.delivery_feedback(g, metrics)
        assert any("brief" in n.lower() for n in notes)

    def test_silence_feedback(self) -> None:
        g = timing.guidance_for_question_type("behavioural")
        metrics = timing.compute_delivery_metrics(
            word_count=0, total_duration_seconds=0.0
        )
        notes = timing.delivery_feedback(g, metrics)
        assert notes and "No speaking time" in notes[0]

    def test_feedback_is_plain_language_no_scores(self) -> None:
        g = timing.guidance_for_question_type("behavioural")
        metrics = timing.compute_delivery_metrics(
            word_count=200, segments=[(0.5, 90.0)]
        )
        notes = timing.delivery_feedback(g, metrics)
        assert all(isinstance(n, str) for n in notes)
        # Delivery coaching never emits a numeric score.
        blob = " ".join(notes).lower()
        assert "/100" not in blob and "score" not in blob


# --- Aggregation for the report ----------------------------------------------


class TestAggregation:
    def test_empty_when_no_spoken_answers(self) -> None:
        # Typed-only session: no fabricated speech metrics.
        assert timing.aggregate_delivery([])["spoken_answers"] == 0
        assert timing.aggregate_delivery([{"word_count": 10}])["spoken_answers"] == 0

    def test_aggregates_spoken_answers(self) -> None:
        entries = [
            {
                "total_speaking_seconds": 200.0,
                "recommended_seconds": 100.0,
                "words_per_minute": 150.0,
                "longest_segment_seconds": 120.0,
            },
            {
                "total_speaking_seconds": 90.0,
                "recommended_seconds": 100.0,
                "words_per_minute": 130.0,
                "longest_segment_seconds": 80.0,
            },
        ]
        summary = timing.aggregate_delivery(entries)
        assert summary["spoken_answers"] == 2
        assert summary["average_answer_seconds"] == 145.0
        assert summary["answers_substantially_over_target"] == 1  # 200 > 100*1.25
        assert summary["longest_uninterrupted_seconds"] == 120.0
        assert summary["coaching"]
