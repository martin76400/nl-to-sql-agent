"""Interface Streamlit de l'agent NL-to-SQL.

Lancement : streamlit run app.py

Streamlit réexécute ce fichier de haut en bas à chaque interaction. Tout ce qui
doit survivre d'une exécution à l'autre (ici l'historique) vit donc dans
st.session_state.
"""

import pandas as pd
import streamlit as st

from src import agent, config, db
from src.chain import Result

EXAMPLES = [
    "Quels sont les 5 artistes qui ont le plus d'albums ?",
    "Quel genre génère le plus de revenus ?",
    "Combien de clients y a-t-il par pays ?",
]

st.set_page_config(page_title="Agent NL-to-SQL", page_icon="🗃️", layout="centered")


def show_result(result: Result) -> None:
    """Affiche une réponse : texte, SQL, tableau, puis détail des essais ratés."""
    if result.error:
        st.error(f"Je n'ai pas réussi à répondre : {result.error}")
    else:
        st.markdown(result.answer)

    if result.sql:
        st.caption(f"SQL généré ({result.attempts} essai(s))")
        st.code(result.sql, language="sql")

    if result.rows:
        st.dataframe(
            pd.DataFrame(result.rows, columns=result.columns),
            hide_index=True,
            width="stretch",
        )
        if len(result.rows) == config.DEFAULT_LIMIT:
            st.caption(
                f"Résultat limité à {config.DEFAULT_LIMIT} lignes par sécurité."
            )

    if result.failures:
        with st.expander(f"Essais ratés ({len(result.failures)})"):
            for failure in result.failures:
                st.code(failure["sql"], language="sql")
                st.caption(f"Erreur : {failure['error']}")


# --- Barre latérale : contexte et exemples ---
with st.sidebar:
    st.header("Agent NL-to-SQL")
    st.caption(f"Modèle : `{config.OLLAMA_MODEL}` (Ollama, local)")
    st.caption(f"Base : `{config.DB_PATH.name}` (lecture seule)")

    st.subheader("Exemples")
    for example in EXAMPLES:
        if st.button(example, width="stretch"):
            st.session_state.pending_question = example

    with st.expander("Schéma de la base"):
        try:
            st.code(db.get_schema(), language="text")
        except FileNotFoundError as exc:
            st.warning(str(exc))

    if st.button("Effacer l'historique"):
        st.session_state.history = []

# --- Zone principale : historique puis nouvelle question ---
st.title("Pose une question à la base Chinook")

if "history" not in st.session_state:
    st.session_state.history = []  # liste de Result, du plus ancien au plus récent

for past in st.session_state.history:
    with st.chat_message("user"):
        st.markdown(past.question)
    with st.chat_message("assistant"):
        show_result(past)

# La question vient du champ de saisie ou d'un bouton d'exemple.
question = st.chat_input("Ex. : Quels sont les 3 pays avec le plus de clients ?")
question = question or st.session_state.pop("pending_question", None)

if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Génération et exécution de la requête..."):
            try:
                result = agent.ask(question)
            except Exception as exc:  # Ollama arrêté, base absente, etc.
                result = Result(
                    question=question,
                    error=f"{exc} — Vérifie qu'Ollama tourne et que la base "
                    "est téléchargée.",
                    attempts=0,
                )
        show_result(result)
    st.session_state.history.append(result)
