"""Comparaison tolérante des résultats pour l'évaluation."""

import json
from pathlib import Path

from src.evaluation import results_match


def test_row_order_is_ignored():
    assert results_match([(1,), (2,)], [(2,), (1,)])


def test_extra_columns_are_accepted():
    assert results_match([("Queen",)], [(3, "Queen", "x")])


def test_numbers_are_rounded_and_numeric_strings_match():
    assert results_match([("2009", 5.651)], [(2009, 5.65)])


def test_different_values_or_row_counts_do_not_match():
    assert not results_match([(1,)], [(2,)])
    assert not results_match([(1,)], [(1,), (1,)])
    assert not results_match([(1, 2)], [(1,)])  # il manque une colonne


def test_question_file_is_well_formed():
    path = Path(__file__).resolve().parent.parent / "eval" / "questions.json"
    questions = json.loads(path.read_text(encoding="utf-8"))
    assert len(questions) == 15
    assert [q["id"] for q in questions] == list(range(1, 16))
    assert all(q["question"] and q["sql"].upper().startswith("SELECT") for q in questions)
