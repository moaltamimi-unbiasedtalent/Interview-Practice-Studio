"""Repository tests — persistence round-trips and strict user isolation.

Uses an in-memory SQLite database; no external services. The most important
guarantee: one user can never read, export or delete another user's data.
"""

import pytest

from src.persistence import init_db, make_engine, make_session_factory
from src.repository import InterviewRepository


@pytest.fixture()
def repo() -> InterviewRepository:
    engine = make_engine("sqlite://")
    init_db(engine)
    return InterviewRepository(make_session_factory(engine))


def _payload(role: str = "Registered Nurse", score: int = 72) -> dict:
    return {
        "configuration": {"target_role": role},
        "mode": "Record",
        "status": "completed",
        "questions": [
            {
                "position": 0,
                "canonical_question": "Tell me about a challenge.",
                "question_type": "behavioural",
                "difficulty": "moderate",
                "timing_guidance": {"recommended_seconds": 100},
                "answer": {
                    "text": "I handled a migration.",
                    "evaluation": {
                        "overall_score": score,
                        "improvement_areas": ["add metrics"],
                    },
                    "timing_metrics": {"total_speaking_seconds": 90},
                    "visual_metrics": {"screen_facing_percentage": 88, "confident": True},
                },
            },
            {
                "position": 1,
                "canonical_question": "Why that approach?",
                "question_type": "behavioural",
                "difficulty": "moderate",
                "is_deep_dive": True,
                "parent_position": 0,
                "answer": {"text": "Because...", "evaluation": {"overall_score": 70}},
            },
        ],
        "report": {
            "report": {"overall_readiness_score": 68},
            "usage": {"total_tokens": 300},
            "cost_usd": 0.002,
        },
    }


class TestUsers:
    def test_get_or_create_is_idempotent(self, repo) -> None:
        a = repo.get_or_create_user(subject="s1", provider="google")
        b = repo.get_or_create_user(subject="s1", provider="google")
        assert a == b

    def test_same_subject_different_provider_is_distinct(self, repo) -> None:
        g = repo.get_or_create_user(subject="s1", provider="google")
        m = repo.get_or_create_user(subject="s1", provider="microsoft")
        assert g != m


class TestRoundTrip:
    def test_save_and_get(self, repo) -> None:
        uid = repo.get_or_create_user(subject="s", provider="google")
        iid = repo.save_interview(uid, _payload())
        detail = repo.get_interview(uid, iid)
        assert detail is not None
        assert detail["configuration"]["target_role"] == "Registered Nurse"
        assert len(detail["questions"]) == 2
        assert detail["questions"][1]["is_deep_dive"] is True
        assert detail["questions"][1]["parent_position"] == 0
        assert detail["report"]["report"]["overall_readiness_score"] == 68

    def test_list_newest_first(self, repo) -> None:
        uid = repo.get_or_create_user(subject="s", provider="google")
        first = repo.save_interview(uid, _payload(role="A"))
        second = repo.save_interview(uid, _payload(role="B"))
        ids = [row["id"] for row in repo.list_interviews(uid)]
        assert ids[0] == second and first in ids


class TestUserIsolation:
    def test_one_user_cannot_read_anothers_interview(self, repo) -> None:
        alice = repo.get_or_create_user(subject="alice", provider="google")
        bob = repo.get_or_create_user(subject="bob", provider="google")
        iid = repo.save_interview(alice, _payload())
        assert repo.get_interview(bob, iid) is None  # not visible
        assert repo.list_interviews(bob) == []

    def test_one_user_cannot_delete_anothers_interview(self, repo) -> None:
        alice = repo.get_or_create_user(subject="alice", provider="google")
        bob = repo.get_or_create_user(subject="bob", provider="google")
        iid = repo.save_interview(alice, _payload())
        assert repo.delete_interview(bob, iid) is False  # no-op
        assert repo.get_interview(alice, iid) is not None  # still there

    def test_export_is_scoped_to_the_user(self, repo) -> None:
        alice = repo.get_or_create_user(subject="alice", provider="google")
        bob = repo.get_or_create_user(subject="bob", provider="google")
        repo.save_interview(alice, _payload(role="Alice role"))
        export = repo.export_user_data(bob)
        assert export["interviews"] == []


class TestDeletion:
    def test_delete_own_interview(self, repo) -> None:
        uid = repo.get_or_create_user(subject="s", provider="google")
        iid = repo.save_interview(uid, _payload())
        assert repo.delete_interview(uid, iid) is True
        assert repo.get_interview(uid, iid) is None

    def test_delete_all_for_user_only(self, repo) -> None:
        alice = repo.get_or_create_user(subject="alice", provider="google")
        bob = repo.get_or_create_user(subject="bob", provider="google")
        repo.save_interview(alice, _payload())
        repo.save_interview(alice, _payload())
        repo.save_interview(bob, _payload())
        removed = repo.delete_all_for_user(alice)
        assert removed == 2
        assert repo.list_interviews(alice) == []
        assert len(repo.list_interviews(bob)) == 1  # untouched


class TestExportAndDashboard:
    def test_export_contains_user_and_interviews(self, repo) -> None:
        uid = repo.get_or_create_user(
            subject="s", provider="google", display_name="Sam", email="s@x.com"
        )
        repo.save_interview(uid, _payload())
        export = repo.export_user_data(uid)
        assert export["user"]["display_name"] == "Sam"
        assert export["user"]["email"] == "s@x.com"
        assert len(export["interviews"]) == 1

    def test_dashboard_metrics(self, repo) -> None:
        uid = repo.get_or_create_user(subject="s", provider="google")
        repo.save_interview(uid, _payload(score=80))
        repo.save_interview(uid, _payload(score=60))
        metrics = repo.dashboard_metrics(uid)
        assert metrics["interviews_completed"] == 2
        assert metrics["average_practice_score"] == 70.0  # (80+70+60+70)/4
        assert metrics["most_common_improvement_area"] == "add metrics"
        assert metrics["average_answer_seconds"] == 90.0
        assert len(metrics["recent_interviews"]) == 2
