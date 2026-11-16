"""Garde-fous : ce qui doit passer, ce qui doit être bloqué, et le LIMIT."""

import pytest

from src import safety
from src.safety import UnsafeQueryError


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM Artist",
        "select Name from Artist where ArtistId = 1;",
        "WITH a AS (SELECT 1 AS x) SELECT x FROM a",
        # Mots interdits présents, mais dans une chaîne ou un commentaire.
        "SELECT * FROM Artist WHERE Name = 'Drop Kings'",
        "SELECT * FROM Artist WHERE Name = 'a; DELETE FROM Artist'",
        "SELECT * FROM Artist -- update plus tard",
        # REPLACE est une fonction de lecture ; LastUpdate n'est pas UPDATE.
        "SELECT REPLACE(Name, 'a', 'b') AS LastUpdate FROM Artist",
    ],
)
def test_read_queries_are_allowed(sql):
    safety.validate(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE Artist",
        "DELETE FROM Artist",
        "UPDATE Artist SET Name = 'x'",
        "INSERT INTO Artist VALUES (9, 'x')",
        "ALTER TABLE Artist ADD COLUMN c TEXT",
        "CREATE TABLE t (x)",
        "PRAGMA table_info(Artist)",
        "delete from Artist",  # insensible à la casse
        "SELECT 1; DROP TABLE Artist",  # deux instructions
        "SELECT 1 /* c */ ; DELETE FROM Artist",
        "WITH a AS (SELECT 1) DELETE FROM Artist",  # écriture cachée derrière WITH
        "",
        "   ",
        "-- juste un commentaire",
    ],
)
def test_dangerous_queries_are_blocked(sql):
    with pytest.raises(UnsafeQueryError):
        safety.validate(sql)


def test_limit_is_added_when_missing():
    assert safety.ensure_limit("SELECT * FROM Artist", 50) == "SELECT * FROM Artist\nLIMIT 50"


def test_existing_limit_is_kept():
    assert safety.ensure_limit("SELECT * FROM Artist LIMIT 3;") == "SELECT * FROM Artist LIMIT 3"


def test_limit_inside_subquery_does_not_count():
    sql = "SELECT * FROM (SELECT * FROM Artist LIMIT 2)"
    assert safety.ensure_limit(sql, 50).endswith("LIMIT 50")


def test_limit_survives_trailing_comment():
    # Sans retour à la ligne, le LIMIT ajouté serait avalé par le commentaire.
    assert safety.ensure_limit("SELECT 1 -- fin", 50).splitlines()[-1] == "LIMIT 50"
