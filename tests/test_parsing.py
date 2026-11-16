"""Extraction du SQL dans la réponse brute du modèle."""

import pytest

from src.llm import extract_sql
from src.prompts import CANNOT_ANSWER, SQL_PROMPT


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("SELECT 1", "SELECT 1"),
        ("SELECT 1;", "SELECT 1"),
        ("```sql\nSELECT Name FROM Artist;\n```", "SELECT Name FROM Artist"),
        ("```\nSELECT 1\n```", "SELECT 1"),
        ("Voici la requête :\nSELECT 1", "SELECT 1"),
        ("SELECT 1; Cette requête renvoie 1.", "SELECT 1"),
        ("with a as (select 1) select * from a", "with a as (select 1) select * from a"),
        ("  \n SELECT 1 \n ", "SELECT 1"),
        ("CANNOT_ANSWER", CANNOT_ANSWER),
        ("I'm sorry. CANNOT_ANSWER.", CANNOT_ANSWER),
    ],
)
def test_extract_sql(raw, expected):
    assert extract_sql(raw) == expected


def test_prompt_contains_schema_examples_and_question():
    messages = SQL_PROMPT.invoke({"schema": "MON_SCHEMA", "question": "MA_QUESTION"})
    text = messages.to_string()
    assert "MON_SCHEMA" in text
    assert "strftime('%Y', InvoiceDate)" in text  # un exemple few-shot intact
    assert text.rstrip().endswith("MA_QUESTION")
