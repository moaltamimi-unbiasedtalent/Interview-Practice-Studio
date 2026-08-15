"""Authentication abstraction over Streamlit's native OIDC support.

The rest of the app never touches ``st.user`` directly — it calls
:func:`current_user` / :func:`resolve_user`, so identity handling lives in one
place and is easy to test. Streamlit's built-in OIDC (``st.login``/``st.logout``/
``st.user``) provides the provider integrations (Google, Microsoft, …); the
provider client ids/secrets live in ``.streamlit/secrets.toml`` under ``[auth]``
and are never stored by this app.

Development mode (``APP_AUTH_REQUIRED=false``) allows anonymous local use;
production (``APP_AUTH_REQUIRED=true``) requires login.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AuthUser",
    "ANONYMOUS_USER",
    "resolve_user",
    "read_streamlit_user",
    "current_user",
    "login",
    "logout",
]


@dataclass(frozen=True)
class AuthUser:
    """A resolved identity. ``subject``+``provider`` are the stable account key."""

    subject: str
    provider: str
    display_name: str | None = None
    email: str | None = None
    is_anonymous: bool = False


# The single local-development identity used when auth is not required.
ANONYMOUS_USER = AuthUser(
    subject="local-dev",
    provider="dev",
    display_name="Local developer",
    is_anonymous=True,
)


def resolve_user(
    *, auth_required: bool, user_claims: dict | None
) -> AuthUser | None:
    """Resolve the current identity from OIDC claims and the auth policy.

    * A logged-in user (``is_logged_in``) becomes an :class:`AuthUser`.
    * Otherwise, when auth is required, returns ``None`` (must log in).
    * Otherwise (local dev), returns the anonymous developer identity.

    Pure and side-effect free so it can be unit-tested without Streamlit.
    """
    if user_claims and user_claims.get("is_logged_in"):
        subject = str(
            user_claims.get("sub") or user_claims.get("email") or "unknown"
        )
        provider = str(
            user_claims.get("iss") or user_claims.get("provider") or "oidc"
        )
        return AuthUser(
            subject=subject,
            provider=provider,
            display_name=user_claims.get("name"),
            email=user_claims.get("email"),
        )
    if auth_required:
        return None
    return ANONYMOUS_USER


def read_streamlit_user() -> dict | None:
    """Read OIDC claims from ``st.user`` — the ONLY place ``st.user`` is used.

    Returns a plain dict (or None) so callers depend on data, not Streamlit.
    """
    try:
        import streamlit as st

        user = st.user
        if user is None:
            return None
        return {
            "is_logged_in": bool(getattr(user, "is_logged_in", False)),
            "sub": getattr(user, "sub", None),
            "email": getattr(user, "email", None),
            "name": getattr(user, "name", None),
            "iss": getattr(user, "iss", None),
        }
    except Exception:
        # No auth configured / not running in Streamlit: treat as no claims.
        return None


def current_user(config) -> AuthUser | None:
    """Resolve the current identity using app config and Streamlit claims."""
    return resolve_user(
        auth_required=getattr(config, "auth_required", False),
        user_claims=read_streamlit_user(),
    )


def login(provider: str | None = None) -> None:  # pragma: no cover - thin wrapper
    import streamlit as st

    st.login(provider) if provider else st.login()


def logout() -> None:  # pragma: no cover - thin wrapper
    import streamlit as st

    st.logout()
