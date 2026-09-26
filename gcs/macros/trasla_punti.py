"""Esempio macro 1 — Trasla punti
================================

Applica una traslazione personalizzata a OGNI punto della selezione.
La geometria del punto (vertice) viene sostituita (replace=True di default).
"""

from gcs.core.macro_engine import macro, P
from gcs.core import occ_utils as ou


@macro(
    nome="Trasla punti",
    applies_to=("punto",),
    params=[
        P("dx", "float", default=0.0, help="Spostamento lungo X [mm]"),
        P("dy", "float", default=0.0, help="Spostamento lungo Y [mm]"),
        P("dz", "float", default=0.0, help="Spostamento lungo Z [mm]"),
    ],
    category="Esempi",
)
def run(ctx, target, params):
    """Trasla ogni punto selezionato del vettore (dx, dy, dz)."""
    v = ou.vertex_point(target.shape)
    nuovo = ou.make_vertex((v[0] + params["dx"], v[1] + params["dy"],
                            v[2] + params["dz"]))
    return nuovo
