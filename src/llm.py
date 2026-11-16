"""Le modèle de langage et le nettoyage de sa sortie."""

import re

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from src import config


def get_llm() -> BaseChatModel:
    """Construit le client du modèle Ollama local.

    temperature=0 : on veut la requête la plus probable, pas de la créativité.
    Les mêmes questions donnent ainsi (presque) toujours le même SQL.
    """
    return ChatOllama(
        model=config.OLLAMA_MODEL,
        base_url=config.OLLAMA_BASE_URL,
        temperature=0,
    )


_FENCE = re.compile(r"```(?:sql|sqlite)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_START = re.compile(r"\b(SELECT|WITH)\b", re.IGNORECASE)


def extract_sql(text: str) -> str:
    """Isole la requête SQL dans la réponse brute du modèle.

    Malgré la consigne « uniquement le SQL », un modèle ajoute parfois des
    balises markdown ou une phrase d'introduction. On gère trois cas :
    1. bloc ```sql ... ```  -> on garde l'intérieur du bloc ;
    2. texte avant la requête -> on démarre au premier SELECT ou WITH ;
    3. texte après la requête -> on coupe au premier point-virgule.

    La coupe au point-virgule est volontairement naïve (elle ignore le cas d'un
    « ; » dans une chaîne de caractères). C'est suffisant ici.
    """
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start = _START.search(text)
    if start:
        text = text[start.start() :]
    return text.split(";")[0].strip()
