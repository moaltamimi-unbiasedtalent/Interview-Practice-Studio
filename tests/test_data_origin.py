"""CI-PH2 tests: real official data is never confused with synthetic fixtures."""

from __future__ import annotations

import argparse

import pytest

from src.copilot import constants
from src.copilot.knowledge import manifest as km
from src.copilot.knowledge import origins as korigins
from src.copilot.knowledge import status as kstatus
from src.copilot.knowledge.loader_cli import add_source_args, resolve_source


# --- Origins ledger ----------------------------------------------------------


class TestOriginsLedger:
    def test_record_and_load_roundtrip(self, tmp_path) -> None:
        p = str(tmp_path / "o.json")
        korigins.record_origins({"onet": constants.ORIGIN_OFFICIAL_LOCAL,
                                 "ecf": constants.ORIGIN_SYNTHETIC_FIXTURE}, path=p)
        loaded = korigins.load_origins(p)
        assert loaded["onet"] == [constants.ORIGIN_OFFICIAL_LOCAL]
        assert loaded["ecf"] == [constants.ORIGIN_SYNTHETIC_FIXTURE]

    def test_record_merges_without_clobbering(self, tmp_path) -> None:
        p = str(tmp_path / "o.json")
        korigins.record_origins({"digcomp": constants.ORIGIN_SYNTHETIC_FIXTURE}, path=p)
        korigins.record_origins({"digcomp": constants.ORIGIN_AUTHORISED_MANUAL}, path=p)
        assert set(korigins.load_origins(p)["digcomp"]) == {
            constants.ORIGIN_SYNTHETIC_FIXTURE, constants.ORIGIN_AUTHORISED_MANUAL}

    def test_resolve_origin(self) -> None:
        assert korigins.resolve_origin(None) is None
        assert korigins.resolve_origin([constants.ORIGIN_SYNTHETIC_FIXTURE]) == constants.ORIGIN_SYNTHETIC_FIXTURE
        assert korigins.resolve_origin([constants.ORIGIN_OFFICIAL_LOCAL]) == constants.ORIGIN_OFFICIAL_LOCAL
        # A real origin plus a fixture collapses to the real one, not fixture.
        assert korigins.resolve_origin(
            [constants.ORIGIN_SYNTHETIC_FIXTURE, constants.ORIGIN_OFFICIAL_LOCAL]
        ) == constants.ORIGIN_OFFICIAL_LOCAL
        # Two distinct real origins → mixed.
        assert korigins.resolve_origin(
            [constants.ORIGIN_OFFICIAL_LOCAL, constants.ORIGIN_AUTHORISED_MANUAL]
        ) == constants.ORIGIN_MIXED

    def test_is_fixture_only(self) -> None:
        assert korigins.is_fixture_only([constants.ORIGIN_SYNTHETIC_FIXTURE])
        assert not korigins.is_fixture_only(
            [constants.ORIGIN_SYNTHETIC_FIXTURE, constants.ORIGIN_OFFICIAL_LOCAL])
        assert not korigins.is_fixture_only(None)


# --- Production readiness / origin application -------------------------------


def _entry(**over) -> km.SourceEntry:
    base = dict(source_id="x", title="X", publisher="P", group="occupations")
    base.update(over)
    return km.SourceEntry(**base)


def _status(**over) -> kstatus.SourceStatus:
    base = dict(source_id="x", record_count=10, indexed=True, available_for_retrieval=True)
    base.update(over)
    return kstatus.SourceStatus(**base)


