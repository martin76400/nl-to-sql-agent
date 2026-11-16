"""Chaîne basique : question -> SQL -> exécution -> réponse.

Une « chaîne » est une suite d'étapes fixe, sans boucle ni décision : si le SQL
généré est faux, elle échoue. C'est la brique de base ; src/agent.py réutilise
ces mêmes maillons et ajoute la boucle de correction.

Essai en ligne de commande :
    python -m src.chain "Combien y a-t-il d'artistes ?"
"""

import sqlite3
import sys
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableLambda

from src import db
from src.llm import extract_sql, get_llm
from src.prompts import ANSWER_PROMPT, SQL_PROMPT

# Nombre de lignes de résultat montrées au modèle pour rédiger la réponse.
# Au-delà, le prompt grossit sans que la réponse s'améliore.
MAX_ROWS_IN_PROMPT = 20


@dataclass
class Result:
    """Tout ce qu'on sait à la fin du traitement d'une question."""

    question: str
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    answer: str = ""
    error: str = ""  # vide si tout s'est bien passé
    attempts: int = 1
    # Essais ratés de l'agent : [{"sql": ..., "error": ...}, ...]
    failures: list[dict] = field(default_factory=list)


def build_sql_chain(llm: BaseChatModel) -> Runnable:
    """Maillon 1 : {schema, question} -> requête SQL nettoyée.

    L'opérateur | de LangChain (LCEL) enchaîne les étapes : la sortie de l'une
    devient l'entrée de la suivante, comme un pipe Unix.
    """
    return SQL_PROMPT | llm | StrOutputParser() | RunnableLambda(extract_sql)


def build_answer_chain(llm: BaseChatModel) -> Runnable:
    """Maillon 2 : {question, sql, result} -> réponse en langage naturel."""
    return ANSWER_PROMPT | llm | StrOutputParser()


def format_result(result: db.QueryResult) -> str:
    """Met le résultat SQL sous forme de texte lisible par le modèle."""
    if not result.rows:
        return "(no rows)"
    lines = [" | ".join(result.columns)]
    for row in result.rows[:MAX_ROWS_IN_PROMPT]:
        lines.append(" | ".join(str(value) for value in row))
    hidden = len(result.rows) - MAX_ROWS_IN_PROMPT
    if hidden > 0:
        lines.append(f"... ({hidden} more rows not shown)")
    return "\n".join(lines)


def run_chain(question: str, llm: BaseChatModel | None = None) -> Result:
    """Traite une question en un seul passage, sans réessai."""
    llm = llm or get_llm()
    result = Result(question=question)

    result.sql = build_sql_chain(llm).invoke(
        {"schema": db.get_schema(), "question": question}
    )
    try:
        query_result = db.run_query(result.sql)
    except sqlite3.Error as exc:
        result.error = str(exc)
        return result

    result.columns, result.rows = query_result.columns, query_result.rows
    result.answer = build_answer_chain(llm).invoke(
        {
            "question": question,
            "sql": result.sql,
            "result": format_result(query_result),
        }
    ).strip()
    return result


if __name__ == "__main__":
    outcome = run_chain(" ".join(sys.argv[1:]) or "Combien y a-t-il d'artistes ?")
    print(f"SQL     : {outcome.sql}")
    print(f"Lignes  : {outcome.rows[:5]}")
    print(f"Réponse : {outcome.answer or 'ERREUR : ' + outcome.error}")
