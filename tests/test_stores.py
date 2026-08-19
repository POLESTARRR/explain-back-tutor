"""Choosing between local JSON stores and per-user database stores."""

import pytest

from src import db, stores
from src.concepts import ConceptStore
from src.progress import ProgressStore
from src.tutor import TutorHistory


@pytest.fixture
def no_database(monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)


@pytest.fixture
def with_database(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://example.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "token")


# ------------------------------------------------------------- selection


def test_local_by_default(no_database):
    assert stores.using_database() is False
    assert isinstance(stores.concept_store(), ConceptStore)
    assert isinstance(stores.progress_store(), ProgressStore)
    assert isinstance(stores.tutor_history(), TutorHistory)


def test_database_when_configured(with_database):
    assert stores.using_database() is True
    assert isinstance(stores.concept_store("u1"), db.TursoConceptStore)
    assert isinstance(stores.progress_store("u1"), db.TursoProgressStore)
    assert isinstance(stores.tutor_history("u1"), db.TursoTutorHistory)


def test_half_configured_stays_local(monkeypatch):
    """A URL without a token must not be treated as a working database."""
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://example.turso.io")
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    assert stores.using_database() is False


def test_database_stores_carry_their_user(with_database):
    assert stores.concept_store("alice").user_id == "alice"
    assert stores.progress_store("bob").user_id == "bob"


# ----------------------------------------------------------- session key


def test_session_key_is_local_when_offline(no_database):
    # Locally everything shares one history, which the terminal also uses.
    assert stores.session_key("anything") == stores.LOCAL_USER


def test_session_key_is_the_user_when_deployed(with_database):
    assert stores.session_key("alice") == "alice"


# ------------------------------------------------------------- contract


def test_both_concept_stores_expose_the_same_surface(with_database):
    """If these drift, the app breaks only once deployed, which is the worst
    possible moment to find out."""
    required = {
        "get", "subject_of", "exists", "names", "subjects", "subject_exists",
        "counts_by_subject", "find_close_matches", "add", "merge", "replace_all", "save",
    }
    assert required <= set(dir(ConceptStore))
    assert required <= set(dir(db.TursoConceptStore))


def test_both_progress_stores_expose_the_same_surface(with_database):
    required = {
        "record", "history", "average", "averages", "latest_score", "review_state",
        "review_states", "due", "weakest", "studied_concepts", "total_attempts",
        "all_attempts",
    }
    assert required <= set(dir(ProgressStore))
    assert required <= set(dir(db.TursoProgressStore))


def test_both_tutor_histories_expose_the_same_surface(with_database, tmp_path):
    """Checked on instances, not classes: the JSON store sets `turns` in
    __init__ while the database one exposes it as a property, so a class-level
    check would miss it on one side and prove nothing."""
    required = {"add", "clear", "recent", "turns"}
    assert required <= set(dir(TutorHistory(tmp_path / "t.json")))
    assert required <= set(dir(db.TursoTutorHistory("u1")))


# ------------------------------------------------------------- database


def test_connect_requires_both_settings(monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    with pytest.raises(db.DatabaseError, match="TURSO_DATABASE_URL"):
        db.connect()


def test_schema_covers_every_table():
    combined = " ".join(db.SCHEMA)
    for table in ("concepts", "attempts", "review_state", "tutor_turns"):
        assert table in combined


def test_every_table_is_scoped_by_user():
    """The whole isolation guarantee rests on this."""
    for statement in db.SCHEMA:
        if "CREATE TABLE" in statement:
            assert "user_id" in statement


def test_user_scoped_tables_key_on_user_id():
    for statement in db.SCHEMA:
        if "PRIMARY KEY" in statement:
            assert "user_id" in statement.split("PRIMARY KEY")[1]
