"""Esempio macro 4 — Marca per area
==================================

Applica una funzione personalizzata con effetti collaterali: classifica
ogni superficie selezionata in base all'area e le raggruppa/colore.
Dimostra l'uso di ``ctx.doc`` (documento) e dei gruppi dal dentro una macro.
"""

from gcs.core.macro_engine import macro, P
from gcs.core import occ_utils as ou


@macro(
    nome="Marca per area",
    applies_to=("superficie",),
    params=[
        P("soglia", "float", default=50.0, min=0.0,
          help="Superficie con area >= soglia -> 'grande', altrimenti 'piccola'"),
        P("colora", "bool", default=True,
          help="Assegna un colore distintivo alle due classi"),
    ],
    category="Esempi",
)
def run(ctx, target, params):
    """Classifica ogni superficie: 'grande' se area >= soglia, 'piccola' altrimenti."""
    area = ou.area_of(target.shape)
    classe = "grande" if area >= params["soglia"] else "piccola"
    target.entity.meta["marca"] = classe
    target.entity.meta["area"] = round(area, 4)
    if params["colora"]:
        target.entity.color = (0.9, 0.3, 0.3) if classe == "grande" else (0.3, 0.7, 0.4)
    g = ctx.doc.groups.get_or_create(f"superfici_{classe}")
    g.member_ids.add(target.entity.id)
    ctx.log(f"{target.label}: area={area:.2f} -> {classe}")
