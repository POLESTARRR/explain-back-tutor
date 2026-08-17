from src.progress import ProgressStore


def test_record_and_history(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.record("chat1", "inflation", 7)
    store.record("chat1", "inflation", 9)

    history = store.history("chat1", "inflation")
    assert [e["score"] for e in history] == [7, 9]
    assert all("ts" in e for e in history)


def test_average(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.record("chat1", "inflation", 4)
    store.record("chat1", "inflation", 8)
    assert store.average("chat1", "inflation") == 6

    assert store.average("chat1", "unseen") is None


def test_weakest_sorted_ascending_by_average(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.record("chat1", "strong", 9)
    store.record("chat1", "weak", 2)
    store.record("chat1", "medium", 5)

    ranked = store.weakest("chat1")
    assert [r[0] for r in ranked] == ["weak", "medium", "strong"]


def test_weakest_respects_limit(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    for i, concept in enumerate(["a", "b", "c", "d"]):
        store.record("chat1", concept, i)
    assert len(store.weakest("chat1", limit=2)) == 2


def test_weakest_empty_when_no_history(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    assert store.weakest("chat1") == []


def test_chats_are_isolated(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.record("chat1", "inflation", 10)
    store.record("chat2", "inflation", 2)
    assert store.average("chat1", "inflation") == 10
    assert store.average("chat2", "inflation") == 2


def test_persists_across_instances(tmp_path):
    path = tmp_path / "progress.json"
    store1 = ProgressStore(path)
    store1.record("chat1", "inflation", 5)

    store2 = ProgressStore(path)
    assert store2.average("chat1", "inflation") == 5


def test_studied_concepts(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.record("chat1", "b", 5)
    store.record("chat1", "a", 5)
    assert store.studied_concepts("chat1") == ["a", "b"]
