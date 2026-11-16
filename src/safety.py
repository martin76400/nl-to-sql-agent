"""Garde-fous appliqués à toute requête AVANT son exécution.

Un LLM peut produire n'importe quoi : par erreur, ou parce que l'utilisateur le
lui demande (« supprime la table des clients »). On ne lui fait donc jamais
confiance. Ce module est une des couches de défense, les autres sont dans db.py :

1. validate()      : une seule instruction, en lecture, sans mot-clé interdit ;
2. ensure_limit()  : un LIMIT par défaut, pour ne jamais rapatrier une table entière ;
3. db.connect()    : connexion SQLite en lecture seule (même si 1 laisse passer
                     une écriture, SQLite la refuse) ;
4. db.run_query()  : timeout d'exécution.

L'analyse repose sur des expressions régulières, pas sur un vrai parseur SQL :
c'est simple à lire et suffisant ici, précisément parce que la couche 3 rattrape
ce qui passerait entre les mailles.
"""

import re

from src import config

# Mots-clés qui modifient les données, la structure ou la configuration.
FORBIDDEN_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "VACUUM",
    "REINDEX",
)


class UnsafeQueryError(ValueError):
    """Requête refusée par les garde-fous."""


# Commentaires (-- ... et /* ... */) et littéraux ('texte', "identifiant").
_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_LITERALS = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
_PARENTHESES = re.compile(r"\([^()]*\)")


def _skeleton(sql: str) -> str:
    """Renvoie la requête sans commentaires ni littéraux.

    Sans cette étape, une requête légitime comme
        SELECT * FROM Track WHERE Name = 'Drop the beat'
    serait refusée à cause du mot DROP, et à l'inverse un mot-clé pourrait se
    cacher derrière un commentaire.
    """
    sql = _COMMENTS.sub(" ", sql)
    return _LITERALS.sub("''", sql)


def validate(sql: str) -> None:
    """Lève UnsafeQueryError si la requête n'est pas une lecture simple."""
    skeleton = _skeleton(sql).strip().rstrip(";").strip()
    if not skeleton:
        raise UnsafeQueryError("Empty query.")
    if ";" in skeleton:
        raise UnsafeQueryError("Only one SQL statement is allowed.")
    if not re.match(r"(SELECT|WITH)\b", skeleton, re.IGNORECASE):
        raise UnsafeQueryError("Only SELECT queries are allowed.")
    for keyword in FORBIDDEN_KEYWORDS:
        # \b = frontière de mot : UPDATE est interdit, la colonne LastUpdate non.
        if re.search(rf"\b{keyword}\b", skeleton, re.IGNORECASE):
            raise UnsafeQueryError(f"Forbidden keyword: {keyword}. Read-only access.")


def ensure_limit(sql: str, limit: int | None = None) -> str:
    """Ajoute un LIMIT si la requête n'en a pas au niveau principal.

    Un LIMIT dans une sous-requête ne compte pas : on retire donc le contenu des
    parenthèses, de l'intérieur vers l'extérieur, avant de chercher le mot.
    """
    limit = limit or config.DEFAULT_LIMIT
    sql = sql.strip().rstrip(";").strip()
    top_level = _skeleton(sql)
    while _PARENTHESES.search(top_level):
        top_level = _PARENTHESES.sub(" ", top_level)
    if re.search(r"\bLIMIT\b", top_level, re.IGNORECASE):
        return sql
    # Retour à la ligne : si la requête finit par un commentaire --, le LIMIT
    # ne doit pas être avalé par ce commentaire.
    return f"{sql}\nLIMIT {limit}"


def make_safe(sql: str) -> str:
    """Valide la requête puis lui garantit un LIMIT. Point d'entrée du module."""
    validate(sql)
    return ensure_limit(sql)
