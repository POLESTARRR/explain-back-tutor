#!/usr/bin/env python3
"""Explain-Back Tutor — terminal study tool.

Interactive:
    python src/study.py

One-shot (scriptable — pipe it, alias it, or call it from cron):
    python src/study.py list
    python src/study.py weak
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

# Progress is keyed by "chat id" in the shared engine; the terminal is one fixed
# identity so scores persist across sessions.
LOCAL_CHAT_ID = "local"

EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit"}

console = Console()


def score_style(score: float) -> str:
    if score >= 8:
        return "green"
    if score >= 5:
        return "yellow"
    return "red"


def render_feedback(concept: str, result: dict) -> None:
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


def grade_one(concepts: ConceptStore, progress: ProgressStore, concept: str, explanation: str) -> int:
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

    progress.record(LOCAL_CHAT_ID, concept.strip().lower(), result["score"])
    render_feedback(concept, result)
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


def interactive(concepts: ConceptStore, progress: ProgressStore) -> int:
    console.print(
        Panel(
            "[bold]Explain-Back Tutor[/bold]\n"
            "Type a concept name to be graded on it.\n"
            "[dim]/list  /weak  /help  /exit[/dim]",
            border_style="cyan",
        )
    )
    convo = ConversationManager(concepts, progress)  # used for /help text only

    while True:
        try:
            entry = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye.[/dim]")
            return 0

        if not entry:
            continue
        if entry.lower() in EXIT_COMMANDS:
            console.print("[dim]Bye.[/dim]")
            return 0
        if entry == "/list":
            render_concepts(concepts)
            continue
        if entry == "/weak":
            render_weak(progress)
            continue
        if entry == "/help":
            console.print(convo.handle_message(LOCAL_CHAT_ID, "/help"))
            continue
        if entry.startswith("/"):
            console.print(f"[yellow]Unknown command:[/yellow] {entry}  [dim](/list /weak /help /exit)[/dim]")
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
        grade_one(concepts, progress, entry, explanation)


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

    console.print(f"[red]Unknown command:[/red] {command}  [dim](list, weak, explain)[/dim]")
    return 2


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
