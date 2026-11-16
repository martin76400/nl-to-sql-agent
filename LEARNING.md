# Comprendre le projet

Ce document t'explique comment le projet fonctionne, pourquoi il est construit ainsi, et te propose cinq exercices pour le modifier toi-même. Lis-le avec le code ouvert à côté.

## 1. L'idée en une minute

Un modèle de langage sait écrire du SQL, mais il ne connaît pas ta base et il ne peut rien exécuter. Le projet lui apporte ce qui manque :

1. on lui **décrit la base** (le schéma) dans le prompt ;
2. on **exécute** nous-mêmes le SQL qu'il écrit ;
3. si la requête échoue, on lui **renvoie l'erreur** pour qu'il se corrige ;
4. on lui redonne le **résultat** pour qu'il rédige une réponse.

Le modèle n'a donc jamais accès à la base. Il produit du texte, et c'est notre code Python qui décide quoi en faire. Toute la sécurité repose sur cette séparation.

## 2. Le chemin complet d'une question

Prenons « Qui est l'artiste numéro 2 ? », en supposant que le modèle se trompe une première fois.

| Étape | Qui agit | Ce qui se passe | Où dans le code |
|---|---|---|---|
| 1 | Streamlit | Tu valides la question ; l'interface appelle `agent.ask(question)` | `app.py` |
| 2 | Agent | Le graphe démarre avec l'état `{"question": ...}` | `agent.ask` |
| 3 | Base | L'agent lit le schéma : une ligne par table | nœud `read_schema` → `db.get_schema` |
| 4 | Modèle | Le prompt (règles + schéma + exemples + question) part chez Ollama, qui renvoie `SELECT Nom FROM Artist` | nœud `generate_sql` → `chain.build_sql_chain` |
| 5 | Python | La réponse brute est nettoyée (balises markdown, point-virgule) | `llm.extract_sql` |
| 6 | Garde-fous | La requête est validée et reçoit un `LIMIT` | nœud `execute_sql` → `db.run_query` → `safety.make_safe` |
| 7 | Base | SQLite répond `no such column: Nom` | `db.run_query` |
| 8 | Agent | L'erreur est rangée dans `failures` ; il reste des essais, donc retour à l'étape 4 | fonction `next_step` |
| 9 | Modèle | Le prompt contient maintenant la requête fautive et son erreur ; le modèle renvoie `SELECT Name FROM Artist WHERE ArtistId = 2` | nœud `generate_sql` |
| 10 | Base | La requête passe : une ligne, `Queen` | nœud `execute_sql` |
| 11 | Modèle | Second prompt (question + SQL + résultat) ; le modèle rédige « L'artiste numéro 2 est Queen. » | nœud `answer` |
| 12 | Streamlit | L'interface affiche la réponse, le SQL, le tableau et l'essai raté | `app.show_result` |

Ce scénario exact est rejoué, avec un faux modèle, dans `tests/test_agent.py` (`test_error_is_sent_back_and_corrected`). C'est un bon point de départ pour lire le code : lance ce test avec un point d'arrêt.

## 3. Les fichiers, un par un

L'ordre ci-dessous est l'ordre de lecture conseillé : chaque fichier ne dépend que des précédents.

### `src/config.py` : les réglages

Rassemble toutes les valeurs réglables. Celles qui dépendent de la machine viennent de `.env` (`OLLAMA_MODEL`, `OLLAMA_BASE_URL`) ; les autres sont des constantes : `MAX_ATTEMPTS` (3 essais), `DEFAULT_LIMIT` (200 lignes), `QUERY_TIMEOUT_S` (5 secondes).

### `src/safety.py` : les garde-fous sur le texte du SQL

- `validate(sql)` refuse tout ce qui n'est pas une lecture simple : requête vide, plusieurs instructions, autre chose que `SELECT` ou `WITH`, mot-clé interdit.
- `_skeleton(sql)` retire d'abord les commentaires et les chaînes de caractères. Sans cela, `WHERE Name = 'Drop the beat'` serait refusé à tort.
- `ensure_limit(sql)` ajoute `LIMIT 200` s'il n'y a pas de `LIMIT` au niveau principal de la requête.
- `make_safe(sql)` enchaîne les deux. C'est la seule fonction appelée de l'extérieur.

