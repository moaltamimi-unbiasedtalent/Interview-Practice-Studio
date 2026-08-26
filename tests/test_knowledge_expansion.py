"""KB-2 tests: authoritative knowledge expansion (offline fixtures only).

Covers the expanded manifest, source-status lifecycle, licence flags, geographic
source precedence, new-lane routing, the new normalisers, the competency and
labour-market repositories, dedup/provenance completeness, and the KB grouping.
No network, no paid LLM calls — everything runs against committed samples.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.copilot import constants
from src.copilot.knowledge import manifest as km
from src.copilot.knowledge import status as kstatus
from src.copilot.knowledge.normalisers_ext import (
    normalise_ba_kompetenzkatalog,
    normalise_bls_ooh,
    normalise_cedefop_forecast,
    normalise_cedefop_openings,
    normalise_cedefop_shortage,
    normalise_civil_service_success_profiles,
    normalise_digcomp,
    normalise_ecf,
    normalise_nice,
    normalise_opm_qualification_standards,
)
from src.copilot.knowledge.router import (
    RetrievalLane,
    detect_country,
    route_question,
    source_priority,
)
from src.copilot.knowledge.structured_ext import (
    CompetencyRepository,
    LabourMarketRepository,
)

SAMPLES = Path("evaluations/knowledge_samples")


def _load(name: str) -> dict | list:
    with open(SAMPLES / name, encoding="utf-8") as handle:
        return json.load(handle)


# --- Manifest validation -----------------------------------------------------


class TestManifest:
    def test_expanded_source_count(self) -> None:
        entries = km.load_manifest(constants.SOURCE_MANIFEST_PATH)
        assert len(entries) >= 20  # expanded corpus

    def test_every_source_has_group_and_authority(self) -> None:
        for e in km.load_manifest(constants.SOURCE_MANIFEST_PATH):
            assert e.group, f"{e.source_id} missing group"
            assert e.group in {g for g, _ in km.GROUPS}
            assert e.authority_level in (
                constants.AUTHORITY_OFFICIAL,
                constants.AUTHORITY_PUBLIC_FRAMEWORK,
                constants.AUTHORITY_INDUSTRY,
            )

    def test_unique_source_ids(self) -> None:
        ids = [e.source_id for e in km.load_manifest(constants.SOURCE_MANIFEST_PATH)]
        assert len(ids) == len(set(ids)), "duplicate source_id in manifest"

    def test_licence_flags_never_guessed(self) -> None:
        # A source without a resolved licence must be flagged for review or manual
        # acquisition — never silently treated as redistributable.
        for e in km.load_manifest(constants.SOURCE_MANIFEST_PATH):
            if not e.licence:
                assert e.licence_review_required or e.manual_acquisition_required, (
                    f"{e.source_id} has no licence but is not flagged for review"
                )

    def test_by_group_partitions_all(self) -> None:
        entries = km.load_manifest(constants.SOURCE_MANIFEST_PATH)
        grouped = sum(len(km.by_group(entries, g)) for g, _ in km.GROUPS)
        assert grouped == len(entries)


# --- Source status / lifecycle ----------------------------------------------


class TestSourceStatus:
    def test_status_covers_every_source(self) -> None:
        entries = km.load_manifest(constants.SOURCE_MANIFEST_PATH)
        statuses = kstatus.compute_status(constants.SOURCE_MANIFEST_PATH)
        assert {s.source_id for s in statuses} == {e.source_id for e in entries}

    def test_available_requires_records_or_index(self) -> None:
        # Lifecycle AVAILABLE must be backed by measured local data, never implied.
        for s in kstatus.compute_status(constants.SOURCE_MANIFEST_PATH):
            if s.lifecycle == kstatus.AVAILABLE:
                assert s.available_for_retrieval and (s.record_count > 0 or s.indexed)

    def test_manual_source_not_marked_available_without_data(self) -> None:
        statuses = {s.source_id: s for s in kstatus.compute_status(constants.SOURCE_MANIFEST_PATH)}
        # A manual-acquisition source with zero records must not read as AVAILABLE.
        for s in statuses.values():
            if s.needs_manual_acquisition and s.record_count == 0 and not s.indexed:
                assert s.lifecycle != kstatus.AVAILABLE

    def test_summary_counts_are_consistent(self) -> None:
        statuses = kstatus.compute_status(constants.SOURCE_MANIFEST_PATH)
        summary = kstatus.summary(statuses)
        assert summary["configured"] == len(statuses)
        assert summary["available_locally"] <= summary["configured"]
        assert summary["structured_records"] >= 0

    def test_write_and_load_roundtrip(self, tmp_path) -> None:
        out = tmp_path / "source_status.json"
        written = kstatus.write_status(str(out), constants.SOURCE_MANIFEST_PATH)
        loaded = kstatus.load_status(str(out))
        assert len(loaded) == len(written)
        assert {s.source_id for s in loaded} == {s.source_id for s in written}


# --- Geographic source precedence -------------------------------------------


class TestGeoPrecedence:
    @pytest.mark.parametrize("query,expected", [
        ("What does a Data Analyst earn in Germany?", "DE"),
        ("Nurse salary in the UK", "UK"),
        ("Federal data scientist qualifications in the US", "US"),
        ("Skills demand across Europe", "EU"),
        ("What does a plumber do?", None),
    ])
    def test_detect_country(self, query, expected) -> None:
        assert detect_country(query) == expected

    def test_de_prefers_national_sources(self) -> None:
        priority = source_priority("DE")
        assert priority[0] == "kldb"
        assert priority.index("kldb") < priority.index("esco")

    def test_unknown_country_defaults_to_eu(self) -> None:
        assert source_priority(None) == source_priority("EU") == list(
            constants.COUNTRY_SOURCE_PRIORITY["EU"]
        )


# --- Routing (new lanes; existing behaviour preserved) ----------------------


class TestRouting:
    @pytest.mark.parametrize("query,lane", [
        ("What digital competencies does a project manager need?", RetrievalLane.COMPETENCY),
        ("What are cybersecurity incident response responsibilities?", RetrievalLane.CYBERSECURITY),
        ("Is there a shortage of software developers in Germany?", RetrievalLane.SHORTAGE),
        ("How many job openings are there for nurses?", RetrievalLane.OPENINGS),
        ("How do I transition from teaching into a data analyst role?", RetrievalLane.TRANSITION),
        ("What are the behaviours expected at Grade 7?", RetrievalLane.SENIORITY),
    ])
    def test_new_lanes(self, query, lane) -> None:
        assert route_question(query).lane == lane

    @pytest.mark.parametrize("query,lane", [
        ("What does a Logistics Manager do?", RetrievalLane.STRUCTURED_ROLE),
        ("What skills do cybersecurity analysts need?", RetrievalLane.STRUCTURED_ROLE),
        ("What does a Data Analyst earn in Germany?", RetrievalLane.COMPENSATION),
        ("Is demand for AI roles expected to grow?", RetrievalLane.FORECAST),
    ])
    def test_existing_lanes_unchanged(self, query, lane) -> None:
        assert route_question(query).lane == lane


# --- New normalisers ---------------------------------------------------------


class TestNormalisers:
    def test_digcomp(self) -> None:
        comps, levels = normalise_digcomp(_load("digcomp.json"))
        assert comps and levels
        assert all(c.source_id == "digcomp" and c.framework for c in comps)
        assert all(lv.competency for lv in levels)

    def test_nice(self) -> None:
        comps, links = normalise_nice(_load("nice.json"))
        assert comps and links
        assert all(oc.occupation_code for oc in links)
        assert all(c.source_id == "nice_framework" for c in comps)

    def test_ecf_and_ba(self) -> None:
        assert normalise_ecf(_load("ecf.json"))
        assert normalise_ba_kompetenzkatalog(_load("ba_kompetenzkatalog.json"))

    def test_civil_service_behaviours_have_levels(self) -> None:
        behaviours = normalise_civil_service_success_profiles(
            _load("civil_service_success_profiles.json")
        )
        assert behaviours
        # Seniority is expressed as source-defined behaviours per grade, never
        # as a fabricated "years of experience" rule.
        assert all(b.level and b.behaviour for b in behaviours)

    def test_opm_qualifications(self) -> None:
        reqs = normalise_opm_qualification_standards(_load("opm_qualification_standards.json"))
        assert reqs
        assert all(q.reference and q.requirement for q in reqs)

    def test_cedefop_labour_market(self) -> None:
        assert normalise_cedefop_forecast(_load("cedefop_forecast.json"))
        assert normalise_cedefop_openings(_load("cedefop_openings.json"))
        assert normalise_cedefop_shortage(_load("cedefop_shortage.json"))

    def test_bls_ooh_is_structured_occupation(self) -> None:
        occs = _load("bls_ooh.json")
        norm = normalise_bls_ooh(occs[0])
        assert norm.source_id == "bls_ooh"
        assert norm.title and norm.tasks


# --- Extended repositories ---------------------------------------------------


class TestRepositories:
    def test_competency_repo_roundtrip(self) -> None:
        repo = CompetencyRepository(":memory:")
        comps, levels = normalise_digcomp(_load("digcomp.json"))
        for c in comps:
            repo.add_competency(c)
        for lv in levels:
            repo.add_level(lv)
        assert repo.counts()["competencies"] == len(comps)
        by_source = repo.counts_by_source()
        assert by_source.get("digcomp", 0) == len(comps) + len(levels)
        repo.close()

    def test_behaviours_for_level(self) -> None:
        repo = CompetencyRepository(":memory:")
        for b in normalise_civil_service_success_profiles(
            _load("civil_service_success_profiles.json")
        ):
            repo.add_behaviour(b)
        rows = repo.behaviours_for_level("UK Civil Service Success Profiles", "Grade 6/7")
        assert rows
        repo.close()

    def test_labour_repo_queries(self) -> None:
        repo = LabourMarketRepository(":memory:")
        for f in normalise_cedefop_forecast(_load("cedefop_forecast.json")):
            repo.add_forecast(f)
        for s in normalise_cedefop_shortage(_load("cedefop_shortage.json")):
            repo.add_shortage(s)
        assert repo.forecast_for("Data Analyst")
        assert repo.shortages_for("Nurse")
        repo.close()


# --- Provenance completeness / dedup ----------------------------------------


class TestProvenanceAndDedup:
    def test_bls_ooh_records_carry_source(self) -> None:
        for row in _load("bls_ooh.json"):
            assert normalise_bls_ooh(row).source_id == "bls_ooh"

    def test_role_repo_idempotent_dedup(self) -> None:
        from src.copilot.knowledge.roles import RoleRepository

        repo = RoleRepository(":memory:")
        occ = normalise_bls_ooh(_load("bls_ooh.json")[0])
        repo.add_occupation(occ)
        repo.add_occupation(occ)  # re-ingest same code+source → replace, not duplicate
        assert repo.counts()["occupations"] == 1
        repo.close()

    def test_every_new_competency_has_source(self) -> None:
        comps, _ = normalise_digcomp(_load("digcomp.json"))
        assert all(c.source_id for c in comps)
