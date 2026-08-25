"""Ingest the career knowledge base: discover → load → clean → chunk → report.

No embeddings are created (that is a later phase). Processed chunks + a manifest
are written to ``data/processed/`` so the UI and later phases can read the KB.

Usage:
  python scripts/ingest.py                          # ingest data/raw, write processed
  python scripts/ingest.py --raw-dir data/raw --no-write
  python scripts/ingest.py --csv-content-columns title,description \
                           --csv-metadata-columns occupation,year
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.ingestion import indexer  # noqa: E402


def _csv_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [c.strip() for c in value.split(",") if c.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the career knowledge base.")
    parser.add_argument("--raw-dir", default=constants.RAW_DIR)
    parser.add_argument("--no-write", action="store_true", help="Report only.")
    parser.add_argument("--csv-content-columns", default=None)
    parser.add_argument("--csv-metadata-columns", default=None)
    args = parser.parse_args(argv)

    paths = indexer.discover_documents(args.raw_dir)
    if not paths:
        print(
            f"No documents found under {args.raw_dir}. See data/raw/README.md for "
            "how to add sources."
        )
        return 0

    print(f"Discovered {len(paths)} document(s). Ingesting…")
    chunks, report = indexer.ingest_paths(
        paths,
        content_columns=_csv_list(args.csv_content_columns),
        metadata_columns=_csv_list(args.csv_metadata_columns),
    )

    print("\n=== Ingestion report ===")
    print(f"Documents ingested : {report.documents}")
    print(f"Chunks produced    : {report.chunks}")
    print(f"Duplicate files     : {report.skipped_duplicate_files}")
    print(f"By type            : {report.by_type}")
    if report.errors:
        print(f"Errors             : {len(report.errors)}")
        for err in report.errors:
            print(f"  - {err['filename']}: {err['error']}")

    if not args.no_write:
        indexer.write_processed(chunks, report)
        print(
            f"\nWrote {constants.PROCESSED_CHUNKS_FILE} and "
            f"{constants.PROCESSED_MANIFEST_FILE}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
