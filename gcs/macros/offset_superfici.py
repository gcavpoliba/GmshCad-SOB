"""Esempio macro 2 — Offset ogni superficie
==========================================

Con ``create_new=True`` il risultato di ogni singola superficie (un guscio
offset) NON sostituisce l'originale ma viene registrato come nuova entità
nel gruppo "Risultati — Offset ogni superficie".
"""

from gcs.core.macro_engine import macro, P
from gcs.core import occ_utils as ou


@macro(
    nome="Offset ogni superficie",
    applies_to=("superficie",),
    params=[
        P("offset", "float", default=1.0, min=-50.0, max=50.0,
          help="Spostamento lungo la normale [+fuori / -dentro, mm]"),
    ],
    category="Esempi",
    create_new=True,
)
def run(ctx, target, params):
    """Crea una copia offset di ogni superficie selezionata."""
    shape = ou.offset_shape(target.shape, params["offset"])
    return shape
