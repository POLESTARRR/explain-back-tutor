from datetime import date

import pytest

from src import web
from src.concepts import ConceptStore
from src.progress import ProgressStore

TODAY = date(2026, 8, 18)


@pytest.fixture
def stores(tmp_path, monkeypatch):
    concepts = ConceptStore(tmp_path / "concepts.json")
    concepts.add("inflation", "Inflation is a sustained rise in prices.")
    concepts.add("photosynthesis", "Plants convert light into chemical energy.")
    concepts.save()
    progress = ProgressStore(tmp_path / "progress.json")

    monkeypatch.setattr(web, "ConceptStore", lambda *a, **k: concepts)
    monkeypatch.setattr(web, "ProgressStore", lambda *a, **k: progress)
    return concepts, progress


@pytest.fixture
def client(stores):
    web.app.config["TESTING"] = True
    return web.app.test_client()


def test_dashboard_data_empty_state(stores):
    data = web.build_dashboard_data()
    assert data["totals"]["loaded"] == 2
    assert data["totals"]["studied"] == 0
    assert data["totals"]["attempts"] == 0
    assert data["totals"]["overall_average"] is None
    assert data["trend"] == []


def test_dashboard_data_after_attempts(stores):
    _, progress = stores
    progress.record(web.LOCAL_CHAT_ID, "inflation", 4, today=TODAY)
    progress.record(web.LOCAL_CHAT_ID, "inflation", 8, today=TODAY)

    data = web.build_dashboard_data()
    assert data["totals"]["studied"] == 1
    assert data["totals"]["attempts"] == 2
    assert data["totals"]["overall_average"] == 6.0

    inflation = next(c for c in data["concepts"] if c["concept"] == "inflation")
    assert inflation["average"] == 6.0
    assert inflation["scores"] == [4, 8]
    assert inflation["latest"] == 8
    assert inflation["due"] is not None


def test_dashboard_includes_unstudied_concepts(stores):
    data = web.build_dashboard_data()
    names = {c["concept"] for c in data["concepts"]}
    assert names == {"inflation", "photosynthesis"}
    unstudied = next(c for c in data["concepts"] if c["concept"] == "photosynthesis")
    assert unstudied["attempts"] == 0
    assert unstudied["average"] is None


def test_trend_groups_by_day(stores):
    _, progress = stores
    progress.record(web.LOCAL_CHAT_ID, "inflation", 6, today=TODAY)
    progress.record(web.LOCAL_CHAT_ID, "photosynthesis", 8, today=TODAY)

    trend = web.build_dashboard_data()["trend"]
    assert len(trend) == 1
    assert trend[0]["count"] == 2
    assert trend[0]["average"] == 7.0


def test_due_list_reports_overdue(stores):
    _, progress = stores
    progress.record(web.LOCAL_CHAT_ID, "inflation", 8, today=date(2026, 8, 1))
    data = web.build_dashboard_data()
    assert any(row["concept"] == "inflation" for row in data["due"])


def test_index_renders_html(client, stores):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Explain-Back Tutor" in body
    assert "inflation" in body


def test_index_renders_with_scores(client, stores):
    _, progress = stores
    progress.record(web.LOCAL_CHAT_ID, "inflation", 7, today=TODAY)
    body = client.get("/").get_data(as_text=True)
    assert "7.0" in body
    assert "Daily average" in body


def test_api_returns_json(client, stores):
    response = client.get("/api/data")
    assert response.status_code == 200
    payload = response.get_json()
    assert "totals" in payload
    assert "concepts" in payload
    assert payload["totals"]["loaded"] == 2


# ----------------------------------------------------------------- subjects


