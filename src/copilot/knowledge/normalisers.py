"""Normalise source-specific occupation records into ``NormalisedOccupation``.

Pure functions over already-parsed fixture dicts (CSV/JSON rows) — no downloads.
Each preserves provenance (source_id + authority). Field mappings are documented
inline so a reviewer can see how each taxonomy maps onto the common schema.
"""

from __future__ import annotations

from src.copilot import constants
from src.copilot.knowledge.provenance import Provenance
from src.copilot.knowledge.roles import Mapping, NormalisedOccupation, Relationship, Skill

__all__ = ["normalise_esco", "normalise_onet", "normalise_isco", "normalise_kldb"]


def _prov(source_id: str, title: str, publisher: str, country: str, isco: str | None = None,
          occupation_code: str | None = None, occupation_title: str | None = None) -> Provenance:
    return Provenance(
        source_id=source_id, source_title=title, source_type="occupation_taxonomy",
        authority_level=constants.AUTHORITY_OFFICIAL, publisher=publisher, country=country,
        content_type="structured", isco_code=isco, occupation_code=occupation_code,
        occupation_title=occupation_title,
    )


def _skills(names, skill_type: str) -> list[Skill]:
    return [Skill(name=n, skill_type=skill_type) for n in (names or [])]


def normalise_esco(raw: dict, source_id: str = "esco") -> NormalisedOccupation:
    """ESCO occupation → NormalisedOccupation.

    ESCO fields: code, preferredLabel, alternativeLabels, description,
    essentialSkills, optionalSkills, knowledge, iscoGroup, relatedOccupations.
    """
    code = str(raw.get("code") or raw.get("conceptUri") or raw.get("preferredLabel"))
    title = raw.get("preferredLabel") or raw.get("title") or code
    isco = raw.get("iscoGroup") or raw.get("isco")
    return NormalisedOccupation(
        occupation_code=code,
        title=title,
        source_id=source_id,
        description=raw.get("description"),
        isco_code=isco,
        aliases=list(raw.get("alternativeLabels") or []),
        skills=_skills(raw.get("essentialSkills"), "essential") + _skills(raw.get("optionalSkills"), "optional"),
        knowledge=list(raw.get("knowledge") or []),
        relationships=[Relationship(related_code=str(r), relation_type="related") for r in raw.get("relatedOccupations") or []],
        mappings=[Mapping(scheme="isco", code=str(isco))] if isco else [],
        provenance=_prov(source_id, "ESCO", "European Commission", "EU", isco, code, title),
    )


def normalise_onet(raw: dict, source_id: str = "onet") -> NormalisedOccupation:
    """O*NET occupation → NormalisedOccupation.

    O*NET fields: onetsoc_code, title, alternate_titles, tasks, skills, knowledge,
    abilities, work_activities, work_context, work_styles, technology_skills,
    related_occupations.
    """
    code = str(raw.get("onetsoc_code") or raw.get("code") or raw.get("title"))
    title = raw.get("title") or code
    activities = list(raw.get("work_activities") or []) + list(raw.get("work_context") or []) + list(raw.get("work_styles") or [])
    return NormalisedOccupation(
        occupation_code=code,
        title=title,
        source_id=source_id,
        description=raw.get("description"),
        aliases=list(raw.get("alternate_titles") or []),
        tasks=list(raw.get("tasks") or []),
        skills=_skills(raw.get("skills"), "essential") + _skills(raw.get("technology_skills"), "technology"),
        knowledge=list(raw.get("knowledge") or []) + list(raw.get("abilities") or []),
        activities=activities,
        relationships=[Relationship(related_code=str(r), relation_type="related") for r in raw.get("related_occupations") or []],
        provenance=_prov(source_id, "O*NET", "U.S. Department of Labor", "US", None, code, title),
    )


def normalise_isco(raw: dict, source_id: str = "isco08") -> list[NormalisedOccupation]:
    """ISCO hierarchy → NormalisedOccupations (one per group), with parent links.

    ISCO fields: groups[{code, level, title, definition, parent, example_occupations}].
    Levels: major_group, sub_major_group, minor_group, unit_group.
    """
    out: list[NormalisedOccupation] = []
    for group in raw.get("groups") or []:
        code = str(group["code"])
        parent = group.get("parent")
        out.append(
            NormalisedOccupation(
                occupation_code=code,
                title=group.get("title") or code,
                source_id=source_id,
                description=group.get("definition"),
                isco_code=code,
                occupation_group=group.get("parent_title"),
                level=group.get("level"),
                aliases=list(group.get("example_occupations") or []),
                relationships=[Relationship(related_code=str(parent), relation_type="parent")] if parent else [],
                provenance=_prov(source_id, "ISCO-08", "International Labour Organization", "global", code, code, group.get("title")),
            )
        )
    return out


def normalise_kldb(raw: dict, source_id: str = "kldb") -> NormalisedOccupation:
    """KldB 2010 occupation → NormalisedOccupation.

    KldB fields: code, title, occupation_group, tasks, activities, skills,
    knowledge, parent, mappings[{scheme, code}].
    """
    code = str(raw.get("code") or raw.get("title"))
    title = raw.get("title") or code
    return NormalisedOccupation(
        occupation_code=code,
        title=title,
        source_id=source_id,
        description=raw.get("description"),
        occupation_group=raw.get("occupation_group"),
        level=raw.get("level"),
        tasks=list(raw.get("tasks") or []),
        skills=_skills(raw.get("skills"), "essential"),
        knowledge=list(raw.get("knowledge") or []),
        activities=list(raw.get("activities") or []),
        relationships=[Relationship(related_code=str(raw["parent"]), relation_type="parent")] if raw.get("parent") else [],
        mappings=[Mapping(scheme=m["scheme"], code=str(m["code"])) for m in raw.get("mappings") or []],
        provenance=_prov(source_id, "KldB 2010", "Bundesagentur für Arbeit", "DE", None, code, title),
    )
