"""Authentication-abstraction tests (no Streamlit runtime required).

resolve_user is pure, so development (anonymous) and production (login-required)
modes are covered directly.
"""

from src import auth


class TestResolveUser:
    def test_anonymous_in_dev_mode_without_login(self) -> None:
        user = auth.resolve_user(auth_required=False, user_claims=None)
        assert user is auth.ANONYMOUS_USER
        assert user.is_anonymous is True

    def test_login_required_blocks_when_not_logged_in(self) -> None:
        # Production: no session until the user logs in.
        assert auth.resolve_user(auth_required=True, user_claims=None) is None
        assert (
            auth.resolve_user(
                auth_required=True, user_claims={"is_logged_in": False}
            )
            is None
        )

    def test_logged_in_user_is_resolved(self) -> None:
        user = auth.resolve_user(
            auth_required=True,
            user_claims={
                "is_logged_in": True,
                "sub": "abc123",
                "iss": "https://accounts.google.com",
                "name": "Alex",
                "email": "alex@example.com",
            },
        )
        assert user is not None
        assert user.subject == "abc123"
        assert user.provider == "https://accounts.google.com"
        assert user.display_name == "Alex"
        assert user.email == "alex@example.com"
        assert user.is_anonymous is False

    def test_subject_falls_back_to_email(self) -> None:
        user = auth.resolve_user(
            auth_required=False,
            user_claims={"is_logged_in": True, "email": "only@example.com"},
        )
        assert user.subject == "only@example.com"

    def test_logged_in_wins_even_in_dev_mode(self) -> None:
        user = auth.resolve_user(
            auth_required=False,
            user_claims={"is_logged_in": True, "sub": "s", "iss": "microsoft"},
        )
        assert user.subject == "s" and user.is_anonymous is False
