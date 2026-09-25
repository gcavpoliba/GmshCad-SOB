"""Esempio macro 5 — Scala ogni entità
=====================================

Bersaglio ``entita``: la funzione riceve l'entità INTERA (non le sotto-shape)
e viene eseguita una volta per ogni entità selezionata. Ogni entità viene
scalata attorno al proprio centro, così la geometria non si allontana.
Dimostra anche la gestione degli errori per-entità del motore macro.
"""

from gcs.core.macro_engine import macro, P
from gcs.core import occ_utils as ou


@macro(
    nome="Scala ogni entità",
    applies_to=("entita",),
    params=[
        P("fattore", "float", default=1.1, min=0.01, max=10.0,
          help="Fattore di scala (1.1 = +10%)"),
    ],
    category="Esempi",
)
def run(ctx, target, params):
    """Scala ogni entità selezionata attorno al proprio centro."""
    if target.shape is None or not hasattr(target.shape, "ShapeType"):
        raise ValueError("L'entità non ha geometria scalabile")
    centro = ou.center_of(target.shape)
    nuovo = ou.scale(target.shape, params["fattore"], centro)
    return nuovo
