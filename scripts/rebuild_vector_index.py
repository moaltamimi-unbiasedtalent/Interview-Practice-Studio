"""Rebuild the narrative vector index from processed chunks.

Thin, safe wrapper over scripts/build_index.py with --reset, so narrative
knowledge (methodology, reports, frameworks) is re-embedded into Chroma. Role and
compensation data are structured and are NOT embedded here.

Usage:  python scripts/rebuild_vector_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    from scripts import build_index

    print("Rebuilding the narrative vector index (structured lanes are separate)…")
    return build_index.main(["--reset"])


if __name__ == "__main__":
    sys.exit(main())
