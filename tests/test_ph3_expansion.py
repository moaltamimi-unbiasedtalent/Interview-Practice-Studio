"""CI-PH3 tests: education/training/credential expansion (schema-derived fixtures)."""

from __future__ import annotations

import os

import pytest

from src.copilot.knowledge import local_readers as lr
from src.copilot.knowledge.retrieval import StructuredRetrievalCoordinator
from src.copilot.knowledge.roles import NormalisedOccupation, RoleRepository
from src.copilot.knowledge.router import RetrievalLane, route_question
from src.copilot.knowledge.structured_ext import (
    Certification,
    CredentialRepository,
    OccupationLicence,
)


# --- Role schema: new entry/outlook attributes round-trip --------------------


class TestRoleSchema:
    def test_new_fields_persist(self) -> None:
        repo = RoleRepository(":memory:")
        repo.add_occupation(NormalisedOccupation(
            occupation_code="X1", title="Accountant", source_id="bls_ooh",
            entry_education="Bachelor's degree", work_experience="None",
            on_the_job_training="Moderate-term", outlook="Faster than average",
            certifications=["CPA"], licences=["State CPA licence"], industries=["Finance"]))
        occ = repo.get_occupation("X1")
        assert occ["entry_education"] == "Bachelor's degree"
        assert occ["on_the_job_training"] == "Moderate-term"
        assert occ["outlook"] == "Faster than average"
        assert occ["certifications"] == ["CPA"]
        assert occ["licences"] == ["State CPA licence"]
        assert occ["industries"] == ["Finance"]
        repo.close()

    def test_counts_include_new_tables(self) -> None:
        repo = RoleRepository(":memory:")
        c = repo.counts()
        for t in ("occupation_attributes", "occupation_certifications",
                  "occupation_licences", "occupation_industries"):
            assert t in c
        repo.close()


# --- Credential repository ---------------------------------------------------


class TestCredentialRepository:
    def _repo(self) -> CredentialRepository:
        repo = CredentialRepository(":memory:")
        repo.add_certification(Certification(
            source_id="careeronestop", certification_id="C1", name="PMP",
            organisation="PMI", type="professional", occupation_title="Project Manager"))
        repo.add_licence(OccupationLicence(
            source_id="careeronestop", licence_id="L1", title="RN Licence",
            occupation="Registered Nurse", jurisdiction="US",
            exam_requirement="NCLEX-RN"))
        return repo

    def test_certifications_for(self) -> None:
        repo = self._repo()
        assert repo.certifications_for("project manager")
        assert repo.counts()["certifications"] == 1
        repo.close()

    def test_licences_for_jurisdiction(self) -> None:
        repo = self._repo()
        assert repo.licences_for("registered nurse", "US")
        assert not repo.licences_for("registered nurse", "DE")
        repo.close()


# --- Router: new lanes -------------------------------------------------------


class TestRouterLanes:
    @pytest.mark.parametrize("query,lane", [
        ("What degree is typical for a nurse?", RetrievalLane.EDUCATION),
        ("What training does a plumber need?", RetrievalLane.TRAINING),
        ("What certifications are relevant for a PM?", RetrievalLane.CERTIFICATION),
        ("Do I need a licence to practise as an electrician?", RetrievalLane.LICENCE),
        ("What is demand like right now for analysts?", RetrievalLane.CURRENT_VACANCY),
        ("What is the short-term outlook for retail?", RetrievalLane.SHORT_TERM_OUTLOOK),
    ])
    def test_new_lanes(self, query, lane) -> None:
        assert route_question(query).lane == lane

    @pytest.mark.parametrize("query,lane", [
        ("What does a Data Analyst earn in Germany?", RetrievalLane.COMPENSATION),
        ("What skills do cybersecurity analysts need?", RetrievalLane.STRUCTURED_ROLE),
        ("How many job openings are expected for nurses?", RetrievalLane.OPENINGS),
    ])
    def test_existing_lanes_unchanged(self, query, lane) -> None:
        assert route_question(query).lane == lane


# --- Coordinator: new lanes hit the right stores -----------------------------


def _coordinator():
    role = RoleRepository(":memory:")
    role.add_occupation(NormalisedOccupation(
        occupation_code="onet:13-2011", title="Accountant", source_id="onet",
        entry_education="Bachelor's degree", on_the_job_training="None",
        work_experience="None"))
    cred = CredentialRepository(":memory:")
    cred.add_certification(Certification(source_id="careeronestop", certification_id="C1",
                                         name="PMP", occupation_title="Project Manager"))
    cred.add_licence(OccupationLicence(source_id="careeronestop", licence_id="L1",
                                       title="RN Licence", occupation="Registered Nurse",
                                       jurisdiction="US"))
    role.add_occupation(NormalisedOccupation(
        occupation_code="onet:11-3021", title="Project Manager", source_id="onet"))
    role.add_occupation(NormalisedOccupation(
        occupation_code="onet:29-1141", title="Registered Nurse", source_id="onet"))
    return StructuredRetrievalCoordinator(role_repo=role, credential_repo=cred,
                                          manifest_entries=[])


