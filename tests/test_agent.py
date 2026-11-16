"""Boucle de l'agent, avec un LLM factice (aucun appel à Ollama)."""

from src import agent, config
from src.chain import run_chain
from src.prompts import CANNOT_ANSWER


def test_success_on_first_attempt(fake_llm):
    llm = fake_llm("SELECT COUNT(*) FROM Artist", "Il y a 3 artistes.")
    result = agent.ask("Combien d'artistes ?", llm=llm)
    assert result.rows == [(3,)]
    assert result.answer == "Il y a 3 artistes."
    assert result.attempts == 1
    assert not result.error and not result.failures


def test_error_is_sent_back_and_corrected(fake_llm):
    llm = fake_llm(
        "SELECT Nom FROM Artist",  # colonne inexistante
        "SELECT Name FROM Artist WHERE ArtistId = 2",  # correction
        "Queen.",
    )
    result = agent.ask("Qui est l'artiste 2 ?", llm=llm)
    assert result.rows == [("Queen",)]
    assert result.attempts == 2
    assert "no such column" in result.failures[0]["error"]


def test_gives_up_after_max_attempts(fake_llm):
    llm = fake_llm("SELECT x FROM Inconnue")  # le faux LLM répète cette réponse
    result = agent.ask("Question impossible", llm=llm)
    assert result.error
    assert result.attempts == config.MAX_ATTEMPTS == len(result.failures)
    assert result.answer == ""


def test_write_request_is_refused_without_retry(fake_llm):
    llm = fake_llm("DELETE FROM Artist", "SELECT 1")
    result = agent.ask("Supprime les artistes", llm=llm)
    assert "SELECT" in result.error
    assert len(result.failures) == 1  # pas de second essai
    assert result.rows == []


def test_out_of_scope_question(fake_llm):
    result = agent.ask("Quelle est la météo ?", llm=fake_llm(CANNOT_ANSWER))
    assert result.error == agent.OUT_OF_SCOPE_MESSAGE
    assert result.sql == "" and not result.failures


def test_answer_can_be_skipped(fake_llm):
    llm = fake_llm("SELECT COUNT(*) FROM Album")
    result = agent.ask("Combien d'albums ?", llm=llm, write_answer=False)
    assert result.rows == [(3,)] and result.answer == ""


def test_basic_chain_does_not_retry(fake_llm):
    result = run_chain("?", llm=fake_llm("SELECT Nom FROM Artist", "SELECT 1"))
    assert "no such column" in result.error
