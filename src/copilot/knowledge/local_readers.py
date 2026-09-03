"""Local-first readers for the real source files under ``data/raw``.

These parse the user's actual downloaded datasets (O*NET 31.0, ESCO v1.2.1,
ISCO-08, KldB 2010, BLS OEWS, ONS ASHE) into the shared normalised models so the
structured stores are built from real data — no network, no fabrication. Each
reader is defensive: a missing/renamed file yields an empty result rather than
crashing, and every record keeps its ``source_id`` provenance.

Readers are intentionally bounded (e.g. O*NET keeps important skills/knowledge,
not every rating row) to keep the derived SQLite stores compact and explainable.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from src.copilot.knowledge.compensation import CompensationRecord
from src.copilot.knowledge.roles import (
    Mapping,
    NormalisedOccupation,
    Relationship,
    Skill,
)
from src.copilot.knowledge.structured_ext import (
    Competency,
    LabourForecast,
    LabourOpenings,
    LabourShortage,
    LabourVacancy,
)

__all__ = [
    "read_onet", "read_esco", "read_isco", "read_kldb",
    "read_oews", "read_ashe", "read_ooh", "read_nice_structured",
    "read_bls_projections", "read_bls_ep_characteristics",
    "read_cedefop_clssi", "read_eurostat_vacancy", "read_digcomp_structured",
]

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    import html

    text = html.unescape(_TAG_RE.sub(" ", str(text)))
    return re.sub(r"\s+", " ", text).strip()

# O*NET importance scale id; keep elements at/above this importance so rows stay
# meaningful without storing the full rating matrix.
_ONET_IMPORTANCE_MIN = 3.0


def _df(path, **kwargs):
    import pandas as pd

    return pd.read_excel(path, **kwargs)


# --- O*NET 31.0 --------------------------------------------------------------


def read_onet(raw_dir: str = "data/raw/db_31_0_excel", *, source_id: str = "onet"):
    """Read the O*NET 31.0 Excel database into NormalisedOccupations."""
    d = Path(raw_dir)
    occ_file = d / "Occupation Data.xlsx"
    if not occ_file.is_file():
        return []
    import pandas as pd

    occ = _df(occ_file).rename(columns={"O*NET-SOC Code": "code"})

    def _grouped(name, key, how=None, importance=False):
        p = d / name
        if not p.is_file():
            return {}
        frame = _df(p).rename(columns={"O*NET-SOC Code": "code"})
        if importance:
            frame = frame[(frame.get("Scale ID") == "IM")
                          & (frame.get("Data Value") >= _ONET_IMPORTANCE_MIN)]
        out: dict[str, list[str]] = {}
        for code, sub in frame.groupby("code"):
            vals = [str(v) for v in sub[key].dropna().tolist()]
            # De-duplicate, preserve order, cap to keep rows bounded.
            seen, kept = set(), []
            for v in vals:
                if v not in seen:
                    seen.add(v); kept.append(v)
            out[str(code)] = kept[:25]
        return out

    tasks = _grouped("Task Statements.xlsx", "Task")
    skills = _grouped("Essential Skills.xlsx", "Element Name", importance=True)
    knowledge = _grouped("Knowledge.xlsx", "Element Name", importance=True)
    activities = _grouped("Work Activities.xlsx", "Element Name", importance=True)
    tech = _grouped("Software Skills.xlsx", "Element Name")

    related: dict[str, list[str]] = {}
    rel_file = d / "Related Occupations.xlsx"
    if rel_file.is_file():
        rf = _df(rel_file).rename(columns={"O*NET-SOC Code": "code"})
        for code, sub in rf.groupby("code"):
            related[str(code)] = [str(c) for c in sub["Related O*NET-SOC Code"].dropna().tolist()][:10]

    out: list[NormalisedOccupation] = []
    for _, row in occ.iterrows():
        code = str(row["code"])
        out.append(NormalisedOccupation(
            occupation_code=code,
            title=str(row.get("Title") or code),
            source_id=source_id,
            description=(str(row["Description"]) if not pd.isna(row.get("Description")) else None),
            tasks=tasks.get(code, []),
            skills=([Skill(name=n, skill_type="essential") for n in skills.get(code, [])]
                    + [Skill(name=n, skill_type="technology") for n in tech.get(code, [])]),
            knowledge=knowledge.get(code, []),
            activities=activities.get(code, []),
            relationships=[Relationship(related_code=c, relation_type="related")
                           for c in related.get(code, [])],
        ))
    return out


# --- ESCO v1.2.1 -------------------------------------------------------------


def read_esco(raw_dir: str = "data/raw/ESCO dataset - v1.2.1 - classification - en - csv",
              *, source_id: str = "esco", limit: int | None = None):
    """Read ESCO occupations + skill relations into NormalisedOccupations."""
    import pandas as pd

    d = Path(raw_dir)
    occ_file = d / "occupations_en.csv"
    if not occ_file.is_file():
        return []
    occ = pd.read_csv(occ_file)
    rel_file = d / "occupationSkillRelations_en.csv"
    ess: dict[str, list[str]] = {}
    opt: dict[str, list[str]] = {}
    if rel_file.is_file():
        rel = pd.read_csv(rel_file)
        for uri, sub in rel.groupby("occupationUri"):
            e = sub[sub["relationType"] == "essential"]["skillLabel"].dropna().tolist()
            o = sub[sub["relationType"] == "optional"]["skillLabel"].dropna().tolist()
            ess[uri] = [str(x) for x in e][:25]
            opt[uri] = [str(x) for x in o][:15]

    rows = occ.itertuples(index=False)
    out: list[NormalisedOccupation] = []
    for r in rows:
        uri = getattr(r, "conceptUri", None)
        code = str(getattr(r, "code", None) or uri or getattr(r, "preferredLabel", ""))
        isco = getattr(r, "iscoGroup", None)
        alt = getattr(r, "altLabels", None)
        aliases = [a.strip() for a in str(alt).split("\n") if a and a.strip()] if alt and not pd.isna(alt) else []
        desc = getattr(r, "description", None)
        out.append(NormalisedOccupation(
            occupation_code=code,
            title=str(getattr(r, "preferredLabel", None) or code),
            source_id=source_id,
            description=(str(desc) if desc and not pd.isna(desc) else None),
            isco_code=(str(int(isco)) if isco and not pd.isna(isco) else None),
            aliases=aliases[:10],
            skills=([Skill(name=n, skill_type="essential") for n in ess.get(uri, [])]
                    + [Skill(name=n, skill_type="optional") for n in opt.get(uri, [])]),
            mappings=([Mapping(scheme="isco", code=str(int(isco)))]
                      if isco and not pd.isna(isco) else []),
        ))
        if limit and len(out) >= limit:
            break
    return out


# --- ISCO-08 -----------------------------------------------------------------


_ISCO_LEVELS = {1: "major_group", 2: "sub_major_group", 3: "minor_group", 4: "unit_group"}


def read_isco(path: str = "data/raw/ISCO-08 EN Structure and definitions.xlsx",
              *, source_id: str = "isco08"):
    """Read the ISCO-08 structure workbook into NormalisedOccupations."""
    if not os.path.isfile(path):
        return []
    import pandas as pd

    df = _df(path, sheet_name=0)
    out: list[NormalisedOccupation] = []
    for _, row in df.iterrows():
        code = row.get("ISCO 08 Code")
        if pd.isna(code):
            continue
        code = str(int(code)) if isinstance(code, float) else str(code)
        level = int(row["Level"]) if not pd.isna(row.get("Level")) else None
        parent = code[:-1] if level and level > 1 else None
        tasks_raw = row.get("Tasks include")
        tasks = []
        if tasks_raw and not pd.isna(tasks_raw):
            tasks = [t.strip(" ;") for t in str(tasks_raw).split(";") if t.strip()][:15]
        out.append(NormalisedOccupation(
            occupation_code=code,
            title=str(row.get("Title EN") or code),
            source_id=source_id,
            description=(str(row["Definition"]) if not pd.isna(row.get("Definition")) else None),
            isco_code=code,
            level=_ISCO_LEVELS.get(level or 0),
            tasks=tasks,
            relationships=[Relationship(related_code=parent, relation_type="parent")] if parent else [],
        ))
    return out


# --- KldB 2010 ---------------------------------------------------------------


def read_kldb(path: str = "data/raw/Systematisches-Verzeichnis-KldB-2020.xlsx",
              *, source_id: str = "kldb"):
    """Read the KldB 2010 systematic index (long labels) into NormalisedOccupations."""
    if not os.path.isfile(path):
        return []
    import pandas as pd

    df = _df(path, sheet_name="Systematik_Langbezeichnungen", header=None, skiprows=5)
    out: list[NormalisedOccupation] = []
    for _, row in df.iterrows():
        code = row.iloc[0]
        title = row.iloc[1]
        if pd.isna(code) or pd.isna(title):
            continue
        code = str(code).strip()
        level = len(code)  # KldB code length == hierarchy level
        parent = code[:-1] if level > 1 else None
        out.append(NormalisedOccupation(
            occupation_code=code,
            title=str(title).strip(),
            source_id=source_id,
            level=str(level),
            relationships=[Relationship(related_code=parent, relation_type="parent")] if parent else [],
        ))
    return out


# --- BLS OEWS (compensation) -------------------------------------------------


def read_oews(path: str = "data/raw/oesm25nat/oesm25nat/national_M2025_dl.xlsx",
              *, source_id: str = "bls_oews", year: int = 2025):
    """Read BLS OEWS national annual wages into CompensationRecords."""
    if not os.path.isfile(path):
        return []

    df = _df(path)

    def _num(v):
        try:
            f = float(v)
            return f if f == f else None  # drop NaN
        except (TypeError, ValueError):
            return None  # '*' / '#' suppression markers

    out: list[CompensationRecord] = []
    for _, row in df.iterrows():
        # Keep detailed + broad occupations, skip the "total" aggregate row.
        if str(row.get("O_GROUP", "")).lower() == "total":
            continue
        median = _num(row.get("A_MEDIAN"))
        if median is None:
            continue
        out.append(CompensationRecord(
            source_id=source_id,
            occupation_code=str(row.get("OCC_CODE") or ""),
            occupation_title=str(row.get("OCC_TITLE") or ""),
            geography="US", country="US", year=year,
            currency="USD", pay_period="annual", statistic_type="median",
            value=median,
            lower_bound=_num(row.get("A_PCT10")),
            upper_bound=_num(row.get("A_PCT90")),
            sample_quality="final",
            source_url="https://www.bls.gov/oes/",
        ))
    return out


# --- ONS ASHE (compensation) -------------------------------------------------


def read_ashe(path: str = ("data/raw/ashetable142025provisional/"
                           "PROV - Occupation SOC20 (4) Table 14.1a   Weekly pay - Gross 2025.xlsx"),
              *, source_id: str = "ons_ashe", year: int = 2025):
    """Read ONS ASHE Table 14.1a (gross weekly pay, all employees) into records.

    ASHE tables carry a description block, then a header row containing
    "Description"/"Code"/"Median"; rows are (occupation, SOC code, median, …).
    Suppressed values ("x") are skipped.
    """
    if not os.path.isfile(path):
        return []
    import pandas as pd

    raw = _df(path, sheet_name="All", header=None)
    # Locate the header row (contains both "Description" and "Median").
    header_idx = None
    for i in range(min(30, len(raw))):
        cells = [str(c).strip().lower() for c in raw.iloc[i].tolist()]
        if "description" in cells and "median" in cells:
            header_idx = i
            break
    if header_idx is None:
        return []
    header = [str(c).strip() for c in raw.iloc[header_idx].tolist()]
    body = raw.iloc[header_idx + 1:].copy()
    body.columns = header
    lower = {c.lower(): c for c in header}
    desc_c, code_c, med_c = lower.get("description"), lower.get("code"), lower.get("median")
    if not (desc_c and med_c):
        return []

    def _num(v):
        try:
            f = float(str(v).replace(",", ""))
            return f if f == f else None
        except (TypeError, ValueError):
            return None

    out: list[CompensationRecord] = []
    for _, row in body.iterrows():
        title = row.get(desc_c)
        median = _num(row.get(med_c))
        if not title or pd.isna(title) or median is None:
            continue
        code = row.get(code_c) if code_c else None
        out.append(CompensationRecord(
            source_id=source_id,
            occupation_code=(str(code).strip() if code and not pd.isna(code) else None),
            occupation_title=str(title).strip(),
            geography="UK", country="UK", year=year,
            currency="GBP", pay_period="weekly", statistic_type="median",
            value=median,
            sample_quality="provisional",
            source_url="https://www.ons.gov.uk/",
        ))
    return out


# --- BLS Occupational Outlook Handbook (structured XML) ----------------------


def read_ooh(path: str = "data/raw/OOH xml-compilation.xml", *, source_id: str = "bls_ooh"):
    """Read the BLS OOH XML compilation into NormalisedOccupations.

    Each ``<occupation>`` carries HTML summary blocks; we keep a plain-text
    'what they do' description plus a short list of duties parsed from list items.
    """
    if not os.path.isfile(path):
        return []
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []

    out: list[NormalisedOccupation] = []
    for occ in root.findall(".//occupation"):
        title = (occ.findtext("title") or "").strip()
        if not title:
            continue
        code = (occ.findtext("occupation_code") or occ.findtext("soc_coverage") or "").strip()
        what = occ.findtext("summary_what_they_do") or ""
        # Duties: list items inside the HTML, if any.
        duties = [_strip_html(li) for li in re.findall(r"<li>(.*?)</li>", what, re.S)]
        duties = [d for d in duties if d][:15]
        # Education/training (how to become one), outlook, related occupations.
        how = _strip_html(occ.findtext("summary_how_to_become_one"))[:600] or None
        outlook = _strip_html(occ.findtext("summary_outlook"))[:600] or None
        similar_html = occ.findtext("summary_similar_occupations") or ""
        related = [_strip_html(a) for a in re.findall(r"<a[^>]*>(.*?)</a>", similar_html, re.S)]
        related = [r for r in dict.fromkeys(related) if r][:10]
        out.append(NormalisedOccupation(
            occupation_code=code or title,
            title=title,
            source_id=source_id,
            description=_strip_html(what)[:800] or None,
            tasks=duties,
            entry_education=how,
            outlook=outlook,
            relationships=[Relationship(related_code=r, relation_type="similar") for r in related],
        ))
    return out


def read_bls_ep_characteristics(path: str = "data/raw/occupation.xlsx",
                                *, source_id: str = "bls_projections"):
    """Read BLS EP Table 1.2 (worker characteristics) into occupation attributes.

    Provides entry education, related work experience, on-the-job training and a
    growth-based outlook per US occupation. The median wage is captured as
    *contextual* supporting evidence only — OEWS remains the primary wage source.
    """
    if not os.path.isfile(path):
        return []
    import pandas as pd

    xl = pd.ExcelFile(path)
    if "Table 1.2" not in xl.sheet_names:
        return []
    df = pd.read_excel(xl, "Table 1.2", header=1)

    def col(*needles):
        for c in df.columns:
            cl = str(c).lower()
            if all(n in cl for n in needles):
                return c
        return None

    title_c = col("title")
    code_c = col("code")
    type_c = col("occupation type")
    edu_c = col("typical education")
    exp_c = col("work experience")
    ojt_c = col("on-the-job training")
    growth_c = col("employment change", "percent")
    col("median annual wage")

    def _s(v):
        return None if v is None or (isinstance(v, float) and v != v) else str(v).strip() or None

    out: list[NormalisedOccupation] = []
    for _, row in df.iterrows():
        title = _s(row.get(title_c))
        if not title or title.lower().startswith("total"):
            continue
        if type_c and str(row.get(type_c) or "").strip().lower() != "line item":
            continue
        growth = row.get(growth_c) if growth_c else None
        outlook = None
        try:
            g = float(growth)
            trend = ("much faster than average" if g >= 8 else "faster than average" if g >= 5
                     else "about as fast as average" if g >= 2 else "little or no change" if g >= -1
                     else "decline")
            outlook = f"Projected 2025–35 employment change {g:g}% ({trend})."
        except (TypeError, ValueError):
            pass
        # Median wage is intentionally NOT stored here — OEWS remains the primary
        # wage source; EP wage is only contextual and would duplicate it.
        out.append(NormalisedOccupation(
            occupation_code=_s(row.get(code_c)) or title,
            title=title,
            source_id=source_id,
            entry_education=_s(row.get(edu_c)) if edu_c else None,
            work_experience=_s(row.get(exp_c)) if exp_c else None,
            on_the_job_training=_s(row.get(ojt_c)) if ojt_c else None,
            outlook=outlook,
        ))
    return out


# --- NICE Framework Components v2.2.0 (structured competencies) ---------------


def read_nice_structured(path: str = "data/raw/NICE Framework Components v2.2.0.xlsx",
                         *, source_id: str = "nice_framework"):
    """Read NICE work roles + TKS statements into Competency records.

    Returns a list of :class:`Competency` (framework 'NICE'): work roles become
    competencies in an 'Work Role' area; TKS statements become competencies typed
    by their id prefix (T=Task, K=Knowledge, S=Skill).
    """
    if not os.path.isfile(path):
        return []
    import pandas as pd

    comps: list[Competency] = []
    xl = pd.ExcelFile(path)

    # Work roles.
    if "v2.2.0 Work Roles + Categories" in xl.sheet_names:
        wr = pd.read_excel(xl, "v2.2.0 Work Roles + Categories")
        for _, row in wr.iterrows():
            name = str(row.get("Work Role") or "").strip()
            wid = row.get("Work Role ID")
            if not name or pd.isna(wid):  # skip category header rows (no id)
                continue
            comps.append(Competency(source_id=source_id, framework="NICE",
                                    area="Work Role", name=name[:200],
                                    description=_strip_html(row.get("Work Role Description")) or None))

    # TKS statements (Task/Knowledge/Skill).
    if "v2.2.0 TKS Statements" in xl.sheet_names:
        tks = pd.read_excel(xl, "v2.2.0 TKS Statements")
        kind = {"T": "Task", "K": "Knowledge", "S": "Skill"}
        for _, row in tks.iterrows():
            tid = str(row.get("TKS ID") or "").strip()
            desc = str(row.get("TKS Description") or "").strip()
            if not tid or not desc:
                continue
            area = kind.get(tid[:1].upper(), "TKS")
            comps.append(Competency(source_id=source_id, framework="NICE",
                                    area=area, name=desc[:250], description=None))
    return comps


# --- BLS Employment Projections (structured labour-market) --------------------


def read_bls_projections(path: str = "data/raw/occupation.xlsx",
                         *, source_id: str = "bls_projections", year: int = 2025):
    """Read BLS Employment Projections Table 1.10 into forecasts + openings (US)."""
    if not os.path.isfile(path):
        return [], []
    import pandas as pd

    xl = pd.ExcelFile(path)
    if "Table 1.10" not in xl.sheet_names:
        return [], []
    df = pd.read_excel(xl, "Table 1.10", header=1)
    cols = {c: c for c in df.columns}
    title_c = next((c for c in cols if "title" in str(c).lower()), None)
    next((c for c in cols if "code" in str(c).lower()), None)
    type_c = next((c for c in cols if "occupation type" in str(c).lower()), None)
    pct_c = next((c for c in cols if "percent" in str(c).lower()), None)
    open_c = next((c for c in cols if "openings" in str(c).lower()), None)

    def _num(v):
        try:
            f = float(v)
            return f if f == f else None
        except (TypeError, ValueError):
            return None

    forecasts: list[LabourForecast] = []
    openings: list[LabourOpenings] = []
    for _, row in df.iterrows():
        title = str(row.get(title_c) or "").strip()
        if not title or title.lower().startswith("total"):
            continue
        # Only detailed line items, not summary aggregates.
        if type_c and str(row.get(type_c) or "").strip().lower() != "line item":
            continue
        pct = _num(row.get(pct_c)) if pct_c else None
        if pct is not None:
            forecasts.append(LabourForecast(
                source_id=source_id, occupation=title, country="US",
                employment_change=pct / 100.0, horizon="2025-2035", reference_year=year))
        openings_val = _num(row.get(open_c)) if open_c else None
        if openings_val is not None:
            openings.append(LabourOpenings(
                source_id=source_id, occupation=title, geography="US",
                period="2025-2035 annual avg", total_openings=openings_val))
    return forecasts, openings


# --- Cedefop CLSSI (structural labour-shortage index) ------------------------


def read_cedefop_clssi(path: str = "data/raw/2026_cedefop_labour_skills_shortage_index_clssi_dataset.xlsx",
                       *, source_id: str = "cedefop_clssi", period: str = "2026"):
    """Read the Cedefop CLSSI (per-country sheets) into LabourShortage records.

    Each sheet is a country (EU27, AT, BE, …); each row is a 2-digit ISCO
    occupation group with a Labour Shortage Index. This is *structural* shortage
    (kept distinct from real-time demand and long-term forecasts).
    """
    if not os.path.isfile(path):
        return []
    import pandas as pd

    xl = pd.ExcelFile(path)
    out: list[LabourShortage] = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet)
        occ_c = next((c for c in df.columns if "2 digit" in str(c).lower() or "occupation group" in str(c).lower()), None)
        idx_c = next((c for c in df.columns if "shortage index" in str(c).lower()), None)
        main_c = next((c for c in df.columns if "main occupation" in str(c).lower()), None)
        if not (occ_c and idx_c):
            continue
        for _, row in df.iterrows():
            occ = row.get(occ_c)
            val = row.get(idx_c)
            if occ is None or pd.isna(occ) or pd.isna(val):
                continue
            try:
                score = float(val)
            except (TypeError, ValueError):
                continue
            band = ("high shortage" if score >= 3.5 else "shortage" if score >= 2.5
                    else "balanced" if score >= 1.5 else "surplus")
            out.append(LabourShortage(
                source_id=source_id, occupation=str(occ).strip(), country=str(sheet).strip(),
                skill_level=(str(row.get(main_c)).strip() if main_c and not pd.isna(row.get(main_c)) else None),
                shortage_indicator=f"CLSSI {score:.2f} ({band})", period=period))
    return out


# --- Eurostat Job Vacancy Statistics (jvs_a_isco3 default view) ---------------


def read_eurostat_vacancy(path: str = "data/raw/jvs_a_isco3_r1$defaultview_spreadsheet.xlsx",
                          *, source_id: str = "eurostat_occ_vacancy"):
    """Read Eurostat job-vacancy sheets into LabourVacancy records (country level).

    The default-view export carries the ISCO dimension as "Total" (not broken out
    by occupation), so this yields country-level job-vacancy-rate and job-vacancy
    counts by year. Eurostat JVS-by-occupation is experimental — flagged as such.
    """
    if not os.path.isfile(path):
        return []
    import pandas as pd

    xl = pd.ExcelFile(path)
    wanted = {"Job vacancy rate", "Job vacancies"}
    out: list[LabourVacancy] = []
    for sheet in xl.sheet_names:
        if not sheet.lower().startswith("sheet"):
            continue
        raw = pd.read_excel(xl, sheet, header=None)
        meta = {}
        header_idx = None
        for i in range(min(15, len(raw))):
            key = str(raw.iloc[i, 0])
            val = str(raw.iloc[i, 2]) if raw.shape[1] > 2 else ""
            if "Classification" in key:
                meta["isco"] = val
            if "indicator" in key.lower():
                meta["indicator"] = val
            if "Unit" in key:
                meta["unit"] = val
            if key.strip().upper() == "TIME":
                header_idx = i
        if meta.get("indicator") not in wanted or header_idx is None:
            continue
        # Year columns are on the TIME row; values on GEO rows below "GEO (Labels)".
        years = {}
        for j, cell in enumerate(raw.iloc[header_idx].tolist()):
            try:
                y = int(float(cell))
                if 1990 <= y <= 2100:
                    years[j] = y
            except (TypeError, ValueError):
                pass
        geo_start = header_idx + 1
        for i in range(header_idx + 1, len(raw)):
            if str(raw.iloc[i, 0]).strip().upper().startswith("GEO"):
                geo_start = i + 1
                break
        for i in range(geo_start, len(raw)):
            geo = raw.iloc[i, 0]
            if geo is None or (isinstance(geo, float) and geo != geo) or not str(geo).strip():
                continue
            geo_s = str(geo).strip()
            # The GEO block ends at the flag/footnote legend.
            if geo_s.lower().startswith(("special value", "available flags", "flags:", ":")):
                break
            # Pick the most recent real value across year columns (skip ":" / NaN).
            val = None; year = None
            for j in sorted(years, key=lambda k: -years[k]):
                cell = raw.iloc[i, j] if j < raw.shape[1] else None
                try:
                    f = float(cell)
                except (TypeError, ValueError):
                    continue
                if f == f:  # not NaN
                    val = f; year = years[j]; break
            if val is None:
                continue
            out.append(LabourVacancy(
                source_id=source_id, occupation=meta.get("isco", "Total") or "Total",
                country=str(geo).strip(), year=year, indicator=meta.get("indicator"),
                unit=meta.get("unit"), value=val, experimental=True))
    return out


# --- DigComp 2.2 (real structured competences from the ESCO mapping) ----------


def read_digcomp_structured(path: str = "data/raw/DigComp 2.2 ESCO Skills Mapping.xlsx",
                            *, source_id: str = "digcomp"):
    """Read the DigComp 2.2 competences from the ESCO↔DigComp mapping workbook.

    Rows flagged ``MapDigComp == 1`` carry the DigComp competence in the
    ``DigComp 1..4`` columns (e.g. "1.3: Managing data …"). We emit the distinct
    DigComp 2.2 competences (area parsed from the "X.Y" code) — real structured
    framework data replacing the earlier sample.
    """
    if not os.path.isfile(path):
        return []
    import pandas as pd

    sheet = "ESCO DigComp OJA mapping"
    xl = pd.ExcelFile(path)
    if sheet not in xl.sheet_names:
        return []
    df = pd.read_excel(xl, sheet)
    mapped = df[df.get("MapDigComp") == 1] if "MapDigComp" in df.columns else df

    _AREAS = {"1": "Information and data literacy", "2": "Communication and collaboration",
              "3": "Digital content creation", "4": "Safety", "5": "Problem solving"}
    seen: dict[str, Competency] = {}
    for _, row in mapped.iterrows():
        for col in ("DigComp 1", "DigComp 2", "DigComp 3", "DigComp 4"):
            comp = row.get(col)
            if comp is None or (isinstance(comp, float) and comp != comp) or not str(comp).strip():
                continue
            comp = str(comp).strip()
            if comp in seen:
                continue
            area = _AREAS.get(comp.split(".", 1)[0], "DigComp")
            name = comp.split(":", 1)[1].strip() if ":" in comp else comp
            seen[comp] = Competency(source_id=source_id, framework="DigComp 2.2",
                                    area=area, name=name, description=comp)
    return list(seen.values())
