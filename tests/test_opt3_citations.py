"""OPT-3A: invalid citation markers are removed from the user-visible answer."""

from __future__ import annotations

from src.copilot.security import guard_output


class TestCitationSanitisation:
    def test_valid_markers_preserved(self) -> None:
        r = guard_output("AI demand is rising [1] and pay grew [2].",
                         allowed_markers={"[1]", "[2]"})
        assert r.safe_answer == "AI demand is rising [1] and pay grew [2]."
        assert not r.invalid_citations

    def test_invalid_marker_removed(self) -> None:
        r = guard_output("Grounded claim [1]. Unsupported claim [7].",
                         allowed_markers={"[1]"})
        assert "[7]" not in r.safe_answer
        assert "[1]" in r.safe_answer
        assert r.invalid_citations == ["[7]"]
        assert any("Removed invalid citation" in f for f in r.findings)

    def test_mixed_valid_and_invalid(self) -> None:
        r = guard_output("A [1] B [2] C [9] D [1].", allowed_markers={"[1]", "[2]"})
        assert "[9]" not in r.safe_answer
        assert r.safe_answer.count("[1]") == 2 and "[2]" in r.safe_answer

    def test_no_evidence_all_markers_removed(self) -> None:
        r = guard_output("Claim [1] and [2].", allowed_markers=set())
        assert "[1]" not in r.safe_answer and "[2]" not in r.safe_answer
        assert set(r.invalid_citations) == {"[1]", "[2]"}

    def test_punctuation_tidied_after_removal(self) -> None:
        r = guard_output("The role earns well [5] .", allowed_markers=set())
        assert "[5]" not in r.safe_answer
        assert "  " not in r.safe_answer  # no double spaces left

    def test_secret_redaction_still_works(self) -> None:
        r = guard_output("key sk-or-abcdefghijklmnop and cite [3]", allowed_markers=set())
        assert "[REDACTED]" in r.safe_answer
        assert "[3]" not in r.safe_answer

    def test_markers_untouched_when_allowed_is_none(self) -> None:
        # allowed_markers=None means "do not validate citations" (back-compat).
        r = guard_output("Answer [1].", allowed_markers=None)
        assert r.safe_answer == "Answer [1]."
        assert not r.invalid_citations
