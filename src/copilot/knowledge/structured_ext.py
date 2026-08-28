"""Extended structured stores: competencies/frameworks and labour-market data.

Kept separate from the occupation `RoleRepository` so the new data types
(DigComp/NICE/EQF competencies, Civil Service/OPM role behaviours & qualification
requirements, Cedefop forecasts/openings/shortages) have their own tables without
bloating the role store. Every row carries a ``source_id`` for provenance.
"""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel

__all__ = [
    "Competency", "CompetencyLevel", "OccupationCompetency", "RoleBehaviour",
    "QualificationRequirement", "CompetencyRepository",
    "LabourForecast", "LabourOpenings", "LabourShortage", "LabourMarketRepository",
    "Certification", "OccupationLicence", "CredentialRepository",
]


# --- Competencies / frameworks -----------------------------------------------


class Competency(BaseModel):
    source_id: str
    framework: str
    area: str = ""
    name: str
    description: str | None = None


class CompetencyLevel(BaseModel):
    source_id: str
    framework: str
    competency: str
    level: str
    descriptor: str | None = None


class OccupationCompetency(BaseModel):
    source_id: str
    occupation_code: str
    competency: str
    importance: str | None = None


class RoleBehaviour(BaseModel):
    source_id: str
    framework: str
    level: str  # grade / seniority level
    behaviour: str
    expectation: str | None = None


class QualificationRequirement(BaseModel):
    source_id: str
    reference: str  # occupation / series
    requirement_type: str  # education | experience | series
    requirement: str


_COMP_SCHEMA = """
CREATE TABLE IF NOT EXISTS competencies (source_id TEXT, framework TEXT, area TEXT, name TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS competency_levels (source_id TEXT, framework TEXT, competency TEXT, level TEXT, descriptor TEXT);
CREATE TABLE IF NOT EXISTS occupation_competencies (source_id TEXT, occupation_code TEXT, competency TEXT, importance TEXT);
CREATE TABLE IF NOT EXISTS role_behaviours (source_id TEXT, framework TEXT, level TEXT, behaviour TEXT, expectation TEXT);
CREATE TABLE IF NOT EXISTS qualification_requirements (source_id TEXT, reference TEXT, requirement_type TEXT, requirement TEXT);
"""
_COMP_TABLES = ["competencies", "competency_levels", "occupation_competencies",
                "role_behaviours", "qualification_requirements"]


