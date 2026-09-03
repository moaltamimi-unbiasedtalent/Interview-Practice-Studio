"""Structured compensation repository (SQLite).

Pay statistics are stored with strict context so figures are never implied to be
more precise or comparable than the source allows: statistic type (median/mean),
pay period (annual/monthly/hourly), currency, geography, reference year, and
sample quality. Comparisons must normalise context — the repository never mixes
currencies or periods for you.
"""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel

__all__ = ["CompensationRecord", "CompensationRepository"]


class CompensationRecord(BaseModel):
    source_id: str
    occupation_code: str | None = None
    occupation_title: str = ""
    geography: str = ""
    country: str = ""
    region: str | None = None
    industry: str | None = None
    year: int | None = None
    currency: str = ""
    pay_period: str = "annual"          # annual | monthly | hourly
    statistic_type: str = "median"      # median | mean | percentile
    value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    sample_quality: str | None = None   # e.g. provisional | final
    source_url: str | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS compensation_records (
    source_id TEXT, occupation_code TEXT, occupation_title TEXT, geography TEXT,
    country TEXT, region TEXT, industry TEXT, year INTEGER, currency TEXT,
    pay_period TEXT, statistic_type TEXT, value REAL, lower_bound REAL,
    upper_bound REAL, sample_quality TEXT, source_url TEXT
);
"""

_COLUMNS = [
    "source_id", "occupation_code", "occupation_title", "geography", "country",
    "region", "industry", "year", "currency", "pay_period", "statistic_type",
    "value", "lower_bound", "upper_bound", "sample_quality", "source_url",
]


class CompensationRepository:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def add(self, record: CompensationRecord) -> None:
        values = [getattr(record, c) for c in _COLUMNS]
        self._conn.execute(
            f"INSERT INTO compensation_records ({','.join(_COLUMNS)}) "
            f"VALUES ({','.join(['?'] * len(_COLUMNS))})",
            values,
        )
        self._conn.commit()

    def add_many(self, records) -> int:
        for r in records:
            self.add(r)
        return len(list(records)) if not hasattr(records, "__len__") else len(records)

    def filter(self, *, country: str | None = None, year: int | None = None,
               occupation_code: str | None = None, title: str | None = None) -> list[CompensationRecord]:
        """Filter records by context. Never merges different countries/periods."""
        clauses, params = [], []
        if country:
            clauses.append("lower(country)=?"); params.append(country.lower())
        if year is not None:
            clauses.append("year=?"); params.append(year)
        if occupation_code:
            clauses.append("occupation_code=?"); params.append(occupation_code)
        if title:
            clauses.append("lower(occupation_title) LIKE ?"); params.append(f"%{title.lower()}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(f"SELECT * FROM compensation_records{where}", params).fetchall()
        return [CompensationRecord(**{k: r[k] for k in _COLUMNS}) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM compensation_records").fetchone()[0]

    def countries(self) -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT DISTINCT country FROM compensation_records")]

    def counts_by_source(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT source_id, COUNT(*) AS n FROM compensation_records GROUP BY source_id"
        ).fetchall()
        return {r["source_id"]: r["n"] for r in rows}
