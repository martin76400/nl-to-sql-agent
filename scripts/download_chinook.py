"""Télécharge la base de démonstration Chinook dans data/chinook.sqlite.

Usage : python scripts/download_chinook.py

Chinook modélise un magasin de musique en ligne (artistes, albums, pistes,
clients, factures). Le fichier n'est pas commité : ce script le récupère depuis
la release officielle du projet lerocha/chinook-database.
"""

import sqlite3
import sys
import urllib.request
from pathlib import Path

URL = (
    "https://github.com/lerocha/chinook-database/releases/download/"
    "v1.4.5/Chinook_Sqlite.sqlite"
)
DEST = Path(__file__).resolve().parent.parent / "data" / "chinook.sqlite"
EXPECTED_TABLES = 11


def count_tables(path: Path) -> int:
    """Compte les tables : sert à vérifier que le fichier est une base valide."""
    with sqlite3.connect(path) as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()
    return count


def main() -> int:
    if DEST.exists():
        print(f"Déjà présent : {DEST}")
        return 0

    DEST.parent.mkdir(parents=True, exist_ok=True)
    print(f"Téléchargement de {URL}")
    urllib.request.urlretrieve(URL, DEST)

    tables = count_tables(DEST)
    if tables != EXPECTED_TABLES:
        DEST.unlink()
        print(f"Fichier invalide : {tables} tables au lieu de {EXPECTED_TABLES}.")
        return 1

    print(f"OK : {DEST} ({DEST.stat().st_size // 1024} Ko, {tables} tables)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