class TestProductionReady:
    def test_fixture_never_production_ready(self) -> None:
        s = _status()
        kstatus._apply_origin(s, _entry(), [constants.ORIGIN_SYNTHETIC_FIXTURE], korigins)
        assert s.fixture_only is True
        assert s.data_origin == constants.ORIGIN_SYNTHETIC_FIXTURE
        assert s.production_ready is False

    def test_official_local_can_be_production_ready(self) -> None:
        s = _status()
        kstatus._apply_origin(s, _entry(licence="CC BY 4.0"), [constants.ORIGIN_OFFICIAL_LOCAL], korigins)
        assert s.data_origin == constants.ORIGIN_OFFICIAL_LOCAL
        assert s.fixture_only is False
        assert s.production_ready is True

    def test_licence_review_blocks_production_ready(self) -> None:
        s = _status()
        kstatus._apply_origin(s, _entry(licence_review_required=True),
                              [constants.ORIGIN_OFFICIAL_LOCAL], korigins)
        assert s.data_origin == constants.ORIGIN_OFFICIAL_LOCAL  # still real
        assert s.production_ready is False  # but licence unconfirmed → blocked

    def test_missing_origin_defaults_safely(self) -> None:
        # No ledger entry and no data → origin unknown, not production-ready.
        s = _status(record_count=0, chunk_count=0, indexed=False, available_for_retrieval=False)
        kstatus._apply_origin(s, _entry(), None, korigins)
        assert s.data_origin is None
        assert s.production_ready is False
        assert s.fixture_only is False

    def test_fallback_local_file_is_real(self) -> None:
        # No ledger, but records + a real local file → treated as official_local.
        s = _status(local_file_found=True)
        kstatus._apply_origin(s, _entry(), None, korigins)
        assert s.data_origin == constants.ORIGIN_OFFICIAL_LOCAL
        assert s.production_ready is True

    def test_fallback_records_without_local_file_is_fixture(self) -> None:
        # No ledger, records but NO local file → assumed synthetic fixture (safe).
        s = _status(local_file_found=False)
        kstatus._apply_origin(s, _entry(), None, korigins)
        assert s.data_origin == constants.ORIGIN_SYNTHETIC_FIXTURE
        assert s.fixture_only is True
        assert s.production_ready is False


# --- Status remains measurable + lifecycle compatible ------------------------


class TestStatusCompatibility:
    def test_status_has_origin_fields_and_summary_counts(self) -> None:
        statuses = kstatus.compute_status(constants.SOURCE_MANIFEST_PATH)
        assert statuses
        for s in statuses:
            assert hasattr(s, "data_origin")
            assert hasattr(s, "production_ready")
            assert hasattr(s, "fixture_only")
        summ = kstatus.summary(statuses)
        assert "production_ready" in summ and "fixture_only" in summ
        assert summ["production_ready"] <= summ["available_locally"]

    def test_lifecycle_semantics_unchanged(self) -> None:
        # AVAILABLE still requires measured records/index (prior semantics).
        for s in kstatus.compute_status(constants.SOURCE_MANIFEST_PATH):
            if s.lifecycle == kstatus.AVAILABLE:
                assert s.available_for_retrieval and (s.record_count > 0 or s.indexed)

    def test_production_ready_implies_not_fixture(self) -> None:
        for s in kstatus.compute_status(constants.SOURCE_MANIFEST_PATH):
            if s.production_ready:
                assert not s.fixture_only
                assert s.data_origin in constants.REAL_ORIGINS or s.data_origin == constants.ORIGIN_MIXED


# --- Loader CLI requires an explicit source ----------------------------------


class TestLoaderCli:
    def _args(self, **kw):
        p = argparse.ArgumentParser()
        add_source_args(p)
        return p.parse_args([] if not kw else sum(([f"--{k}", v] if v is not True else [f"--{k}"]
                                                   for k, v in kw.items()), []))

    def test_no_flag_refuses(self) -> None:
        with pytest.raises(SystemExit):
            resolve_source(self._args())

    def test_fixtures_flag_marks_synthetic(self) -> None:
        path, origin = resolve_source(self._args(fixtures=True))
        assert origin == constants.ORIGIN_SYNTHETIC_FIXTURE
        assert "knowledge_samples" in path

    def test_source_flag_marks_real(self) -> None:
        path, origin = resolve_source(self._args(source="data/real"))
        assert origin == constants.ORIGIN_OFFICIAL_LOCAL
        assert path == "data/real"
