"""Motore di selezione entità.

Include tutte le funzioni di selezione classiche dei pre/post-processor mesh:
per tipo, per nome, per gruppo, per regione (box/sfera/piano), per proprietà
dimensionali, per direzione della normale, per adiacenza topologica
(espandi/riduci/connessi), per bordo, per sotto-entità, ecc.

Due stili d'uso:

1. funzioni libere ``select_*`` che modificano ``doc.selection``::

       select_by_type(doc, "superficie")
       select_box(doc, 0, 0, 0, 10, 10, 10)

2. **query fluenti** componibili::

       doc.query().type("face").planar().in_box(...).select()

Modalità di applicazione: ``replace`` (sostituisce), ``add`` (aggiunge),
``toggle`` (inverte membership), ``remove`` (toglie dalla selezione).
"""

from __future__ import annotations

import fnmatch
import re
import math
from typing import Iterable, List, Optional, Set, Tuple

from .entities import Entity, normalize_type, NOME_TIPO_IT
from .mesh import corner_nodes


# ---------------------------------------------------------------------------
# helper interni
# ---------------------------------------------------------------------------

def _entities_of_types(doc, types: Optional[Iterable[str]]) -> List[Entity]:
    if types is None:
        return list(doc.entities.values())
    norm = {normalize_type(t) for t in types}
    return [e for e in doc.entities.values() if e.etype in norm]


def _entity_measure(ent: Entity) -> Optional[float]:
    """Misura caratteristica: area (superfici), lunghezza (curve), volume (solidi)."""
    from . import occ_utils as ou
    if ent.shape is None:
        return None
    try:
        if ent.etype == "face":
            return ou.area_of(ent.shape)
        if ent.etype == "curve":
            return ou.length_of(ent.shape)
        if ent.etype == "solid":
            return ou.volume_of(ent.shape)
        return None
    except Exception:
        return None


