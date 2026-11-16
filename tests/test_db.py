"""Connexion, schéma, et garde-fous appliqués au niveau de la base."""

import sqlite3

import pytest

from src import config, db
from src.safety import UnsafeQueryError

INFINITE_QUERY = (
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
    "SELECT COUNT(*) FROM c"
)


def test_run_query_returns_columns_and_rows():
    result = db.run_query("SELECT Name FROM Artist ORDER BY ArtistId")
    assert result.columns == ["Name"]
    assert result.rows == [("AC/DC",), ("Queen",), ("Drop Kings",)]


def test_schema_is_compact_and_shows_keys():
    schema = db.get_schema()
    assert schema.splitlines() == [
        "Album(AlbumId INTEGER PK, Title TEXT, ArtistId INTEGER -> Artist.ArtistId)",
        "Artist(ArtistId INTEGER PK, Name TEXT)",
    ]


def test_connection_is_read_only():
    # Ce test contourne volontairement safety.validate : même sans lui,
    # SQLite refuse l'écriture.
    conn = db.connect()
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM Artist")
    conn.close()
    assert len(db.run_query("SELECT * FROM Artist").rows) == 3


def test_run_query_blocks_writes_before_execution():
    with pytest.raises(UnsafeQueryError):
        db.run_query("DROP TABLE Artist")


def test_default_limit_is_applied(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_LIMIT", 2)
    result = db.run_query("SELECT * FROM Artist")
    assert len(result.rows) == 2
    assert result.sql.endswith("LIMIT 2")


def test_slow_query_times_out():
    with pytest.raises(TimeoutError):
        db.run_query(INFINITE_QUERY, timeout_s=0.2)


def test_invalid_sql_raises_sqlite_error():
    with pytest.raises(sqlite3.Error, match="no such column"):
        db.run_query("SELECT Nom FROM Artist")


def test_missing_database_gives_a_helpful_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_chinook"):
        db.connect(tmp_path / "absente.sqlite")
