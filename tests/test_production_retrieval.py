"""Integration tests: structured stores participate in the production chat answer.

Each test builds real (in-memory) repositories, wires them through the
StructuredRetrievalCoordinator into CareerIntelligenceService, asks a realistic
question, and asserts BOTH that the relevant repository method was actually called
AND that structured evidence/citations were produced. These do not merely check
route_question().
"""

from __future__ import annotations

from unittest import mock

import pytest

from src.copilot.knowledge.compensation import CompensationRecord, CompensationRepository
from src.copilot.knowledge.retrieval import StructuredRetrievalCoordinator
from src.copilot.knowledge.roles import NormalisedOccupation, RoleRepository, Skill
from src.copilot.knowledge.structured_ext import (
    Competency,
    CompetencyRepository,
    LabourForecast,
    LabourMarketRepository,
    LabourOpenings,
    LabourShortage,
    RoleBehaviour,
)
from src.copilot.rag.responder import ModelReply
from src.copilot.service import CareerIntelligenceService


# --- Fixtures ----------------------------------------------------------------


def _role_repo() -> RoleRepository:
    repo = RoleRepository(":memory:")
    repo.add_occupation(NormalisedOccupation(
        occupation_code="onet:15-2051", title="Data Analyst", source_id="onet",
        tasks=["Clean and prepare data", "Build dashboards", "Communicate findings"],
        skills=[Skill(name="SQL"), Skill(name="Statistics"),
                Skill(name="Python", skill_type="technology")],
        knowledge=["Mathematics"]))
    repo.add_occupation(NormalisedOccupation(
        occupation_code="onet:11-2021", title="Product Manager", source_id="onet",
        tasks=["Define roadmap", "Prioritise features"],
        skills=[Skill(name="Stakeholder management"), Skill(name="Market research"),
                Skill(name="Product lifecycle")]))
    repo.add_occupation(NormalisedOccupation(
        occupation_code="onet:13-1111", title="Business Analyst", source_id="onet",
        tasks=["Gather requirements", "Analyse processes"],
        skills=[Skill(name="Stakeholder management"), Skill(name="Market research"),
                Skill(name="Requirements analysis")]))
    return repo


def _comp_repo() -> CompensationRepository:
    repo = CompensationRepository(":memory:")
    repo.add(CompensationRecord(
        source_id="bls_oews", occupation_code="11-3121", occupation_title="Human Resources Managers",
        geography="US", country="US", year=2025, currency="USD", pay_period="annual",
        statistic_type="median", value=149280.0, lower_bound=88200.0, upper_bound=267810.0,
        sample_quality="final"))
    repo.add(CompensationRecord(
        source_id="ons_ashe", occupation_code="1135", occupation_title="Human Resources Managers",
        geography="UK", country="UK", year=2025, currency="GBP", pay_period="weekly",
        statistic_type="median", value=980.0, sample_quality="provisional"))
    repo.add(CompensationRecord(
        source_id="bls_oews", occupation_code="15-2051", occupation_title="Data Analyst",
        geography="US", country="US", year=2025, currency="USD", pay_period="annual",
        statistic_type="median", value=100910.0, sample_quality="final"))
    return repo


def _competency_repo() -> CompetencyRepository:
    repo = CompetencyRepository(":memory:")
    repo.add_competency(Competency(source_id="digcomp", framework="DigComp 2.2",
                                   area="Information and data literacy",
                                   name="Browsing, searching and filtering data"))
    repo.add_competency(Competency(source_id="digcomp", framework="DigComp 2.2",
                                   area="Digital content creation", name="Developing digital content"))
    repo.add_competency(Competency(source_id="nice_framework", framework="NICE",
                                   area="Cyber Defense Incident Responder",
                                   name="Skill in preserving evidence integrity"))
    repo.add_behaviour(RoleBehaviour(source_id="uk_civil_service_success_profiles",
                                     framework="UK Civil Service Success Profiles",
                                     level="Grade 7", behaviour="Leadership",
                                     expectation="Role-model organisational values."))
    return repo