### `src/db.py` : la base

- `connect()` ouvre SQLite en **lecture seule** (`mode=ro`).
- `get_schema()` interroge SQLite (`PRAGMA table_info`, `PRAGMA foreign_key_list`) et fabrique le schéma compact.
- `run_query(sql)` est la **seule porte** vers la base pour du SQL généré : elle appelle `safety.make_safe`, installe le timeout, exécute, et renvoie un `QueryResult` (colonnes, lignes, SQL réellement exécuté).
- `QUERY_ERRORS` liste les trois erreurs « normales » : refus des garde-fous, erreur SQLite, timeout.

### `src/prompts.py` : ce qu'on dit au modèle

- `SQL_SYSTEM` : les règles et l'emplacement `{schema}`.
- `FEW_SHOT_EXAMPLES` : sept paires question → SQL, présentées au modèle comme de faux tours de conversation.
- `SQL_PROMPT` : système + exemples + question + emplacement `corrections` pour les essais ratés.
- `CORRECTION_TEMPLATE` : le message envoyé après une erreur.
- `CANNOT_ANSWER` : le mot que le modèle renvoie quand la question est hors périmètre.
- `ANSWER_PROMPT` : le prompt de rédaction de la réponse.

### `src/llm.py` : le modèle et le nettoyage de sa sortie

- `get_llm()` crée le client `ChatOllama`, à température 0 pour des réponses stables.
- `extract_sql(text)` isole la requête dans la réponse brute. C'est ce qu'on appelle le *parsing*.

### `src/chain.py` : la chaîne simple

- `Result` : la structure rendue à la fin (question, SQL, colonnes, lignes, réponse, erreur, essais).
- `build_sql_chain(llm)` : `SQL_PROMPT | llm | StrOutputParser() | extract_sql`. Le `|` enchaîne les étapes comme un pipe Unix.
- `build_answer_chain(llm)` : même principe pour la rédaction.
- `run_chain(question)` : la version sans boucle. Si le SQL est faux, elle échoue.

### `src/agent.py` : l'agent

- `AgentState` : la mémoire de travail pour une question.
- `build_graph(llm)` : quatre nœuds (`read_schema`, `generate_sql`, `execute_sql`, `answer`) et la fonction `next_step`, qui choisit la suite après l'exécution : rédiger, réessayer ou abandonner.
- `ask(question)` : lance le graphe et convertit l'état final en `Result`.

L'agent réutilise les deux maillons de `chain.py`. La seule chose qu'il ajoute est la boucle.

### `src/evaluation.py` et `eval/`

- `results_match(expected, actual)` compare deux résultats de façon tolérante.
- `eval/questions.json` : 15 questions avec leur requête de référence.
- `eval/run_eval.py` : pose chaque question à l'agent et calcule l'exactitude.

### `app.py` : l'interface

Streamlit réexécute le fichier entier à chaque clic. L'historique survit grâce à `st.session_state.history`. `show_result` dessine une réponse ; le bas du fichier gère la saisie.

### `tests/`

`conftest.py` crée pour chaque test une mini-base jetable et fournit `fake_llm`, un faux modèle qui récite des réponses écrites d'avance. Les tests tournent ainsi en une seconde, sans Ollama, y compris dans la CI.

## 4. Les concepts

### Chaîne ou agent

Une **chaîne** est une suite d'étapes fixe : A, puis B, puis C. Elle est simple et prévisible, mais elle ne rattrape pas ses erreurs. C'est `run_chain`.

Un **agent** contient une boucle et une décision : selon ce qu'il observe, il choisit l'étape suivante. Ici, la décision tient dans `next_step` : succès, nouvel essai ou abandon.

Le mot « agent » désigne souvent quelque chose de plus libre : un modèle à qui l'on donne des outils (« lister les tables », « exécuter une requête ») et qui choisit lui-même lesquels appeler et dans quel ordre. Ce projet fait un choix différent : **le code tient le volant**. Le modèle n'écrit que du SQL, et c'est le graphe qui décide de l'enchaînement. Un modèle de 7 milliards de paramètres est peu fiable pour appeler des outils, alors qu'il est bon pour écrire une requête quand on lui donne le schéma.

