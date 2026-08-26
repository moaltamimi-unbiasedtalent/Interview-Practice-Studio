"""Structured role repository (SQLite) for normalised occupation data.

Lightweight and explainable — a single SQLite database with the logical tables
from the spec. Every record preserves its ``source_id`` so provenance survives.
Occupations are NOT forced into embeddings; this lane answers role/skill/task
questions directly from structured data.
"""

from __future__ import annotations

import sqlite3
from pydantic import BaseModel, Field

from src.copilot.knowledge.provenance import Provenance

__all__ = ["Skill", "Relationship", "Mapping", "NormalisedOccupation", "RoleRepository"]


class Skill(BaseModel):
    name: str
    skill_type: str = "essential"  # essential | optional | technology


class Relationship(BaseModel):
    related_code: str
    relation_type: str = "related"


class Mapping(BaseModel):
    scheme: str
    code: str


class NormalisedOccupation(BaseModel):
    """A source-neutral occupation record produced by the normalisers."""

    occupation_code: str
    title: str
    source_id: str
    description: str | None = None
    isco_code: str | None = None
    occupation_group: str | None = None
    level: str | None = None  # e.g. major_group / unit_group for ISCO
    aliases: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    knowledge: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    mappings: list[Mapping] = Field(default_factory=list)
    provenance: Provenance | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS occupations (
    occupation_code TEXT PRIMARY KEY, title TEXT, description TEXT,
    isco_code TEXT, occupation_group TEXT, level TEXT, source_id TEXT
);
CREATE TABLE IF NOT EXISTS occupation_aliases (occupation_code TEXT, alias TEXT, source_id TEXT);
CREATE TABLE IF NOT EXISTS occupation_tasks (occupation_code TEXT, task TEXT, source_id TEXT);
CREATE TABLE IF NOT EXISTS occupation_skills (occupation_code TEXT, skill TEXT, skill_type TEXT, source_id TEXT);
CREATE TABLE IF NOT EXISTS occupation_knowledge (occupation_code TEXT, knowledge TEXT, source_id TEXT);
CREATE TABLE IF NOT EXISTS occupation_activities (occupation_code TEXT, activity TEXT, source_id TEXT);
CREATE TABLE IF NOT EXISTS occupation_relationships (occupation_code TEXT, related_code TEXT, relation_type TEXT, source_id TEXT);
CREATE TABLE IF NOT EXISTS occupation_mappings (occupation_code TEXT, scheme TEXT, code TEXT, source_id TEXT);
"""

_TABLES = [
    "occupations", "occupation_aliases", "occupation_tasks", "occupation_skills",
    "occupation_knowledge", "occupation_activities", "occupation_relationships",
    "occupation_mappings",
]


class RoleRepository:
    """SQLite-backed structured role store."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def add_occupation(self, occ: NormalisedOccupation) -> None:
        """Insert/replace an occupation and its related records (idempotent)."""
        code, sid = occ.occupation_code, occ.source_id
        cur = self._conn
        # Replace this occupation's rows so re-ingesting the same code is idempotent.
        cur.execute("DELETE FROM occupations WHERE occupation_code=? AND source_id=?", (code, sid))
        for table in _TABLES[1:]:
            cur.execute(f"DELETE FROM {table} WHERE occupation_code=? AND source_id=?", (code, sid))
        cur.execute(
            "INSERT INTO occupations VALUES (?,?,?,?,?,?,?)",
            (code, occ.title, occ.description, occ.isco_code, occ.occupation_group, occ.level, sid),
        )
        cur.executemany("INSERT INTO occupation_aliases VALUES (?,?,?)", [(code, a, sid) for a in occ.aliases])
        cur.executemany("INSERT INTO occupation_tasks VALUES (?,?,?)", [(code, t, sid) for t in occ.tasks])
        cur.executemany("INSERT INTO occupation_skills VALUES (?,?,?,?)", [(code, s.name, s.skill_type, sid) for s in occ.skills])
        cur.executemany("INSERT INTO occupation_knowledge VALUES (?,?,?)", [(code, k, sid) for k in occ.knowledge])
        cur.executemany("INSERT INTO occupation_activities VALUES (?,?,?)", [(code, a, sid) for a in occ.activities])
        cur.executemany("INSERT INTO occupation_relationships VALUES (?,?,?,?)", [(code, r.related_code, r.relation_type, sid) for r in occ.relationships])
        cur.executemany("INSERT INTO occupation_mappings VALUES (?,?,?,?)", [(code, m.scheme, m.code, sid) for m in occ.mappings])
        self._conn.commit()

    def get_occupation(self, code: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM occupations WHERE occupation_code=?", (code,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["aliases"] = [r["alias"] for r in self._conn.execute("SELECT alias FROM occupation_aliases WHERE occupation_code=?", (code,))]
        out["tasks"] = [r["task"] for r in self._conn.execute("SELECT task FROM occupation_tasks WHERE occupation_code=?", (code,))]
        out["skills"] = [dict(r) for r in self._conn.execute("SELECT skill, skill_type FROM occupation_skills WHERE occupation_code=?", (code,))]
        out["knowledge"] = [r["knowledge"] for r in self._conn.execute("SELECT knowledge FROM occupation_knowledge WHERE occupation_code=?", (code,))]
        out["activities"] = [r["activity"] for r in self._conn.execute("SELECT activity FROM occupation_activities WHERE occupation_code=?", (code,))]
        out["relationships"] = [dict(r) for r in self._conn.execute("SELECT related_code, relation_type FROM occupation_relationships WHERE occupation_code=?", (code,))]
        out["mappings"] = [dict(r) for r in self._conn.execute("SELECT scheme, code FROM occupation_mappings WHERE occupation_code=?", (code,))]
        return out

    def search(self, text: str, limit: int = 10) -> list[dict]:
        """Find occupations by title or alias (case-insensitive substring)."""
        like = f"%{text.lower()}%"
        rows = self._conn.execute(
            "SELECT DISTINCT o.occupation_code, o.title, o.source_id FROM occupations o "
            "LEFT JOIN occupation_aliases a ON a.occupation_code=o.occupation_code "
            "WHERE lower(o.title) LIKE ? OR lower(a.alias) LIKE ? LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def skills_for(self, code: str) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT skill, skill_type FROM occupation_skills WHERE occupation_code=?", (code,))]

    def counts(self) -> dict[str, int]:
        return {t: self._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _TABLES}

    def all_codes(self) -> list[str]:
        return [r["occupation_code"] for r in self._conn.execute("SELECT occupation_code FROM occupations")]

    def counts_by_source(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT source_id, COUNT(*) AS n FROM occupations GROUP BY source_id"
        ).fetchall()
        return {r["source_id"]: r["n"] for r in rows}
