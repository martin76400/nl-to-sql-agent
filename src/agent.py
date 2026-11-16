"""Agent NL-to-SQL : génère une requête, l'exécute, et se corrige en cas d'erreur.

Différence avec la chaîne (src/chain.py) : ici il y a une BOUCLE. Quand SQLite
refuse une requête, le message d'erreur est renvoyé au modèle, qui propose une
correction. On s'arrête au premier succès ou après MAX_ATTEMPTS essais.

Le déroulé est décrit par un graphe LangGraph :

    lire_schema -> generer_sql -> executer_sql --succès--> rediger_reponse -> FIN
                        ^               |
                        +--- erreur ----+   (tant qu'il reste des essais)

Chaque nœud est une fonction qui reçoit l'état courant et renvoie les champs
qu'elle modifie. LangGraph fusionne ces champs dans l'état et suit les flèches.

Essai en ligne de commande :
    python -m src.agent "Quels sont les 5 artistes avec le plus d'albums ?"
"""

import sqlite3
import sys
from typing import TypedDict

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from src import config, db
from src.chain import Result, build_answer_chain, build_sql_chain, format_result
from src.llm import get_llm
from src.prompts import CORRECTION_TEMPLATE


class AgentState(TypedDict, total=False):
    """Mémoire de travail de l'agent pour UNE question."""

    question: str
    schema: str
    sql: str  # dernière requête générée
    error: str  # erreur de la dernière exécution ("" si succès)
    failures: list[dict]  # essais ratés : [{"sql": ..., "error": ...}, ...]
    columns: list[str]
    rows: list[tuple]
    answer: str


def build_graph(llm: BaseChatModel, write_answer: bool = True):
    """Assemble et compile le graphe de l'agent.

    write_answer=False saute la rédaction finale : l'évaluation ne compare que
    les résultats SQL, inutile de payer un second appel au modèle.
    """
    sql_chain = build_sql_chain(llm)
    answer_chain = build_answer_chain(llm)

    def read_schema(state: AgentState) -> dict:
        # Le schéma est relu à chaque question : si la base change, l'agent suit.
        return {"schema": db.get_schema(), "failures": []}

    def generate_sql(state: AgentState) -> dict:
        # Chaque essai raté est rejoué comme un échange : la requête fautive
        # (côté "ai"), puis l'erreur obtenue (côté "human"). Le modèle voit ainsi
        # tout l'historique et évite de reproposer la même requête.
        corrections = []
        for failure in state["failures"]:
            corrections.append(("ai", failure["sql"]))
            corrections.append(
                ("human", CORRECTION_TEMPLATE.format(error=failure["error"]))
            )
        sql = sql_chain.invoke(
            {
                "schema": state["schema"],
                "question": state["question"],
                "corrections": corrections,
            }
        )
        return {"sql": sql}

    def execute_sql(state: AgentState) -> dict:
        try:
            if not state["sql"]:
                raise ValueError("The answer contained no SQL query.")
            result = db.run_query(state["sql"])
        except (sqlite3.Error, ValueError) as exc:
            failure = {"sql": state["sql"], "error": str(exc)}
            return {"error": str(exc), "failures": state["failures"] + [failure]}
        return {"error": "", "columns": result.columns, "rows": result.rows}

    def answer(state: AgentState) -> dict:
        result = db.QueryResult(columns=state["columns"], rows=state["rows"])
        text = answer_chain.invoke(
            {
                "question": state["question"],
                "sql": state["sql"],
                "result": format_result(result),
            }
        )
        return {"answer": text.strip()}

    def next_step(state: AgentState) -> str:
        """Décide de la suite après l'exécution : c'est le « cerveau » de la boucle."""
        if not state["error"]:
            return "answer" if write_answer else END
        if len(state["failures"]) < config.MAX_ATTEMPTS:
            return "generate_sql"
        return END  # essais épuisés : on abandonne avec l'erreur

    graph = StateGraph(AgentState)
    graph.add_node("read_schema", read_schema)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("answer", answer)
    graph.add_edge(START, "read_schema")
    graph.add_edge("read_schema", "generate_sql")
    graph.add_edge("generate_sql", "execute_sql")
    graph.add_conditional_edges(
        "execute_sql", next_step, ["answer", "generate_sql", END]
    )
    graph.add_edge("answer", END)
    return graph.compile()


def ask(
    question: str, llm: BaseChatModel | None = None, write_answer: bool = True
) -> Result:
    """Point d'entrée : pose une question à l'agent et renvoie un Result."""
    graph = build_graph(llm or get_llm(), write_answer=write_answer)
    state = graph.invoke({"question": question})
    failures = state.get("failures", [])
    succeeded = not state.get("error")
    return Result(
        question=question,
        sql=state.get("sql", ""),
        columns=state.get("columns", []),
        rows=state.get("rows", []),
        answer=state.get("answer", ""),
        error=state.get("error", ""),
        attempts=len(failures) + (1 if succeeded else 0),
        failures=failures,
    )


if __name__ == "__main__":
    outcome = ask(" ".join(sys.argv[1:]) or "Combien y a-t-il d'artistes ?")
    for number, failure in enumerate(outcome.failures, start=1):
        print(f"Essai {number} raté : {failure['sql']}\n  -> {failure['error']}")
    print(f"SQL ({outcome.attempts} essai(s)) : {outcome.sql}")
    print(f"Lignes  : {outcome.rows[:5]}")
    print(f"Réponse : {outcome.answer or 'ERREUR : ' + outcome.error}")
