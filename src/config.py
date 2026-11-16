"""Configuration centralisée du projet.

Toutes les valeurs réglables vivent ici, pour éviter les constantes éparpillées.
Celles qui dépendent de la machine (modèle, adresse d'Ollama) se lisent dans le
fichier .env ; les autres sont de simples constantes Python.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Racine du dépôt : ce fichier est dans src/, donc on remonte d'un cran.
ROOT_DIR = Path(__file__).resolve().parent.parent

# Charge .env s'il existe. Sans .env, les valeurs par défaut ci-dessous s'appliquent.
load_dotenv(ROOT_DIR / ".env")

# --- LLM (Ollama local) ---
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- Base de données ---
DB_PATH = Path(os.getenv("DB_PATH", ROOT_DIR / "data" / "chinook.sqlite"))

# --- Agent ---
# Nombre maximal de tentatives de génération SQL pour une question.
MAX_ATTEMPTS = 3

# --- Garde-fous ---
# LIMIT ajouté aux requêtes qui n'en ont pas.
DEFAULT_LIMIT = 200
# Durée maximale d'exécution d'une requête, en secondes.
QUERY_TIMEOUT_S = 5.0
