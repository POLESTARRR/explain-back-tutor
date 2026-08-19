#!/usr/bin/env python3
"""Browser front end, the same engine the terminal uses, with a UI.

    python src/webapp.py                 # http://127.0.0.1:5050
    python src/webapp.py --port 8080

This is a real read/write interface: explain concepts and get graded, upload
photos of notes, ask the tutor, and see your progress. It adds no study logic of
its own, every route delegates to the same modules `study.py` calls, so the two
front ends can never disagree about a score or a schedule.

It binds to localhost by default. `--host 0.0.0.0` exposes it to your network,
which is unauthenticated by design, so it warns loudly.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.concepts import UNCATEGORIZED, ConceptStore, parse_markdown_notes  # noqa: E402
from src.gamification import (  # noqa: E402
    ALL_BADGES,
    attempt_xp,
    current_streak,
    earned_badge_keys,
    earned_badges,
    level_for_xp,
    longest_streak,
    total_xp,
)
from src.grader import GradingError, grade_explanation  # noqa: E402
from src.import_notes import ImportError_, transcribe_image  # noqa: E402
from src.progress import ProgressStore  # noqa: E402
from src.scheduler import pick_next  # noqa: E402
from src.tutor import TutorError, TutorHistory  # noqa: E402
from src.tutor import answer as tutor_answer  # noqa: E402

SESSION_ID = "local"  # shared with the terminal, so progress is one history
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def stores() -> tuple[ConceptStore, ProgressStore]:
    """Fresh stores per request, they're small, and this avoids stale reads
    when the terminal is used alongside the browser."""
    return ConceptStore(), ProgressStore()


# ------------------------------------------------------------------ pages


@app.get("/")
def study_page():
    concepts, progress = stores()
    names = concepts.names()

    requested = (request.args.get("concept") or "").strip().lower()
    reason = None
    concept = None

    if requested and concepts.exists(requested):
        concept = requested
    elif names:
        choice = pick_next(names, progress.averages(SESSION_ID), progress.review_states(SESSION_ID))
        if choice:
            concept, raw_reason = choice
            reason = {
                "due": "due for review",
                "weak": "a weak spot",
                "strong": "reinforcing a strength",
                "new": "not tried yet",
            }.get(raw_reason, raw_reason)

    return render_template(
        "study.html",
        active="study",
        concept=concept,
        subject=concepts.subject_of(concept) if concept else None,
        reason=reason,
        concepts=names,
        total_concepts=len(names),
        due_count=len(progress.due(SESSION_ID)),
    )


@app.get("/dashboard")
def dashboard_page():
    return render_template("dashboard.html", active="dashboard", data=build_dashboard_data())


@app.get("/tutor")
def tutor_page():
    history = TutorHistory()
    return render_template("tutor.html", active="tutor", turns=history.recent(40))


@app.get("/notes")
def import_page():
    concepts, _ = stores()
    return render_template(
        "import.html",
        active="import",
        total_concepts=len(concepts),
        concepts=[
            {"name": n, "subject": concepts.subject_of(n) or UNCATEGORIZED}
            for n in concepts.names()
        ],
    )


# -------------------------------------------------------------------- api


@app.post("/api/explain")
def api_explain():
    payload = request.get_json(silent=True) or {}
    concept = (payload.get("concept") or "").strip().lower()
    explanation = (payload.get("explanation") or "").strip()

    if not concept:
        return jsonify({"error": "No concept given."}), 400
    if not explanation:
        return jsonify({"error": "Write an explanation first."}), 400

    concepts, progress = stores()
    notes = concepts.get(concept)
    if notes is None:
        return jsonify({"error": f'"{concept}" isn\'t loaded.'}), 404

    try:
        result = grade_explanation(concept, notes, explanation)
    except GradingError as exc:
        return jsonify({"error": str(exc)}), 502

    mapping = {n: concepts.subject_of(n) for n in concepts.names()}
    before = earned_badge_keys(progress.all_attempts(SESSION_ID), mapping)
    state = progress.record(SESSION_ID, concept, result["score"])
    after = earned_badge_keys(progress.all_attempts(SESSION_ID), mapping)

    new_badges = [b.name for b in ALL_BADGES if b.key in (after - before)]
    return jsonify({
        **result,
        "concept": concept,
        "next_due": state.due,
        "xp": attempt_xp(result["score"]),
        "new_badges": new_badges,
    })


@app.post("/api/tutor")
def api_tutor():
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Ask something first."}), 400

    concepts, progress = stores()
    try:
        reply = tutor_answer(question, concepts, progress, TutorHistory(), SESSION_ID)
    except TutorError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"reply": reply})


@app.post("/api/tutor/forget")
def api_tutor_forget():
    TutorHistory().clear()
    return jsonify({"ok": True})


@app.post("/api/import")
def api_import():
    uploads = request.files.getlist("images")
    if not uploads:
        return jsonify({"error": "No images uploaded."}), 400

    subject = (request.form.get("subject") or "").strip() or None
    sections: list[str] = []
    failures: list[str] = []

    for index, upload in enumerate(uploads):
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix or ".png"
        # Written to a real file because transcription reads from disk.
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            upload.save(tmp.name)
            temp_path = Path(tmp.name)
        try:
            markdown = transcribe_image(temp_path, subject if index == 0 else None)
            sections.append(markdown)
        except ImportError_ as exc:
            failures.append(f"{upload.filename}: {exc}")
        finally:
            temp_path.unlink(missing_ok=True)

    if not sections:
        return jsonify({"error": "Couldn't read any of those. " + " ".join(failures)}), 502

    combined = "\n\n".join(sections) + "\n"
    return jsonify({
        "markdown": combined,
        "concept_count": len(parse_markdown_notes(combined, default_subject=subject)),
        "failures": failures,
    })


@app.post("/api/import/save")
def api_import_save():
    payload = request.get_json(silent=True) or {}
    markdown = (payload.get("markdown") or "").strip()
    subject = (payload.get("subject") or "").strip() or None

    if not markdown:
        return jsonify({"error": "Nothing to save."}), 400

    parsed = parse_markdown_notes(markdown, default_subject=subject)
    if not parsed:
        return jsonify({"error": "No '## Concept' headings found, nothing to save."}), 400

    concepts, _ = stores()
    concepts.merge(parsed)
    concepts.save()
    return jsonify({"added": len(parsed), "total": len(concepts)})


@app.get("/api/data")
def api_data():
    return jsonify(build_dashboard_data())


# -------------------------------------------------------------- dashboard


def build_dashboard_data() -> dict:
    """Everything the dashboard renders, derived from the same stores as the CLI."""
    concepts, progress = stores()

    averages = progress.averages(SESSION_ID)
    states = progress.review_states(SESSION_ID)
    due = progress.due(SESSION_ID)
    attempts = progress.all_attempts(SESSION_ID)

    per_concept = []
    for name in concepts.names():
        history = progress.history(SESSION_ID, name)
        state = states.get(name)
        per_concept.append({
            "concept": name,
            "subject": concepts.subject_of(name) or UNCATEGORIZED,
            "average": averages.get(name),
            "attempts": len(history),
            "latest": history[-1]["score"] if history else None,
            "scores": [h["score"] for h in history],
            "due": state.due if state else None,
        })

    per_subject = []
    for subject in concepts.subjects():
        names = concepts.names(subject)
        studied = [n for n in names if n in averages]
        per_subject.append({
            "subject": subject,
            "concepts": len(names),
            "studied": len(studied),
            "average": (sum(averages[n] for n in studied) / len(studied)) if studied else None,
            "due": len([c for c, _ in due if c in set(names)]),
        })

    by_day: dict[str, list[float]] = defaultdict(list)
    for _, score, ts in attempts:
        by_day[ts[:10]].append(score)
    trend = [
        {"date": day, "average": sum(s) / len(s), "count": len(s)}
        for day, s in sorted(by_day.items())
    ]

    mapping = {n: concepts.subject_of(n) for n in concepts.names()}
    xp = total_xp(attempts)
    level = level_for_xp(xp)
    unlocked = {b.key for b in earned_badges(attempts, mapping)}

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "totals": {
            "loaded": len(concepts),
            "studied": len(averages),
            "attempts": progress.total_attempts(SESSION_ID),
            "due": len(due),
            "overall_average": (sum(averages.values()) / len(averages)) if averages else None,
        },
        "gamification": {
            "xp": xp,
            "level": level.level,
            "xp_into_level": level.xp_into_level,
            "xp_for_next": level.xp_for_next,
            "progress_percent": round(level.progress_fraction * 100),
            "current_streak": current_streak(attempts),
            "longest_streak": longest_streak(attempts),
            "badges": [
                {"name": b.name, "description": b.description, "earned": b.key in unlocked}
                for b in ALL_BADGES
            ],
            "earned_count": len(unlocked),
            "total_count": len(ALL_BADGES),
        },
        "concepts": per_concept,
        "subjects": per_subject,
        "due": [{"concept": c, "days_overdue": d} for c, d in due],
        "trend": trend,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Feynly, browser interface.")
    parser.add_argument("--port", "-p", type=int, default=int(os.environ.get("PORT", "5050")),
                        help="Port to serve on (default 5050; 5000 collides with macOS AirPlay)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address. Default is localhost only.")
    args = parser.parse_args()

    if args.host != "127.0.0.1":
        print(
            "\n  WARNING: binding to "
            f"{args.host} exposes this to your network with no login,\n"
            "  and anyone who reaches it can spend your Claude subscription.\n"
        )

    print(f"Feynly: http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        app.run(host=args.host, port=args.port, debug=False)
    except OSError as exc:
        print(f"\nCould not start on port {args.port}: {exc}", file=sys.stderr)
        print(f"Try:  python src/webapp.py --port {args.port + 1}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
