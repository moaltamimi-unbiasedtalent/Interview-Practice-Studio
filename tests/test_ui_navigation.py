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

    def test_display_label_preserves_underlying_value(self) -> None:
        # The route value (used by routing/tests) is unchanged by grouping.
        for page in nav.PRIMARY_NAV_ITEMS:
            assert page in nav.display_label(page) or page == nav.HOME

    def test_workflow_has_five_steps(self) -> None:
        assert nav.WORKFLOW_STEPS == ["UNDERSTAND", "PREPARE", "PRACTISE", "REVIEW", "IMPROVE"]
        assert "→" in nav.WORKFLOW

    # --- Primary vs diagnostic split (secondary-nav UX fix) ------------------

    def test_primary_nav_items(self) -> None:  # (14 A–D)
        assert nav.PRIMARY_NAV_ITEMS == [
            nav.HOME, nav.CAREER, nav.INTERVIEW, nav.KNOWLEDGE_BASE,
        ]

    def test_diagnostic_nav_items(self) -> None:  # (14 E, F)
        assert nav.DIAGNOSTIC_NAV_ITEMS == [nav.RAG_INSPECTOR, nav.EVALUATION]

    def test_nav_items_is_primary_plus_diagnostics(self) -> None:
        assert nav.NAV_ITEMS == nav.PRIMARY_NAV_ITEMS + nav.DIAGNOSTIC_NAV_ITEMS

    def test_diagnostics_are_not_in_primary(self) -> None:
        # Diagnostics never clutter the primary product navigation…
        for route in nav.DIAGNOSTIC_NAV_ITEMS:
            assert route not in nav.PRIMARY_NAV_ITEMS
        # …but they remain valid, routable pages (never removed from NAV_ITEMS).
        assert nav.RAG_INSPECTOR in nav.NAV_ITEMS
        assert nav.EVALUATION in nav.NAV_ITEMS

    def test_is_diagnostic(self) -> None:
        assert nav.is_diagnostic(nav.RAG_INSPECTOR)
        assert nav.is_diagnostic(nav.EVALUATION)
        assert not nav.is_diagnostic(nav.HOME)

    def test_visible_nav_items_gate_removed(self) -> None:  # (14 L)
        # The reviewer-mode gate that used to hide diagnostics no longer exists.
        assert not hasattr(nav, "visible_nav_items")
        assert not hasattr(nav, "ADVANCED_ROUTES")


class TestSharedDesignSystem:
    def test_exports_are_callable(self) -> None:
        for name in (
            "page_header", "section_header", "card", "badge", "badges",
            "alert", "loading", "source_card", "action_button", "empty_state",
        ):
            assert callable(getattr(shared, name))
