"""Esempio macro 3 — Perturba nodi
=================================

Macro sui **nodi della mesh** (bersaglio ``nodo_mesh``): sposta ogni nodo
della selezione corrente con un jitter casuale entro il raggio indicato.
Dimostra la modifica diretta del modello mesh dal motore macro.
"""

import math
import random

from gcs.core.macro_engine import macro, P


@macro(
    nome="Perturba nodi",
    applies_to=("nodo_mesh",),
    params=[
        P("raggio", "float", default=0.5, min=0.0, max=100.0,
          help="Ampiezza massima dello spostamento [mm]"),
        P("solo_z", "bool", default=False,
          help="Perturba solo la coordinata Z"),
        P("seed", "int", default=0,
          help="Seed del generatore casuale (0 = casuale)"),
    ],
    category="Esempi",
)
def run(ctx, target, params):
    """Sposta casualmente ogni nodo della selezione entro ``raggio``."""
    if params["seed"]:
        random.seed(params["seed"])
    x, y, z = target.model.nodes[target.node_id]
    dx, dy, dz = params["raggio"], params["raggio"], params["raggio"]
    if params["solo_z"]:
        dz *= random.uniform(-1.0, 1.0)
        target.model.nodes[target.node_id] = (x, y, z + dz)
    else:
        # direzione casuale uniforme sulla sfera
        theta = random.uniform(0, 2 * math.pi)
        phi = math.acos(random.uniform(-1, 1))
        r = params["raggio"] * random.random()
        target.model.nodes[target.node_id] = (
            x + r * math.sin(phi) * math.cos(theta),
            y + r * math.sin(phi) * math.sin(theta),
            z + r * math.cos(phi))
    ctx.log(f"{target.label}: spostato di {params['raggio']:.3g} max")
