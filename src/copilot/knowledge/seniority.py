"""Role-architecture / seniority framework layer.

Describes seniority by *dimensions* (autonomy, responsibility, scope, complexity,
leadership, stakeholder exposure) drawn from public frameworks (e.g. the EQF
level descriptors), never by invented rules like "senior = X years". Levels are
loaded from provenance-bearing descriptors; a small EQF-derived default ships so
the layer is usable, clearly attributed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.copilot.knowledge.provenance import AuthorityLevel, Provenance

__all__ = ["SeniorityLevel", "SeniorityFramework", "default_eqf_framework"]

DIMENSIONS = ["autonomy", "responsibility", "scope", "complexity", "leadership", "stakeholder"]


class SeniorityLevel(BaseModel):
    key: str
    label: str
    descriptors: dict = Field(default_factory=dict)  # dimension -> short descriptor


class SeniorityFramework(BaseModel):
    name: str
    levels: list[SeniorityLevel] = Field(default_factory=list)
    provenance: Provenance | None = None

    def describe(self, key: str) -> SeniorityLevel | None:
        for level in self.levels:
            if level.key == key:
                return level
        return None


def default_eqf_framework() -> SeniorityFramework:
    """A small framework derived from public EQF level descriptors (attributed).

    Descriptors paraphrase the EQF's autonomy/responsibility progression; they are
    generic and source-attributed, not invented corporate tenure rules.
    """
    prov = Provenance(
        source_id="eqf", source_title="European Qualifications Framework (level descriptors)",
        source_type="competency_framework", authority_level=AuthorityLevel.PUBLIC_FRAMEWORK,
        publisher="European Commission", country="EU", content_type="framework",
    )
    levels = [
        SeniorityLevel(key="entry", label="Entry", descriptors={
            "autonomy": "works under supervision", "responsibility": "own tasks",
            "scope": "defined tasks", "complexity": "routine", "leadership": "none",
            "stakeholder": "team-internal"}),
        SeniorityLevel(key="professional", label="Professional", descriptors={
            "autonomy": "self-directed within guidelines", "responsibility": "own work + quality",
            "scope": "a work area", "complexity": "varied problems", "leadership": "may guide peers",
            "stakeholder": "cross-team"}),
        SeniorityLevel(key="senior", label="Senior", descriptors={
            "autonomy": "high autonomy", "responsibility": "outcomes + others' work",
            "scope": "multiple work areas", "complexity": "ambiguous problems",
            "leadership": "mentors, may lead", "stakeholder": "cross-functional"}),
        SeniorityLevel(key="lead_manager", label="Lead / Manager", descriptors={
            "autonomy": "sets direction for a team", "responsibility": "team results",
            "scope": "a team or function", "complexity": "strategic within scope",
            "leadership": "manages people", "stakeholder": "senior stakeholders"}),
        SeniorityLevel(key="executive", label="Executive", descriptors={
            "autonomy": "accountable for strategy", "responsibility": "organisational outcomes",
            "scope": "organisation-wide", "complexity": "high uncertainty",
            "leadership": "leads leaders", "stakeholder": "board / external"}),
    ]
    return SeniorityFramework(name="EQF-derived seniority", levels=levels, provenance=prov)
