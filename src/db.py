"""Accès à la base SQLite : connexion, schéma compact, exécution de requêtes.

Ce module ne connaît rien du LLM. Il fournit deux services au reste du projet :
- get_schema() : une description courte de la base, à glisser dans le prompt ;
- run_query()  : exécuter du SQL et rendre colonnes + lignes.

run_query() est la SEULE porte d'entrée vers la base pour du SQL généré. Tous
les garde-fous y sont donc appliqués, et aucun appelant ne peut les oublier.
"""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from src import config, safety


# Erreurs « normales » d'une requête générée : refus des garde-fous, SQL
# invalide, dépassement du temps imparti.
QUERY_ERRORS = (safety.UnsafeQueryError, sqlite3.Error, TimeoutError)


@dataclass
class QueryResult:
    """Résultat d'une requête : noms de colonnes, lignes et SQL réellement exécuté."""

    columns: list[str]
    rows: list[tuple]
    sql: str = ""  # la requête après garde-fous (avec son LIMIT éventuel)


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Ouvre une connexion en LECTURE SEULE vers la base.

    mode=ro est appliqué par SQLite lui-même : toute écriture échoue avec
    « attempt to write a readonly database », quoi que contienne la requête.
    C'est le garde-fou le plus solide, car il ne dépend pas de notre analyse
    du SQL.
    """
    path = Path(db_path or config.DB_PATH).resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"Base introuvable : {path}. Lance `python scripts/download_chinook.py`."
        )
    # as_uri() encode les espaces et caractères spéciaux du chemin.
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)


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


def run_query(
    sql: str,
    db_path: Path | str | None = None,
    timeout_s: float | None = None,
) -> QueryResult:
    """Exécute une requête avec tous les garde-fous et renvoie colonnes + lignes.

    Erreurs possibles :
    - safety.UnsafeQueryError : requête refusée avant exécution ;
    - sqlite3.Error           : SQL invalide (table ou colonne inconnue, etc.) ;
    - TimeoutError            : requête trop longue.
    """
    sql = safety.make_safe(sql)
    timeout_s = timeout_s or config.QUERY_TIMEOUT_S
    deadline = time.monotonic() + timeout_s

    conn = connect(db_path)
    # SQLite appelle ce handler toutes les 10 000 instructions de sa machine
    # virtuelle. S'il renvoie True, la requête en cours est interrompue : c'est
    # ce qui arrête une requête trop coûteuse (ex. produit cartésien géant).
    conn.set_progress_handler(lambda: time.monotonic() > deadline, 10_000)
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        return QueryResult(columns=columns, rows=cursor.fetchall(), sql=sql)
    except sqlite3.OperationalError as exc:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Query interrupted: it ran for more than {timeout_s:g} seconds."
            ) from exc
        raise
    finally:
        conn.close()
