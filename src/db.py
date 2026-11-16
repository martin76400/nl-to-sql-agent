"""Accès à la base SQLite : connexion, schéma compact, exécution de requêtes.

Ce module ne connaît rien du LLM. Il fournit deux services au reste du projet :
- get_schema() : une description courte de la base, à glisser dans le prompt ;
- run_query()  : exécuter du SQL et rendre colonnes + lignes.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src import config


@dataclass
class QueryResult:
    """Résultat d'une requête : noms de colonnes et lignes."""

    columns: list[str]
    rows: list[tuple]


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Ouvre une connexion vers la base."""
    path = Path(db_path or config.DB_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Base introuvable : {path}. Lance `python scripts/download_chinook.py`."
        )
    return sqlite3.connect(path)


def _short_type(declared: str) -> str:
    """Réduit un type SQL déclaré (ex. NVARCHAR(160)) à une famille courte.

    Le modèle n'a pas besoin de la longueur exacte d'un champ texte : moins de
    bruit dans le prompt = moins d'erreurs et un prompt plus court.
    """
    declared = declared.upper()
    if "INT" in declared:
        return "INTEGER"
    if "CHAR" in declared or "TEXT" in declared:
        return "TEXT"
    if "DATE" in declared or "TIME" in declared:
        return "DATETIME"
    return "NUMERIC"


def get_schema(db_path: Path | str | None = None) -> str:
    """Décrit la base en une ligne par table, par introspection.

    Exemple de ligne produite :
        Album(AlbumId INTEGER PK, Title TEXT, ArtistId INTEGER -> Artist.ArtistId)

    Les clés étrangères (->) sont l'information la plus utile pour le modèle :
    elles lui indiquent comment écrire les JOIN.
    """
    conn = connect(db_path)
    try:
        tables = [
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        lines = []
        for table in tables:
            # PRAGMA foreign_key_list : (id, seq, table_cible, col_source, col_cible, ...)
            foreign_keys = {
                fk[3]: f"{fk[2]}.{fk[4]}"
                for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")')
            }
            columns = []
            # PRAGMA table_info : (cid, nom, type, notnull, défaut, rang_dans_la_pk)
            for _, name, declared, _, _, pk in conn.execute(
                f'PRAGMA table_info("{table}")'
            ):
                text = f"{name} {_short_type(declared)}"
                if pk:
                    text += " PK"
                if name in foreign_keys:
                    text += f" -> {foreign_keys[name]}"
                columns.append(text)
            lines.append(f"{table}({', '.join(columns)})")
        return "\n".join(lines)
    finally:
        conn.close()


def run_query(sql: str, db_path: Path | str | None = None) -> QueryResult:
    """Exécute une requête et renvoie colonnes + lignes.

    Lève sqlite3.Error si le SQL est invalide : l'appelant décide quoi en faire
    (l'agent, lui, renvoie le message d'erreur au modèle).
    """
    conn = connect(db_path)
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        return QueryResult(columns=columns, rows=cursor.fetchall())
    finally:
        conn.close()
