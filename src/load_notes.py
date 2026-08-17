#!/usr/bin/env python3
"""One-time (or repeatable) notes loader.

Usage:
    python src/load_notes.py notes.md              # merge into the concept store
    python src/load_notes.py notes.md --replace     # wipe the store first
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.concepts import ConceptStore, parse_markdown_notes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notes_file", type=Path, help="Markdown file, concepts split by ## headings")
    parser.add_argument("--replace", action="store_true", help="Overwrite the store instead of merging")
    parser.add_argument("--store", type=Path, default=None, help="Path to concepts.json (default: data/concepts.json)")
    args = parser.parse_args()

    if not args.notes_file.exists():
        print(f"Notes file not found: {args.notes_file}", file=sys.stderr)
        return 1

    text = args.notes_file.read_text(encoding="utf-8")
    parsed = parse_markdown_notes(text)
    if not parsed:
        print("No '## Concept Name' sections found in that file — nothing loaded.", file=sys.stderr)
        return 1

    store = ConceptStore(args.store) if args.store else ConceptStore()
    if args.replace:
        store.replace_all(parsed)
        verb = "Replaced with"
    else:
        store.merge(parsed)
        verb = "Merged"
    store.save()

    names = ", ".join(sorted(parsed.keys()))
    print(f"{verb} {len(parsed)} concept(s): {names}")
    print(f"Store now has {len(store)} concept(s) total at {store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