### Le prompt de schéma

Le modèle ne peut pas deviner les noms de tables. On les lui donne, sous une forme courte :

```text
Album(AlbumId INTEGER PK, Title TEXT, ArtistId INTEGER -> Artist.ArtistId)
```

Trois choix comptent :

- **Compact** : une ligne par table plutôt que les `CREATE TABLE` complets. Un prompt plus court est plus rapide et laisse moins de place à la confusion.
- **Clés étrangères visibles** (`->`) : c'est ce qui indique au modèle comment écrire les `JOIN`.
- **Lu automatiquement** : `get_schema` interroge la base, rien n'est écrit en dur.

Les **exemples few-shot** complètent le schéma. Ils montrent le style attendu (dialecte SQLite, alias, `LIMIT`) mieux que n'importe quelle règle. Pendant le développement, la question « quel genre génère le plus de revenus ? » produisait un `JOIN` faux entre deux tables sans lien ; ajouter un seul exemple de jointure sur trois tables a réglé le problème.

### Les garde-fous

Le principe est la **défense en profondeur** : plusieurs protections indépendantes, pour qu'une faille dans l'une soit rattrapée par une autre.

| Couche | Arrête | Faiblesse |
|---|---|---|
| Validation par mots-clés | Les écritures évidentes, avant exécution | Repose sur des expressions régulières, donc contournable en théorie |
| Connexion lecture seule | Toute écriture, quoi qu'il arrive | Ne protège pas contre une lecture trop lourde |
| `LIMIT` par défaut | Le rapatriement d'une table entière | Ne limite pas le temps de calcul |
| Timeout | Les requêtes trop longues | Coupe aussi une requête légitime mais lente |

Deux leçons tirées des tests de ce projet :

- Un refus des garde-fous **n'est pas réessayé**. Au début, il l'était : après le refus d'un `DROP TABLE`, le modèle « réussissait » au deuxième essai en inventant une requête sans rapport, et l'interface affichait une réponse hors sujet.
- Le modèle peut **renoncer** en répondant `CANNOT_ANSWER`. Mieux vaut un refus clair qu'une requête inventée.

### L'évaluation

Sans mesure, impossible de savoir si une modification du prompt améliore ou dégrade l'agent. Le script d'évaluation donne un chiffre à comparer avant et après chaque changement.

On mesure l'**exactitude d'exécution** : la requête de l'agent et la requête de référence sont exécutées, et l'on compare les données obtenues. Comparer le texte des requêtes n'aurait pas de sens, car deux SQL différents peuvent être tous deux corrects.

La comparaison ignore l'ordre des lignes et les noms de colonnes, arrondit les nombres, et accepte des colonnes en plus. Cette tolérance a un coût : elle peut, rarement, valider un résultat juste par coïncidence. C'est pourquoi les 15 requêtes générées ont été relues à la main.

Le score de 15/15 dit que l'agent fonctionne sur des questions de ce niveau, pas qu'il est infaillible. Trois règles à retenir :

