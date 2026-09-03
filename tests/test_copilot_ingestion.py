"""Ingestion tests: loaders, cleaning, chunking, dedup, indexer.

Uses small fixtures created in a temp dir; a real PDF is generated with fpdf2.
No network and no embeddings.
"""

import os

import pytest

from src.copilot.ingestion import indexer, loaders
from src.copilot.ingestion.chunking import chunk_units, source_id_for_text
from src.copilot.ingestion.cleaners import clean_text
from src.copilot.ingestion.loaders import LoaderError, load_document


def _write(path, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _write_pdf(path: str, text: str) -> str:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    pdf.output(path)
    return path


# --- Cleaning ----------------------------------------------------------------


class TestCleaning:
    def test_collapses_blank_lines_and_trailing_space(self) -> None:
        cleaned = clean_text("# Heading   \n\n\n\nBody text.   \n")
        assert cleaned == "# Heading\n\nBody text."

    def test_preserves_headings_and_punctuation(self) -> None:
        text = "## Skills\n- Triage: fast, accurate."
        assert clean_text(text) == text


# --- Loaders -----------------------------------------------------------------


class TestLoaders:
    def test_text_ingestion(self, tmp_path) -> None:
        path = _write(str(tmp_path / "note.txt"), "A career note about nursing.")
        units = load_document(path)
        assert len(units) == 1
        assert "nursing" in units[0].text
        assert units[0].metadata["filename"] == "note.txt"

    def test_markdown_sections(self, tmp_path) -> None:
        md = "# Intro\nOverview.\n\n## Skills\nTriage and communication."
        path = _write(str(tmp_path / "guide.md"), md)
        units = load_document(path)
        sections = [u.metadata.get("section") for u in units]
        assert "Skills" in sections

    def test_csv_rows_become_documents(self, tmp_path) -> None:
        csv = "title,description,occupation\nRN,Provides care,Nurse\nEMT,Responds,Paramedic\n"
        path = _write(str(tmp_path / "roles.csv"), csv)
        units = load_document(
            path, content_columns=["title", "description"], metadata_columns=["occupation"]
        )
        assert len(units) == 2
        assert "Provides care" in units[0].text
        assert units[0].metadata["occupation"] == "Nurse"

    def test_pdf_ingestion_captures_page_and_text(self, tmp_path) -> None:
        path = _write_pdf(
            str(tmp_path / "report.pdf"), "Nurses triage patients and coordinate care."
        )
        units = load_document(path)
        assert units, "expected at least one page unit"
        assert units[0].metadata["page"] == 1
        assert "triage" in " ".join(u.text.lower() for u in units)

    def test_document_type_inferred_from_subfolder(self, tmp_path) -> None:
        path = _write(str(tmp_path / "labour_market" / "wef.txt"), "Jobs outlook.")
        units = load_document(path)
        assert units[0].metadata["document_type"] == "labour_market"

    def test_unsupported_type_raises(self, tmp_path) -> None:
        path = _write(str(tmp_path / "x.docx"), "nope")
        with pytest.raises(LoaderError):
            load_document(path)


# --- Chunking ----------------------------------------------------------------


class TestChunking:
    def test_chunk_boundaries_split_long_text(self, tmp_path) -> None:
        long_text = ("Sentence about careers. " * 400).strip()
        units = [loaders.LoadedUnit(text=long_text, metadata={"document_type": "skills"})]
        chunks = chunk_units(units, source_id="s1", chunk_size=200, chunk_overlap=40)
        assert len(chunks) > 1
        assert [c.position for c in chunks] == list(range(len(chunks)))
        assert all(c.metadata["document_type"] == "skills" for c in chunks)

    def test_stable_ids_are_deterministic(self) -> None:
        units = [loaders.LoadedUnit(text="Grounded career guidance.", metadata={})]
        first = chunk_units(units, source_id="s1")
        second = chunk_units(units, source_id="s1")
        assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
        # A different source id yields different chunk ids.
        other = chunk_units(units, source_id="s2")
        assert first[0].chunk_id != other[0].chunk_id

    def test_duplicate_chunks_within_document_dropped(self) -> None:
        dup = "Identical paragraph."
        units = [
            loaders.LoadedUnit(text=dup, metadata={}),
            loaders.LoadedUnit(text=dup, metadata={}),
        ]
        chunks = chunk_units(units, source_id="s1")
        assert len(chunks) == 1  # the second identical chunk is deduped

    def test_source_id_for_text_is_stable(self) -> None:
        assert source_id_for_text("abc") == source_id_for_text("abc")


# --- Indexer -----------------------------------------------------------------


class TestIndexer:
    def test_ingest_reports_statistics(self, tmp_path) -> None:
        _write(str(tmp_path / "labour_market" / "a.txt"), "Labour market outlook.")
        _write(str(tmp_path / "skills" / "b.md"), "# Skills\nTriage.")
        chunks, report = indexer.ingest_directory(str(tmp_path))
        assert report.documents == 2
        assert report.chunks >= 2
        assert set(report.by_type) == {"labour_market", "skills"}
        assert len(report.filenames) == 2

    def test_duplicate_file_is_ingested_once(self, tmp_path) -> None:
        path = _write(str(tmp_path / "a.txt"), "Same content.")
        _chunks, report = indexer.ingest_paths([path, path])
        assert report.documents == 1
        assert report.skipped_duplicate_files == 1

    def test_malformed_pdf_is_handled(self, tmp_path) -> None:
        path = _write(str(tmp_path / "broken.pdf"), "%PDF-1.4 this is not valid")
        chunks, report = indexer.ingest_paths([path])
        assert report.chunks == 0
        # Either recorded as an error or as a zero-chunk document — never a crash.
        assert report.errors or report.documents >= 0

    def test_empty_document_produces_no_chunks(self, tmp_path) -> None:
        path = _write(str(tmp_path / "empty.txt"), "   \n\n")
        chunks, report = indexer.ingest_paths([path])
        assert report.chunks == 0
        assert not report.errors  # empty is not an error

    def test_write_and_load_manifest_roundtrip(self, tmp_path) -> None:
        _write(str(tmp_path / "a.txt"), "Career guidance content.")
        chunks, report = indexer.ingest_directory(str(tmp_path))
        chunks_path = str(tmp_path / "processed" / "chunks.jsonl")
        manifest_path = str(tmp_path / "processed" / "manifest.json")
        indexer.write_processed(
            chunks, report, chunks_path=chunks_path, manifest_path=manifest_path
        )
        loaded = indexer.load_manifest(manifest_path)
        assert loaded is not None
        assert loaded["documents"] == report.documents
        assert os.path.isfile(chunks_path)
