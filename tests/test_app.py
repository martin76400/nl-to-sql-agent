"""Test de fumée de l'interface, avec l'agent remplacé par une fausse réponse."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import agent
from src.chain import Result

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")
# Le premier lancement importe Streamlit et pandas à froid : le délai par défaut
# (3 s) peut alors être dépassé sur une machine lente.
TIMEOUT_S = 30


def test_app_shows_answer_sql_table_and_history(monkeypatch):
    def fake_ask(question, **kwargs):
        return Result(
            question=question,
            sql="SELECT Name FROM Artist",
            columns=["Name"],
            rows=[("AC/DC",), ("Queen",)],
            answer="AC/DC et Queen.",
        )

    monkeypatch.setattr(agent, "ask", fake_ask)
    app = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT_S).run()
    assert not app.exception

    app.chat_input[0].set_value("Quels artistes ?").run()
    assert not app.exception
    reply = app.chat_message[1]
    assert reply.markdown[0].value == "AC/DC et Queen."
    assert reply.code[0].value == "SELECT Name FROM Artist"
    assert app.dataframe[0].value.shape == (2, 1)
    assert len(app.session_state.history) == 1


def test_app_shows_error_when_agent_fails(monkeypatch):
    def broken_ask(question, **kwargs):
        raise ConnectionError("Ollama injoignable")

    monkeypatch.setattr(agent, "ask", broken_ask)
    app = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT_S).run()
    app.chat_input[0].set_value("Une question").run()
    assert not app.exception
    assert "Ollama injoignable" in app.error[0].value
