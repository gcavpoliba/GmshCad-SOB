"""Modalità Geometria: modifica ed editing di punti, curve, superfici, solidi.

:class:`GeometryEditor` include trasformazioni (trasla/ruota/scala/specchia),
booleane (fusione/taglio/intersezione), raccordi e smussi, svuotamento,
esplodi in sotto-entità, offset e la modifica parametrica di punti e curve
(rigenerazione dal punto di controllo corretto). Tutte le operazioni hanno undo.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from .entities import Entity, normalize_type, NOME_TIPO_IT
from . import occ_utils as ou
from .document import CADDocument, DocumentError


class GeometryEditor:
    """Operazioni di modifica ed editing sul documento."""

    def __init__(self, doc: CADDocument):
        self.doc = doc

    # ------------------------------------------------------------- utilità
    def _entities(self, ids) -> List[Entity]:
        out = []
        for i in ids:
            e = self.doc.get(i)
            if e is None:
                raise DocumentError(f"Entità {i} inesistente")
            out.append(e)
        return out

    def _require_shape(self, e: Entity):
        if e.shape is None:
            raise DocumentError(f"'{e.name}' non ha geometria modificabile "
                                "(è un blocco mesh?)")
        return e.shape

    # ------------------------------------------------------- trasformazioni
    def trasla(self, ids: Iterable[int], dx, dy, dz, push_undo: bool = True) -> int:
        """Traslazione delle entità indicate (con undo di default).

        Se `push_undo=False`, salta la registrazione nello stack di undo
        (utile per il drag live del mouse, dove l'undo è registrato al rilascio).
        """
        entita = self._entities(ids)
        fatti = 0
        for e in entita:
            if e.shape is None:
                continue
            nuovo = ou.translate(e.shape, (dx, dy, dz))
            self.doc.replace_entity_shape(e, nuovo, push_undo=push_undo)
            self._shift_ctrl_points(e, (dx, dy, dz))
            fatti += 1
        self.doc.notify("entities_changed", {"ids": [e.id for e in entita]})
        return fatti

    def ruota(self, ids, px, py, pz, ax, ay, az, angolo_deg, push_undo: bool = True) -> int:
        entita = self._entities(ids)
        fatti = 0
        for e in entita:
            if e.shape is None:
                continue
            nuovo = ou.rotate(e.shape, (px, py, pz), (ax, ay, az), angolo_deg)
            self.doc.replace_entity_shape(e, nuovo, push_undo=push_undo)
            fatti += 1
        return fatti

    def scala(self, ids, fattore, centro=(0, 0, 0), push_undo: bool = True) -> int:
        entita = self._entities(ids)
        fatti = 0
        for e in entita:
            if e.shape is None:
                continue
            nuovo = ou.scale(e.shape, fattore, centro)
            self.doc.replace_entity_shape(e, nuovo, push_undo=push_undo)
            if e.meta.get("ctrl_points"):
                e.meta["ctrl_points"] = [
                    tuple(centro[k] + (p[k] - centro[k]) * float(fattore)
                          for k in range(3)) for p in e.meta["ctrl_points"]]
            fatti += 1
        return fatti

    def specchia(self, ids, px, py, pz, nx, ny, nz) -> int:
        entita = self._entities(ids)
        fatti = 0
        for e in entita:
            if e.shape is None:
                continue
            nuovo = ou.mirror(e.shape, (px, py, pz), (nx, ny, nz))
            self.doc.replace_entity_shape(e, nuovo)
            fatti += 1
        return fatti

    def copia(self, ids: Iterable[int]) -> List[Entity]:
        """Duplica le entità indicate (shape condivisa clonata via copia)."""
        out = []
        for e in self._entities(ids):
            if e.shape is None:
                continue
            nuovo = ou.translate(e.shape, (0, 0, 0))   # copia geometrica
            copia = Entity(e.etype, shape=nuovo, name=f"{e.name} copia")
            copia.color = e.color
            copia.meta.update({k: v for k, v in e.meta.items() if k != "parent"})
            self.doc.add_entity(copia)
            out.append(copia)
        return out

    # ---------------------------------------------------------- editing punti
    def trasla_punto(self, punto_id: int, dx, dy, dz) -> None:
        """Sposta un'entità punto; se fa da controllo a curve/superfici,
        quelle vengono rigenerate."""
        e = self.doc.get(punto_id)
        if e is None or e.etype != "point" or e.shape is None:
            raise DocumentError("Serve l'id di un'entità punto")
        v = ou.vertex_point(e.shape)
        nuovo = ou.make_vertex((v[0] + dx, v[1] + dy, v[2] + dz))
        self.doc.replace_entity_shape(e, nuovo)
        self._propagate_point_edit(e, (v[0] + dx, v[1] + dy, v[2] + dz))

    def imposta_punto(self, punto_id: int, x, y, z) -> None:
        e = self.doc.get(punto_id)
        if e is None or e.etype != "point" or e.shape is None:
            raise DocumentError("Serve l'id di un'entità punto")
        self.doc.replace_entity_shape(e, ou.make_vertex((x, y, z)))
        self._propagate_point_edit(e, (x, y, z))

    def _propagate_point_edit(self, punto: Entity, nuovo_punto) -> None:
        """Se il punto è usato come controllo da curve/superfici (meta['ctrl_refs']),
        rigenera quelle geometrie con la nuova posizione."""
        self._rebuild_dependents(punto, nuovo_punto)

    def _rebuild_dependents(self, punto: Entity, nuovo_punto) -> None:
        """Curve/superfici collegate al punto tramite meta['ctrl_refs']."""
        refs = punto.meta.get("ctrl_refs") or []
        for (eid, idx) in refs:
            e = self.doc.get(eid)
            if e is None or not e.meta.get("ctrl_points"):
                continue
            if idx < len(e.meta["ctrl_points"]):
                e.meta["ctrl_points"][idx] = tuple(map(float, nuovo_punto))
            self._rebuild_parametric(e)

    def _shift_ctrl_points(self, e: Entity, d) -> None:
        ctrl = e.meta.get("ctrl_points")
        if ctrl:
            e.meta["ctrl_points"] = [(p[0] + d[0], p[1] + d[1], p[2] + d[2])
                                     for p in ctrl]

    def edita_punto_curva(self, curve_id: int, indice: int, x, y, z) -> None:
        """Modifica il punto di controllo ``indice`` di una curva parametrica."""
        e = self.doc.get(curve_id)
        if e is None or not e.meta.get("ctrl_points"):
            raise DocumentError("La curva non ha punti di controllo editabili")
        ctrl = e.meta["ctrl_points"]
        if not 0 <= indice < len(ctrl):
            raise DocumentError(f"Indice {indice} fuori range (0..{len(ctrl) - 1})")
        ctrl[indice] = (float(x), float(y), float(z))
        self._rebuild_parametric(e)

    def _rebuild_parametric(self, e: Entity) -> None:
        """Rigenera curve/superfici parametriche dai punti di controllo."""
        kind = e.meta.get("kind")
        ctrl = e.meta.get("ctrl_points") or []
        try:
            if e.etype == "curve":
                if kind == "cerchio":
                    n = e.meta.get("normal", (0, 0, 1))
                    e.meta["raggio"] = e.meta.get("raggio", 1.0)
                    nuovo = ou.make_edge_circle(ctrl[0], e.meta["raggio"], n)
                else:
                    nuovo = ou.make_edge_spline(ctrl, e.meta.get("closed", False))
            elif e.etype == "face" and len(ctrl) >= 3:
                nuovo = ou.make_face_polygon(ctrl)
            else:
                return
            self.doc.replace_entity_shape(e, nuovo)
        except Exception as exc:
            raise DocumentError(f"Ricostruzione di '{e.name}' fallita: {exc}")

    # ------------------------------------------------------------- booleane
    def fusa(self, ids: Iterable[int], mantieni=False) -> Entity:
        """Fusione (union) delle entità indicate; crea un nuovo solido."""
        entita = self._entities(ids)
        shapes = [self._require_shape(e) for e in entita]
        if len(shapes) < 2:
            raise DocumentError("Servono almeno 2 entità per la fusione")
        acc = shapes[0]
        for s in shapes[1:]:
            acc = ou.fuse(acc, s)
        res = self.doc.add_entity(Entity("solid", shape=acc,
                                         name=f"Fusione di {len(shapes)}"))
        if not mantieni:
            self.doc.remove_entities([e.id for e in entita])
        return res

    def taglia(self, id_a: int, id_b: int, mantieni=False) -> Entity:
        """Differenza booleana: A meno B."""
        a, b = self._entities([id_a, id_b])
        res_shape = ou.cut(self._require_shape(a), self._require_shape(b))
        res = self.doc.add_entity(Entity("solid", shape=res_shape,
                                         name=f"{a.name} - {b.name}"))
        if not mantieni:
            self.doc.remove_entities([id_a, id_b])
        return res

    def intersezione(self, id_a: int, id_b: int, mantieni=False) -> Entity:
        a, b = self._entities([id_a, id_b])
        res_shape = ou.common(self._require_shape(a), self._require_shape(b))
        res = self.doc.add_entity(Entity("solid", shape=res_shape,
                                         name=f"Int. {a.name}/{b.name}"))
        if not mantieni:
            self.doc.remove_entities([id_a, id_b])
        return res

    # ----------------------------------------------------- raccordi / smussi
    def raccorda(self, solid_id: int, edge_ids: Optional[Iterable[int]] = None,
                 raggio: float = 1.0) -> Entity:
        """Raccorda gli spigoli indicati (o tutti se non specificati)."""
        solido = self.doc.get(solid_id)
        if solido is None or solido.etype != "solid":
            raise DocumentError("Serve un'entità solido da raccordare")
        shape = self._require_shape(solido)
        if edge_ids:
            edges = [self._require_shape(self.doc.get(i)) for i in edge_ids]
        else:
            edges = ou.unique_subshapes(shape, ou.TopAbs_EDGE)
        nuovo = ou.fillet_edges(shape, edges, raggio)
        self.doc.replace_entity_shape(solido, nuovo)
        return solido

    def smussa(self, solid_id: int, edge_ids: Optional[Iterable[int]] = None,
               distanza: float = 1.0) -> Entity:
        solido = self.doc.get(solid_id)
        if solido is None or solido.etype != "solid":
            raise DocumentError("Serve un'entità solido da smussare")
        shape = self._require_shape(solido)
        if edge_ids:
            edges = [self._require_shape(self.doc.get(i)) for i in edge_ids]
        else:
            edges = ou.unique_subshapes(shape, ou.TopAbs_EDGE)
        nuovo = ou.chamfer_edges(shape, edges, distanza)
        self.doc.replace_entity_shape(solido, nuovo)
        return solido

    def svuota(self, solid_id: int, spessore: float,
               face_ids_da_aprire: Optional[Iterable[int]] = None) -> Entity:
        """Svuota il solido (cavity) rimuovendo le facce indicate."""
        solido = self.doc.get(solid_id)
        if solido is None or solido.etype != "solid":
            raise DocumentError("Serve un'entità solido")
        shape = self._require_shape(solido)
        apri = []
        if face_ids_da_aprire:
            apri = [self._require_shape(self.doc.get(i)) for i in face_ids_da_aprire]
        nuovo = ou.hollow_solid(shape, apri, spessore)
        self.doc.replace_entity_shape(solido, nuovo)
        return solido

    def offset(self, ent_id: int, distanza: float) -> Entity:
        """Offset di superficie o solido (crea nuova entità)."""
        e = self.doc.get(ent_id)
        if e is None or e.shape is None:
            raise DocumentError("Entità non valida per l'offset")
        nuovo = ou.offset_shape(e.shape, distanza)
        ttype = e.etype if e.etype in ("face", "solid") else "solid"
        return self.doc.add_entity(Entity(ttype, shape=nuovo,
                                          name=f"{e.name} offset {distanza:+g}"))

    # ------------------------------------------------------------- esplodi
    def esplodi(self, ids: Iterable[int], ttype: str = "face") -> List[Entity]:
        """Estrae le sotto-entità (punti/curve/superfici) delle entità selezionate
        e le registra come entità indipendenti raggruppate."""
        t = normalize_type(ttype)
        kind = {"point": ou.TopAbs_VERTEX, "curve": ou.TopAbs_EDGE,
                "face": ou.TopAbs_FACE}[t]
        create = []
        gruppi_nomi = set()
        for eid in list(ids):
            e = self.doc.get(eid)
            if e is None:
                continue
            shape = self._require_shape(e)
            subs = ou.unique_subshapes(shape, kind)
            gname = f"{e.name} — {NOME_TIPO_IT[t]}"
            gruppi_nomi.add(gname)
            gcolor = e.color
            nuovi = []
            for s in subs:
                figlio = Entity(t, shape=s, name=f"{e.name}.{t}")
                figlio.meta["parent"] = e.id
                figlio.color = gcolor
                self.doc.add_entity(figlio)
                nuovi.append(figlio)
                create.append(figlio)
            if nuovi:
                g = self.doc.groups.get_or_create(gname, gcolor)
                g.member_ids.update(f.id for f in nuovi)
        self.doc.notify("entities_added_batch", {"ids": [f.id for f in create]})
        return create

    # -------------------------------------------------------------- attributi
    def rinomina(self, ent_id: int, nome: str) -> None:
        e = self.doc.get(ent_id)
        if e is None:
            raise DocumentError("Entità inesistente")
        e.name = nome
        self.doc.notify("entity_updated", {"id": ent_id})

    def imposta_colore(self, ids: Iterable[int], rgb: Tuple[float, float, float]) -> None:
        for e in self._entities(ids):
            e.color = tuple(float(c) for c in rgb)
        self.doc.notify("entities_changed", {"ids": [e.id for e in self._entities(ids)]})

    def elimina(self, ids: Iterable[int]) -> int:
        return self.doc.remove_entities(ids)