class TestCoordinatorNewLanes:
    def test_education_from_attributes(self) -> None:
        c = _coordinator()
        out = c.retrieve(route_question("What degree is typical for an accountant?"),
                         "What degree is typical for an accountant?")
        assert any(e.evidence_type == "education" for e in out.evidence)

    def test_certification_uses_credential_repo(self) -> None:
        from unittest import mock
        c = _coordinator()
        with mock.patch.object(c.credential_repo, "certifications_for",
                               wraps=c.credential_repo.certifications_for) as spy:
            out = c.retrieve(route_question("What certifications are relevant for a project manager?"),
                             "What certifications are relevant for a project manager?")
        assert spy.called
        assert any(e.evidence_type == "certification" for e in out.evidence)

    def test_licence_uses_credential_repo(self) -> None:
        c = _coordinator()
        out = c.retrieve(route_question("Do I need a licence to work as a registered nurse in the US?"),
                         "Do I need a licence to work as a registered nurse in the US?")
        assert any(e.evidence_type == "licence" for e in out.evidence)

    def test_current_vacancy_is_honest_gap(self) -> None:
        c = _coordinator()
        out = c.retrieve(route_question("What is demand like right now for accountants?"),
                         "What is demand like right now for accountants?")
        assert out.insufficient
        assert not out.evidence


# --- Real-data reader smoke (skipped when files absent) ----------------------


@pytest.mark.skipif(not os.path.isfile("data/raw/OOH xml-compilation.xml"),
                    reason="OOH XML not present")
def test_ooh_reader_extracts_education_outlook() -> None:
    occs = lr.read_ooh()
    assert any(o.entry_education for o in occs)
    assert any(o.outlook for o in occs)


@pytest.mark.skipif(not os.path.isfile("data/raw/occupation.xlsx"),
                    reason="BLS EP workbook not present")
def test_bls_ep_characteristics_reader() -> None:
    occs = lr.read_bls_ep_characteristics()
    assert occs
    assert any(o.entry_education for o in occs)
    assert any(o.work_experience for o in occs)


# --- Labour vacancy store + new-source readers (CLSSI / Eurostat / DigComp) ---


class TestLabourVacancy:
    def test_vacancy_repo_roundtrip(self) -> None:
        from src.copilot.knowledge.structured_ext import LabourMarketRepository, LabourVacancy
        repo = LabourMarketRepository(":memory:")
        repo.add_vacancy(LabourVacancy(
            source_id="eurostat_occ_vacancy", occupation="Total", country="Belgium",
            year=2024, indicator="Job vacancy rate", unit="Percentage", value=4.27,
            experimental=True))
        rows = repo.vacancies_for(country="belgium")
        assert rows and rows[0]["value"] == 4.27 and rows[0]["experimental"] == 1
        assert "labour_vacancies" in repo.counts()
        repo.close()

    def test_current_vacancy_lane_uses_vacancy_store(self) -> None:
        from unittest import mock
        from src.copilot.knowledge.retrieval import StructuredRetrievalCoordinator
        from src.copilot.knowledge.structured_ext import LabourMarketRepository, LabourVacancy
        labour = LabourMarketRepository(":memory:")
        labour.add_vacancy(LabourVacancy(
            source_id="eurostat_occ_vacancy", occupation="Total", country="Germany",
            year=2024, indicator="Job vacancy rate", unit="Percentage", value=3.1))
        coord = StructuredRetrievalCoordinator(labour_repo=labour, manifest_entries=[])
        with mock.patch.object(labour, "vacancies_for", wraps=labour.vacancies_for) as spy:
            out = coord.retrieve(route_question("What is demand like right now in Germany?"),
                                 "What is demand like right now in Germany?")
        assert spy.called
        assert any(e.evidence_type == "vacancy" for e in out.evidence)


@pytest.mark.skipif(not os.path.isfile("data/raw/2026_cedefop_labour_skills_shortage_index_clssi_dataset.xlsx"),
                    reason="CLSSI dataset not present")
def test_clssi_reader() -> None:
    rows = lr.read_cedefop_clssi()
    assert len(rows) > 100
    assert all(r.source_id == "cedefop_clssi" and r.shortage_indicator for r in rows)


@pytest.mark.skipif(not os.path.isfile("data/raw/jvs_a_isco3_r1$defaultview_spreadsheet.xlsx"),
                    reason="Eurostat JVS not present")
def test_eurostat_vacancy_reader() -> None:
    rows = lr.read_eurostat_vacancy()
    rates = [r for r in rows if r.indicator == "Job vacancy rate" and r.unit == "Percentage"]
    assert rates and all(r.experimental for r in rates)


@pytest.mark.skipif(not os.path.isfile("data/raw/DigComp 2.2 ESCO Skills Mapping.xlsx"),
                    reason="DigComp mapping not present")
def test_digcomp_structured_reader() -> None:
    comps = lr.read_digcomp_structured()
    assert comps
    assert all(c.framework == "DigComp 2.2" for c in comps)
    assert {c.area for c in comps} & {"Information and data literacy", "Problem solving"}
