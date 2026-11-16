"""Fixtures partagées par tous les tests.

Les tests ne dépendent ni d'Ollama ni de la base Chinook : ils tournent donc
tels quels dans la CI. On fabrique une mini-base SQLite jetable, et le LLM est
remplacé par un faux modèle qui récite des réponses écrites à l'avance.
"""

import sqlite3

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src import config


@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    """Crée une petite base (2 tables, 1 clé étrangère) et y branche le projet.

    autouse=True : chaque test l'utilise sans avoir à la demander. Aucun test ne
    peut ainsi toucher par accident à la vraie base.
    """
    path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE Artist (ArtistId INTEGER PRIMARY KEY, Name NVARCHAR(120));
        CREATE TABLE Album (
            AlbumId INTEGER PRIMARY KEY,
            Title NVARCHAR(160),
            ArtistId INTEGER REFERENCES Artist (ArtistId)
        );
        INSERT INTO Artist VALUES (1, 'AC/DC'), (2, 'Queen'), (3, 'Drop Kings');
        INSERT INTO Album VALUES (1, 'Let There Be Rock', 1), (2, 'Jazz', 2),
                                 (3, 'News Of The World', 2);
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", path)
    return path


@pytest.fixture
def fake_llm():
    """Fabrique un faux LLM qui renvoie, dans l'ordre, les réponses données."""

    def make(*responses: str) -> FakeListChatModel:
        return FakeListChatModel(responses=list(responses))

    return make
