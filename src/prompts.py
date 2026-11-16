"""Prompts envoyés au modèle.

Les prompts sont rédigés en anglais : les petits modèles de code suivent mieux
des consignes en anglais. La question, elle, peut être posée en français, et la
réponse finale est rédigée dans la langue de la question.

Trois leviers compensent les faiblesses d'un petit modèle local :
1. un schéma compact (voir db.get_schema) injecté dans le prompt système ;
2. des exemples few-shot question -> SQL, qui montrent le style attendu ;
3. un prompt de correction qui renvoie au modèle sa requête et l'erreur obtenue.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

SQL_SYSTEM = """You are an expert SQLite analyst. Given a database schema and a \
question, write ONE SQLite query that answers the question.

Rules:
- Output ONLY the SQL query: no explanation, no markdown, no comment.
- Write a single read-only SELECT statement (WITH ... SELECT is allowed).
- Use only the tables and columns listed in the schema. Never invent a column.
- Join two tables ONLY through a foreign key (->) listed in the schema. If two tables are not directly linked, go through the tables in between.
- Select only the columns needed to answer the question.
- SQLite dialect: use LIMIT (not TOP), || to concatenate, \
strftime('%Y', column) to extract a year.
- For "top", "most" or "best" questions, use ORDER BY ... DESC with LIMIT.
- If the question asks to modify data (delete, update, insert, drop...) or cannot \
be answered from this schema, output exactly CANNOT_ANSWER instead of a query.
- Text values are in English (e.g. Country = 'France', 'USA', 'Germany').
- Track.Milliseconds is a duration in milliseconds. Invoice.Total is an amount in dollars.

Schema (one table per line, PK = primary key, -> = foreign key):
{schema}"""

# Mot que le modèle renvoie à la place d'une requête quand la question est hors
# périmètre (demande d'écriture, sujet absent de la base). Voir agent.execute_sql.
CANNOT_ANSWER = "CANNOT_ANSWER"

# Exemples few-shot : ils couvrent les constructions les plus fréquentes
# (agrégat, filtre, JOIN, GROUP BY, date). Ils ne doivent PAS reprendre les
# questions du jeu d'évaluation, sinon le score serait artificiellement gonflé.
FEW_SHOT_EXAMPLES = [
    (
        "Combien y a-t-il d'employés ?",
        "SELECT COUNT(*) AS NbEmployes FROM Employee",
    ),
    (
        "Quels sont les clients qui habitent au Canada ?",
        "SELECT FirstName, LastName FROM Customer WHERE Country = 'Canada'",
    ),
    (
        "List the albums of the artist Queen.",
        "SELECT Album.Title FROM Album "
        "JOIN Artist ON Album.ArtistId = Artist.ArtistId "
        "WHERE Artist.Name = 'Queen'",
    ),
    (
        "Quels sont les 3 genres qui ont le plus de pistes ?",
        "SELECT Genre.Name, COUNT(*) AS NbPistes FROM Track "
        "JOIN Genre ON Track.GenreId = Genre.GenreId "
        "GROUP BY Genre.GenreId ORDER BY NbPistes DESC LIMIT 3",
    ),
    (
        "Quel est le montant total des ventes en 2011 ?",
        "SELECT SUM(Total) AS TotalVentes FROM Invoice "
        "WHERE strftime('%Y', InvoiceDate) = '2011'",
    ),
    (
        # Montre au modèle quand renoncer plutôt qu'inventer une requête.
        "Supprime toutes les factures de 2009.",
        CANNOT_ANSWER,
    ),
    (
        # Jointure en plusieurs sauts : sans cet exemple, le modèle relie
        # volontiers deux tables qui n'ont aucune clé en commun.
        "Which album has sold the most tracks?",
        "SELECT Album.Title, SUM(InvoiceLine.Quantity) AS TracksSold FROM InvoiceLine "
        "JOIN Track ON InvoiceLine.TrackId = Track.TrackId "
        "JOIN Album ON Track.AlbumId = Album.AlbumId "
        "GROUP BY Album.AlbumId ORDER BY TracksSold DESC LIMIT 1",
    ),
]


def _few_shot_messages() -> list[tuple[str, str]]:
    """Transforme les exemples en faux tours de conversation human/ai."""
    messages = []
    for question, sql in FEW_SHOT_EXAMPLES:
        messages.append(("human", question))
        # Les accolades sont doublées pour ne pas être lues comme des variables.
        messages.append(("ai", sql.replace("{", "{{").replace("}", "}}")))
    return messages


# Prompt de génération : système (règles + schéma), exemples, la question, puis
# les éventuels essais ratés. "corrections" est vide au premier essai ; l'agent
# y place ensuite chaque requête fautive suivie de son message d'erreur.
SQL_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SQL_SYSTEM),
        *_few_shot_messages(),
        ("human", "{question}"),
        MessagesPlaceholder("corrections", optional=True),
    ]
)

# Message renvoyé au modèle après un échec (voir agent.generate_sql).
CORRECTION_TEMPLATE = (
    "That query failed with this error:\n{error}\n\n"
    "Check the table and column names against the schema, then fix the query. "
    "Output ONLY the corrected SQL."
)

# Prompt de rédaction : transforme le résultat brut en phrase.
ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You turn the result of a SQL query into a short answer for a "
            "non-technical user.\n"
            "- Answer in the same language as the question.\n"
            "- Use only the data in the result. Never invent a value.\n"
            "- Be concise: one or two sentences.\n"
            "- If the result has several rows, list them one per line; do not "
            "describe a trend or compute anything yourself.\n"
            "- If the result is empty, say that no data matches.\n"
            "- Do not mention SQL or the database.",
        ),
        (
            "human",
            "Question: {question}\n\nSQL query:\n{sql}\n\nResult:\n{result}",
        ),
    ]
)
