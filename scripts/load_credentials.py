"""Load certifications + occupational licences into the credential store.

Certifications (optional professional credentials) and occupational licences
(legal requirement to practise) are kept as separate models. Real sources
(e.g. CareerOneStop) are not yet present locally, so this ships schema-derived
sample fixtures — use ``--fixtures`` deliberately, or ``--source`` for real JSON.
Origin is recorded so fixture data is never presented as real official data.

Usage:
  python scripts/load_credentials.py --fixtures
  python scripts/load_credentials.py --source path/to/dir
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import origins as korigins  # noqa: E402
from src.copilot.knowledge.loader_cli import add_source_args, resolve_source  # noqa: E402
from src.copilot.knowledge.structured_ext import (  # noqa: E402
    Certification,
    CredentialRepository,
    OccupationLicence,
)

# Fixture credentials stand in for CareerOneStop until the real export is present.
_SOURCE_ID = "careeronestop"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load certifications + licences.")
    add_source_args(parser)
    parser.add_argument("--db", default=constants.CREDENTIAL_DB_PATH)
    args = parser.parse_args(argv)
    source_dir, origin = resolve_source(args)

    certs_path = os.path.join(source_dir, "certifications.json")
    lic_path = os.path.join(source_dir, "licences.json")
    if not (os.path.isfile(certs_path) or os.path.isfile(lic_path)):
        print(f"No credential files under {source_dir}.")
        return 0

    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    if os.path.isfile(args.db):
        os.remove(args.db)
    repo = CredentialRepository(args.db)

    n_cert = n_lic = 0
    if os.path.isfile(certs_path):
        for row in json.load(open(certs_path, encoding="utf-8")):
            repo.add_certification(Certification(source_id=_SOURCE_ID, **row))
            n_cert += 1
    if os.path.isfile(lic_path):
        for row in json.load(open(lic_path, encoding="utf-8")):
            repo.add_licence(OccupationLicence(source_id=_SOURCE_ID, **row))
            n_lic += 1
    repo.close()
    korigins.record_origins({_SOURCE_ID: origin})
    print(f"Credential DB {args.db}: {n_cert} certification(s), {n_lic} licence(s).")
    print(f"Recorded data origin: {{'{_SOURCE_ID}': '{origin}'}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