class CompetencyRepository:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_COMP_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def add_competency(self, c: Competency) -> None:
        self._conn.execute("INSERT INTO competencies VALUES (?,?,?,?,?)",
                           (c.source_id, c.framework, c.area, c.name, c.description))
        self._conn.commit()

    def add_level(self, level: CompetencyLevel) -> None:
        self._conn.execute("INSERT INTO competency_levels VALUES (?,?,?,?,?)",
                           (level.source_id, level.framework, level.competency, level.level, level.descriptor))
        self._conn.commit()

    def add_occupation_competency(self, oc: OccupationCompetency) -> None:
        self._conn.execute("INSERT INTO occupation_competencies VALUES (?,?,?,?)",
                           (oc.source_id, oc.occupation_code, oc.competency, oc.importance))
        self._conn.commit()

    def add_behaviour(self, b: RoleBehaviour) -> None:
        self._conn.execute("INSERT INTO role_behaviours VALUES (?,?,?,?,?)",
                           (b.source_id, b.framework, b.level, b.behaviour, b.expectation))
        self._conn.commit()

    def add_qualification(self, q: QualificationRequirement) -> None:
        self._conn.execute("INSERT INTO qualification_requirements VALUES (?,?,?,?)",
                           (q.source_id, q.reference, q.requirement_type, q.requirement))
        self._conn.commit()

    def competencies_in(self, framework: str) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT area, name, description FROM competencies WHERE framework=?", (framework,))]

    def frameworks(self) -> list[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT DISTINCT framework FROM competencies") if r[0]]

    def search_competencies(self, *, text: str | None = None, framework: str | None = None,
                            limit: int = 20) -> list[dict]:
        """Competencies filtered by framework (LIKE) and/or free text (LIKE)."""
        clauses, params = [], []
        if framework:
            clauses.append("lower(framework) LIKE ?"); params.append(f"%{framework.lower()}%")
        if text:
            like = f"%{text.lower()}%"
            clauses.append("(lower(name) LIKE ? OR lower(area) LIKE ? OR lower(description) LIKE ?)")
            params.extend([like, like, like])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return [dict(r) for r in self._conn.execute(
            f"SELECT source_id, framework, area, name, description FROM competencies{where} LIMIT ?",
            (*params, limit))]

    def behaviours_for_level(self, framework: str, level: str) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT behaviour, expectation FROM role_behaviours WHERE framework=? AND level=?",
            (framework, level))]

    def behaviours(self, *, framework: str | None = None, level: str | None = None,
                   limit: int = 30) -> list[dict]:
        clauses, params = [], []
        if framework:
            clauses.append("lower(framework) LIKE ?"); params.append(f"%{framework.lower()}%")
        if level:
            clauses.append("lower(level) LIKE ?"); params.append(f"%{level.lower()}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return [dict(r) for r in self._conn.execute(
            f"SELECT source_id, framework, level, behaviour, expectation FROM role_behaviours{where} LIMIT ?",
            (*params, limit))]

    def qualifications(self, *, reference: str | None = None, limit: int = 20) -> list[dict]:
        clauses, params = [], []
        if reference:
            clauses.append("lower(reference) LIKE ?"); params.append(f"%{reference.lower()}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return [dict(r) for r in self._conn.execute(
            f"SELECT source_id, reference, requirement_type, requirement FROM qualification_requirements{where} LIMIT ?",
            (*params, limit))]

    def counts(self) -> dict[str, int]:
        return {t: self._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _COMP_TABLES}

    def counts_by_source(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for t in _COMP_TABLES:
            for r in self._conn.execute(f"SELECT source_id, COUNT(*) AS n FROM {t} GROUP BY source_id"):
                totals[r["source_id"]] = totals.get(r["source_id"], 0) + r["n"]
        return totals


# --- Labour market -----------------------------------------------------------


class LabourForecast(BaseModel):
    source_id: str
    occupation: str
    country: str
    sector: str | None = None
    employment_change: float | None = None
    replacement_demand: float | None = None
    horizon: str | None = None
    reference_year: int | None = None


class LabourOpenings(BaseModel):
    source_id: str
    occupation: str
    geography: str
    period: str | None = None
    new_jobs: float | None = None
    replacement_demand: float | None = None
    total_openings: float | None = None


class LabourShortage(BaseModel):
    source_id: str
    occupation: str
    country: str
    skill_level: str | None = None
    shortage_indicator: str | None = None
    period: str | None = None


_LM_SCHEMA = """
CREATE TABLE IF NOT EXISTS labour_market_forecasts (source_id TEXT, occupation TEXT, country TEXT, sector TEXT, employment_change REAL, replacement_demand REAL, horizon TEXT, reference_year INTEGER);
CREATE TABLE IF NOT EXISTS labour_market_openings (source_id TEXT, occupation TEXT, geography TEXT, period TEXT, new_jobs REAL, replacement_demand REAL, total_openings REAL);
CREATE TABLE IF NOT EXISTS labour_shortages (source_id TEXT, occupation TEXT, country TEXT, skill_level TEXT, shortage_indicator TEXT, period TEXT);
"""
_LM_TABLES = ["labour_market_forecasts", "labour_market_openings", "labour_shortages"]


class LabourMarketRepository:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_LM_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def add_forecast(self, f: LabourForecast) -> None:
        self._conn.execute("INSERT INTO labour_market_forecasts VALUES (?,?,?,?,?,?,?,?)",
                           (f.source_id, f.occupation, f.country, f.sector, f.employment_change,
                            f.replacement_demand, f.horizon, f.reference_year))
        self._conn.commit()

    def add_openings(self, o: LabourOpenings) -> None:
        self._conn.execute("INSERT INTO labour_market_openings VALUES (?,?,?,?,?,?,?)",
                           (o.source_id, o.occupation, o.geography, o.period, o.new_jobs,
                            o.replacement_demand, o.total_openings))
        self._conn.commit()

    def add_shortage(self, s: LabourShortage) -> None:
        self._conn.execute("INSERT INTO labour_shortages VALUES (?,?,?,?,?,?)",
                           (s.source_id, s.occupation, s.country, s.skill_level,
                            s.shortage_indicator, s.period))
        self._conn.commit()

    def forecast_for(self, occupation: str, country: str | None = None) -> list[dict]:
        q = "SELECT * FROM labour_market_forecasts WHERE lower(occupation) LIKE ?"
        params = [f"%{occupation.lower()}%"]
        if country:
            q += " AND lower(country)=?"; params.append(country.lower())
        return [dict(r) for r in self._conn.execute(q, params)]

    def openings_for(self, occupation: str) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM labour_market_openings WHERE lower(occupation) LIKE ?",
            (f"%{occupation.lower()}%",))]

    def shortages_for(self, occupation: str, country: str | None = None) -> list[dict]:
        q = "SELECT * FROM labour_shortages WHERE lower(occupation) LIKE ?"
        params = [f"%{occupation.lower()}%"]
        if country:
            q += " AND lower(country)=?"; params.append(country.lower())
        return [dict(r) for r in self._conn.execute(q, params)]

    def counts(self) -> dict[str, int]:
        return {t: self._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _LM_TABLES}

    def counts_by_source(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for t in _LM_TABLES:
            for r in self._conn.execute(f"SELECT source_id, COUNT(*) AS n FROM {t} GROUP BY source_id"):
                totals[r["source_id"]] = totals.get(r["source_id"], 0) + r["n"]
        return totals


# --- Credentials: certifications & occupational licences ----------------------


class Certification(BaseModel):
    source_id: str
    certification_id: str
    name: str
    organisation: str | None = None
    type: str | None = None           # e.g. vendor | professional | industry
    occupation_code: str | None = None
    occupation_title: str | None = None
    last_updated: str | None = None


class OccupationLicence(BaseModel):
    source_id: str
    licence_id: str
    title: str
    occupation: str | None = None
    jurisdiction: str | None = None   # e.g. US-CA, UK, DE
    issuing_body: str | None = None
    education_requirement: str | None = None
    exam_requirement: str | None = None
    experience_requirement: str | None = None
    description: str | None = None


_CRED_SCHEMA = """
CREATE TABLE IF NOT EXISTS certifications (source_id TEXT, certification_id TEXT, name TEXT, organisation TEXT, type TEXT, occupation_code TEXT, occupation_title TEXT, last_updated TEXT);
CREATE TABLE IF NOT EXISTS occupational_licences (source_id TEXT, licence_id TEXT, title TEXT, occupation TEXT, jurisdiction TEXT, issuing_body TEXT, education_requirement TEXT, exam_requirement TEXT, experience_requirement TEXT, description TEXT);
"""
_CRED_TABLES = ["certifications", "occupational_licences"]


class CredentialRepository:
    """Certifications (optional) and occupational licences (may be required).

    The two are deliberately separate models: a licence is a legal requirement to
    practise in a jurisdiction; a certification is an optional professional
    credential. Nothing here implies a credential is *required* unless the source
    says so.
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_CRED_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def add_certification(self, c: Certification) -> None:
        self._conn.execute("INSERT INTO certifications VALUES (?,?,?,?,?,?,?,?)",
                           (c.source_id, c.certification_id, c.name, c.organisation, c.type,
                            c.occupation_code, c.occupation_title, c.last_updated))
        self._conn.commit()

    def add_licence(self, l: OccupationLicence) -> None:
        self._conn.execute("INSERT INTO occupational_licences VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (l.source_id, l.licence_id, l.title, l.occupation, l.jurisdiction,
                            l.issuing_body, l.education_requirement, l.exam_requirement,
                            l.experience_requirement, l.description))
        self._conn.commit()

    def certifications_for(self, occupation: str) -> list[dict]:
        like = f"%{occupation.lower()}%"
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM certifications WHERE lower(occupation_title) LIKE ? OR lower(name) LIKE ?",
            (like, like))]

    def licences_for(self, occupation: str, jurisdiction: str | None = None) -> list[dict]:
        q = "SELECT * FROM occupational_licences WHERE (lower(occupation) LIKE ? OR lower(title) LIKE ?)"
        params = [f"%{occupation.lower()}%", f"%{occupation.lower()}%"]
        if jurisdiction:
            q += " AND lower(jurisdiction) LIKE ?"; params.append(f"%{jurisdiction.lower()}%")
        return [dict(r) for r in self._conn.execute(q, params)]

    def counts(self) -> dict[str, int]:
        return {t: self._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _CRED_TABLES}

    def counts_by_source(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for t in _CRED_TABLES:
            for r in self._conn.execute(f"SELECT source_id, COUNT(*) AS n FROM {t} GROUP BY source_id"):
                totals[r["source_id"]] = totals.get(r["source_id"], 0) + r["n"]
        return totals
