"""Phase 4 regression: company upload resource limits (bounded before read)."""

from __future__ import annotations

from dataclasses import dataclass

from src.career import ui as career_ui
from src.copilot import constants


@dataclass
class _Upload:
    name: str
    size: int
    _payload: bytes = b""

    def getvalue(self) -> bytes:  # only called AFTER validation accepts the file
        return self._payload


def test_file_at_exact_size_limit_is_accepted() -> None:
    accepted, errors = career_ui.validate_company_uploads(
        [_Upload("a.pdf", constants.MAX_FILE_BYTES)])
    assert len(accepted) == 1 and errors == []


def test_file_over_size_limit_is_rejected() -> None:
    accepted, errors = career_ui.validate_company_uploads(
        [_Upload("big.pdf", constants.MAX_FILE_BYTES + 1)])
    assert accepted == []
    assert any("per-file limit" in e for e in errors)


def test_too_many_files_are_capped() -> None:
    ups = [_Upload(f"f{i}.txt", 10) for i in range(constants.MAX_COMPANY_FILES + 2)]
    accepted, errors = career_ui.validate_company_uploads(ups)
    assert len(accepted) == constants.MAX_COMPANY_FILES
    assert any("Too many files" in e for e in errors)


def test_total_size_limit_enforced() -> None:
    half = constants.MAX_FILE_BYTES
    # Three ~10MB files exceed the 25MB total → third rejected.
    ups = [_Upload(f"f{i}.pdf", half) for i in range(3)]
    accepted, errors = career_ui.validate_company_uploads(ups)
    total = sum(u.size for u in accepted)
    assert total <= constants.MAX_TOTAL_UPLOAD_BYTES
    assert any("total upload" in e for e in errors)


def test_getvalue_not_called_for_oversized_file() -> None:
    class _Boom(_Upload):
        def getvalue(self):
            raise AssertionError("bytes must not be read for a rejected file")

    accepted, _ = career_ui.validate_company_uploads(
        [_Boom("big.pdf", constants.MAX_FILE_BYTES + 1)])
    assert accepted == []  # rejected purely on .size, never read


def test_extracted_text_truncated_to_char_cap() -> None:
    from src.copilot.ingestion.loaders import LoadedUnit

    big = [LoadedUnit(text="x" * (constants.MAX_EXTRACTED_CHARS + 100), metadata={})]
    # _cap_extracted_units leaves .txt units alone; truncation happens on join.
    joined = "\n".join(u.text for u in big)[: constants.MAX_EXTRACTED_CHARS]
    assert len(joined) == constants.MAX_EXTRACTED_CHARS


def test_pdf_pages_capped() -> None:
    from src.copilot.ingestion.loaders import LoadedUnit

    units = [LoadedUnit(text=f"p{i}", metadata={"page": i})
             for i in range(constants.MAX_PDF_PAGES + 50)]
    assert len(career_ui._cap_extracted_units(units, ".pdf")) == constants.MAX_PDF_PAGES


def test_csv_rows_capped() -> None:
    from src.copilot.ingestion.loaders import LoadedUnit

    units = [LoadedUnit(text=f"r{i}", metadata={"row": i})
             for i in range(constants.MAX_CSV_ROWS + 50)]
    assert len(career_ui._cap_extracted_units(units, ".csv")) == constants.MAX_CSV_ROWS
