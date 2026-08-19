import subprocess

import pytest

from src import tutor
from src.concepts import ConceptStore
from src.progress import ProgressStore
from src.tutor import (
    MAX_TURNS_REPLAYED,
    Turn,
    TutorError,
    TutorHistory,
    answer,
    build_history_summary,
    build_prompt,
    relevant_concepts,
)

SESSION = "local"


@pytest.fixture
def concepts(tmp_path):
    store = ConceptStore(tmp_path / "concepts.json")
    store.add("Inflation", "Inflation is a sustained rise in the general price level.")
    store.add("Photosynthesis", "Plants convert light energy into glucose.")
    store.add("TCP vs UDP", "TCP is reliable and ordered; UDP is fast and connectionless.")
    store.save()
    return store


@pytest.fixture
def progress(tmp_path):
    return ProgressStore(tmp_path / "progress.json")


@pytest.fixture
def history(tmp_path):
    return TutorHistory(tmp_path / "tutor_history.json")


# --------------------------------------------------------- concept matching


def test_relevant_concepts_matches_exact_name(concepts):
    matched = relevant_concepts("explain inflation to me", concepts.names())
    assert "inflation" in matched


def test_relevant_concepts_matches_multiword_name(concepts):
    matched = relevant_concepts("what's the deal with tcp vs udp?", concepts.names())
    assert "tcp vs udp" in matched


def test_relevant_concepts_matches_on_token_overlap(concepts):
    matched = relevant_concepts("tell me about udp", concepts.names())
    assert "tcp vs udp" in matched


def test_relevant_concepts_empty_for_unrelated_question(concepts):
    assert relevant_concepts("what should I eat for lunch", concepts.names()) == []


def test_relevant_concepts_empty_question():
    assert relevant_concepts("", ["inflation"]) == []


def test_relevant_concepts_respects_limit(concepts):
    matched = relevant_concepts("inflation photosynthesis tcp udp", concepts.names(), limit=1)
    assert len(matched) == 1


def test_exact_name_outranks_token_overlap(concepts):
    matched = relevant_concepts("inflation and photosynthesis", concepts.names())
    assert matched[0] in {"inflation", "photosynthesis"}


# ------------------------------------------------------------ history summary


def test_history_summary_with_no_attempts():
    assert "not been graded" in build_history_summary({}, [], 0)


def test_history_summary_reports_weakest_and_strongest():
    summary = build_history_summary({"a": 2.0, "b": 9.0}, [], 2)
    assert "Weakest" in summary
    assert "a (2.0/10)" in summary
    assert "b (9.0/10)" in summary


def test_history_summary_includes_due_concepts():
    summary = build_history_summary({"a": 5.0}, [("a", 3)], 1)
    assert "Due for review" in summary
    assert "a" in summary


def test_history_summary_omits_due_when_none():
    assert "Due for review" not in build_history_summary({"a": 5.0}, [], 1)


# -------------------------------------------------------------------- prompt


def test_prompt_includes_notes_and_question():
    prompt = build_prompt("what is inflation?", {"inflation": "prices rise"}, "summary", [])
    assert "prices rise" in prompt
    assert "what is inflation?" in prompt
    assert "STUDENT'S NOTES" in prompt


def test_prompt_states_grounding_rules():
    prompt = build_prompt("q", {}, "summary", [])
    # The grounding discipline is the whole point; it must always be present.
    assert "your notes don't cover this" in prompt
    assert "CONTRADICT" in prompt


def test_prompt_handles_no_matching_notes():
    prompt = build_prompt("unrelated", {}, "summary", [])
    assert "No notes matched" in prompt


def test_prompt_includes_conversation_history():
    turns = [Turn("student", "earlier question"), Turn("tutor", "earlier answer")]
    prompt = build_prompt("new question", {}, "summary", turns)
    assert "earlier question" in prompt
    assert "earlier answer" in prompt


def test_prompt_omits_history_section_when_empty():
    assert "EARLIER IN THIS CONVERSATION" not in build_prompt("q", {}, "s", [])


def test_prompt_includes_score_history():
    prompt = build_prompt("q", {}, "Weakest: inflation (2.0/10)", [])
    assert "inflation (2.0/10)" in prompt


# ------------------------------------------------------------------- memory


