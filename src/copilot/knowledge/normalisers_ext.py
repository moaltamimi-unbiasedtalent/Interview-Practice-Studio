"""Normalisers for the extended source types: competency/behaviour frameworks
and labour-market data.

Pure functions over already-parsed fixture rows (JSON) — no downloads. Each
returns the strongly-typed records for :mod:`structured_ext` (competencies,
role behaviours, qualification requirements, forecasts, openings, shortages) or,
for BLS OOH, a :class:`NormalisedOccupation` for the role store. Every record
carries its ``source_id`` so provenance survives into the stores.
"""

from __future__ import annotations

from src.copilot.knowledge.roles import NormalisedOccupation, Skill
from src.copilot.knowledge.structured_ext import (
    Competency,
    CompetencyLevel,
    LabourForecast,
    LabourOpenings,
    LabourShortage,
    OccupationCompetency,
    QualificationRequirement,
    RoleBehaviour,
)

__all__ = [
    "normalise_digcomp",
    "normalise_nice",
    "normalise_ecf",
    "normalise_ba_kompetenzkatalog",
    "normalise_civil_service_success_profiles",
    "normalise_opm_qualification_standards",
    "normalise_cedefop_forecast",
    "normalise_cedefop_openings",
    "normalise_cedefop_shortage",
    "normalise_bls_ooh",
]


# --- Competency / behaviour frameworks ---------------------------------------


def normalise_digcomp(raw: dict, source_id: str = "digcomp") -> tuple[list[Competency], list[CompetencyLevel]]:
    """DigComp 2.2 → competencies + proficiency levels.

    Fields: framework, competences[{area, name, description, levels[{level, descriptor}]}].
    """
    framework = raw.get("framework") or "DigComp 2.2"
    comps: list[Competency] = []
    levels: list[CompetencyLevel] = []
    for c in raw.get("competences") or []:
        name = c["name"]
        comps.append(Competency(source_id=source_id, framework=framework, area=c.get("area", ""),
                                name=name, description=c.get("description")))
        for lv in c.get("levels") or []:
            levels.append(CompetencyLevel(source_id=source_id, framework=framework, competency=name,
                                          level=str(lv["level"]), descriptor=lv.get("descriptor")))
    return comps, levels


def normalise_nice(raw: dict, source_id: str = "nice_framework") -> tuple[list[Competency], list[OccupationCompetency]]:
    """NICE Workforce Framework → work-role competencies + occupation mappings.

    Fields: framework, work_roles[{id, name, tasks[], knowledge_skills[]}].
    """
    framework = raw.get("framework") or "NICE"
    comps: list[Competency] = []
    links: list[OccupationCompetency] = []
    for role in raw.get("work_roles") or []:
        code = str(role.get("id") or role["name"])
        for ks in role.get("knowledge_skills") or []:
            comps.append(Competency(source_id=source_id, framework=framework, area=role["name"],
                                    name=ks, description=None))
            links.append(OccupationCompetency(source_id=source_id, occupation_code=code,
                                              competency=ks, importance="required"))
    return comps, links


def normalise_ecf(raw: dict, source_id: str = "ecf") -> list[Competency]:
    """European e-Competence Framework → competencies.

    Fields: framework, competences[{area, name, description}].
    """
    framework = raw.get("framework") or "e-CF"
    return [
        Competency(source_id=source_id, framework=framework, area=c.get("area", ""),
                   name=c["name"], description=c.get("description"))
        for c in raw.get("competences") or []
    ]


def normalise_ba_kompetenzkatalog(raw: dict, source_id: str = "ba_kompetenzkatalog") -> list[Competency]:
    """Bundesagentur für Arbeit Kompetenzkatalog → competencies.

    Fields: framework, competences[{area, name, description}].
    """
    framework = raw.get("framework") or "BA Kompetenzkatalog"
    return [
        Competency(source_id=source_id, framework=framework, area=c.get("area", ""),
                   name=c["name"], description=c.get("description"))
        for c in raw.get("competences") or []
    ]


