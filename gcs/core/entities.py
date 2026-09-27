"""Entità del documento CAD.

Un'entità rappresenta un oggetto geometrico (punto, curva, superficie, solido,
composto) oppure un blocco di mesh importato da Gmsh. Il modulo è volutamente
indipendente da OpenCASCADE: l'eventuale shape TopoDS viene solo *custodito*,
così la logica di documento/gruppi/macro resta testabile anche senza OCC.
"""

from __future__ import annotations

import itertools
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Tipi di entità (valori canonici inglesi; alias italiano risolti da normalize_type)
# ---------------------------------------------------------------------------

POINT = "point"
CURVE = "curve"
FACE = "face"
SOLID = "solid"
COMPOUND = "compound"
MESH = "mesh"

TIPI_ENTITA = (POINT, CURVE, FACE, SOLID, COMPOUND, MESH)

#: etichette italiane per la UI
NOME_TIPO_IT = {
    POINT: "Punto",
    CURVE: "Curva",
    FACE: "Superficie",
    SOLID: "Solido",
    COMPOUND: "Composto",
    MESH: "Mesh",
}

#: dimensione topologica del tipo (2 = superficie, 3 = volume, ...)
DIM_TIPO = {POINT: 0, CURVE: 1, FACE: 2, SOLID: 3, COMPOUND: None, MESH: None}

#: alias ammessi nelle funzioni pubbliche (macro, console, menu)
_ALIASES = {
    "punto": POINT, "point": POINT, "vertex": POINT, "vertice": POINT, "p": POINT,
    "curva": CURVE, "curve": CURVE, "linea": CURVE, "linee": CURVE, "edge": CURVE,
    "spigolo": CURVE, "spigoli": CURVE, "edge": CURVE, "c": CURVE,
    "superficie": FACE, "superfici": FACE, "surface": FACE, "faces": FACE,
    "face": FACE, "faccia": FACE, "facce": FACE, "s": FACE,
    "solido": SOLID, "solidi": SOLID, "solid": SOLID, "volume": SOLID,
    "volumi": SOLID, "v": SOLID,
    "composto": COMPOUND, "compounds": COMPOUND, "compound": COMPOUND,
    "mesh": MESH,
}


def normalize_type(tipo: str) -> str:
    """Normalizza il nome di un tipo, accettando sinonimi italiane/inglesi."""
    t = (tipo or "").strip().lower()
    if t in _ALIASES:
        return _ALIASES[t]
    if t in TIPI_ENTITA:
        return t
    raise ValueError(
        f"Tipo entità '{tipo}' non riconosciuto. Valori ammessi: "
        f"{', '.join(TIPI_ENTITA)} (o alias: punto, curva, superficie, solido, ...)"
    )


_id_counter = itertools.count(1)


class Entity:
    """Entità del documento: un oggetto geometrico (o blocco mesh) con attributi.

    Attributi principali
    --------------------
    id        : identificatore univoco nel documento
    etype     : tipo canonico (POINT/CURVE/FACE/SOLID/COMPOUND/MESH)
    shape     : TopoDS_Shape OpenCASCADE (opzionale; None per blocchi mesh
                il cui display viene costruito al volo dal viewer)
    name      : nome mostrato nell'albero entità
    color     : colore (r, g, b) in [0, 1] oppure None (colore di default del tipo)
    visible   : visibilità nel viewer
    marker    : tag fisico Gmsh associato (per blocchi mesh / gruppi fisici)
    meta      : dizionario libero (punti di controllo, parentela, dati mesh...)
    """

    def __init__(self, etype: str, shape=None, name: Optional[str] = None,
                 marker: int = 0):
        self.id: int = next(_id_counter)
        self.etype: str = etype
        self.shape = shape
        self.name: str = name or f"{NOME_TIPO_IT.get(etype, etype)} {self.id}"
        self.color: Optional[Tuple[float, float, float]] = None
        self.visible: bool = True
        self.marker: int = marker
        self.meta: dict = {}

    # ------------------------------------------------------------------ util
    @property
    def dim(self) -> Optional[int]:
        return DIM_TIPO.get(self.etype)

    @property
    def is_mesh_block(self) -> bool:
        """True se l'entità è un blocco di mesh importato (display on-the-fly)."""
        return "mesh_ref" in self.meta

    def mesh_ref(self):
        """Restituisce (nome_modello, dim, tag) per i blocchi mesh, altrimenti None."""
        return self.meta.get("mesh_ref")

    def __repr__(self):  # pragma: no cover - diagnostica
        return f"Entity(id={self.id}, tipo={self.etype}, nome='{self.name}')"
