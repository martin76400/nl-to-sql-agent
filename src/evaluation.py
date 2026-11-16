"""Comparaison d'un résultat obtenu avec le résultat attendu.

On mesure l'exactitude d'EXÉCUTION : on ne compare pas le texte des requêtes
(deux SQL différents peuvent être tous deux justes), mais les données qu'elles
renvoient. La comparaison est tolérante sur ce qui ne change pas le sens :

- l'ordre des lignes est ignoré ;
- les noms de colonnes sont ignorés ;
- l'agent peut renvoyer des colonnes EN PLUS (ex. le nombre d'albums à côté du
  nom de l'artiste) : il suffit que les colonnes attendues s'y retrouvent ;
- les nombres sont arrondis à 2 décimales, et '2009' vaut 2009.
"""

from itertools import permutations


def _normalize(value) -> str:
    """Ramène une valeur à une forme comparable."""
    if value is None:
        return "null"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value).strip().lower()


def results_match(expected: list[tuple], actual: list[tuple]) -> bool:
    """Vrai si `actual` contient les données de `expected`.

    On cherche un choix de colonnes de `actual` qui, pris dans un certain ordre,
    redonne exactement les lignes attendues (sans tenir compte de leur ordre).
    """
    if len(expected) != len(actual):
        return False
    if not expected:
        return True

    expected_rows = sorted(tuple(_normalize(v) for v in row) for row in expected)
    actual_rows = [tuple(_normalize(v) for v in row) for row in actual]
    n_expected, n_actual = len(expected_rows[0]), len(actual_rows[0])
    if n_actual < n_expected:
        return False

    # Essaie chaque façon de piocher n_expected colonnes parmi celles obtenues.
    # Les résultats ont peu de colonnes : la force brute suffit largement.
    for picked in permutations(range(n_actual), n_expected):
        projected = sorted(tuple(row[i] for i in picked) for row in actual_rows)
        if projected == expected_rows:
            return True
    return False
