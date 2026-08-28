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
from pathlib import Path

from src.copilot.knowledge.compensation import CompensationRecord
from src.copilot.knowledge.roles import (
    Mapping,
    NormalisedOccupation,
    Relationship,
    Skill,
)

__all__ = [
    "read_onet", "read_esco", "read_isco", "read_kldb",
    "read_oews", "read_ashe",
]

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
    import pandas as pd

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
