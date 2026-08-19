"""Grades a user's explanation of a concept against source notes, via `claude -p`.

Uses headless Claude Code (your subscription, not the metered API) as the judge.
The model never sees this file's prompt template pre-filled with the user's
notes on disk anywhere else, the notes + explanation are passed fresh each call
so grading always stays grounded in what the user actually wrote for that concept.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from typing import Callable

CLAUDE_BIN = "claude"
GRADE_TIMEOUT_SECONDS = 90
GRADE_ATTEMPTS = 3           # total tries, including the first
RETRY_BACKOFF_SECONDS = 2    # multiplied by the attempt number

GRADING_PROMPT_TEMPLATE = """You are a strict but fair study grader using the Feynman technique. \
A student is trying to prove they understand a concept by explaining it in their own words. \
Grade their explanation ONLY against the source notes below, do not use outside knowledge, \
and do not reward correct-sounding claims that the notes don't actually support.

SOURCE NOTES for "{concept}":
---
{notes}
---

STUDENT'S EXPLANATION:
---
{explanation}
---

Evaluate the explanation and respond with ONLY a single JSON object (no markdown fences, \
no prose outside the JSON) with this exact shape:

{{
  "score": <integer 0-10>,
  "correct": ["point the student got right", ...],
  "vague": ["point the student gestured at but didn't clearly nail down", ...],
  "wrong_or_missing": ["point that is wrong, or an important point from the notes the student left out", ...],
  "notes_gaps": ["claim the student made that is plausible and relevant but that the notes simply don't cover", ...],
  "summary": "one or two sentence overall verdict, direct and specific"
}}

Scoring guide: 9-10 = explained fully and precisely in their own words. 6-8 = core idea right, \
missing nuance or minor gaps. 3-5 = partial/vague understanding, several gaps. 0-2 = mostly wrong \
or a restatement of jargon without real explanation. Empty lists are fine when there's nothing to \
report for that category.

Keep "wrong_or_missing" and "notes_gaps" strictly distinct. Something the notes contradict, or an \
important point the notes make that the student omitted, is wrong_or_missing and should cost them \
score. Something the student asserted that the notes are simply silent on is a notes_gap: it means \
their notes may be incomplete, NOT that the student was wrong, so it must not reduce the score. \
Output raw JSON only."""


class GradingError(RuntimeError):
    """A grading attempt failed.

    `transient` marks failures worth retrying (a timeout, a hiccup in the CLI, a
    malformed reply) as opposed to ones that will fail identically every time
    (the `claude` binary not being installed).
    """

    def __init__(self, message: str, transient: bool = True):
        super().__init__(message)
        self.transient = transient


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    # Strip markdown code fences if the model added them despite instructions.
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fall back to grabbing the first {...} block in case of stray prose.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise GradingError(f"No JSON object found in grader output: {raw[:300]!r}")
    return json.loads(match.group(0))


def _validate(result: dict) -> dict:
    if "score" not in result:
        raise GradingError(f"Grader output missing 'score': {result!r}")
    try:
        score = float(result["score"])
    except (TypeError, ValueError) as exc:
        raise GradingError(f"Grader 'score' is not numeric: {result.get('score')!r}") from exc
    score = max(0.0, min(10.0, score))
    return {
        "score": score,
        "correct": list(result.get("correct") or []),
        "vague": list(result.get("vague") or []),
        "wrong_or_missing": list(result.get("wrong_or_missing") or []),
        "notes_gaps": list(result.get("notes_gaps") or []),
        "summary": str(result.get("summary") or "").strip(),
    }


def _grade_once(concept: str, notes: str, explanation: str) -> dict:
    """One `claude -p` grading attempt. Raises GradingError on any failure."""
    prompt = GRADING_PROMPT_TEMPLATE.format(concept=concept, notes=notes, explanation=explanation)
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=GRADE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        # Retrying cannot fix a missing binary.
        raise GradingError(
            "`claude` CLI not found on PATH. Install Claude Code and run `claude setup-token`.",
            transient=False,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GradingError(f"Grading timed out after {GRADE_TIMEOUT_SECONDS}s.") from exc

    if proc.returncode != 0:
        raise GradingError(f"`claude -p` exited {proc.returncode}: {proc.stderr.strip()[:500]}")

    return _validate(_extract_json(proc.stdout))


def grade_explanation(
    concept: str,
    notes: str,
    explanation: str,
    attempts: int = GRADE_ATTEMPTS,
    on_retry: Callable[[int, GradingError], None] | None = None,
) -> dict:
    """Grade `explanation` against `notes`, retrying transient failures.

    The model occasionally returns prose instead of JSON, and the CLI can time
    out under load. Both are worth one more try before making the user retype a
    long explanation. `on_retry(attempt_number, error)` is called before each
    retry so a UI can say what's happening.

    Raises GradingError once retries are exhausted, so callers decide how to
    surface it rather than silently mis-scoring the user.
    """
    last_error: GradingError | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return _grade_once(concept, notes, explanation)
        except GradingError as exc:
            last_error = exc
            if not exc.transient or attempt >= attempts:
                raise
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    raise last_error  # unreachable; retained so the contract is explicit
