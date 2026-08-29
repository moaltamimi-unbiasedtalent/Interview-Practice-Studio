"""OPT-5: the synthetic demo knowledge pack is clearly non-production."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "load_sample_knowledge",
    Path(__file__).resolve().parent.parent / "scripts" / "load_sample_knowledge.py",
)
sample = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sample)


def test_in_memory_dry_run_returns_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(sample, "DEMO_DIR", tmp_path / "demo")
    assert sample.main(["--in-memory"]) == 0


def test_demo_chunks_are_synthetic_and_not_production_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(sample, "DEMO_DIR", tmp_path / "demo")
    paths = sample._write_demo_files()
    assert paths
    from src.copilot.ingestion import indexer

    chunks, _ = indexer.ingest_paths(paths)
    for chunk in chunks:
        chunk.metadata["data_origin"] = "synthetic_fixture"
        chunk.metadata["production_ready"] = False
    assert chunks
    assert all(c.metadata["data_origin"] == "synthetic_fixture" for c in chunks)
    assert all(c.metadata["production_ready"] is False for c in chunks)


def test_demo_content_labels_itself_synthetic(monkeypatch, tmp_path):
    monkeypatch.setattr(sample, "DEMO_DIR", tmp_path / "demo")
    for path in sample._write_demo_files():
        assert "synthetic" in Path(path).read_text(encoding="utf-8").lower()