def _labour_repo() -> LabourMarketRepository:
    repo = LabourMarketRepository(":memory:")
    repo.add_shortage(LabourShortage(source_id="cedefop_shortage_index", occupation="Nurse",
                                     country="EU", skill_level="high",
                                     shortage_indicator="shortage", period="2023"))
    repo.add_openings(LabourOpenings(source_id="cedefop_future_job_openings", occupation="Nurse",
                                     geography="EU", period="2022-2035", new_jobs=590000,
                                     replacement_demand=1800000, total_openings=2390000))
    repo.add_forecast(LabourForecast(source_id="cedefop_skills_forecast", occupation="Data Analyst",
                                     country="EU", employment_change=0.14, horizon="2022-2035"))
    return repo


_MANIFEST = [
    type("E", (), {"source_id": s, "title": t, "source_url": u, "publisher": p,
                   "authority_level": 1, "region": r, "country": c})()
    for s, t, u, p, r, c in [
        ("onet", "O*NET", "https://onet.org", "US DOL", "US", "US"),
        ("bls_oews", "BLS OEWS", "https://bls.gov/oes", "BLS", "US", "US"),
        ("ons_ashe", "ONS ASHE", "https://ons.gov.uk", "ONS", "UK", "UK"),
        ("digcomp", "DigComp", "https://digcomp.eu", "EC JRC", "EU", "EU"),
        ("nice_framework", "NICE", "https://nist.gov", "NIST", "US", "US"),
        ("uk_civil_service_success_profiles", "Civil Service Success Profiles",
         "https://gov.uk", "Cabinet Office", "UK", "UK"),
        ("cedefop_shortage_index", "Cedefop Shortage", "https://cedefop.eu", "Cedefop", "EU", "EU"),
        ("cedefop_future_job_openings", "Cedefop Openings", "https://cedefop.eu", "Cedefop", "EU", "EU"),
        ("cedefop_skills_forecast", "Cedefop Forecast", "https://cedefop.eu", "Cedefop", "EU", "EU"),
    ]
]


@pytest.fixture
def stores():
    role, comp, comp_fw, labour = _role_repo(), _comp_repo(), _competency_repo(), _labour_repo()
    yield role, comp, comp_fw, labour
    for r in (role, comp, comp_fw, labour):
        r.close()


def _service(stores):
    role, comp, comp_fw, labour = stores
    coord = StructuredRetrievalCoordinator(
        role_repo=role, comp_repo=comp, competency_repo=comp_fw, labour_repo=labour,
        manifest_entries=_MANIFEST)
    # Fake responder cites the first two evidence markers so citations flow through.
    responder = lambda m: ModelReply(content="Per the evidence [1][2].")
    return CareerIntelligenceService(
        knowledge_coordinator=coord, synthesis_responder=responder, retriever=None), coord


def _types(evidence):
    return {e.evidence_type for e in evidence}


# --- Tests -------------------------------------------------------------------