def test_history_starts_empty(history):
    assert len(history) == 0
    assert history.recent() == []


def test_history_records_turns(history):
    history.add("student", "question")
    history.add("tutor", "answer")
    assert len(history) == 2
    assert history.turns[0].role == "student"


def test_history_persists_across_instances(tmp_path):
    path = tmp_path / "tutor_history.json"
    first = TutorHistory(path)
    first.add("student", "remembered question")

    second = TutorHistory(path)
    assert len(second) == 1
    assert second.turns[0].text == "remembered question"


def test_history_clear(history):
    history.add("student", "q")
    history.clear()
    assert len(history) == 0


def test_history_clear_persists(tmp_path):
    path = tmp_path / "tutor_history.json"
    store = TutorHistory(path)
    store.add("student", "q")
    store.clear()
    assert len(TutorHistory(path)) == 0


def test_recent_trims_to_limit(history):
    for i in range(MAX_TURNS_REPLAYED + 10):
        history.add("student", f"q{i}")
    assert len(history.recent()) == MAX_TURNS_REPLAYED
    # Keeps the most recent, not the oldest.
    assert history.recent()[-1].text == f"q{MAX_TURNS_REPLAYED + 9}"


def test_corrupt_history_does_not_crash(tmp_path):
    path = tmp_path / "tutor_history.json"
    path.write_text("{ not json")
    store = TutorHistory(path)
    assert len(store) == 0
    assert store.warning is not None


# --------------------------------------------------------------------- ask


def test_answer_records_both_turns(concepts, progress, history):
    answer("what is inflation?", concepts, progress, history, SESSION, ask=lambda p: "an answer")
    assert [t.role for t in history.turns] == ["student", "tutor"]
    assert history.turns[1].text == "an answer"


def test_answer_returns_the_reply(concepts, progress, history):
    reply = answer("q", concepts, progress, history, SESSION, ask=lambda p: "the reply")
    assert reply == "the reply"


def test_answer_passes_matching_notes_into_the_prompt(concepts, progress, history):
    captured = {}

    def fake_ask(prompt):
        captured["prompt"] = prompt
        return "ok"

    answer("tell me about inflation", concepts, progress, history, SESSION, ask=fake_ask)
    assert "sustained rise in the general price level" in captured["prompt"]


def test_answer_includes_real_scores(concepts, progress, history):
    progress.record(SESSION, "inflation", 3)
    captured = {}

    def fake_ask(prompt):
        captured["prompt"] = prompt
        return "ok"

    answer("how am I doing?", concepts, progress, history, SESSION, ask=fake_ask)
    assert "inflation (3.0/10)" in captured["prompt"]


def test_answer_replays_previous_turns(concepts, progress, history):
    history.add("student", "first question")
    history.add("tutor", "first answer")
    captured = {}

    def fake_ask(prompt):
        captured["prompt"] = prompt
        return "ok"

    answer("follow-up", concepts, progress, history, SESSION, ask=fake_ask)
    assert "first question" in captured["prompt"]


# ------------------------------------------------------------ claude errors


def test_ask_claude_missing_binary(monkeypatch):
    def fake_run(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(TutorError, match="claude"):
        tutor.ask_claude("prompt")


def test_ask_claude_timeout(monkeypatch):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=120)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(TutorError, match="timed out"):
        tutor.ask_claude("prompt")


def test_ask_claude_nonzero_exit(monkeypatch):
    class P:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: P())
    with pytest.raises(TutorError, match="exited 1"):
        tutor.ask_claude("prompt")


def test_ask_claude_empty_reply(monkeypatch):
    class P:
        returncode = 0
        stdout = "   "
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: P())
    with pytest.raises(TutorError, match="empty"):
        tutor.ask_claude("prompt")


def test_ask_claude_success(monkeypatch):
    class P:
        returncode = 0
        stdout = "  the answer  "
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: P())
    assert tutor.ask_claude("prompt") == "the answer"


def test_failed_answer_does_not_record_turns(concepts, progress, history):
    def boom(prompt):
        raise TutorError("down")

    with pytest.raises(TutorError):
        answer("q", concepts, progress, history, SESSION, ask=boom)
    # A failed exchange must not pollute memory.
    assert len(history) == 0
