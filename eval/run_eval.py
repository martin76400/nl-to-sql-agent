"""Évalue l'agent sur eval/questions.json et affiche son exactitude.

Usage : python eval/run_eval.py

Pour chaque question, on exécute la requête de référence et celle de l'agent,
puis on compare les RÉSULTATS (voir src/evaluation.py). Le détail est écrit
dans eval/results.json.
"""

import json
import sys
import time
from pathlib import Path

# Permet de lancer le script depuis n'importe où : la racine du dépôt est
# ajoutée au chemin d'import pour que `from src import ...` fonctionne.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import agent, config, db  # noqa: E402
from src.evaluation import results_match  # noqa: E402
from src.llm import get_llm  # noqa: E402

QUESTIONS_PATH = ROOT / "eval" / "questions.json"
RESULTS_PATH = ROOT / "eval" / "results.json"


def main() -> int:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    llm = get_llm()
    details = []
    started = time.time()

    for item in questions:
        expected = db.run_query(item["sql"])
        # write_answer=False : seule la requête compte, on saute la rédaction.
        result = agent.ask(item["question"], llm=llm, write_answer=False)
        correct = not result.error and results_match(expected.rows, result.rows)

        details.append(
            {
                "id": item["id"],
                "level": item["level"],
                "question": item["question"],
                "correct": correct,
                "attempts": result.attempts,
                "generated_sql": result.sql,
                "error": result.error,
            }
        )
        mark = "OK  " if correct else "FAUX"
        print(f"{mark} [{item['level']:<9}] {item['id']:>2}. {item['question']}")
        if not correct:
            print(f"       SQL    : {result.sql}")
            print(f"       Obtenu : {result.error or result.rows[:3]}")
            print(f"       Attendu: {expected.rows[:3]}")

    total = len(details)
    n_correct = sum(d["correct"] for d in details)
    print(f"\nModèle : {config.OLLAMA_MODEL}")
    for level in dict.fromkeys(d["level"] for d in details):
        subset = [d for d in details if d["level"] == level]
        print(f"  {level:<9} : {sum(d['correct'] for d in subset)}/{len(subset)}")
    print(f"Exactitude : {n_correct}/{total} = {n_correct / total:.0%}")
    print(f"Durée : {time.time() - started:.0f} s")

    RESULTS_PATH.write_text(
        json.dumps(
            {
                "model": config.OLLAMA_MODEL,
                "accuracy": round(n_correct / total, 3),
                "correct": n_correct,
                "total": total,
                "details": details,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
