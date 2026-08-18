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
