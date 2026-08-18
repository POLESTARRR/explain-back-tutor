#!/usr/bin/env python3
"""Explain-Back Tutor — terminal study tool.

Interactive:
    python src/study.py

One-shot (scriptable — pipe it, alias it, or call it from cron/launchd):
    python src/study.py list
    python src/study.py weak
    python src/study.py due
    python src/study.py next
    python src/study.py stats
    python src/study.py explain <concept>
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.concepts import ConceptStore  # noqa: E402
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


def score_style(score: float) -> str:
    if score >= 8:
        return "green"
    if score >= 5:
        return "yellow"
    return "red"


def render_feedback(concept: str, result: dict, next_due: str | None = None) -> None:
    """Print a graded result as a colorized panel."""
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


def render_concepts(store: ConceptStore) -> None:
    names = store.names()
    if not names:
        console.print("[yellow]No concepts loaded.[/yellow] Run: python src/load_notes.py <notes.md>")
        return
    table = Table(title=f"Loaded concepts ({len(names)})", show_header=False, border_style="cyan")
    for name in names:
        table.add_row(name)
    console.print(table)


def render_weak(progress: ProgressStore) -> None:
    rows = progress.weakest(LOCAL_CHAT_ID)
    if not rows:
        console.print("[yellow]No graded attempts yet[/yellow] — explain a concept first.")
        return
    table = Table(title="Your weakest concepts", border_style="cyan")
    table.add_column("Concept")
    table.add_column("Average", justify="right")
    table.add_column("Attempts", justify="right")
    for concept, avg, attempts in rows:
        table.add_row(concept, f"[{score_style(avg)}]{avg:.1f}/10[/{score_style(avg)}]", str(attempts))
    console.print(table)


def render_due(progress: ProgressStore) -> None:
    rows = progress.due(LOCAL_CHAT_ID)
    if not rows:
        console.print("[green]Nothing due for review.[/green] [dim]Try `next` for something to study.[/dim]")
        return
    table = Table(title=f"Due for review ({len(rows)})", border_style="cyan")
    table.add_column("Concept")
    table.add_column("Overdue", justify="right")
    for concept, days_overdue in rows:
        label = "today" if days_overdue <= 0 else f"{days_overdue}d"
        table.add_row(concept, label)
    console.print(table)


def render_stats(concepts: ConceptStore, progress: ProgressStore) -> None:
    averages = progress.averages(LOCAL_CHAT_ID)
    total_attempts = progress.total_attempts(LOCAL_CHAT_ID)
    studied = len(averages)
    loaded = len(concepts)
    due_now = len(progress.due(LOCAL_CHAT_ID))

    body = Text()
    body.append(f"Concepts loaded:   {loaded}\n")
    body.append(f"Concepts studied:  {studied}")
    if loaded:
        body.append(f"  ({studied / loaded * 100:.0f}% coverage)")
    body.append("\n")
    body.append(f"Total attempts:    {total_attempts}\n")
    body.append(f"Due for review:    {due_now}\n")
    if averages:
        overall = sum(averages.values()) / len(averages)
        body.append("Overall average:   ", style="")
        body.append(f"{overall:.1f}/10\n", style=score_style(overall))
    console.print(Panel(body, title="[bold]Your stats[/bold]", border_style="cyan"))


def suggest_next(concepts: ConceptStore, progress: ProgressStore) -> str | None:
    """Pick and announce the next concept to study. Returns the concept name."""
    choice = pick_next(
        concepts.names(),
        progress.averages(LOCAL_CHAT_ID),
        progress.review_states(LOCAL_CHAT_ID),
    )
    if choice is None:
        console.print("[yellow]No concepts loaded.[/yellow] Run: python src/load_notes.py <notes.md>")
        return None
    concept, reason = choice
    console.print(
        Panel(
            f"[bold]{concept}[/bold]\n[dim]{REASON_LABELS.get(reason, reason)}[/dim]",
            title="Next up",
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
        console.print(f"[red]\"{concept}\" isn't loaded.[/red]")
        suggestions = concepts.find_close_matches(concept)
        if suggestions:
            console.print("Did you mean: " + ", ".join(suggestions))
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
    """End-of-session recap, plus the saved log path."""
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


def interactive(concepts: ConceptStore, progress: ProgressStore) -> int:
    console.print(
        Panel(
            "[bold]Explain-Back Tutor[/bold]\n"
            "Type a concept name to be graded on it.\n"
            "[dim]/next  /due  /list  /weak  /stats  /help  /exit[/dim]",
            border_style="cyan",
        )
    )
    convo = ConversationManager(concepts, progress)  # used for /help text only
    session = StudySession()

    def finish() -> int:
        render_session_summary(session)
        console.print("[dim]Bye.[/dim]")
        return 0

    while True:
        try:
            entry = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return finish()

        if not entry:
            continue
        if entry.lower() in EXIT_COMMANDS:
            return finish()
        if entry == "/list":
            render_concepts(concepts)
            continue
        if entry == "/weak":
            render_weak(progress)
            continue
        if entry == "/due":
            render_due(progress)
            continue
        if entry == "/stats":
            render_stats(concepts, progress)
            continue
        if entry == "/help":
            console.print(convo.handle_message(LOCAL_CHAT_ID, "/help"))
            continue
        if entry == "/next":
            picked = suggest_next(concepts, progress)
            if picked is None:
                continue
            explanation = read_multiline_explanation(picked)
            if explanation is None:
                console.print("[dim]Skipped.[/dim]")
                continue
            grade_one(concepts, progress, picked, explanation, session)
            continue
        if entry.startswith("/"):
            console.print(
                f"[yellow]Unknown command:[/yellow] {entry}  "
                "[dim](/next /due /list /weak /stats /help /exit)[/dim]"
            )
            continue

        if not concepts.exists(entry):
            console.print(f"[red]\"{entry}\" isn't loaded.[/red]")
            suggestions = concepts.find_close_matches(entry)
            if suggestions:
                console.print("Did you mean: " + ", ".join(suggestions))
            else:
                console.print("[dim]/list to see what's available.[/dim]")
            continue

        explanation = read_multiline_explanation(entry)
        if explanation is None:
            console.print("[dim]Cancelled.[/dim]")
            continue
        grade_one(concepts, progress, entry, explanation, session)


def run(argv: list[str]) -> int:
    """Dispatch one-shot subcommands, or fall through to the interactive REPL."""
    concepts = ConceptStore()
    progress = ProgressStore()

    if not argv:
        return interactive(concepts, progress)

    command, args = argv[0], argv[1:]

    if command == "list":
        render_concepts(concepts)
        return 0
    if command == "weak":
        render_weak(progress)
        return 0
    if command == "due":
        render_due(progress)
        return 0
    if command == "stats":
        render_stats(concepts, progress)
        return 0
    if command == "next":
        return 0 if suggest_next(concepts, progress) else 1
    if command == "explain":
        if not args:
            console.print("[red]Usage:[/red] study.py explain <concept>  [dim](explanation on stdin)[/dim]")
            return 2
        concept = " ".join(args)
        # Validate the concept before asking for an explanation, so the user isn't
        # made to type one only to be told the concept doesn't exist.
        if not concepts.exists(concept):
            console.print(f"[red]\"{concept}\" isn't loaded.[/red]")
            suggestions = concepts.find_close_matches(concept)
            if suggestions:
                console.print("Did you mean: " + ", ".join(suggestions))
            return 1
        explanation = sys.stdin.read().strip() if not sys.stdin.isatty() else (
            read_multiline_explanation(concept) or ""
        )
        if not explanation:
            console.print("[red]No explanation given.[/red]")
            return 2
        return grade_one(concepts, progress, concept, explanation)

    console.print(
        f"[red]Unknown command:[/red] {command}  "
        "[dim](list, weak, due, next, stats, explain)[/dim]"
    )
    return 2


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
