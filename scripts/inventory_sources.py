"""Inventory the local ``data/raw`` corpus and map it to the source manifest.

Local-first acquisition: this walks the user's existing raw files, identifies the
source / version / geography / storage target for each (by path + filename, and
never overriding an uncertain guess), maps them to ``data/source_manifest.json``,
and writes:

  data/source_inventory.json     — machine-readable inventory + source mapping
  docs/local_source_inventory.md — human-readable report

It is read-only over ``data/raw`` (no move/rename/delete) and makes no network
calls. Counts and hashes are measured, never estimated.

Usage:  python scripts/inventory_sources.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import manifest as km  # noqa: E402

RAW_DIR = Path("data/raw")
INVENTORY_JSON = Path("data/source_inventory.json")
INVENTORY_MD = Path("docs/local_source_inventory.md")

_SKIP = {".DS_Store", ".gitkeep", "README.md"}
_PARSEABLE_EXT = {".csv", ".tsv", ".xlsx", ".xls", ".pdf", ".txt", ".md", ".json"}

# Ordered identification rules: (predicate over the lowercased relative path,
# source_id, detected_version, detected_year, storage_target hint, confidence, note).
# First match wins. Predicates are intentionally specific so a filename alone
# never forces an identity the content does not support.
_STRUCTURED, _VECTOR, _MIXED = "structured", "vector", "mixed"


def _rules():
    P = lambda *subs: (lambda p: all(s in p for s in subs))  # noqa: E731
    return [
        # O*NET database 31.0 (structured occupation taxonomy).
        (P("db_31_0_excel"), "onet", "31.0", 2026, _STRUCTURED, "high", "O*NET 31.0 Excel database"),
        # ESCO v1.2.1 classification CSVs.
        (P("esco dataset - v1.2.1"), "esco", "v1.2.1", 2022, _STRUCTURED, "high", "ESCO v1.2.1 classification (en, csv)"),
        # ESCO Skills/Knowledge–Occupation matrix workbooks + technical report.
        (P("matrix tables_escov1.2.1"), "esco_matrix", "v1.2.1", 2022, _STRUCTURED, "high", "ESCO skill/knowledge–occupation matrix"),
        (P("esco skill-occupation matrix"), "esco_matrix", "v1.2.1", 2022, _VECTOR, "high", "ESCO matrix technical report (narrative)"),
        # ISCO-08.
        (P("isco-08"), "isco08", "ISCO-08", 2008, _STRUCTURED, "high", "ISCO-08 classification"),
        # KldB 2010 (Fassung 2020).
        (P("kldb"), "kldb", "2010 (Fassung 2020)", 2020, _STRUCTURED, "high", "KldB 2010"),
        (P("berufssektoren"), "kldb", "2010 (Fassung 2020)", 2020, _STRUCTURED, "high", "KldB sectors/segments"),
        (P("berufsbenennungen"), "kldb", "2010 (Fassung 2020)", 2020, _STRUCTURED, "medium", "KldB alphabetical index of occupation names"),
        # BLS OEWS May 2025.
        (P("oesm25"), "bls_oews", "M2025", 2025, _STRUCTURED, "high", "BLS OEWS May 2025"),
        (P("occupation_definitions_m2025"), "bls_oews", "M2025", 2025, _STRUCTURED, "high", "OEWS occupation definitions"),
        # ONS ASHE 2025 provisional.
        (P("ashetable"), "ons_ashe", "2025 provisional", 2025, _STRUCTURED, "high", "ONS ASHE 2025 provisional"),
        # WEF Future of Jobs 2025 (narrative).
        (P("wef_future_of_jobs"), "wef_future_of_jobs", "2025", 2025, _VECTOR, "high", "WEF Future of Jobs report 2025"),
        # Cedefop skills forecast 2026 technical report (narrative).
        (P("skills_forecast_2026"), "cedefop_skills_forecast", "2026", 2026, _VECTOR, "high", "Cedefop skills forecast 2026 technical report"),
        # EQF brochure (narrative).
        (P("eqf brochure"), "eqf", "brochure", None, _VECTOR, "high", "EQF explanatory brochure"),
        # NICE / NIST SP 800-181r1 (narrative framework).
        (P("nist.sp.800-181"), "nice_framework", "SP 800-181r1", 2020, _VECTOR, "high", "NICE Workforce Framework (NIST SP 800-181r1)"),
        # UK Civil Service Success Profiles (narrative).
        (P("success_profile_matrices"), "uk_civil_service_success_profiles", "v0f", None, _VECTOR, "high", "Civil Service Success Profile matrices"),
        (P("guidance-application_of_success_profile_guides"), "uk_civil_service_success_profiles", None, None, _VECTOR, "high", "Success Profiles recruitment guidance (EO–Grade 6)"),
        # UK HR Success Profiles (narrative).
        (P("hr_director"), "uk_hr_success_profiles", "v0e", None, _VECTOR, "high", "HR Success Profiles"),
        (P("hr_deputy_director"), "uk_hr_success_profiles", "v0e", None, _VECTOR, "high", "HR Success Profiles (Deputy Director)"),
        (P("success_profile-hr"), "uk_hr_success_profiles", "v0e", None, _VECTOR, "high", "HR Director success profile collection"),
        # OPM Handbook of Occupational Groups and Families (Dec 2018) — job architecture.
        (P("occupationalhandbook"), "opm_occupational_groups", "Dec 2018", 2018, _VECTOR, "high", "OPM Handbook of Occupational Groups & Families"),
        (P("classifierhandbook"), "opm_occupational_groups", "TS-107 1991", 1991, _VECTOR, "medium", "OPM Classifier's Handbook (position classification)"),
        (P("positionclassificationintro"), "opm_occupational_groups", "2009 rev", 2009, _VECTOR, "medium", "OPM Introduction to Position Classification Standards"),
        # Eurostat Structure of Earnings Survey 2022 report (narrative statistical report).
        (P("ks-01-25-044"), "eurostat_earnings", "SES 2022", 2022, _VECTOR, "high", "Eurostat SES 2022 wage-determinants report (narrative, not raw table)"),
        # ESCO Handbook Sept 2017 (narrative).
        (P("handbook.pdf"), "esco_handbook", "Sept 2017", 2017, _VECTOR, "high", "ESCO Handbook (narrative)"),
        # DigComp 3.0 framework (JRC 2025) — narrative.
        (P("jrc144121"), "digcomp", "3.0", 2025, _VECTOR, "high", "DigComp 3.0 framework (JRC 2025)"),
        # NICE Framework Components v2.2.0 — structured (work roles + TKS).
        (P("nice framework components"), "nice_framework", "v2.2.0", 2024, _STRUCTURED, "high", "NICE structured components (work roles + TKS)"),
        # BLS Occupational Outlook Handbook (structured XML compilation).
        (P("ooh xml-compilation"), "bls_ooh", "2025", 2025, _STRUCTURED, "high", "BLS OOH XML compilation"),
        # BLS Employment Projections occupation tables (2025–2035).
        (P("occupation.xlsx"), "bls_projections", "2025-2035", 2025, _STRUCTURED, "high", "BLS Employment Projections occupation tables"),
        # Cedefop STAS (short-term analytical system) — sector-macro, not occupation-level.
        (P("stas_dataset"), "cedefop_stas", "Jan 2026", 2026, _STRUCTURED, "medium", "Cedefop STAS (sector-macro; not normalised into occupation stores)"),
        # Cedefop CLSSI structural labour-shortage index (per-country, ISCO 2-digit).
        (P("clssi"), "cedefop_clssi", "2026", 2026, _STRUCTURED, "high", "Cedefop CLSSI structural shortage index"),
        # Eurostat Job Vacancy Statistics (jvs_a_isco3 default view).
        (P("jvs_a_isco3"), "eurostat_occ_vacancy", "jvs_a_isco3_r1", 2026, _STRUCTURED, "high", "Eurostat job vacancy statistics"),
        # DigComp 2.2 ESCO skills mapping — real structured digital-competence data.
        (P("digcomp 2.2 esco"), "digcomp", "2.2", 2022, _STRUCTURED, "high", "DigComp 2.2 structured (ESCO mapping)"),
    ]


# Loose top-level O*NET workbook names (copies of the db_31_0_excel members).
_ONET_LOOSE = {
    "abilities.xlsx", "knowledge.xlsx", "occupation data.xlsx", "task ratings.xlsx",
    "task statements.xlsx", "work activities.xlsx", "work context.xlsx",
    "work context categories.xlsx", "work styles.xlsx", "related occupations.xlsx",
    "essential skills.xlsx", "software skills.xlsx", "transferable skills.xlsx",
    "education.xlsx", "education categories.xlsx", "job titles.xlsx",
}

_YEAR_RE = re.compile(r"(19|20)\d{2}")


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _identify(rel_lower: str, name_lower: str, rules):
    for predicate, sid, ver, year, storage, conf, note in rules:
        if predicate(rel_lower):
            return sid, ver, year, storage, conf, note
    if name_lower in _ONET_LOOSE:
        return "onet", "31.0", 2026, _STRUCTURED, "high", "O*NET 31.0 loose workbook (top level)"
    return "unresolved", None, None, None, "none", "source identity not confirmed"


def build_inventory() -> dict:
    rules = _rules()
    manifest = {e.source_id: e for e in km.load_manifest(constants.SOURCE_MANIFEST_PATH)}
    files: list[dict] = []

    for path in sorted(RAW_DIR.rglob("*")):
        if not path.is_file() or path.name in _SKIP:
            continue
        rel = path.relative_to(RAW_DIR).as_posix()
        rel_lower, name_lower = rel.lower(), path.name.lower()
        ext = path.suffix.lower()
        sid, ver, year, storage, conf, note = _identify(rel_lower, name_lower, rules)
        entry = manifest.get(sid)
        # A year embedded in the filename can refine detection.
        m = _YEAR_RE.search(name_lower)
        detected_year = year if year is not None else (int(m.group(0)) if m else None)
        files.append({
            "relative_path": rel,
            "filename": path.name,
            "extension": ext,
            "size_bytes": path.stat().st_size,
            "sha256": _hash(path),
            "source_id": sid,
            "likely_publisher": entry.publisher if entry else None,
            "likely_geography": (entry.region or entry.country) if entry else None,
            "likely_source_type": entry.source_type if entry else None,
            "detected_version": ver,
            "detected_reference_year": detected_year,
            "acquisition_method": "local_existing",
            "parseable": ext in _PARSEABLE_EXT,
            "intended_storage_target": storage,
            "licensing_status": (
                "review required" if (entry and entry.licence_review_required)
                else (entry.licence if entry else "unknown")
            ),
            "ingestion_readiness": "ready" if (ext in _PARSEABLE_EXT and sid != "unresolved") else "review",
            "identification_confidence": conf,
            "notes": note,
        })

    # source_id -> [relative paths]
    mapping: dict[str, list[str]] = {}
    for f in files:
        mapping.setdefault(f["source_id"], []).append(f["relative_path"])

    total_bytes = sum(f["size_bytes"] for f in files)
    return {
        "generated": "on-demand",
        "raw_dir": RAW_DIR.as_posix(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "unresolved_count": len(mapping.get("unresolved", [])),
        "source_ids_found": sorted(s for s in mapping if s != "unresolved"),
        "mapping": {k: sorted(v) for k, v in sorted(mapping.items())},
        "files": files,
    }


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n/1024**(['B','KB','MB','GB'].index(unit)):.1f}{unit}"
        n_prev = n
    return f"{n}B"


def _human(inv: dict) -> str:
    lines = ["# Local Source Inventory\n"]
    lines.append("Measured inventory of `data/raw` mapped to `data/source_manifest.json`.")
    lines.append("Read-only over the raw corpus; no files were moved, renamed or deleted.\n")
    lines.append(f"- Files discovered: **{inv['file_count']}**")
    lines.append(f"- Total size: **{inv['total_bytes']/1024/1024:.1f} MB**")
    found = inv["source_ids_found"]
    lines.append(f"- Distinct sources found locally: **{len(found)}**")
    lines.append(f"- Unresolved files: **{inv['unresolved_count']}**\n")

    lines.append("## Source → local files\n")
    for sid, paths in inv["mapping"].items():
        lines.append(f"### `{sid}` — {len(paths)} file(s)")
        for p in paths[:40]:
            lines.append(f"- `{p}`")
        if len(paths) > 40:
            lines.append(f"- … and {len(paths) - 40} more")
        lines.append("")

    lines.append("## Files (measured)\n")
    lines.append("| File | Source | Ver | Year | Store | Parse | Licence | Conf |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for f in inv["files"]:
        lines.append(
            f"| `{f['relative_path']}` | {f['source_id']} | {f['detected_version'] or '—'} | "
            f"{f['detected_reference_year'] or '—'} | {f['intended_storage_target'] or '—'} | "
            f"{'✓' if f['parseable'] else '✗'} | {f['licensing_status']} | {f['identification_confidence']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not RAW_DIR.is_dir():
        print(f"No raw directory at {RAW_DIR}.")
        return 1
    inv = build_inventory()
    INVENTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY_JSON.write_text(json.dumps(inv, indent=2), encoding="utf-8")
    INVENTORY_MD.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY_MD.write_text(_human(inv), encoding="utf-8")

    print(f"Files discovered : {inv['file_count']} ({inv['total_bytes']/1024/1024:.1f} MB)")
    print(f"Sources found    : {len(inv['source_ids_found'])} -> {', '.join(inv['source_ids_found'])}")
    print(f"Unresolved files : {inv['unresolved_count']}")
    print(f"Wrote {INVENTORY_JSON} and {INVENTORY_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
