"""Shared CLI helpers for the data loaders.

Production loaders must never *silently* fall back to the synthetic sample
corpus. The caller must choose explicitly: ``--source <real path>`` for real
extracts, or ``--fixtures`` for deliberate demo/test data. This helper enforces
that and reports the corresponding data origin so the ledger stays honest.
"""

from __future__ import annotations

import argparse

from src.copilot import constants

FIXTURES_DIR = "evaluations/knowledge_samples"


def add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", default=None,
                        help="Directory of REAL normalised source files.")
    parser.add_argument("--fixtures", action="store_true",
                        help="Deliberately use the committed synthetic sample corpus.")


def resolve_source(args) -> tuple[str, str]:
    """Return ``(source_dir, data_origin)`` or raise SystemExit(2) if unspecified.

    ``--source`` implies real official-local data; ``--fixtures`` implies the
    synthetic fixture corpus. Requiring one of them prevents a production run from
    quietly loading demo data.
    """
    if getattr(args, "source", None):
        return args.source, constants.ORIGIN_OFFICIAL_LOCAL
    if getattr(args, "fixtures", False):
        return FIXTURES_DIR, constants.ORIGIN_SYNTHETIC_FIXTURE
    raise SystemExit(
        "Refusing to guess a data source. Pass --source <real path> for official "
        "data, or --fixtures for the synthetic demo/test corpus."
    )
