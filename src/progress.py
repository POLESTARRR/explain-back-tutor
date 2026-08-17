"""Per-chat, per-concept score tracking (progress.json).

Layout: { "<chat_id>": { "<concept>": [ {"score": 7, "ts": "2026-08-18T01:10:00Z"}, ... ] } }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "progress.json"


class ProgressStore:
    def __init__(self, path: Path | str = DEFAULT_STORE_PATH):
        self.path = Path(path)
        self._data: dict[str, dict[str, list[dict]]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def record(self, chat_id: str | int, concept: str, score: float) -> None:
        chat_key = str(chat_id)
        chat_scores = self._data.setdefault(chat_key, {})
        entries = chat_scores.setdefault(concept, [])
        entries.append({
            "score": score,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        self._save()

    def history(self, chat_id: str | int, concept: str) -> list[dict]:
        return self._data.get(str(chat_id), {}).get(concept, [])

    def average(self, chat_id: str | int, concept: str) -> float | None:
        entries = self.history(chat_id, concept)
        if not entries:
            return None
        return sum(e["score"] for e in entries) / len(entries)

    def weakest(self, chat_id: str | int, limit: int = 5) -> list[tuple[str, float, int]]:
        """Return [(concept, avg_score, attempts), ...] sorted ascending by avg score."""
        chat_scores = self._data.get(str(chat_id), {})
        rows = []
        for concept, entries in chat_scores.items():
            if not entries:
                continue
            avg = sum(e["score"] for e in entries) / len(entries)
            rows.append((concept, avg, len(entries)))
        rows.sort(key=lambda r: (r[1], -r[2]))
        return rows[:limit]

    def studied_concepts(self, chat_id: str | int) -> list[str]:
        return sorted(self._data.get(str(chat_id), {}).keys())
