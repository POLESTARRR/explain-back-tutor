"""Load and search the concept store (concepts.json).

A concept store is a flat JSON object: { "concept name": "source notes text", ... }.
Keys are stored lowercase; lookups are case-insensitive.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "concepts.json"


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


class ConceptStore:
    def __init__(self, path: Path | str = DEFAULT_STORE_PATH):
        self.path = Path(path)
        self._concepts: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self._concepts = json.load(f)
        else:
            self._concepts = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._concepts, f, indent=2, ensure_ascii=False, sort_keys=True)

    def add(self, name: str, notes: str) -> None:
        self._concepts[_normalize(name)] = notes.strip()

    def merge(self, other: dict[str, str]) -> None:
        for name, notes in other.items():
            self.add(name, notes)

    def replace_all(self, other: dict[str, str]) -> None:
        self._concepts = {}
        self.merge(other)

    def save(self) -> None:
        self._save()

    def get(self, name: str) -> str | None:
        return self._concepts.get(_normalize(name))

    def exists(self, name: str) -> bool:
        return _normalize(name) in self._concepts

    def names(self) -> list[str]:
        return sorted(self._concepts.keys())

    def __len__(self) -> int:
        return len(self._concepts)

    def find_close_matches(self, name: str, limit: int = 3) -> list[str]:
        """Substring / prefix match fallback for typos or partial names."""
        target = _normalize(name)
        if not target:
            return []
        scored = []
        for candidate in self._concepts:
            if target == candidate:
                continue
            if candidate.startswith(target) or target in candidate:
                scored.append((0, candidate))
            elif candidate in target:
                scored.append((1, candidate))
            else:
                # cheap token overlap score
                overlap = len(set(target.split()) & set(candidate.split()))
                if overlap:
                    scored.append((2 - overlap, candidate))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [c for _, c in scored[:limit]]


def parse_markdown_notes(text: str) -> dict[str, str]:
    """Split a markdown file into {concept_name: notes} by ``## Heading`` sections.

    Content before the first ``##`` heading is ignored (title/intro material).
    """
    concepts: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    def flush():
        if current_name is not None:
            body = "\n".join(current_lines).strip()
            if body:
                concepts[current_name] = body

    for line in text.splitlines():
        heading = re.match(r"^##\s+(.*\S)\s*$", line)
        if heading:
            flush()
            current_name = heading.group(1)
            current_lines = []
        elif current_name is not None:
            current_lines.append(line)
    flush()
    return concepts
