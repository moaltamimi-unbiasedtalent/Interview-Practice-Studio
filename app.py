"""Streamlit entry point for Interview Practice Studio.

Phase 1 shell: displays the product identity and configuration status.
Makes no API requests. All business logic lives in the ``src`` package;
this file only renders the interface.
"""

import streamlit as st

from src import constants
from src.config import load_config


def render_configuration_status() -> None:
    """Show a controlled message describing the API-key configuration state."""
    config = load_config()
    if config.is_configured:
        st.success(
            "OpenRouter API key detected. The app is ready for the next "
            "development phase. No API requests are made in this build."
        )
    else:
        st.warning(
            "No OpenRouter API key is configured yet. Add "
            "`OPENROUTER_API_KEY` to `.streamlit/secrets.toml` (see "
            "`.streamlit/secrets.toml.example`) or set it as an environment "
            "variable for local development. No API requests are made in "
            "this build."
        )


def main() -> None:
    """Render the Phase 1 application shell."""
    st.set_page_config(page_title=constants.APP_NAME, layout="centered")
    st.title(constants.APP_NAME)
    st.markdown(f"**{constants.APP_TAGLINE}**")
    st.info(
        "This build is being initialised. Interview practice features — "
        "question generation, realistic practice sessions and structured "
        "feedback — arrive in the next development phases."
    )
    render_configuration_status()


if __name__ == "__main__":
    main()
