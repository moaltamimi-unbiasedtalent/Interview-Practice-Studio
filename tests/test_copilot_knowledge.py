"""OS-4A tests: multi-source knowledge architecture (fixtures only, no downloads)."""

from src.copilot import constants
from src.copilot.knowledge import manifest as man
from src.copilot.knowledge.compensation import CompensationRecord, CompensationRepository
from src.copilot.knowledge.normalisers import (
    normalise_esco,
    normalise_isco,
    normalise_kldb,
    normalise_onet,
)
from src.copilot.knowledge.provenance import AuthorityLevel, Provenance, authority_for_publisher
from src.copilot.knowledge.roles import RoleRepository
from src.copilot.knowledge.router import RetrievalLane, route_question
from src.copilot.knowledge.seniority import default_eqf_framework
from src.copilot.knowledge.transitions import compare_occupations


# --- Manifest ----------------------------------------------------------------


class TestManifest:
    def test_parses_committed_manifest(self) -> None:
        entries = man.load_manifest(constants.SOURCE_MANIFEST_PATH)
        ids = {e.source_id for e in entries}
        assert {"onet", "esco", "bls_oews", "ba_entgeltatlas"} <= ids

    def test_licence_and_manual_flags(self) -> None:
        entries = {e.source_id: e for e in man.load_manifest(constants.SOURCE_MANIFEST_PATH)}
        # Uncertain licences are flagged, not invented.
        assert entries["esco"].licence_review_required is True
        assert entries["ba_entgeltatlas"].manual_acquisition_required is True
        # Clearly-open sources are marked redistributable.
        assert entries["onet"].redistribution_allowed is True
        assert entries["bls_oews"].licence_review_required is False

    def test_auto_vs_manual(self) -> None:
        entries = man.load_manifest(constants.SOURCE_MANIFEST_PATH)
        auto_ids = {e.source_id for e in man.auto_downloadable(entries)}
        manual_ids = {e.source_id for e in man.manual_sources(entries)}
        assert "onet" in auto_ids and "esco" not in auto_ids
        assert "ba_entgeltatlas" in manual_ids

    def test_by_type(self) -> None:
        entries = man.load_manifest(constants.SOURCE_MANIFEST_PATH)
        comp = {e.source_id for e in man.by_type(entries, "compensation_dataset")}
        assert {"bls_oews", "ons_ashe", "eurostat_earnings"} <= comp


# --- Provenance / authority --------------------------------------------------


class TestProvenance:
    def test_authority_for_publisher(self) -> None:
        assert authority_for_publisher("European Commission") == AuthorityLevel.OFFICIAL
        assert authority_for_publisher("DigComp framework") == AuthorityLevel.PUBLIC_FRAMEWORK
        assert authority_for_publisher("Some Consultancy") == AuthorityLevel.INDUSTRY

    def test_provenance_label(self) -> None:
        p = Provenance(source_id="onet", source_title="O*NET", source_type="occupation_taxonomy",
                       reference_year=2024, geography="US")
        assert "O*NET" in p.label() and "2024" in p.label()


# --- Normalisers -------------------------------------------------------------


class TestNormalisers:
    def test_esco(self) -> None:
        occ = normalise_esco({
            "code": "2511", "preferredLabel": "Data analyst",
            "alternativeLabels": ["Data scientist"], "description": "Analyses data.",
            "essentialSkills": ["SQL"], "optionalSkills": ["Python"], "iscoGroup": "2511",
            "relatedOccupations": ["2512"],
        })
        assert occ.title == "Data analyst"
        assert "Data scientist" in occ.aliases
        types = {s.name: s.skill_type for s in occ.skills}
        assert types["SQL"] == "essential" and types["Python"] == "optional"
        assert occ.isco_code == "2511"
        assert any(m.scheme == "isco" for m in occ.mappings)

    def test_onet(self) -> None:
        occ = normalise_onet({
            "onetsoc_code": "15-2051.00", "title": "Data Scientists",
            "alternate_titles": ["ML Engineer"], "tasks": ["Build models"],
            "skills": ["Statistics"], "technology_skills": ["Python"],
            "knowledge": ["Mathematics"], "abilities": ["Reasoning"],
            "work_activities": ["Analyzing data"], "related_occupations": ["15-2041.00"],
        })
        assert occ.occupation_code == "15-2051.00"
        assert {s.skill_type for s in occ.skills} == {"essential", "technology"}
        assert "Analyzing data" in occ.activities
        assert occ.relationships[0].related_code == "15-2041.00"

    def test_isco_hierarchy(self) -> None:
        occs = normalise_isco({"groups": [
            {"code": "2", "level": "major_group", "title": "Professionals", "definition": "..."},
            {"code": "25", "level": "sub_major_group", "title": "ICT Professionals", "parent": "2"},
        ]})
        assert len(occs) == 2
        child = [o for o in occs if o.occupation_code == "25"][0]
        assert child.level == "sub_major_group"
        assert child.relationships[0].relation_type == "parent"
        assert child.relationships[0].related_code == "2"

    def test_kldb(self) -> None:
        occ = normalise_kldb({
            "code": "71304", "title": "Betriebswirt", "occupation_group": "Management",
            "tasks": ["Planung"], "skills": ["BWL"], "parent": "713",
            "mappings": [{"scheme": "isco", "code": "1120"}],
        })
        assert occ.occupation_group == "Management"
        assert occ.mappings[0].code == "1120"
        assert occ.relationships[0].related_code == "713"


