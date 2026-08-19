"""Grounded tutor chat with memory — the conversational counterpart to grading.

Grading is deliberately one-directional: you explain, it judges. This is the
other half — you ask, it answers. The discipline that makes grading trustworthy
is kept here too: the tutor answers from YOUR notes, and when it steps outside
them it must say so explicitly. That keeps it from quietly teaching you things
your source material doesn't support, which is exactly the failure mode an
ungrounded study chatbot has.

It also sees your score history, so "what am I worst at?" and "why did I keep
losing marks on inflation?" are answerable.

Conversation history persists to disk, so the tutor remembers across runs.
`claude -p` is stateless, so the whole exchange is replayed each turn — history
is trimmed to the most recent turns to keep prompts bounded.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.storage import read_json, write_json

DEFAULT_HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "tutor_history.json"

CLAUDE_BIN = "claude"
TUTOR_TIMEOUT_SECONDS = 120

# How much conversation to replay. Enough for real continuity, bounded enough
# that a long-running chat doesn't grow the prompt without limit.
MAX_TURNS_REPLAYED = 12
# Notes are the expensive part of the prompt, so only the most relevant go in.
MAX_NOTES_INCLUDED = 4

SYSTEM_PROMPT = """You are a study tutor for one student. You have their source notes and their \
score history. Follow these rules exactly:

1. Answer primarily from the STUDENT'S NOTES below. They are the authority.
2. If the notes cover the question, answer from them and stay consistent with them.
3. If the notes do NOT cover something you need, you may still answer from general knowledge \
- but you MUST flag it explicitly, e.g. "(your notes don't cover this - from general knowledge:)". \
Never blur the line between what their notes say and what you know.
4. If the notes CONTRADICT what you believe to be true, say so plainly rather than silently \
overriding their notes. Their notes might be wrong, and they need to know that.
5. Use their score history to be specific and personal. Point at actual weak concepts \
rather than giving generic study advice.
6. Be concise and direct. This is a study session, not an essay. Prefer short paragraphs. \
Do not use markdown headers.

Never invent a score, a date, or a concept that is not in the data below."""


class TutorError(RuntimeError):
    pass


@dataclass
class Turn:
    role: str  # "student" or "tutor"
    text: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return {"role": self.role, "text": self.text, "ts": self.ts}

    @classmethod
    def from_dict(cls, data: dict) -> "Turn":
        return cls(
            role=str(data.get("role", "student")),
            text=str(data.get("text", "")),
            ts=str(data.get("ts", "")),
        )


class TutorHistory:
    """Conversation turns, persisted so the tutor remembers across runs."""

    def __init__(self, path: Path | str = DEFAULT_HISTORY_PATH):
        self.path = Path(path)
        self.turns: list[Turn] = []
        self.warning: str | None = None
        self._load()

    def _load(self) -> None:
        raw, self.warning = read_json(self.path)
        self.turns = [Turn.from_dict(t) for t in raw.get("turns", [])]

    def add(self, role: str, text: str) -> None:
        self.turns.append(Turn(role=role, text=text))
        self._save()

    def _save(self) -> None:
        write_json(self.path, {"turns": [t.to_dict() for t in self.turns]})

    def clear(self) -> None:
        self.turns = []
        self._save()

    def recent(self, limit: int = MAX_TURNS_REPLAYED) -> list[Turn]:
        return self.turns[-limit:]

    def __len__(self) -> int:
        return len(self.turns)


# ---------------------------------------------------------------- context


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def relevant_concepts(question: str, concept_names: list[str], limit: int = MAX_NOTES_INCLUDED) -> list[str]:
    """Concepts whose names best match the question, most relevant first."""
    asked = _tokens(question)
    if not asked:
        return []

    scored: list[tuple[int, str]] = []
    for name in concept_names:
        if name.lower() in question.lower():
            scored.append((100, name))  # whole name appears verbatim
            continue
        overlap = len(_tokens(name) & asked)
        if overlap:
            scored.append((overlap, name))

    scored.sort(key=lambda t: (-t[0], t[1]))
    return [name for _, name in scored[:limit]]


def build_history_summary(
    averages: dict[str, float], due: list[tuple[str, int]], total_attempts: int
) -> str:
    """A compact description of how the student is actually doing."""
    if not averages:
        return "The student has not been graded on anything yet."

    ranked = sorted(averages.items(), key=lambda kv: kv[1])
    weakest = ", ".join(f"{c} ({s:.1f}/10)" for c, s in ranked[:5])
    strongest = ", ".join(f"{c} ({s:.1f}/10)" for c, s in reversed(ranked[-3:]))

    lines = [
        f"Total graded explanations: {total_attempts}",
        f"Concepts studied: {len(averages)}",
        f"Weakest: {weakest}",
        f"Strongest: {strongest}",
    ]
    if due:
        lines.append(f"Due for review now: {', '.join(c for c, _ in due[:8])}")
    return "\n".join(lines)


def build_prompt(
    question: str,
    notes: dict[str, str],
    history_summary: str,
    turns: list[Turn],
) -> str:
    parts = [SYSTEM_PROMPT, ""]

    parts.append("=== STUDENT'S NOTES ===")
    if notes:
        for name, text in notes.items():
            parts.append(f"\n## {name}\n{text}")
    else:
        parts.append("(No notes matched this question. Say so if the question needs them.)")

    parts.append("\n=== STUDENT'S SCORE HISTORY ===")
    parts.append(history_summary)

    if turns:
        parts.append("\n=== EARLIER IN THIS CONVERSATION ===")
        for turn in turns:
            speaker = "Student" if turn.role == "student" else "Tutor"
            parts.append(f"{speaker}: {turn.text}")

    parts.append("\n=== STUDENT'S QUESTION ===")
    parts.append(question)
    parts.append("\nAnswer following the rules above.")
    return "\n".join(parts)


# ------------------------------------------------------------------- ask


def ask_claude(prompt: str) -> str:
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=TUTOR_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise TutorError(
            "`claude` CLI not found on PATH. Install Claude Code and run `claude setup-token`."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise TutorError(f"Tutor timed out after {TUTOR_TIMEOUT_SECONDS}s.") from exc

    if proc.returncode != 0:
        raise TutorError(f"`claude -p` exited {proc.returncode}: {proc.stderr.strip()[:400]}")

    reply = proc.stdout.strip()
    if not reply:
        raise TutorError("Tutor returned an empty reply.")
    return reply


def answer(
    question: str,
    concepts,
    progress,
    history: TutorHistory,
    session_id: str,
    ask=ask_claude,
) -> str:
    """Answer one question, grounded in the student's notes and history."""
    names = concepts.names()
    matched = relevant_concepts(question, names)
    notes = {name: concepts.get(name) for name in matched if concepts.get(name)}

    summary = build_history_summary(
        progress.averages(session_id),
        progress.due(session_id),
        progress.total_attempts(session_id),
    )

    prompt = build_prompt(question, notes, summary, history.recent())
    reply = ask(prompt)

    history.add("student", question)
    history.add("tutor", reply)
    return reply
