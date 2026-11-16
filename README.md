# nl-to-sql-agent

Mini-agent NL-to-SQL : pose une question en langage naturel, l'agent génère la requête SQL, l'exécute sur SQLite (base Chinook) et répond.

100 % local : LangChain + Ollama, aucune API payante.

> Projet en cours de construction.

## Score d'évaluation

| Modèle | Facile | Moyen | Difficile | Exactitude |
|---|---|---|---|---|
| `qwen2.5-coder:7b` | 5/5 | 5/5 | 5/5 | **15/15 (100 %)** |

Mesuré avec `python eval/run_eval.py` sur les 15 questions de `eval/questions.json` (détail dans `eval/results.json`).