def _entity_center(ent: Entity):
    from . import occ_utils as ou
    if ent.shape is None:
        ref = ent.meta.get("mesh_ref")
        if ref:
            model = doc_model(doc, ref[0])
            if model:
                bb = model.elements_bbox(model.blocks[(ref[1], ref[2])].element_ids)
                if bb:
                    return ((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2)
        return None
    return ou.center_of(ent.shape)


def doc_model(doc, name):
    return doc.mesh_models.get(name)


# ---------------------------------------------------------------------------
# applicazione della selezione
# ---------------------------------------------------------------------------

def apply_selection(doc, new_ids: Iterable[int], mode: str = "replace") -> Set[int]:
    """Applica la selezione al documento secondo la modalità richiesta."""
    new_ids = set(int(i) for i in new_ids)
    if mode == "replace":
        doc.selection = new_ids
    elif mode == "add":
        doc.selection = set(doc.selection) | new_ids
    elif mode == "remove":
        doc.selection = set(doc.selection) - new_ids
    elif mode == "toggle":
        doc.selection = set(doc.selection) ^ new_ids
    else:
        raise ValueError(f"Modalità selezione '{mode}' non valida "
                         "(replace/add/remove/toggle)")
    doc.notify("selection_changed", {"ids": list(doc.selection)})
    return doc.selection


def _commit(doc, ents: Iterable[Entity], mode="replace") -> Set[int]:
    return apply_selection(doc, [e.id for e in ents], mode)


# ---------------------------------------------------------------------------
# selettori fondamentali
# ---------------------------------------------------------------------------

def select_all(doc, types: Optional[Iterable[str]] = None, mode="replace") -> Set[int]:
    """Seleziona tutte le entità (eventualmente solo di certi tipi)."""
    return _commit(doc, _entities_of_types(doc, types), mode)


def select_none(doc) -> Set[int]:
    """Deseleziona tutto."""
    return apply_selection(doc, [], "replace")


def invert_selection(doc, types=None) -> Set[int]:
    """Inverte la selezione corrente."""
    return apply_selection(doc, set(doc.entities) - set(doc.selection), "replace")


def select_visible(doc, mode="replace") -> Set[int]:
    return _commit(doc, [e for e in doc.entities.values() if e.visible], mode)


def select_by_type(doc, ttype: str, mode="replace") -> Set[int]:
    """Seleziona per tipo: punto / curva / superficie / solido / composto."""
    t = normalize_type(ttype)
    return _commit(doc, [e for e in doc.entities.values() if e.etype == t], mode)


def select_by_name(doc, pattern: str, regex=False, mode="replace") -> Set[int]:
    """Seleziona per nome (wildcard ``*`` oppure espressione regolare)."""
    if regex:
        rx = re.compile(pattern, re.IGNORECASE)
        match = lambda e: bool(rx.search(e.name))
    else:
        match = lambda e: fnmatch.fnmatch(e.name.lower(), pattern.lower())
    return _commit(doc, [e for e in doc.entities.values() if match(e)], mode)


def select_by_group(doc, group_name: str, mode="replace") -> Set[int]:
    """Seleziona le entità membro di un gruppo."""
    g = doc.groups.get(group_name)
    if g is None:
        raise ValueError(f"Gruppo '{group_name}' inesistente")
    return apply_selection(doc, g.member_ids, mode)


def select_by_marker(doc, marker: int, mode="replace") -> Set[int]:
    """Seleziona entità con un dato tag fisico Gmsh."""
    return _commit(doc, [e for e in doc.entities.values() if e.marker == marker], mode)


def select_by_color(doc, rgb, tol=0.02, mode="replace") -> Set[int]:
    """Seleziona entità del colore indicato (r,g,b in 0..1)."""
    out = []
    for e in doc.entities.values():
        if e.color is None:
            continue
        if all(abs(e.color[i] - rgb[i]) <= tol for i in range(3)):
            out.append(e)
    return _commit(doc, out, mode)


# ---------------------------------------------------------------------------
# selettori geometrici (regione)
# ---------------------------------------------------------------------------

def select_box(doc, xmin, ymin, zmin, xmax, ymax, zmax,
               inside=True, mode="replace") -> Set[int]:
    """Selezione in parallelepipedo: ``inside=True`` richiede l'entità
    interamente contenuta, altrimenti basta l'intersezione del bbox."""
    from . import occ_utils as ou
    out = []
    for e in doc.entities.values():
        if e.shape is None:
            c = _entity_center(e)
            if c and xmin <= c[0] <= xmax and ymin <= c[1] <= ymax and zmin <= c[2] <= zmax:
                out.append(e)
            continue
        bx = ou.bbox_of(e.shape)
        if bx is None:
            continue
        if inside:
            ok = (bx[0] >= xmin - 1e-9 and bx[1] >= ymin - 1e-9 and bx[2] >= zmin - 1e-9 and
                  bx[3] <= xmax + 1e-9 and bx[4] <= ymax + 1e-9 and bx[5] <= zmax + 1e-9)
        else:
            ok = not (bx[3] < xmin or bx[0] > xmax or bx[4] < ymin or
                      bx[1] > ymax or bx[5] < zmin or bx[2] > zmax)
        if ok:
            out.append(e)
    return _commit(doc, out, mode)


def select_sphere(doc, cx, cy, cz, r, mode="replace") -> Set[int]:
    """Selezione sferica: entità il cui centro cade nella sfera di raggio ``r``."""
    out = []
    r2 = float(r) ** 2
    for e in doc.entities.values():
        c = _entity_center(e)
        if c is None:
            continue
        if (c[0] - cx) ** 2 + (c[1] - cy) ** 2 + (c[2] - cz) ** 2 <= r2:
            out.append(e)
    return _commit(doc, out, mode)


def select_plane(doc, px, py, pz, nx, ny, nz, side="+", mode="replace") -> Set[int]:
    """Selezione semi-spazio: entità dal lato indicato di un piano.

    ``side``: ``'+'`` sopra la normale, ``'-'`` sotto, ``'both'`` entro ±tol.
    """
    out = []
    n = (float(nx), float(ny), float(nz))
    for e in doc.entities.values():
        c = _entity_center(e)
        if c is None:
            continue
        d = ((c[0] - px) * n[0] + (c[1] - py) * n[1] + (c[2] - pz) * n[2])
        if (side == "+" and d > 0) or (side == "-" and d < 0):
            out.append(e)
    return _commit(doc, out, mode)


def select_nearest(doc, x, y, z, n=1, ttype=None) -> Set[int]:
    """Le ``n`` entità più vicine al punto dato (distanza dal centro)."""
    cand = _entities_of_types(doc, [ttype] if ttype else None)
    scored = []
    for e in cand:
        c = _entity_center(e)
        if c is not None:
            scored.append((math.dist(c, (x, y, z)), e))
    scored.sort(key=lambda t: t[0])
    return _commit(doc, [e for _, e in scored[:max(1, int(n))]])


# ---------------------------------------------------------------------------
# selettori per proprietà geometriche
# ---------------------------------------------------------------------------

def select_by_size(doc, ttype: str, vmin: float, vmax: float, mode="replace") -> Set[int]:
    """Per misura caratteristica: area (superfici), lunghezza (curve), volume (solidi)."""
    t = normalize_type(ttype)
    out = []
    for e in _entities_of_types(doc, [t]):
        m = _entity_measure(e)
        if m is not None and vmin <= m <= vmax:
            out.append(e)
    return _commit(doc, out, mode)


def select_planar(doc, mode="replace") -> Set[int]:
    """Superfici piane."""
    from . import occ_utils as ou
    out = []
    for e in _entities_of_types(doc, ["face"]):
        try:
            if e.shape is not None and ou.surface_is_planar(e.shape):
                out.append(e)
        except Exception:
            pass
    return _commit(doc, out, mode)


def select_curved(doc, mode="replace") -> Set[int]:
    """Superfici non piane (cilindriche, sferiche, spline...)."""
    planari = set(select_planar(doc, mode="replace"))
    return _commit(doc, [e for e in _entities_of_types(doc, ["face"]) if e not in planari], mode)


def _mesh_block_normal(doc, ref):
    """Normale di un blocco mesh (dalla prima faccia triangolare)."""
    model = doc_model(doc, ref[0])
    if model is None:
        return None
    blk = model.blocks.get((ref[1], ref[2]))
    if blk is None:
        return None
    for eid in blk.element_ids:
        etype, nodes = model.elements.get(eid, (None, []))
        cn = corner_nodes(etype, nodes)
        if len(cn) >= 3 and all(n in model.nodes for n in cn[:3]):
            p1, p2, p3 = (model.nodes[n] for n in cn[:3])
            u = [p2[i] - p1[i] for i in range(3)]
            v = [p3[i] - p1[i] for i in range(3)]
            nrm = (u[1] * v[2] - u[2] * v[1],
                   u[2] * v[0] - u[0] * v[2],
                   u[0] * v[1] - u[1] * v[0])
            mod = math.sqrt(sum(c * c for c in nrm))
            if mod > 1e-15:
                return tuple(c / mod for c in nrm)
    return None


def select_by_normal(doc, dx, dy, dz, tol_deg=15.0, mode="replace") -> Set[int]:
    """Superfici la cui normale è allineata alla direzione data entro tol gradi.

    Funziona sia con superfici B-Rep sia con blocchi mesh (normale stimata
    dalla prima faccia triangolare del blocco).
    """
    from . import occ_utils as ou
    d = (float(dx), float(dy), float(dz))
    mod = math.sqrt(sum(c * c for c in d)) or 1.0
    d = tuple(c / mod for c in d)
    out = []
    for e in _entities_of_types(doc, ["face"]):
        try:
            if e.shape is not None:
                n = ou.face_normal(e.shape)
            elif e.meta.get("mesh_ref"):
                n = _mesh_block_normal(doc, e.meta["mesh_ref"])
            else:
                continue
            if n is None:
                continue
            cosang = sum(n[i] * d[i] for i in range(3))
            cosang = max(-1.0, min(1.0, cosang))
            if math.degrees(math.acos(cosang)) <= tol_deg:
                out.append(e)
        except Exception:
            pass
    return _commit(doc, out, mode)


def select_smallest(doc, n=1, ttype="face", by="measure") -> Set[int]:
    """Le ``n`` entità più piccole per misura (area/lunghezza/volume)."""
    return _extreme(doc, n, ttype, reverse=False)


def select_largest(doc, n=1, ttype="face", by="measure") -> Set[int]:
    """Le ``n`` entità più grandi per misura."""
    return _extreme(doc, n, ttype, reverse=True)


def _extreme(doc, n, ttype, reverse):
    t = normalize_type(ttype)
    scored = []
    for e in _entities_of_types(doc, [t]):
        m = _entity_measure(e)
        if m is not None:
            scored.append((m, e))
    scored.sort(key=lambda t: t[0], reverse=reverse)
    return _commit(doc, [e for _, e in scored[:max(1, int(n))]])


# ---------------------------------------------------------------------------
# selezione topologica / adiacenza
# ---------------------------------------------------------------------------

def _shape_of(e: Entity):
    from . import occ_utils as ou
    if e.shape is not None:
        return e.shape
    ref = e.meta.get("mesh_ref")
    if ref:
        model = doc_model(doc, ref[0])
        if model is not None:
            return ou.mesh_block_shape(model, ref[1], ref[2])
    return None


def select_subshapes(doc, ttype: str, mode="replace") -> Set[int]:
    """Estrae come nuove entità le sotto-entità (punti/curve/superfici) della
    selezione corrente: es. le superfici che compongono un solido."""
    from . import occ_utils as ou
    t = normalize_type(ttype)
    kind = {"point": ou.TopAbs_VERTEX, "curve": ou.TopAbs_EDGE,
            "face": ou.TopAbs_FACE, "solid": ou.TopAbs_SOLID}[t]
    nuove: List[Entity] = []
    for eid in list(doc.selection):
        e = doc.entities.get(eid)
        if e is None:
            continue
        shape = _shape_of(e)
        if shape is None:
            continue
        try:
            subs = ou.unique_subshapes(shape, kind)
        except Exception:
            continue
        for s in subs:
            figlio = doc.find_or_create_sub_entity(e, t, s)
            nuove.append(figlio)
    return _commit(doc, nuove, mode)


def select_vertices_of(doc, mode="replace") -> Set[int]:
    """Punti (vertici) appartenenti alle entità selezionate."""
    return select_subshapes(doc, "point", mode)


def select_edges_of(doc, mode="replace") -> Set[int]:
    """Curve (spigoli) appartenenti alle entità selezionate."""
    return select_subshapes(doc, "curve", mode)


def select_faces_of(doc, mode="replace") -> Set[int]:
    """Superfici appartenenti alle entità selezionate (esplodi solido/composto)."""
    return select_subshapes(doc, "face", mode)


def select_boundary(doc, mode="replace") -> Set[int]:
    """Spigoli di bordo delle superfici selezionate."""
    from . import occ_utils as ou
    out: List[Entity] = []
    for eid in list(doc.selection):
        e = doc.entities.get(eid)
        if e is None or e.etype != "face" or e.shape is None:
            continue
        try:
            for edge in ou.unique_subshapes(e.shape, ou.TopAbs_EDGE):
                out.append(doc.find_or_create_sub_entity(e, "curve", edge))
        except Exception:
            pass
    return _commit(doc, out, mode)


def grow_selection(doc) -> Set[int]:
    """Espande la selezione alle entità adiacenti (che condividono vertici)."""
    from . import occ_utils as ou
    sel = [doc.entities.get(i) for i in doc.selection]
    sel = [e for e in sel if e is not None]
    vertici_sel = set()
    for e in sel:
        shape = _shape_of(e)
        if shape is None:
            continue
        try:
            for v in ou.unique_subshapes(shape, ou.TopAbs_VERTEX):
                vertici_sel.add((v.TShape(), v.Location()))
        except Exception:
            pass
    nuove = set(doc.selection)
    for e in doc.entities.values():
        if e.id in nuove:
            continue
        shape = _shape_of(e)
        if shape is None:
            continue
        try:
            for v in ou.unique_subshapes(shape, ou.TopAbs_VERTEX):
                if (v.TShape(), v.Location()) in vertici_sel:
                    nuove.add(e.id)
                    break
        except Exception:
            continue
    return apply_selection(doc, nuove, "replace")


def shrink_selection(doc) -> Set[int]:
    """Riduce la selezione togliendo le entità di contorno (a contatto con
    entità non selezionate)."""
    from . import occ_utils as ou
    sel_ids = set(doc.selection)
    contatto = set()
    for e in doc.entities.values():
        if e.id in sel_ids:
            continue
        shape = _shape_of(e)
        if shape is None:
            continue
        try:
            for v in ou.unique_subshapes(shape, ou.TopAbs_VERTEX):
                contatto.add((v.TShape(), v.Location()))
        except Exception:
            continue
    rimuovi = set()
    for i in sel_ids:
        e = doc.entities.get(i)
        if e is None:
            continue
        shape = _shape_of(e)
        if shape is None:
            continue
        try:
            for v in ou.unique_subshapes(shape, ou.TopAbs_VERTEX):
                if (v.TShape(), v.Location()) in contatto:
                    rimuovi.add(i)
                    break
        except Exception:
            continue
    return apply_selection(doc, sel_ids - rimuovi, "replace")


def select_connected(doc) -> Set[int]:
    """Selezione connessa: cresce ricorsivamente fino a raggiungere tutte le
    entità toccanti la selezione corrente (equivalente a grow ripetuto)."""
    prev = set(doc.selection)
    while True:
        grow_selection(doc)
        if doc.selection == prev:
            break
        prev = set(doc.selection)
    return doc.selection


# ---------------------------------------------------------------------------
# query fluenti
# ---------------------------------------------------------------------------

class Query:
    """Query di selezione componibile::

        doc.query().type("face").planar().in_box(0,0,0,10,10,10).select()

    Ogni filtro restringe l'insieme corrente; ``.select(mode)`` applica al
    documento, ``.ids()``/``.entities()`` restituiscono il risultato.
    """

    def __init__(self, doc):
        self.doc = doc
        self._ids: Set[int] = set(doc.entities)

    # ---------------- filtri
    def all(self) -> "Query":
        self._ids = set(self.doc.entities)
        return self

    def type(self, ttype) -> "Query":
        t = normalize_type(ttype)
        self._ids &= {e.id for e in self.doc.entities.values() if e.etype == t}
        return self

    def visible(self) -> "Query":
        self._ids &= {e.id for e in self.doc.entities.values() if e.visible}
        return self

    def named(self, pattern, regex=False) -> "Query":
        if regex:
            rx = re.compile(pattern, re.I)
            self._ids &= {e.id for e in self.doc.entities.values() if rx.search(e.name)}
        else:
            self._ids &= {e.id for e in self.doc.entities.values()
                          if fnmatch.fnmatch(e.name.lower(), pattern.lower())}
        return self

    def in_group(self, group_name) -> "Query":
        g = self.doc.groups.get(group_name)
        self._ids &= set(g.member_ids) if g else set()
        return self

    def in_box(self, xmin, ymin, zmin, xmax, ymax, zmax, inside=True) -> "Query":
        ids = select_box(self.doc, xmin, ymin, zmin, xmax, ymax, zmax,
                         inside=inside, mode="replace")
        self._ids &= set(ids)
        return self

    def in_sphere(self, cx, cy, cz, r) -> "Query":
        ids = select_sphere(self.doc, cx, cy, cz, r, mode="replace")
        self._ids &= set(ids)
        return self

    def planar(self) -> "Query":
        self._ids &= set(select_planar(self.doc, mode="replace"))
        return self

    def curved(self) -> "Query":
        self._ids &= set(select_curved(self.doc, mode="replace"))
        return self

    def facing(self, dx, dy, dz, tol_deg=15.0) -> "Query":
        self._ids &= set(select_by_normal(self.doc, dx, dy, dz, tol_deg, mode="replace"))
        return self

    def size_between(self, vmin, vmax) -> "Query":
        """Filtra per misura dell'entità (area/lunghezza/volume)."""
        out = set()
        for eid in self._ids:
            e = self.doc.entities.get(eid)
            if e is None:
                continue
            m = _entity_measure(e)
            if m is not None and vmin <= m <= vmax:
                out.add(eid)
        self._ids = out
        return self

    def with_marker(self, marker) -> "Query":
        self._ids &= {e.id for e in self.doc.entities.values() if e.marker == marker}
        return self

    # ---------------- operatori d'insieme
    def union(self, other_ids: Iterable[int]) -> "Query":
        self._ids |= {int(i) for i in other_ids}
        return self

    def subtract(self, other_ids: Iterable[int]) -> "Query":
        self._ids -= {int(i) for i in other_ids}
        return self

    def grow(self) -> "Query":
        apply_selection(self.doc, self._ids, "replace")
        grow_selection(self.doc)
        self._ids = set(self.doc.selection)
        return self

    def invert(self) -> "Query":
        self._ids = set(self.doc.entities) - self._ids
        return self

    # ---------------- uscita
    def ids(self) -> Set[int]:
        return set(self._ids)

    def entities(self) -> List[Entity]:
        return [self.doc.entities[i] for i in self._ids if i in self.doc.entities]

    def select(self, mode="replace") -> Set[int]:
        return apply_selection(self.doc, self._ids, mode)