# --- Role repository ---------------------------------------------------------


def _repo_with_two() -> RoleRepository:
    repo = RoleRepository(":memory:")
    repo.add_occupation(normalise_onet({
        "onetsoc_code": "DA", "title": "Data Analyst", "alternate_titles": ["Analyst"],
        "tasks": ["Clean data", "Build dashboards"], "skills": ["SQL", "Statistics"],
        "technology_skills": ["Python"],
    }))
    repo.add_occupation(normalise_onet({
        "onetsoc_code": "DS", "title": "Data Scientist", "alternate_titles": ["ML Engineer"],
        "tasks": ["Build models", "Clean data"], "skills": ["Statistics", "Machine Learning"],
        "technology_skills": ["Python"], "related_occupations": ["DA"],
    }))
    return repo


class TestRoleRepository:
    def test_get_and_search_by_alias(self) -> None:
        repo = _repo_with_two()
        occ = repo.get_occupation("DA")
        assert occ["title"] == "Data Analyst"
        assert {s["skill"] for s in occ["skills"]} == {"SQL", "Statistics", "Python"}
        assert repo.search("analyst")  # matches title or alias

    def test_idempotent_no_duplicates(self) -> None:
        repo = _repo_with_two()
        before = repo.counts()
        repo.add_occupation(normalise_onet({
            "onetsoc_code": "DA", "title": "Data Analyst", "alternate_titles": ["Analyst"],
            "tasks": ["Clean data", "Build dashboards"], "skills": ["SQL", "Statistics"],
            "technology_skills": ["Python"],
        }))
        assert repo.counts() == before  # re-adding same code does not duplicate

    def test_missing_occupation_returns_none(self) -> None:
        assert RoleRepository(":memory:").get_occupation("nope") is None


# --- Compensation ------------------------------------------------------------


class TestCompensation:
    def _repo(self) -> CompensationRepository:
        repo = CompensationRepository(":memory:")
        repo.add(CompensationRecord(source_id="bls_oews", occupation_title="Data Analyst",
                                    country="US", geography="US", year=2023, currency="USD",
                                    pay_period="annual", statistic_type="median", value=85000))
        repo.add(CompensationRecord(source_id="ba_entgeltatlas", occupation_title="Data Analyst",
                                    country="DE", geography="Germany", year=2024, currency="EUR",
                                    pay_period="monthly", statistic_type="median", value=5200))
        return repo

    def test_filter_by_country_year(self) -> None:
        repo = self._repo()
        de = repo.filter(country="DE")
        assert len(de) == 1 and de[0].currency == "EUR" and de[0].pay_period == "monthly"
        assert repo.filter(country="US", year=2023)[0].value == 85000

    def test_filter_never_merges_countries(self) -> None:
        repo = self._repo()
        assert {r.country for r in repo.filter(title="data analyst")} == {"US", "DE"}
        assert len(repo.filter(country="FR")) == 0  # missing → empty, no fallback merge


# --- Router ------------------------------------------------------------------


class TestRouter:
    def test_role_query(self) -> None:
        assert route_question("What does a Logistics Manager do?").lane == RetrievalLane.STRUCTURED_ROLE

    def test_skill_query(self) -> None:
        assert route_question("What skills do cybersecurity analysts need?").lane == RetrievalLane.STRUCTURED_ROLE

    def test_compensation_query(self) -> None:
        assert route_question("What does a Data Analyst earn in Germany?").lane == RetrievalLane.COMPENSATION

    def test_trend_query(self) -> None:
        assert route_question("Is demand for AI roles expected to grow?").lane == RetrievalLane.FORECAST

    def test_mixed_query(self) -> None:
        d = route_question("What skills does a Product Manager need and what would they earn in Germany?")
        assert d.lane == RetrievalLane.MIXED

    def test_default_vector(self) -> None:
        assert route_question("Tell me about the future of work philosophy").lane in (
            RetrievalLane.VECTOR, RetrievalLane.FORECAST
        )

    def test_llm_fallback_only_when_ambiguous(self) -> None:
        d = route_question("hmm", llm_classifier=lambda q: RetrievalLane.VECTOR)
        assert d.lane == RetrievalLane.VECTOR and d.confidence <= 0.6


# --- Transitions -------------------------------------------------------------


class TestTransitions:
    def test_compare(self) -> None:
        repo = _repo_with_two()
        cmp = compare_occupations(repo.get_occupation("DA"), repo.get_occupation("DS"))
        assert "Statistics" in cmp.shared_skills
        assert "Machine Learning" in cmp.key_gaps  # target needs, current lacks
        assert "SQL" in cmp.unique_current_skills
        assert "Clean data" in cmp.related_tasks  # shared task


# --- Seniority ---------------------------------------------------------------


class TestSeniority:
    def test_framework_has_dimensions(self) -> None:
        fw = default_eqf_framework()
        level = fw.describe("senior")
        assert level is not None
        assert "autonomy" in level.descriptors and "leadership" in level.descriptors
        assert fw.provenance.source_id == "eqf"
