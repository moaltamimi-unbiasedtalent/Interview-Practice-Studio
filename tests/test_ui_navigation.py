"""OS-5 tests: grouped product navigation + shared design-system exports."""

from src.ui import navigation as nav
from src.ui import shared


class TestNavigation:
    def test_nav_items_are_the_six_routes(self) -> None:
        assert nav.NAV_ITEMS == [
            nav.HOME, nav.CAREER, nav.INTERVIEW,
            nav.KNOWLEDGE_BASE, nav.RAG_INSPECTOR, nav.EVALUATION,
        ]

    def test_display_labels_convey_grouping(self) -> None:
        assert nav.display_label(nav.CAREER).startswith("Prepare")
        assert nav.display_label(nav.INTERVIEW).startswith("Practise")
        assert nav.display_label(nav.KNOWLEDGE_BASE).startswith("Resources")
        assert nav.display_label(nav.RAG_INSPECTOR).startswith("Advanced")
        assert nav.display_label(nav.EVALUATION).startswith("Advanced")

    def test_display_label_preserves_underlying_value(self) -> None:
        # The route value (used by routing/tests) is unchanged by grouping.
        for page in nav.NAV_ITEMS:
            assert page in nav.display_label(page) or page == nav.HOME

    def test_workflow_has_five_steps(self) -> None:
        assert nav.WORKFLOW_STEPS == ["UNDERSTAND", "PREPARE", "PRACTISE", "REVIEW", "IMPROVE"]
        assert "→" in nav.WORKFLOW

    def test_reviewer_mode_shows_all_routes(self) -> None:
        assert nav.visible_nav_items(reviewer_mode=True) == nav.NAV_ITEMS

    def test_default_hides_advanced_routes(self) -> None:
        visible = nav.visible_nav_items(reviewer_mode=False)
        assert nav.RAG_INSPECTOR not in visible
        assert nav.EVALUATION not in visible
        # Candidate journey pages remain.
        for page in (nav.HOME, nav.CAREER, nav.INTERVIEW, nav.KNOWLEDGE_BASE):
            assert page in visible


class TestSharedDesignSystem:
    def test_exports_are_callable(self) -> None:
        for name in (
            "page_header", "section_header", "card", "badge", "badges",
            "alert", "loading", "source_card", "action_button", "empty_state",
        ):
            assert callable(getattr(shared, name))
