#!/usr/bin/env python3
"""Explain-Back Tutor — terminal study tool.

Interactive:
    python src/study.py
    python src/study.py --subject chemistry     # scope the session to one subject

One-shot (scriptable — pipe it, alias it, or call it from cron/launchd):
    python src/study.py list [--subject S]
    python src/study.py due [--subject S]
    python src/study.py next [--subject S]
    python src/study.py weak [--subject S] [--limit N]
    python src/study.py stats [--subject S]
    python src/study.py subjects
    python src/study.py explain <concept>       # explanation on stdin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.concepts import UNCATEGORIZED, ConceptStore  # noqa: E402
from src.conversation import ConversationManager  # noqa: E402
from src.grader import GradingError  # noqa: E402
from src.progress import ProgressStore  # noqa: E402
from src.scheduler import pick_next  # noqa: E402
from src.session import StudySession  # noqa: E402

# Progress is keyed by "session id" in the shared engine; the terminal is one
# fixed identity so scores persist across runs.
LOCAL_CHAT_ID = "local"

EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit"}

REASON_LABELS = {
    "due": "due for review",
    "weak": "one of your weak spots",
    "strong": "reinforcing a strength",
    "new": "you haven't tried this one yet",
}

console = Console()


# --------------------------------------------------------------- formatting


def score_style(score: float) -> str:
    if score >= 8:
        return "green"
    if score >= 5:
        return "yellow"
    return "red"


def scope_label(subject: str | None) -> str:
    return f" · {subject}" if subject else ""


def render_feedback(concept: str, result: dict, next_due: str | None = None) -> None:
    style = score_style(result["score"])
    body = Text()
    if result["summary"]:
        body.append(result["summary"] + "\n", style="italic")

    def section(title: str, items: list[str], item_style: str) -> None:
        if not items:
            return
        body.append(f"\n{title}\n", style=f"bold {item_style}")
        for item in items:
            body.append("  • ", style=item_style)
            body.append(item + "\n")

    section("Correct", result["correct"], "green")
    section("Vague", result["vague"], "yellow")
    section("Wrong / missing", result["wrong_or_missing"], "red")
    # Not a mistake by you — a hole in your source material.
    section("Not covered by your notes", result.get("notes_gaps", []), "cyan")

    if next_due:
        body.append(f"\nNext review: {next_due}\n", style="dim")

    console.print(
        Panel(
            body,
            title=f"[bold]{concept}[/bold] — [{style}]{result['score']:.0f}/10[/{style}]",
            border_style=style,
        )
    )


def render_concepts(store: ConceptStore, subject: str | None = None) -> None:
    names = store.names(subject)
    if not names:
        if subject:
            console.print(f"[yellow]No concepts in \"{subject}\".[/yellow]")
        else:
            console.print(
                "[yellow]No concepts loaded.[/yellow] Run: python src/load_notes.py <notes.md>"
            )
        return
    table = Table(
        title=f"Concepts ({len(names)}){scope_label(subject)}", border_style="cyan"
    )
    table.add_column("Concept")
    if subject is None:
        table.add_column("Subject", style="dim")
        for name in names:
            table.add_row(name, store.subject_of(name) or UNCATEGORIZED)
    else:
        for name in names:
            table.add_row(name)
    console.print(table)


def render_subjects(store: ConceptStore, progress: ProgressStore) -> None:
    subjects = store.subjects()
    if not subjects:
        console.print("[yellow]No concepts loaded.[/yellow] Run: python src/load_notes.py <notes.md>")
        return
    averages = progress.averages(LOCAL_CHAT_ID)
    table = Table(title=f"Subjects ({len(subjects)})", border_style="cyan")
    table.add_column("Subject")
    table.add_column("Concepts", justify="right")
    table.add_column("Studied", justify="right")
    table.add_column("Average", justify="right")
    for subject in subjects:
        names = store.names(subject)
        studied = [n for n in names if n in averages]
        if studied:
            avg = sum(averages[n] for n in studied) / len(studied)
            avg_cell = f"[{score_style(avg)}]{avg:.1f}/10[/{score_style(avg)}]"
        else:
            avg_cell = "[dim]—[/dim]"
        table.add_row(subject, str(len(names)), f"{len(studied)}/{len(names)}", avg_cell)
    console.print(table)


def render_weak(
    concepts: ConceptStore, progress: ProgressStore, subject: str | None = None, limit: int = 5
) -> None:
    allowed = set(concepts.names(subject)) if subject else None
    rows = [
        row for row in progress.weakest(LOCAL_CHAT_ID, limit=1000)
        if allowed is None or row[0] in allowed
    ][:limit]
    if not rows:
        console.print("[yellow]No graded attempts yet[/yellow] — explain a concept first.")
        return
    table = Table(title=f"Your weakest concepts{scope_label(subject)}", border_style="cyan")
    table.add_column("Concept")
    table.add_column("Average", justify="right")
    table.add_column("Attempts", justify="right")
    for concept, avg, attempts in rows:
        table.add_row(concept, f"[{score_style(avg)}]{avg:.1f}/10[/{score_style(avg)}]", str(attempts))
    console.print(table)


def render_due(concepts: ConceptStore, progress: ProgressStore, subject: str | None = None) -> None:
    allowed = set(concepts.names(subject)) if subject else None
    rows = [
        row for row in progress.due(LOCAL_CHAT_ID)
        if allowed is None or row[0] in allowed
    ]
    if not rows:
        console.print(
            f"[green]Nothing due for review{scope_label(subject)}.[/green] "
            "[dim]Try `next` for something to study.[/dim]"
        )
        return
    table = Table(title=f"Due for review ({len(rows)}){scope_label(subject)}", border_style="cyan")
    table.add_column("Concept")
    table.add_column("Overdue", justify="right")
    for concept, days_overdue in rows:
        table.add_row(concept, "today" if days_overdue <= 0 else f"{days_overdue}d")
    console.print(table)


def render_stats(concepts: ConceptStore, progress: ProgressStore, subject: str | None = None) -> None:
    names = concepts.names(subject)
    allowed = set(names)
    averages = {c: a for c, a in progress.averages(LOCAL_CHAT_ID).items() if c in allowed}
    attempts = sum(
        len(progress.history(LOCAL_CHAT_ID, c)) for c in allowed
    )
    due_now = len([r for r in progress.due(LOCAL_CHAT_ID) if r[0] in allowed])

    body = Text()
    body.append(f"Concepts loaded:   {len(names)}\n")
    body.append(f"Concepts studied:  {len(averages)}")
    if names:
        body.append(f"  ({len(averages) / len(names) * 100:.0f}% coverage)")
    body.append("\n")
    body.append(f"Total attempts:    {attempts}\n")
    body.append(f"Due for review:    {due_now}\n")
    if averages:
        overall = sum(averages.values()) / len(averages)
        body.append("Overall average:   ")
        body.append(f"{overall:.1f}/10\n", style=score_style(overall))
    console.print(
        Panel(body, title=f"[bold]Your stats{scope_label(subject)}[/bold]", border_style="cyan")
    )


# ------------------------------------------------------------------ actions


def suggest_next(
    concepts: ConceptStore, progress: ProgressStore, subject: str | None = None
) -> str | None:
    """Pick and announce the next concept to study. Returns the concept name."""
    names = concepts.names(subject)
    choice = pick_next(
        names,
        progress.averages(LOCAL_CHAT_ID),
        progress.review_states(LOCAL_CHAT_ID),
    )
    if choice is None:
        if subject:
            console.print(f"[yellow]No concepts in \"{subject}\".[/yellow]")
        else:
            console.print(
                "[yellow]No concepts loaded.[/yellow] Run: python src/load_notes.py <notes.md>"
            )
        return None
    concept, reason = choice
    console.print(
        Panel(
            f"[bold]{concept}[/bold]\n[dim]{REASON_LABELS.get(reason, reason)}[/dim]",
            title=f"Next up{scope_label(subject)}",
            border_style="cyan",
        )
    )
    return concept


def grade_one(
    concepts: ConceptStore,
    progress: ProgressStore,
    concept: str,
    explanation: str,
    session: StudySession | None = None,
) -> int:
    """Grade a single explanation and render it. Returns a process exit code."""
    notes = concepts.get(concept)
    if notes is None:
        report_unknown_concept(concepts, concept)
        return 1

    with console.status("[cyan]Grading your explanation...[/cyan]"):
        try:
            from src.grader import grade_explanation

            result = grade_explanation(concept, notes, explanation)
        except GradingError as exc:
            console.print(f"[red]Grading failed:[/red] {exc}")
            return 1

    key = concept.strip().lower()
    state = progress.record(LOCAL_CHAT_ID, key, result["score"])
    render_feedback(concept, result, next_due=state.due)
    if session is not None:
        session.record(key, result, next_due=state.due)
    return 0


def report_unknown_concept(concepts: ConceptStore, name: str) -> None:
    console.print(f"[red]\"{name}\" isn't loaded.[/red]")
    suggestions = concepts.find_close_matches(name)
    if suggestions:
        console.print("Did you mean: " + ", ".join(suggestions))
    else:
        console.print("[dim]Use `list` to see what's available.[/dim]")


def read_multiline_explanation(concept: str) -> str | None:
    """Collect an explanation from stdin. Blank line ends it; /cancel aborts."""
    console.print(
        Panel(
            f"Explain [bold]{concept}[/bold] in your own words.\n"
            "[dim]Finish with a blank line. /cancel to back out.[/dim]",
            border_style="cyan",
        )
    )
    lines: list[str] = []
    while True:
        try:
            line = input("  ")
        except EOFError:
            break
        if line.strip() == "/cancel":
            return None
        if not line.strip():
            if lines:
                break
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    return text or None


def render_session_summary(session: StudySession) -> None:
    if not session.attempts:
        return
    body = Text()
    body.append(f"Concepts explained: {session.count}\n")
    if session.average is not None:
        body.append("Average score:      ")
        body.append(f"{session.average:.1f}/10\n", style=score_style(session.average))
    body.append(f"Time studying:      {session.duration_minutes():.0f} min\n")

    gaps = session.all_notes_gaps()
    if gaps:
        body.append(f"\nYour notes may be missing {len(gaps)} thing(s) you mentioned:\n", style="cyan")
        for concept, gap in gaps[:5]:
            body.append(f"  • [{concept}] {gap}\n", style="cyan")

    path = session.save()
    if path:
        body.append(f"\nSession log: {path}\n", style="dim")

    console.print(Panel(body, title="[bold]Session summary[/bold]", border_style="cyan"))


# -------------------------------------------------------------- interactive


HELP_LINES = (
    "/next            pick something to study\n"
    "/due             what's due for review\n"
    "/list            all concepts in scope\n"
    "/subjects        subjects and their coverage\n"
    "/focus <subject> scope to one subject (/focus alone clears it)\n"
    "/weak            your lowest averages\n"
    "/stats           coverage and overall average\n"
    "/exit            finish and save a session log"
)


def interactive(concepts: ConceptStore, progress: ProgressStore, subject: str | None = None) -> int:
    console.print(
        Panel(
            "[bold]Explain-Back Tutor[/bold]\n"
            "Type a concept name to be graded on it, or /next to be given one.\n"
            "[dim]/next  /due  /list  /subjects  /focus  /weak  /stats  /help  /exit[/dim]",
            border_style="cyan",
        )
    )
    if subject:
        console.print(f"[dim]Focused on: {subject}[/dim]")

    session = StudySession()
    focus = subject

    def finish() -> int:
        render_session_summary(session)
        console.print("[dim]Bye.[/dim]")
        return 0

    def study(concept: str) -> None:
        explanation = read_multiline_explanation(concept)
        if explanation is None:
            console.print("[dim]Cancelled.[/dim]")
            return
        grade_one(concepts, progress, concept, explanation, session)

    while True:
        try:
            prompt = f"\n[{focus}]> " if focus else "\n> "
            entry = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return finish()

        if not entry:
            continue
        if entry.lower() in EXIT_COMMANDS:
            return finish()

        if entry.startswith("/"):
            command, _, argument = entry.partition(" ")
            argument = argument.strip()

            if command == "/list":
                render_concepts(concepts, focus)
            elif command == "/subjects":
                render_subjects(concepts, progress)
            elif command == "/weak":
                render_weak(concepts, progress, focus)
            elif command == "/due":
                render_due(concepts, progress, focus)
            elif command == "/stats":
                render_stats(concepts, progress, focus)
            elif command == "/help":
                console.print(Panel(HELP_LINES, title="Commands", border_style="cyan"))
            elif command == "/focus":
                if not argument:
                    focus = None
                    console.print("[dim]Focus cleared — all subjects.[/dim]")
                elif concepts.subject_exists(argument):
                    focus = argument.strip().lower()
                    console.print(f"[cyan]Focused on {focus}.[/cyan]")
                else:
                    available = ", ".join(concepts.subjects()) or "none"
                    console.print(
                        f"[red]No subject \"{argument}\".[/red] [dim]Available: {available}[/dim]"
                    )
            elif command == "/next":
                picked = suggest_next(concepts, progress, focus)
                if picked:
                    study(picked)
            else:
                console.print(
                    f"[yellow]Unknown command:[/yellow] {command}  [dim](/help for the list)[/dim]"
                )
            continue

        if not concepts.exists(entry):
            report_unknown_concept(concepts, entry)
            continue
        study(entry)


# --------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="study.py",
        description="Explain-Back Tutor — explain concepts in your own words and get graded "
                    "against your own notes.",
    )
    parser.add_argument("--subject", "-s", default=None, help="Scope to one subject")
    sub = parser.add_subparsers(dest="command")

    # SUPPRESS, not None: an unset --subject on the subcommand must leave the
    # top-level `study.py --subject X list` value intact rather than blank it.
    for name, help_text in (
        ("list", "List concepts"),
        ("due", "Show concepts due for review"),
        ("next", "Suggest what to study now"),
        ("stats", "Show coverage and averages"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--subject", "-s", default=argparse.SUPPRESS, help="Scope to one subject")

    weak = sub.add_parser("weak", help="Show your lowest-scoring concepts")
    weak.add_argument("--subject", "-s", default=argparse.SUPPRESS, help="Scope to one subject")
    weak.add_argument("--limit", "-n", type=int, default=5, help="How many to show (default 5)")

    sub.add_parser("subjects", help="List subjects and their coverage")

    explain = sub.add_parser("explain", help="Grade an explanation (read from stdin)")
    explain.add_argument("concept", nargs="+", help="Concept name")

    return parser


def run(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    concepts = ConceptStore()
    progress = ProgressStore()
    for store in (concepts, progress):
        if store.warning:
            console.print(f"[yellow]Warning:[/yellow] {store.warning}")

    # A subject may be given before or after the subcommand; the subcommand wins.
    subject = getattr(args, "subject", None) or None
    if subject and not concepts.subject_exists(subject):
        available = ", ".join(concepts.subjects()) or "none loaded"
        console.print(f"[red]No subject \"{subject}\".[/red] [dim]Available: {available}[/dim]")
        return 2

    command = args.command
    if command is None:
        return interactive(concepts, progress, subject)
    if command == "list":
        render_concepts(concepts, subject)
        return 0
    if command == "subjects":
        render_subjects(concepts, progress)
        return 0
    if command == "weak":
        render_weak(concepts, progress, subject, args.limit)
        return 0
    if command == "due":
        render_due(concepts, progress, subject)
        return 0
    if command == "stats":
        render_stats(concepts, progress, subject)
        return 0
    if command == "next":
        return 0 if suggest_next(concepts, progress, subject) else 1
    if command == "explain":
        concept = " ".join(args.concept)
        # Validate before asking for an explanation, so a typo doesn't cost the
        # user a full write-up.
        if not concepts.exists(concept):
            report_unknown_concept(concepts, concept)
            return 1
        explanation = (
            sys.stdin.read().strip()
            if not sys.stdin.isatty()
            else (read_multiline_explanation(concept) or "")
        )
        if not explanation:
            console.print("[red]No explanation given.[/red]")
            return 2
        return grade_one(concepts, progress, concept, explanation)

    parser.print_help()
    return 2


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
