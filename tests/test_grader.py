import subprocess

import pytest

from src.grader import GradingError, _extract_json, _validate, grade_explanation


def test_extract_json_plain():
    assert _extract_json('{"score": 5}') == {"score": 5}


def test_extract_json_strips_markdown_fence():
    raw = '```json\n{"score": 5}\n```'
    assert _extract_json(raw) == {"score": 5}


def test_extract_json_finds_object_in_stray_prose():
    raw = 'Sure, here you go:\n{"score": 7, "summary": "ok"}\nHope that helps!'
    assert _extract_json(raw) == {"score": 7, "summary": "ok"}


def test_extract_json_raises_on_garbage():
    with pytest.raises(GradingError):
        _extract_json("not json at all")


def test_validate_fills_defaults():
    result = _validate({"score": 8})
    assert result == {"score": 8.0, "correct": [], "vague": [], "wrong_or_missing": [], "summary": ""}


def test_validate_clamps_score_range():
    assert _validate({"score": 55})["score"] == 10.0
    assert _validate({"score": -3})["score"] == 0.0


def test_validate_requires_score():
    with pytest.raises(GradingError):
        _validate({"summary": "no score field"})


def test_validate_rejects_non_numeric_score():
    with pytest.raises(GradingError):
        _validate({"score": "not a number"})


def test_grade_explanation_missing_claude_binary(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GradingError, match="claude"):
        grade_explanation("inflation", "notes", "explanation")


def test_grade_explanation_nonzero_exit(monkeypatch):
    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(GradingError, match="exited 1"):
        grade_explanation("inflation", "notes", "explanation")


def test_grade_explanation_success(monkeypatch):
    class FakeProc:
        returncode = 0
        stdout = '{"score": 8, "correct": ["got the basics"], "vague": [], "wrong_or_missing": [], "summary": "solid"}'
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
    result = grade_explanation("inflation", "notes", "explanation")
    assert result["score"] == 8.0
    assert result["correct"] == ["got the basics"]
    assert result["summary"] == "solid"


def test_grade_explanation_timeout(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=90)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GradingError, match="timed out"):
        grade_explanation("inflation", "notes", "explanation")
