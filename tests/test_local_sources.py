"""Tests for local-first acquisition: readers, lifecycle states, inventory map.

The parsing readers are data-dependent (they read the user's ``data/raw``); those
smoke tests are skipped when the real files are absent (e.g. CI). The lifecycle
and robustness logic is tested without any large files.
"""

from __future__ import annotations

import os

import pytest

from src.copilot.knowledge import local_readers as lr
from src.copilot.knowledge import manifest as km
from src.copilot.knowledge import status as kstatus


# --- Reader robustness (no data required) ------------------------------------


class TestReaderRobustness:
    def test_readers_return_empty_for_missing_paths(self, tmp_path) -> None:
        missing = str(tmp_path / "nope")
        assert lr.read_onet(missing) == []
        assert lr.read_esco(missing) == []
        assert lr.read_isco(str(tmp_path / "nope.xlsx")) == []
        assert lr.read_kldb(str(tmp_path / "nope.xlsx")) == []
        assert lr.read_oews(str(tmp_path / "nope.xlsx")) == []
        assert lr.read_ashe(str(tmp_path / "nope.xlsx")) == []


# --- Lifecycle: a local file supersedes "manual acquisition" -----------------


class TestLifecycle:
    def _entry(self, **over) -> km.SourceEntry:
        base = dict(source_id="x", title="X", publisher="P", group="occupations")
        base.update(over)
        return km.SourceEntry(**base)

    def test_local_file_found_beats_manual(self) -> None:
        e = self._entry(manual_acquisition_required=True)
        s = kstatus.SourceStatus(source_id="x", local_file_found=True, record_count=0)
        assert kstatus._lifecycle(s, e) == kstatus.LOCAL_FILE_FOUND

    def test_records_make_it_available(self) -> None:
        e = self._entry()
        s = kstatus.SourceStatus(
            source_id="x", record_count=10, normalised=True, indexed=True,
            available_for_retrieval=True, local_file_found=True,
        )
        assert kstatus._lifecycle(s, e) == kstatus.AVAILABLE

    def test_manual_without_local_file_stays_manual(self) -> None:
        e = self._entry(manual_acquisition_required=True)
        s = kstatus.SourceStatus(source_id="x", local_file_found=False, record_count=0)
        assert kstatus._lifecycle(s, e) == kstatus.MANUAL

    def test_summary_excludes_locally_present_from_outstanding(self) -> None:
        self._entry(manual_acquisition_required=True)
        present = kstatus.SourceStatus(
            source_id="a", needs_manual_acquisition=True, local_file_found=True
        )
        absent = kstatus.SourceStatus(
            source_id="b", needs_manual_acquisition=True, local_file_found=False
        )
        summ = kstatus.summary([present, absent])
        assert summ["manual_acquisition"] == 1  # only the one not present locally


# --- Real-data smoke (skipped when data/raw is absent) -----------------------

_ONET = "data/raw/db_31_0_excel"
_ESCO = "data/raw/ESCO dataset - v1.2.1 - classification - en - csv"


@pytest.mark.skipif(not os.path.isdir(_ONET), reason="local O*NET files not present")
def test_onet_reader_loads_real_occupations() -> None:
    occs = lr.read_onet(_ONET)
    assert len(occs) > 500
    first = occs[0]
    assert first.source_id == "onet"
    assert first.title and (first.tasks or first.skills)


@pytest.mark.skipif(not os.path.isdir(_ESCO), reason="local ESCO files not present")
def test_esco_reader_loads_real_occupations() -> None:
    occs = lr.read_esco(_ESCO, limit=50)
    assert occs
    assert all(o.source_id == "esco" for o in occs)
