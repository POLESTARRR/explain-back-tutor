import json

from src.concepts import ConceptStore, parse_markdown_notes


def test_parse_markdown_notes_splits_on_h2():
    text = """# Title\nintro text ignored\n\n## First Concept\nline one\nline two\n\n## Second\nother notes\n"""
    parsed = parse_markdown_notes(text)
    assert set(parsed.keys()) == {"First Concept", "Second"}
    assert "line one" in parsed["First Concept"]
    assert "line two" in parsed["First Concept"]
    assert parsed["Second"] == "other notes"


def test_parse_markdown_notes_ignores_content_before_first_heading():
    text = "no heading yet\n\n## Only\nbody\n"
    parsed = parse_markdown_notes(text)
    assert parsed == {"Only": "body"}


def test_parse_markdown_notes_drops_empty_sections():
    text = "## Empty\n\n## Real\nsomething\n"
    parsed = parse_markdown_notes(text)
    assert parsed == {"Real": "something"}


def test_add_and_get_is_case_insensitive(tmp_path):
    store = ConceptStore(tmp_path / "concepts.json")
    store.add("Inflation", "some notes")
    assert store.get("inflation") == "some notes"
    assert store.get("  INFLATION  ") == "some notes"
    assert store.exists("Inflation")


def test_get_missing_returns_none(tmp_path):
    store = ConceptStore(tmp_path / "concepts.json")
    assert store.get("nope") is None
    assert not store.exists("nope")


def test_save_and_reload_round_trips(tmp_path):
    path = tmp_path / "concepts.json"
    store = ConceptStore(path)
    store.add("Inflation", "notes about inflation")
    store.save()

    reloaded = ConceptStore(path)
    assert reloaded.get("inflation") == "notes about inflation"
    assert len(reloaded) == 1


def test_merge_keeps_existing_and_adds_new(tmp_path):
    store = ConceptStore(tmp_path / "concepts.json")
    store.add("A", "a-notes")
    store.merge({"B": "b-notes"})
    assert store.get("A") == "a-notes"
    assert store.get("B") == "b-notes"
    assert len(store) == 2


def test_replace_all_wipes_existing(tmp_path):
    store = ConceptStore(tmp_path / "concepts.json")
    store.add("A", "a-notes")
    store.replace_all({"B": "b-notes"})
    assert store.get("A") is None
    assert store.get("B") == "b-notes"
    assert len(store) == 1


def test_names_sorted(tmp_path):
    store = ConceptStore(tmp_path / "concepts.json")
    store.add("Zeta", "z")
    store.add("Alpha", "a")
    assert store.names() == ["alpha", "zeta"]


def test_find_close_matches_prefix_and_substring(tmp_path):
    store = ConceptStore(tmp_path / "concepts.json")
    store.add("inflation", "n")
    store.add("deflation", "n")
    store.add("tcp vs udp", "n")

    matches = store.find_close_matches("inflat")
    assert "inflation" in matches

    matches2 = store.find_close_matches("udp")
    assert "tcp vs udp" in matches2


def test_find_close_matches_empty_query(tmp_path):
    store = ConceptStore(tmp_path / "concepts.json")
    store.add("inflation", "n")
    assert store.find_close_matches("") == []


def test_load_missing_file_starts_empty(tmp_path):
    store = ConceptStore(tmp_path / "does_not_exist.json")
    assert len(store) == 0


def test_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "concepts.json"
    store = ConceptStore(path)
    store.add("A", "a")
    store.save()
    assert path.exists()
    assert json.loads(path.read_text()) == {"a": "a"}
