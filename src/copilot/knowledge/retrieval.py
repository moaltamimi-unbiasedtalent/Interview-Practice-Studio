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
                 labour_repo=None, credential_repo=None, manifest_entries=None) -> None:
        self.role_repo = role_repo
        self.comp_repo = comp_repo
        self.competency_repo = competency_repo
        self.labour_repo = labour_repo
        self.credential_repo = credential_repo
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
                  country=None, year=None, version=None, score=1.0, geography=None,
                  metadata=None) -> KnowledgeEvidence:
        m = self._src(source_id)
        return KnowledgeEvidence(
            evidence_id=eid, text=text, source_id=source_id, source_title=m["title"],
            source_url=m["url"], publisher=m["publisher"], evidence_type=etype,
            retrieval_lane=lane, authority_level=m["authority"],
            geography=geography or m["region"], country=country or m["country"],
            region=m["region"], occupation_code=occ_code, occupation_title=occ_title,
            reference_year=year, version=version, score=score, metadata=metadata or {},
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
            elif lane in (RetrievalLane.EDUCATION, RetrievalLane.TRAINING,
                          RetrievalLane.SHORT_TERM_OUTLOOK):
                self._entry_attributes(query, country, out, lane)
            elif lane == RetrievalLane.CERTIFICATION:
                self._certification(query, out)
            elif lane == RetrievalLane.LICENCE:
                self._licence(query, country, out)
            elif lane == RetrievalLane.CURRENT_VACANCY:
                self._current_vacancy(query, out)
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
                score=3.0 if not note else 1.5, text=text,
                metadata={"currency": r.currency, "pay_period": r.pay_period,
                          "statistic": r.statistic_type, "sample_quality": r.sample_quality}))

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

    def _entry_attributes(self, query, country, out, lane) -> None:
        """Education / training / outlook from occupation attributes (BLS OOH, EP)."""
        resolved = self._resolve(query, country, out)
        if not resolved or not resolved.candidates or resolved.ambiguous:
            return
        want = {
            RetrievalLane.EDUCATION: [("entry_education", "education")],
            RetrievalLane.TRAINING: [("work_experience", "training"),
                                     ("on_the_job_training", "training")],
            RetrievalLane.SHORT_TERM_OUTLOOK: [("outlook", "outlook")],
        }[lane]
        seen_sources = set()
        for cand in resolved.candidates:
            base = cand.source_id.split(":", 1)[0]
            if base in seen_sources:
                continue
            occ = self.role_repo.get_occupation(cand.occupation_code)
            out.structured_queries.append(f"role.get_occupation('{cand.occupation_code}')")
            if not occ:
                continue
            emitted = False
            for field_key, etype in want:
                val = occ.get(field_key)
                if val:
                    emitted = True
                    label = field_key.replace("_", " ")
                    out.evidence.append(self._evidence(
                        eid=f"{cand.occupation_code}:{field_key}", source_id=cand.source_id,
                        lane=lane, etype=etype, occ_title=occ.get("title"),
                        occ_code=cand.occupation_code, score=2.5,
                        text=f"{label.capitalize()}: {val}"))
            if emitted:
                seen_sources.add(base)
                if cand.source_id not in out.sources_considered:
                    out.sources_considered.append(cand.source_id)
            if len(seen_sources) >= 2:
                break
        if not out.evidence:
            out.insufficient = True
            out.notes.append(f"No {lane.replace('_', ' ')} attribute found for "
                             f"'{resolved.phrase}'.")

    def _certification(self, query, out) -> None:
        if self.credential_repo is None:
            out.insufficient = True
            out.notes.append("No certification data is loaded.")
            return
        resolved = self._resolve(query, out.country, out)
        phrase = resolved.phrase if resolved else query
        rows = self.credential_repo.certifications_for(phrase) if phrase else []
        out.structured_queries.append(f"credentials.certifications_for('{phrase}')")
        if not rows:
            out.insufficient = True
            out.notes.append(f"No certification records for '{phrase}'.")
            return
        for i, r in enumerate(rows[:_MAX_ITEMS]):
            sid = r.get("source_id", "")
            if sid not in out.sources_considered:
                out.sources_considered.append(sid)
            out.evidence.append(self._evidence(
                eid=f"cert:{sid}:{i}", source_id=sid, lane=RetrievalLane.CERTIFICATION,
                etype="certification", occ_title=r.get("occupation_title"), score=2.3,
                text=f"Certification (optional): {r.get('name')}"
                     + (f" — {r.get('organisation')}" if r.get("organisation") else "")))

    def _licence(self, query, country, out) -> None:
        if self.credential_repo is None:
            out.insufficient = True
            out.notes.append("No occupational-licence data is loaded.")
            return
        resolved = self._resolve(query, country, out)
        phrase = resolved.phrase if resolved else query
        rows = self.credential_repo.licences_for(phrase, country) if phrase else []
        out.structured_queries.append(f"credentials.licences_for('{phrase}', {country!r})")
        if not rows:
            out.insufficient = True
            out.notes.append(f"No occupational-licence record for '{phrase}'"
                             + (f" in {country}." if country else "."))
            return
        for i, r in enumerate(rows[:_MAX_ITEMS]):
            sid = r.get("source_id", "")
            if sid not in out.sources_considered:
                out.sources_considered.append(sid)
            reqs = "; ".join(x for x in [r.get("education_requirement"),
                                         r.get("exam_requirement"),
                                         r.get("experience_requirement")] if x)
            out.evidence.append(self._evidence(
                eid=f"lic:{sid}:{i}", source_id=sid, lane=RetrievalLane.LICENCE,
                etype="licence", occ_title=r.get("occupation"), country=r.get("jurisdiction"),
                score=2.7,
                text=f"Required licence: {r.get('title')} ({r.get('jurisdiction') or 'n/a'})"
                     + (f" — {reqs}" if reqs else "")))

    def _current_vacancy(self, query, out) -> None:
        # Eurostat job-vacancy statistics (country-level; ISCO 'Total' in the
        # default export). Real official data, flagged experimental.
        if self.labour_repo is None or not hasattr(self.labour_repo, "vacancies_for"):
            out.insufficient = True
            out.notes.append("No vacancy source is loaded.")
            return
        country = out.country
        rate_country = {"DE": "germany", "UK": "united kingdom", "US": "united states",
                        "EU": "european union"}.get(country)
        rows = self.labour_repo.vacancies_for(country=rate_country) if rate_country else []
        if not rows:
            rows = self.labour_repo.vacancies_for()  # fall back to all countries
        out.structured_queries.append(f"labour.vacancies_for(country={rate_country!r})")
        # Prefer the vacancy-rate (%) indicator.
        rates = [r for r in rows if (r.get("indicator") or "").lower() == "job vacancy rate"
                 and (r.get("unit") or "").lower() == "percentage"]
        rows = (rates or rows)
        if not rows:
            out.insufficient = True
            out.notes.append("No job-vacancy record is loaded for that geography.")
            return
        for r in rows[:6]:
            sid = r.get("source_id", "")
            if sid not in out.sources_considered:
                out.sources_considered.append(sid)
            exp = " [experimental statistics]" if r.get("experimental") else ""
            out.evidence.append(self._evidence(
                eid=f"vac:{sid}:{r.get('country')}:{r.get('year')}", source_id=sid,
                lane=RetrievalLane.CURRENT_VACANCY, etype="vacancy",
                country=r.get("country"), year=r.get("year"), score=2.4,
                text=(f"{r.get('indicator')}: {r.get('value')}{'%' if (r.get('unit') or '').lower()=='percentage' else ''} "
                      f"in {r.get('country')} ({r.get('year')}), all occupations{exp}.")))
        out.notes.append("Vacancy data is country-level (ISCO 'Total'); per-occupation "
                         "vacancy breakdown is not in the current Eurostat export.")

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
        CredentialRepository,
        LabourMarketRepository,
    )

    def _open(path, cls):
        return cls(path) if os.path.isfile(path) else None

    return StructuredRetrievalCoordinator(
        role_repo=_open(constants.ROLE_DB_PATH, RoleRepository),
        comp_repo=_open(constants.COMPENSATION_DB_PATH, CompensationRepository),
        competency_repo=_open(constants.COMPETENCY_DB_PATH, CompetencyRepository),
        labour_repo=_open(constants.LABOUR_MARKET_DB_PATH, LabourMarketRepository),
        credential_repo=_open(constants.CREDENTIAL_DB_PATH, CredentialRepository),
    )