- les exemples few-shot ne doivent pas reprendre les questions d'évaluation, sinon on mesure la mémoire du prompt ;
- quand on ajuste le prompt en regardant les échecs, le score devient optimiste ;
- un jeu que le modèle réussit à 100 % ne permet plus de mesurer un progrès : il faut alors ajouter des questions plus dures (voir l'exercice 4).

## 5. Les choix et leurs alternatives

| Choix fait | Alternative | Pourquoi ce choix |
|---|---|---|
| Graphe LangGraph écrit à la main | `create_agent` de LangChain avec des outils SQL (`SQLDatabaseToolkit`) | L'agent à outils laisse le modèle piloter ; avec un petit modèle local, il boucle ou se trompe d'outil. Le graphe explicite est plus fiable et plus facile à lire. |
| LangChain | LlamaIndex (`NLSQLTableQueryEngine`) | LlamaIndex fait du NL-to-SQL en trois lignes, mais cache le prompt et la boucle. Ici, le but est de voir chaque étape. LlamaIndex est plus fort pour interroger des documents. |
| LangChain | Aucun framework (bibliothèque `ollama` seule) | Tout à fait faisable : le projet n'utilise que les prompts, le `|` et le graphe. LangChain apporte le faux modèle pour les tests et la possibilité de changer de fournisseur sans réécrire. |
| Accès SQLite écrit à la main | `SQLDatabase` de `langchain-community` | Une cinquantaine de lignes suffisent, et l'on maîtrise la lecture seule, le timeout et le format du schéma. |
| Validation par expressions régulières | Parseur SQL (`sqlglot`) | Plus simple à lire. La garantie réelle vient de la connexion en lecture seule. |
| Ollama + `qwen2.5-coder:7b` | Modèle plus gros (`qwen3-coder:30b`) ou API payante | Contrainte du projet : local et gratuit. Les versions plus récentes de Qwen-Coder demandent au moins 19 Go de mémoire. |
| Schéma complet dans le prompt | Recherche des tables pertinentes (RAG) | Avec 11 tables, tout tient dans le prompt. |
| Exactitude d'exécution | Comparaison du texte SQL, ou jugement par un LLM | Objective, automatique, et tolérante aux formulations différentes. |
| Température 0 | Température plus haute et vote entre plusieurs réponses | Résultats reproductibles et un seul appel par essai. |

## 6. Cinq exercices

Classés du plus simple au plus ambitieux. Après chacun, lance `pytest` puis `python eval/run_eval.py` pour vérifier que rien n'est cassé.

### Exercice 1 : changer de modèle et comparer

Dans `.env`, mets `OLLAMA_MODEL=qwen2.5-coder:3b` (après `ollama pull qwen2.5-coder:3b`), puis relance l'évaluation. Quelles questions échouent ? Combien demandent plusieurs essais ? Ajoute une ligne au tableau des scores du README.

*Ce que tu apprends : l'effet de la taille du modèle, et l'utilité d'une évaluation chiffrée.*

### Exercice 2 : mesurer l'apport des exemples few-shot

Dans `src/prompts.py`, vide temporairement `FEW_SHOT_EXAMPLES` et relance l'évaluation. Remets ensuite les exemples un par un. Lequel compte le plus ?

*Ce que tu apprends : mesurer chaque élément du prompt au lieu de supposer.*

### Exercice 3 : ajouter un garde-fou

Interdis les requêtes qui lisent la table `Employee` (imagine qu'elle contient des données sensibles). Ajoute une liste `FORBIDDEN_TABLES` dans `src/safety.py`, vérifie-la dans `validate`, et écris les tests dans `tests/test_safety.py` : une requête bloquée, et une requête autorisée qui contient le mot `Employee` dans une chaîne de caractères.

Pour aller plus loin : retire aussi la table du schéma envoyé au modèle. Pourquoi faut-il faire les deux ?

*Ce que tu apprends : écrire un garde-fou et le tester.*

### Exercice 4 : durcir l'évaluation

Ajoute cinq questions de niveau `très difficile` dans `eval/questions.json` : sous-requête corrélée, fonction de fenêtrage (`RANK() OVER`), calcul de pourcentage, comparaison entre deux années, auto-jointure sur `Employee.ReportsTo`. Vérifie chaque requête de référence dans `sqlite3 data/chinook.sqlite` avant de l'ajouter. Pense à mettre à jour `test_question_file_is_well_formed`.

*Ce que tu apprends : écrire un jeu d'évaluation qui distingue encore les bons et les mauvais réglages.*

### Exercice 5 : ajouter une mémoire de conversation

Fais fonctionner « Quels sont les 3 artistes qui ont le plus d'albums ? » suivi de « Et les 5 suivants ? ». Piste : ajoute un champ `history` à `AgentState`, passe les derniers échanges (question et SQL) depuis `app.py`, et insère-les dans `SQL_PROMPT` avec un second `MessagesPlaceholder`, entre les exemples et la question.

*Ce que tu apprends : faire circuler un état de bout en bout, de l'interface au prompt.*