@pytest.fixture
def subject_stores(tmp_path, monkeypatch):
    concepts = ConceptStore(tmp_path / "concepts.json")
    concepts.add("Acids", "Proton donors.", subject="Chemistry")
    concepts.add("Bonding", "Shared electrons.", subject="Chemistry")
    concepts.add("Inertia", "Resists change.", subject="Physics")
    concepts.save()
    progress = ProgressStore(tmp_path / "progress.json")
    monkeypatch.setattr(web, "ConceptStore", lambda *a, **k: concepts)
    monkeypatch.setattr(web, "ProgressStore", lambda *a, **k: progress)
    return concepts, progress


def test_concepts_carry_subject(subject_stores):
    data = web.build_dashboard_data()
    acids = next(c for c in data["concepts"] if c["concept"] == "acids")
    assert acids["subject"] == "chemistry"


def test_unsubjected_concept_reports_uncategorized(stores):
    data = web.build_dashboard_data()
    assert all(c["subject"] == "uncategorized" for c in data["concepts"])


def test_subject_rollup(subject_stores):
    _, progress = subject_stores
    progress.record(web.LOCAL_CHAT_ID, "acids", 8, today=TODAY)

    data = web.build_dashboard_data()
    chemistry = next(s for s in data["subjects"] if s["subject"] == "chemistry")
    assert chemistry["concepts"] == 2
    assert chemistry["studied"] == 1
    assert chemistry["average"] == 8.0

    physics = next(s for s in data["subjects"] if s["subject"] == "physics")
    assert physics["studied"] == 0
    assert physics["average"] is None


def test_subject_section_renders_when_multiple_subjects(subject_stores):
    web.app.config["TESTING"] = True
    body = web.app.test_client().get("/").get_data(as_text=True)
    assert "By subject" in body
    assert "chemistry" in body


def test_subject_section_hidden_for_single_subject(stores):
    web.app.config["TESTING"] = True
    body = web.app.test_client().get("/").get_data(as_text=True)
    assert "By subject" not in body


# ------------------------------------------------------------ gamification


def test_gamification_block_on_empty_history(stores):
    g = web.build_dashboard_data()["gamification"]
    assert g["level"] == 1
    assert g["xp"] == 0
    assert g["earned_count"] == 0
    assert g["total_count"] == len(g["badges"])


def test_gamification_awards_xp_and_badges(stores):
    _, progress = stores
    progress.record(web.LOCAL_CHAT_ID, "inflation", 10, today=TODAY)

    g = web.build_dashboard_data()["gamification"]
    assert g["xp"] > 0
    assert g["earned_count"] >= 2  # First Steps + Perfectionist

    names = {b["name"] for b in g["badges"] if b["earned"]}
    assert "First Steps" in names
    assert "Perfectionist" in names


def test_every_badge_is_listed_earned_or_not(stores):
    _, progress = stores
    progress.record(web.LOCAL_CHAT_ID, "inflation", 5, today=TODAY)

    badges = web.build_dashboard_data()["gamification"]["badges"]
    assert all("earned" in b and "description" in b for b in badges)
    assert any(not b["earned"] for b in badges)


def test_progress_percent_within_bounds(stores):
    _, progress = stores
    for _ in range(5):
        progress.record(web.LOCAL_CHAT_ID, "inflation", 9, today=TODAY)

    g = web.build_dashboard_data()["gamification"]
    assert 0 <= g["progress_percent"] <= 100


def test_dashboard_renders_level_and_badges(client, stores):
    _, progress = stores
    progress.record(web.LOCAL_CHAT_ID, "inflation", 8, today=TODAY)

    body = client.get("/").get_data(as_text=True)
    assert "Level" in body
    assert "Badges" in body
    assert "First Steps" in body


def test_cli_and_dashboard_agree_on_xp(stores):
    """Both surfaces derive from the same history, so they must never disagree."""
    from src.gamification import total_xp

    _, progress = stores
    progress.record(web.LOCAL_CHAT_ID, "inflation", 7, today=TODAY)

    attempts = progress.all_attempts(web.LOCAL_CHAT_ID)
    assert web.build_dashboard_data()["gamification"]["xp"] == total_xp(attempts)
