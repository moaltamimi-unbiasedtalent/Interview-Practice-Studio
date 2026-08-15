"""Tests for the optional Visual Engagement Coach (coaching only, never a score).

All camera processing is browser-local; these tests cover the Python side that
turns aggregated metrics into plain-language coaching, gates on confidence, and
aggregates for the report — plus the privacy guarantees.
"""

from src import constants, visual_coach
from src.session_manager import SessionManager


def _good_raw(**over) -> dict:
    raw = {
        "face_present_percentage": 95.0,
        "screen_facing_percentage": 88.0,
        "longest_away_interval_seconds": 2.0,
        "number_of_extended_away_periods": 0,
        "excessive_head_turn_count": 0,
        "gaze_direction_proxy": "toward_screen",
        "landmark_confidence": 0.9,
        "multiple_faces": False,
    }
    raw.update(over)
    return raw


# --- Confidence gating -------------------------------------------------------


class TestConfidence:
    def test_confident_with_good_signal(self) -> None:
        assert visual_coach.is_confident(
            face_present_percentage=95.0, landmark_confidence=0.9
        )

    def test_multiple_faces_is_not_confident(self) -> None:
        assert not visual_coach.is_confident(
            face_present_percentage=95.0, landmark_confidence=0.9, multiple_faces=True
        )

    def test_low_face_presence_is_not_confident(self) -> None:
        assert not visual_coach.is_confident(
            face_present_percentage=20.0, landmark_confidence=0.9
        )

    def test_low_landmark_confidence_is_not_confident(self) -> None:
        assert not visual_coach.is_confident(
            face_present_percentage=95.0, landmark_confidence=0.2
        )


# --- Build + clamp -----------------------------------------------------------


class TestBuildMetrics:
    def test_clamps_out_of_range_values(self) -> None:
        metrics = visual_coach.build_metrics(
            _good_raw(screen_facing_percentage=150.0, excessive_head_turn_count=-3)
        )
        assert metrics.screen_facing_percentage == 100.0
        assert metrics.excessive_head_turn_count == 0

    def test_unknown_gaze_value_normalised(self) -> None:
        metrics = visual_coach.build_metrics(_good_raw(gaze_direction_proxy="sideways"))
        assert metrics.gaze_direction_proxy == "unknown"

    def test_confident_flag_reflects_signal(self) -> None:
        assert visual_coach.build_metrics(_good_raw()).confident is True
        assert visual_coach.build_metrics(_good_raw(multiple_faces=True)).confident is False

    def test_no_frame_or_image_data_is_retained(self) -> None:
        # Even if a payload smuggled frame/image bytes, they are never stored.
        metrics = visual_coach.build_metrics(
            _good_raw(frame=b"\x00\x01", image="data:image/png;base64,AAAA")
        )
        stored = metrics.as_dict()
        assert "frame" not in stored and "image" not in stored
        assert all(not isinstance(v, (bytes, bytearray)) for v in stored.values())


# --- Coaching text -----------------------------------------------------------


class TestCoaching:
    def test_low_confidence_message(self) -> None:
        metrics = visual_coach.build_metrics(_good_raw(multiple_faces=True))
        notes = visual_coach.coaching_from_metrics(metrics)
        assert notes == [constants.VISUAL_LOW_CONFIDENCE_MESSAGE]

    def test_positive_orientation_message(self) -> None:
        notes = visual_coach.coaching_from_metrics(
            visual_coach.build_metrics(_good_raw(screen_facing_percentage=90.0))
        )
        assert any("interview window" in n for n in notes)

    def test_extended_away_is_described_neutrally(self) -> None:
        notes = visual_coach.coaching_from_metrics(
            visual_coach.build_metrics(
                _good_raw(
                    screen_facing_percentage=60.0,
                    number_of_extended_away_periods=2,
                    longest_away_interval_seconds=7.0,
                )
            )
        )
        blob = " ".join(notes).lower()
        assert "extended" in blob
        # Never judgemental / psychological framing.
        assert "distract" not in blob
        assert "paying attention" not in blob
        assert "attention_score" not in blob

    def test_coaching_never_emits_a_score(self) -> None:
        notes = visual_coach.coaching_from_metrics(
            visual_coach.build_metrics(_good_raw())
        )
        blob = " ".join(notes).lower()
        assert "/100" not in blob and "score" not in blob


# --- Aggregation -------------------------------------------------------------


class TestAggregation:
    def test_empty_without_confident_entries(self) -> None:
        assert visual_coach.aggregate_visual([])["visual_answers"] == 0
        low = [visual_coach.build_metrics(_good_raw(multiple_faces=True)).as_dict()]
        assert visual_coach.aggregate_visual(low)["visual_answers"] == 0

    def test_aggregates_confident_entries(self) -> None:
        entries = [
            visual_coach.build_metrics(_good_raw(screen_facing_percentage=90.0)).as_dict(),
            visual_coach.build_metrics(
                _good_raw(
                    screen_facing_percentage=70.0,
                    number_of_extended_away_periods=1,
                    longest_away_interval_seconds=6.0,
                )
            ).as_dict(),
        ]
        summary = visual_coach.aggregate_visual(entries)
        assert summary["visual_answers"] == 2
        assert summary["average_screen_facing_percentage"] == 80.0
        assert summary["longest_extended_away_seconds"] == 6.0
        assert summary["total_extended_away_periods"] == 1
        assert summary["coaching"]


# --- Session privacy controls ------------------------------------------------


class TestSessionControls:
    def test_disabled_by_default(self) -> None:
        manager = SessionManager({}, clock=lambda: 1.0)
        assert manager.data.visual_metrics == []  # camera off / nothing recorded

    def test_record_and_clear(self) -> None:
        manager = SessionManager({}, clock=lambda: 1.0)
        manager.record_visual_metrics(visual_coach.build_metrics(_good_raw()).as_dict())
        assert len(manager.data.visual_metrics) == 1
        manager.clear_visual_metrics()  # candidate privacy control
        assert manager.data.visual_metrics == []
