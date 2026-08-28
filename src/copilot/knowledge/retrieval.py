"""Structured retrieval coordinator — turns a router decision into real evidence.

Dispatches on the knowledge router's :class:`RouteDecision` to the appropriate
structured store (roles / compensation / competency / labour-market) and returns
a uniform list of :class:`KnowledgeEvidence`. Geographic source precedence is
applied for real (country-specific official sources first), occupations are
resolved robustly, and factual gaps are reported rather than hidden.

Repositories are injected (fixtures in tests; on-disk stores in production via
:func:`build_default_coordinator`), so the service stays hermetic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from src.copilot import constants
from src.copilot.knowledge import manifest as km
from src.copilot.knowledge.resolver import (
    ResolvedOccupation,
    resolve_occupation,
    title_variants,
)
from src.copilot.knowledge.router import RetrievalLane, detect_country, source_priority
from src.copilot.knowledge.transitions import compare_occupations
from src.copilot.models import KnowledgeEvidence

__all__ = ["StructuredRetrievalCoordinator", "StructuredOutcome", "build_default_coordinator"]

_MAX_ITEMS = 12  # cap list-valued evidence so context stays bounded


@dataclass
class StructuredOutcome:
    """Result of structured retrieval for one question."""

    evidence: list[KnowledgeEvidence] = field(default_factory=list)
    resolved: ResolvedOccupation | None = None
    country: str | None = None
    lanes: list[str] = field(default_factory=list)
    sources_considered: list[str] = field(default_factory=list)
    source_precedence: list[str] = field(default_factory=list)
    structured_queries: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    insufficient: bool = False
    clarify: bool = False


class StructuredRetrievalCoordinator:
    def __init__(self, *, role_repo=None, comp_repo=None, competency_repo=None,
                 labour_repo=None, manifest_entries=None) -> None:
        self.role_repo = role_repo
        self.comp_repo = comp_repo
        self.competency_repo = competency_repo
        self.labour_repo = labour_repo
        entries = manifest_entries
        if entries is None:
            try:
                entries = km.load_manifest()
            except Exception:  # pragma: no cover - manifest optional
                entries = []
        self._meta = {e.source_id: e for e in entries}

    # -- source metadata ---------------------------------------------------

    def _src(self, source_id: str) -> dict:
        e = self._meta.get(source_id)
        if not e:
            return {"title": source_id, "url": None, "publisher": None,
                    "authority": constants.AUTHORITY_INDUSTRY, "region": None, "country": None}
        return {"title": e.title, "url": e.source_url, "publisher": e.publisher,
                "authority": e.authority_level, "region": e.region, "country": e.country}

    def _evidence(self, *, eid, text, source_id, lane, etype, occ_title=None, occ_code=None,
                  country=None, year=None, version=None, score=1.0, geography=None) -> KnowledgeEvidence:
        m = self._src(source_id)
        return KnowledgeEvidence(
            evidence_id=eid, text=text, source_id=source_id, source_title=m["title"],
            source_url=m["url"], publisher=m["publisher"], evidence_type=etype,
            retrieval_lane=lane, authority_level=m["authority"],
            geography=geography or m["region"], country=country or m["country"],
            region=m["region"], occupation_code=occ_code, occupation_title=occ_title,
            reference_year=year, version=version, score=score,
        )

    # -- public API --------------------------------------------------------

    def retrieve(self, decision, query: str, *, country: str | None = None) -> StructuredOutcome:
        lane = decision.lane
        country = country or detect_country(query)
        out = StructuredOutcome(country=country, lanes=[lane],
                                source_precedence=source_priority(country))
        try:
            if lane == RetrievalLane.COMPENSATION:
                self._role_or_comp_compensation(query, country, out)
            elif lane in (RetrievalLane.STRUCTURED_ROLE,):
                self._role(query, country, out)
            elif lane == RetrievalLane.CYBERSECURITY:
                self._cyber(query, country, out)
            elif lane == RetrievalLane.COMPETENCY:
                self._competency(query, out)
            elif lane == RetrievalLane.SENIORITY:
                self._seniority(query, out)
            elif lane == RetrievalLane.FORECAST:
                self._labour(query, country, out, kind="forecast")
            elif lane == RetrievalLane.OPENINGS:
                self._labour(query, country, out, kind="openings")
            elif lane == RetrievalLane.SHORTAGE:
                self._labour(query, country, out, kind="shortage")
            elif lane == RetrievalLane.TRANSITION:
                self._transition(query, country, out)
            elif lane == RetrievalLane.MIXED:
                self._role(query, country, out)
                self._role_or_comp_compensation(query, country, out)
            # VECTOR: nothing structured; the service runs the vector lane.
        except Exception as exc:  # noqa: BLE001 - structured retrieval never crashes the turn
            out.notes.append(f"Structured retrieval degraded: {type(exc).__name__}")
        return out

    # -- lane producers ----------------------------------------------------

    def _resolve(self, query, country, out) -> ResolvedOccupation | None:
        if self.role_repo is None:
            return None
        resolved = resolve_occupation(self.role_repo, query, country=country)
        out.resolved = resolved
        out.structured_queries.append(f"role.search('{resolved.phrase}')")
        if resolved.ambiguous:
            out.clarify = True
            names = ", ".join(f"{c.title}" for c in resolved.candidates[:4])
            out.notes.append(f"Occupation '{resolved.phrase}' is ambiguous: {names}.")
        return resolved

    def _occupation_evidence(self, occ: dict, lane: str, out) -> None:
        """Emit tasks/skills/knowledge/technology/activity evidence for one occupation."""
        sid = occ.get("source_id", "")
        title = occ.get("title")
        code = occ.get("occupation_code")
        if sid not in out.sources_considered:
            out.sources_considered.append(sid)

        tasks = occ.get("tasks") or []
        if tasks:
            out.evidence.append(self._evidence(
                eid=f"{code}:tasks", source_id=sid, lane=lane, etype="role_task",
                occ_title=title, occ_code=code, score=3.0,
                text="Typical tasks/responsibilities: " + "; ".join(tasks[:_MAX_ITEMS])))
        skills = [s["skill"] if isinstance(s, dict) else getattr(s, "name", str(s))
                  for s in (occ.get("skills") or [])]
        techs = [s["skill"] for s in (occ.get("skills") or [])
                 if isinstance(s, dict) and s.get("skill_type") == "technology"]
        core_skills = [s for s in skills if s not in techs]
        if core_skills:
            out.evidence.append(self._evidence(
                eid=f"{code}:skills", source_id=sid, lane=lane, etype="skill",
                occ_title=title, occ_code=code, score=2.6,
                text="Key skills: " + "; ".join(core_skills[:_MAX_ITEMS])))
        if techs:
            out.evidence.append(self._evidence(
                eid=f"{code}:tech", source_id=sid, lane=lane, etype="technology",
                occ_title=title, occ_code=code, score=2.2,
                text="Technologies/tools: " + "; ".join(techs[:_MAX_ITEMS])))
        knowledge = occ.get("knowledge") or []
        if knowledge:
            out.evidence.append(self._evidence(
                eid=f"{code}:knowledge", source_id=sid, lane=lane, etype="knowledge",
                occ_title=title, occ_code=code, score=2.0,
                text="Knowledge areas: " + "; ".join(knowledge[:_MAX_ITEMS])))
        activities = occ.get("activities") or []
        if activities:
            out.evidence.append(self._evidence(
                eid=f"{code}:activity", source_id=sid, lane=lane, etype="activity",
                occ_title=title, occ_code=code, score=1.6,
                text="Work activities: " + "; ".join(activities[:_MAX_ITEMS])))

    def _role(self, query, country, out) -> None:
        resolved = self._resolve(query, country, out)
        if not resolved or not resolved.candidates or resolved.ambiguous:
            if resolved and not resolved.candidates:
                out.notes.append(f"No structured occupation matched '{resolved.phrase}'.")
            return
        # Best candidate, plus one from a different source for a second perspective.
        chosen, seen_sources = [], set()
        for cand in resolved.candidates:
            base = cand.source_id.split(":", 1)[0]
            if base in seen_sources:
                continue
            seen_sources.add(base)
            chosen.append(cand)
            if len(chosen) >= 2:
                break
        for cand in chosen:
            occ = self.role_repo.get_occupation(cand.occupation_code)
            out.structured_queries.append(f"role.get_occupation('{cand.occupation_code}')")
            if occ:
                self._occupation_evidence(occ, RetrievalLane.STRUCTURED_ROLE, out)

    def _role_or_comp_compensation(self, query, country, out) -> None:
        if self.comp_repo is None:
            out.notes.append("No compensation store available.")
            return
        resolved = out.resolved or self._resolve(query, country, out)
        phrase = resolved.phrase if resolved else query
        variants = title_variants(phrase)

        def _filter(c):
            found = []
            for v in variants:
                found.extend(self.comp_repo.filter(title=v, country=c) if c
                             else self.comp_repo.filter(title=v))
            return found

        rows = _filter(country) if country else _filter(None)
        out.structured_queries.append(
            f"compensation.filter(title~{variants}, country={country!r})")
        if not rows and country:
            # Requested a specific country but have no record for it: do not fake it.
            out.insufficient = True
            out.notes.append(
                f"No official compensation record for '{phrase}' in {country}.")
            # Offer neighbouring evidence (other geographies), clearly labelled.
            rows = _filter(None)
            out.structured_queries.append("compensation.filter [neighbouring geographies]")
        # De-duplicate equivalent records surfaced by multiple title variants.
        seen_rows, unique = set(), []
        for r in rows:
            key = (r.source_id, r.occupation_code, r.occupation_title, r.country, r.value, r.pay_period)
            if key in seen_rows:
                continue
            seen_rows.add(key); unique.append(r)
        rows = unique
        for r in rows[:6]:
            sid = r.source_id
            if sid not in out.sources_considered:
                out.sources_considered.append(sid)
            band = ""
            if r.lower_bound is not None and r.upper_bound is not None:
                band = f" (range {r.lower_bound:g}–{r.upper_bound:g})"
            note = " [other geography]" if (country and (r.country or "").upper() != country) else ""
            text = (f"{r.statistic_type.title()} {r.pay_period} pay: {r.value:g} {r.currency}{band} "
                    f"in {r.country or r.geography}, {r.year or 'n/a'} "
                    f"({r.sample_quality or 'n/a'}){note}.")
            out.evidence.append(self._evidence(
                eid=f"comp:{sid}:{r.occupation_code or r.occupation_title}:{r.country}",
                source_id=sid, lane=RetrievalLane.COMPENSATION, etype="compensation",
                occ_title=r.occupation_title, occ_code=r.occupation_code,
                country=r.country, year=r.year, geography=r.geography,
                score=3.0 if not note else 1.5, text=text))

    def _cyber(self, query, country, out) -> None:
        # Prefer NICE structured evidence; supplement with role data for cyber roles.
        if self.competency_repo is not None:
            rows = self.competency_repo.search_competencies(framework="nice", limit=_MAX_ITEMS)
            out.structured_queries.append("competency.search_competencies(framework='nice')")
            for i, r in enumerate(rows):
                sid = r.get("source_id", "nice_framework")
                if sid not in out.sources_considered:
                    out.sources_considered.append(sid)
                area = r.get("area") or ""
                out.evidence.append(self._evidence(
                    eid=f"nice:{i}", source_id=sid, lane=RetrievalLane.CYBERSECURITY,
                    etype="competency", occ_title=area or "Cyber work role", score=2.8,
                    text=f"{area}: {r.get('name')}" + (f" — {r['description']}" if r.get('description') else "")))
        # Supplement with O*NET/ESCO cyber occupation if present.
        if self.role_repo is not None:
            self._role(query, country, out)

    def _competency(self, query, out) -> None:
        if self.competency_repo is None:
            out.notes.append("No competency store available.")
            return
        # Digital competence question → DigComp; else any competency match.
        framework = "digcomp" if "digital" in (query or "").lower() else None
        rows = self.competency_repo.search_competencies(framework=framework, limit=_MAX_ITEMS)
        out.structured_queries.append(f"competency.search_competencies(framework={framework!r})")
        if not rows:
            out.insufficient = True
            out.notes.append("No matching competency framework records.")
            return
        for i, r in enumerate(rows):
            sid = r.get("source_id", "")
            if sid not in out.sources_considered:
                out.sources_considered.append(sid)
            area = r.get("area") or ""
            out.evidence.append(self._evidence(
                eid=f"comp_fw:{sid}:{i}", source_id=sid, lane=RetrievalLane.COMPETENCY,
                etype="competency", score=2.4,
                text=f"{r.get('framework')} · {area}: {r.get('name')}"
                     + (f" — {r['description']}" if r.get("description") else "")))

    def _seniority(self, query, out) -> None:
        if self.competency_repo is None:
            out.notes.append("No competency/behaviour store available.")
            return
        import re
        level_m = re.search(r"\b(grade\s*\w+|seo|heo|eo|senior|junior|lead|principal|director)\b",
                            query or "", re.I)
        level = level_m.group(0) if level_m else None
        rows = self.competency_repo.behaviours(level=level)
        out.structured_queries.append(f"competency.behaviours(level={level!r})")
        for i, r in enumerate(rows):
            sid = r.get("source_id", "")
            if sid not in out.sources_considered:
                out.sources_considered.append(sid)
            out.evidence.append(self._evidence(
                eid=f"behaviour:{sid}:{i}", source_id=sid, lane=RetrievalLane.SENIORITY,
                etype="behaviour", score=2.5,
                text=f"{r.get('level')} · {r.get('behaviour')}: {r.get('expectation') or ''}".strip()))
        if not rows:
            out.notes.append("No source-backed seniority behaviours matched; "
                             "seniority is described by frameworks, never a fabricated years rule.")

    def _labour(self, query, country, out, *, kind: str) -> None:
        if self.labour_repo is None:
            out.notes.append("No labour-market store available.")
            return
        resolved = self._resolve(query, country, out)
        phrase = resolved.phrase if resolved else query
        variants = title_variants(phrase)
        rows: list = []
        for v in variants:
            if kind == "forecast":
                rows.extend(self.labour_repo.forecast_for(v, country))
                lane = RetrievalLane.FORECAST
            elif kind == "openings":
                rows.extend(self.labour_repo.openings_for(v))
                lane = RetrievalLane.OPENINGS
            else:
                rows.extend(self.labour_repo.shortages_for(v, country))
                lane = RetrievalLane.SHORTAGE
        etype = kind
        out.structured_queries.append(f"labour.{kind}_for(~{variants}, country={country!r})")
        if not rows:
            out.insufficient = True
            out.notes.append(f"No structured {kind} record for '{phrase}'"
                             + (f" in {country}." if country else "."))
            return
        for i, r in enumerate(rows[:6]):
            sid = r.get("source_id", "")
            if sid not in out.sources_considered:
                out.sources_considered.append(sid)
            out.evidence.append(self._evidence(
                eid=f"{kind}:{sid}:{i}", source_id=sid, lane=lane, etype=etype,
                occ_title=r.get("occupation"), country=r.get("country"),
                year=r.get("reference_year"), score=2.6, text=self._labour_text(kind, r)))

    @staticmethod
    def _labour_text(kind: str, r: dict) -> str:
        occ = r.get("occupation", "")
        if kind == "forecast":
            ec, rd = r.get("employment_change"), r.get("replacement_demand")
            return (f"{occ} ({r.get('country')}): employment change {ec}, replacement demand {rd}, "
                    f"horizon {r.get('horizon') or 'n/a'}.")
        if kind == "openings":
            return (f"{occ} ({r.get('geography')}): total openings {r.get('total_openings')} "
                    f"(new {r.get('new_jobs')}, replacement {r.get('replacement_demand')}), "
                    f"period {r.get('period') or 'n/a'}.")
        return (f"{occ} ({r.get('country')}): shortage {r.get('shortage_indicator')} "
                f"at {r.get('skill_level') or 'n/a'} level, {r.get('period') or 'n/a'}.")

    def _transition(self, query, country, out) -> None:
        if self.role_repo is None:
            out.notes.append("No role store available for transition comparison.")
            return
        import re
        m = re.search(r"from\s+(.+?)\s+(?:in?to|to)\s+(.+?)[\?\.]?$", query or "", re.I)
        if not m:
            self._role(query, country, out)
            return
        cur = resolve_occupation(self.role_repo, m.group(1), country=country)
        tgt = resolve_occupation(self.role_repo, m.group(2), country=country)
        out.structured_queries.append(f"transition: '{cur.phrase}' -> '{tgt.phrase}'")
        if not (cur.best and tgt.best):
            out.insufficient = True
            out.notes.append("Could not resolve both occupations for the transition.")
            return
        cur_occ = self.role_repo.get_occupation(cur.best.occupation_code)
        tgt_occ = self.role_repo.get_occupation(tgt.best.occupation_code)
        if not (cur_occ and tgt_occ):
            return
        cmp = compare_occupations(cur_occ, tgt_occ)
        out.sources_considered.extend(
            s for s in {cur.best.source_id, tgt.best.source_id} if s not in out.sources_considered)
        out.evidence.append(self._evidence(
            eid=f"transition:{cur.best.occupation_code}->{tgt.best.occupation_code}",
            source_id=cur.best.source_id, lane=RetrievalLane.TRANSITION, etype="transition",
            occ_title=f"{cur.best.title} → {tgt.best.title}", score=2.7,
            text=(f"Transferable: {'; '.join(cmp.transferable_capabilities[:_MAX_ITEMS]) or 'none found'}. "
                  f"Key gaps to close: {'; '.join(cmp.key_gaps[:_MAX_ITEMS]) or 'none found'}.")))


def build_default_coordinator(config=None) -> StructuredRetrievalCoordinator:
    """Build a coordinator backed by the on-disk stores that actually exist.

    Missing stores are simply absent (their lanes report insufficient evidence),
    so this is safe to call whether or not the knowledge base has been built.
    """
    from src.copilot.knowledge.compensation import CompensationRepository
    from src.copilot.knowledge.roles import RoleRepository
    from src.copilot.knowledge.structured_ext import (
        CompetencyRepository,
        LabourMarketRepository,
    )

    def _open(path, cls):
        return cls(path) if os.path.isfile(path) else None

    return StructuredRetrievalCoordinator(
        role_repo=_open(constants.ROLE_DB_PATH, RoleRepository),
        comp_repo=_open(constants.COMPENSATION_DB_PATH, CompensationRepository),
        competency_repo=_open(constants.COMPETENCY_DB_PATH, CompetencyRepository),
        labour_repo=_open(constants.LABOUR_MARKET_DB_PATH, LabourMarketRepository),
    )