class TestProductionRetrieval:
    def test_role_do(self, stores) -> None:
        role = stores[0]
        svc, _ = _service(stores)
        with mock.patch.object(role, "get_occupation", wraps=role.get_occupation) as spy:
            r = svc.answer("What does a Data Analyst do?")
        assert spy.called  # role repo actually queried
        assert r.trace.retrieval_lane == "structured_role"
        assert {"role_task", "skill"} & _types(r.response.evidence)
        assert any(c.source_url for c in r.response.evidence)

    def test_role_skills(self, stores) -> None:
        role = stores[0]
        svc, _ = _service(stores)
        with mock.patch.object(role, "search", wraps=role.search) as spy:
            r = svc.answer("What skills does a Product Manager need?")
        assert spy.called
        assert "skill" in _types(r.response.evidence)

    def test_compensation_us(self, stores) -> None:
        comp = stores[1]
        svc, _ = _service(stores)
        with mock.patch.object(comp, "filter", wraps=comp.filter) as spy:
            r = svc.answer("What does an HR Manager earn in the US?")
        assert spy.called
        assert r.trace.detected_country == "US"
        comp_ev = [e for e in r.response.evidence if e.evidence_type == "compensation"]
        assert comp_ev and comp_ev[0].country == "US"
        assert comp_ev[0].source_url

    def test_compensation_uk(self, stores) -> None:
        comp = stores[1]
        svc, _ = _service(stores)
        with mock.patch.object(comp, "filter", wraps=comp.filter) as spy:
            r = svc.answer("What does an HR Manager earn in the UK?")
        assert spy.called
        assert r.trace.detected_country == "UK"
        comp_ev = [e for e in r.response.evidence if e.evidence_type == "compensation"]
        assert comp_ev and comp_ev[0].country == "UK"

    def test_compensation_missing_country_is_flagged(self, stores) -> None:
        # No German record exists → must say so, not invent one.
        svc, _ = _service(stores)
        r = svc.answer("What does an HR Manager earn in Germany?")
        assert r.trace.detected_country == "DE"
        assert any("Germany" in n or "DE" in n for n in r.trace.coverage_notes)

    def test_digital_competency(self, stores) -> None:
        comp_fw = stores[2]
        svc, _ = _service(stores)
        with mock.patch.object(comp_fw, "search_competencies", wraps=comp_fw.search_competencies) as spy:
            r = svc.answer("What digital skills should a manager have?")
        assert spy.called
        assert "competency" in _types(r.response.evidence)

    def test_cybersecurity(self, stores) -> None:
        comp_fw = stores[2]
        svc, _ = _service(stores)
        with mock.patch.object(comp_fw, "search_competencies", wraps=comp_fw.search_competencies) as spy:
            r = svc.answer("What are incident responder responsibilities?")
        assert spy.called
        assert r.trace.retrieval_lane == "cybersecurity"
        assert "competency" in _types(r.response.evidence)

    def test_shortage(self, stores) -> None:
        labour = stores[3]
        svc, _ = _service(stores)
        with mock.patch.object(labour, "shortages_for", wraps=labour.shortages_for) as spy:
            r = svc.answer("Is nursing in shortage?")
        assert spy.called
        assert "shortage" in _types(r.response.evidence)

    def test_openings(self, stores) -> None:
        labour = stores[3]
        svc, _ = _service(stores)
        with mock.patch.object(labour, "openings_for", wraps=labour.openings_for) as spy:
            r = svc.answer("How many job openings are expected for nurses?")
        assert spy.called
        assert "openings" in _types(r.response.evidence)

    def test_seniority(self, stores) -> None:
        comp_fw = stores[2]
        svc, _ = _service(stores)
        with mock.patch.object(comp_fw, "behaviours", wraps=comp_fw.behaviours) as spy:
            r = svc.answer("What is expected at Grade 7?")
        assert spy.called
        assert "behaviour" in _types(r.response.evidence)

    def test_transition(self, stores) -> None:
        role = stores[0]
        svc, _ = _service(stores)
        with mock.patch.object(role, "get_occupation", wraps=role.get_occupation) as spy:
            r = svc.answer("How do I move from Business Analyst to Product Manager?")
        assert spy.call_count >= 2  # both occupations resolved
        assert "transition" in _types(r.response.evidence)

    def test_mixed_skills_and_salary(self, stores) -> None:
        role, comp = stores[0], stores[1]
        svc, _ = _service(stores)
        with mock.patch.object(comp, "filter", wraps=comp.filter) as comp_spy, \
             mock.patch.object(role, "search", wraps=role.search) as role_spy:
            r = svc.answer("What skills and salary are typical for a Data Analyst in the US?")
        assert role_spy.called and comp_spy.called
        assert r.trace.retrieval_lane == "mixed"
        types = _types(r.response.evidence)
        assert "skill" in types or "role_task" in types
        assert "compensation" in types

    def test_no_coordinator_keeps_vector_only(self) -> None:
        # Regression: without a coordinator, no structured evidence is added.
        svc = CareerIntelligenceService(
            synthesis_responder=lambda m: ModelReply(content="ok"), retriever=None)
        r = svc.answer("What does a Data Analyst do?")
        assert r.response.evidence == []