def normalise_civil_service_success_profiles(
    raw: dict, source_id: str = "uk_civil_service_success_profiles"
) -> list[RoleBehaviour]:
    """UK Civil Service Success Profiles → behaviours by grade/level.

    Fields: framework, behaviours[{level, behaviour, expectation}].
    Seniority is expressed as source-defined behavioural expectations per grade —
    never as a fabricated "years of experience" rule.
    """
    framework = raw.get("framework") or "UK Civil Service Success Profiles"
    return [
        RoleBehaviour(source_id=source_id, framework=framework, level=str(b["level"]),
                      behaviour=b["behaviour"], expectation=b.get("expectation"))
        for b in raw.get("behaviours") or []
    ]


def normalise_opm_qualification_standards(
    raw: dict, source_id: str = "opm_qualification_standards"
) -> list[QualificationRequirement]:
    """OPM Qualification Standards → qualification requirements.

    Fields: series[{series, requirements[{type, requirement}]}].
    """
    out: list[QualificationRequirement] = []
    for series in raw.get("series") or []:
        ref = str(series.get("series") or series.get("reference"))
        for req in series.get("requirements") or []:
            out.append(QualificationRequirement(source_id=source_id, reference=ref,
                                                requirement_type=req.get("type", "education"),
                                                requirement=req["requirement"]))
    return out


# --- Labour market -----------------------------------------------------------


def normalise_cedefop_forecast(raw: dict, source_id: str = "cedefop_skills_forecast") -> list[LabourForecast]:
    """Cedefop Skills Forecast → employment-change forecasts.

    Fields: forecasts[{occupation, country, sector, employment_change,
    replacement_demand, horizon, reference_year}].
    """
    return [
        LabourForecast(source_id=source_id, occupation=f["occupation"], country=f.get("country", "EU"),
                       sector=f.get("sector"), employment_change=f.get("employment_change"),
                       replacement_demand=f.get("replacement_demand"), horizon=f.get("horizon"),
                       reference_year=f.get("reference_year"))
        for f in raw.get("forecasts") or []
    ]


def normalise_cedefop_openings(raw: dict, source_id: str = "cedefop_future_job_openings") -> list[LabourOpenings]:
    """Cedefop future job openings → openings records.

    Fields: openings[{occupation, geography, period, new_jobs, replacement_demand,
    total_openings}].
    """
    return [
        LabourOpenings(source_id=source_id, occupation=o["occupation"], geography=o.get("geography", "EU"),
                       period=o.get("period"), new_jobs=o.get("new_jobs"),
                       replacement_demand=o.get("replacement_demand"), total_openings=o.get("total_openings"))
        for o in raw.get("openings") or []
    ]


def normalise_cedefop_shortage(raw: dict, source_id: str = "cedefop_shortage_index") -> list[LabourShortage]:
    """Cedefop shortage index → shortage records.

    Fields: shortages[{occupation, country, skill_level, shortage_indicator, period}].
    """
    return [
        LabourShortage(source_id=source_id, occupation=s["occupation"], country=s.get("country", "EU"),
                       skill_level=s.get("skill_level"), shortage_indicator=s.get("shortage_indicator"),
                       period=s.get("period"))
        for s in raw.get("shortages") or []
    ]


# --- BLS Occupational Outlook Handbook (structured occupation summary) --------


def normalise_bls_ooh(raw: dict, source_id: str = "bls_ooh") -> NormalisedOccupation:
    """BLS Occupational Outlook Handbook entry → NormalisedOccupation.

    Fields: soc_code, title, summary, duties[], skills[], entry_education,
    work_experience. The narrative outlook text belongs in the vector lane; here
    we keep only the structured summary fields.
    """
    code = str(raw.get("soc_code") or raw.get("code") or raw.get("title"))
    title = raw.get("title") or code
    return NormalisedOccupation(
        occupation_code=code,
        title=title,
        source_id=source_id,
        description=raw.get("summary"),
        tasks=list(raw.get("duties") or []),
        skills=[Skill(name=s, skill_type="essential") for s in raw.get("skills") or []],
        knowledge=list(raw.get("knowledge") or []),
    )
