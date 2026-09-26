"""Modalità Geometria: creazione di punti, curve, superfici e solidi.

:class:`GeometryBuilder` espone tutte le operazioni di creazione B-Rep:
ogni funzione registra la nuova entità nel documento (con undo) e la
restituisce. Le curve parametriche conservano i punti di controllo in
``meta['ctrl_points']`` così da poter essere **modificate** in seguito
(spedito il punto, la curva viene rigenerata).
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .entities import Entity, normalize_type
from . import occ_utils as ou
from .document import CADDocument, DocumentError


class GeometryBuilder:
    """Operazioni di creazione geometria su un documento."""

    def __init__(self, doc: CADDocument):
        self.doc = doc

    # ------------------------------------------------------------------ punti
    def punto(self, x: float, y: float, z: float, name: Optional[str] = None) -> Entity:
        """Crea un punto (vertice) alle coordinate date."""
        shape = ou.make_vertex((x, y, z))
        return self.doc.add_entity(Entity("point", shape=shape, name=name))

    def punti(self, lista: Sequence[Sequence[float]], base_name="Punto") -> List[Entity]:
        """Crea una serie di punti; restituisce le entità create."""
        out = []
        for i, p in enumerate(lista):
            out.append(self.punto(p[0], p[1], p[2], name=f"{base_name} {i + 1}"))
        return out

    def punto_medio(self, p1, p2) -> Entity:
        """Punto medio tra due punti."""
        m = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, (p1[2] + p2[2]) / 2)
        return self.punto(*m, name="Punto medio")

    # ------------------------------------------------------------------ curve
    def linea(self, p1, p2, name=None) -> Entity:
        """Segmento tra due punti."""
        shape = ou.make_edge_p2p(p1, p2)
        return self.doc.add_entity(Entity("curve", shape=shape,
                                          name=name or "Linea"))

    def polilinea(self, punti: Sequence[Sequence[float]], name=None) -> List[Entity]:
        """Crea le singole linee di una polilinea aperta."""
        out = []
        for i in range(len(punti) - 1):
            out.append(self.linea(punti[i], punti[i + 1],
                                  name=(name or "Polilinea") + f" {i + 1}"))
        return out

    def spline(self, punti: Sequence[Sequence[float]], closed=False,
               name=None) -> Entity:
        """Spline passante per i punti; i punti restano editabili."""
        shape = ou.make_edge_spline(punti, closed)
        e = self.doc.add_entity(Entity("curve", shape=shape,
                                       name=name or "Spline"))
        e.meta["ctrl_points"] = [tuple(map(float, p)) for p in punti]
        e.meta["closed"] = bool(closed)
        return e

    def cerchio(self, cx, cy, cz, r, normal=(0, 0, 1), name=None) -> Entity:
        """Circonferenza (curva chiusa) con centro, raggio e normale."""
        shape = ou.make_edge_circle((cx, cy, cz), r, normal)
        e = self.doc.add_entity(Entity("curve", shape=shape,
                                       name=name or f"Cerchio r={r}"))
        e.meta["ctrl_points"] = [(float(cx), float(cy), float(cz))]
        e.meta["kind"] = "cerchio"
        e.meta["raggio"] = float(r)
        return e

    def arco(self, p1, pm, p2, name=None) -> Entity:
        """Arco definito da estremi e punto di mezzo."""
        shape = ou.make_edge_arc3p(p1, pm, p2)
        return self.doc.add_entity(Entity("curve", shape=shape,
                                          name=name or "Arco"))

    # -------------------------------------------------------------- superfici
    def superficie_da_punti(self, punti: Sequence[Sequence[float]],
                            name=None) -> Entity:
        """Superficie planare da poligono di punti (ordine orario/antiorario)."""
        face = ou.make_face_polygon(punti)
        e = self.doc.add_entity(Entity("face", shape=face,
                                       name=name or "Superficie"))
        e.meta["ctrl_points"] = [tuple(map(float, p)) for p in punti]
        return e

    def rettangolo(self, cx, cy, larghezza, altezza, z=0.0, name=None) -> Entity:
        """Superficie rettangolare orizzontale centrata in (cx, cy, z)."""
        l, a = float(larghezza) / 2, float(altezza) / 2
        pts = [(cx - l, cy - a, z), (cx + l, cy - a, z),
               (cx + l, cy + a, z), (cx - l, cy + a, z)]
        return self.superficie_da_punti(pts, name=name or "Rettangolo")

    def superficie_da_curve(self, curve_ids: List[int], name=None) -> Entity:
        """Superficie planare dal profilo chiuso formato dalle curve indicate."""
        curve = [self.doc.get(i) for i in curve_ids]
        curve = [c for c in curve if c is not None and c.shape is not None]
        if len(curve) < 1:
            raise DocumentError("Servono curve valide per costruire il profilo")
        wire = ou.make_wire([c.shape for c in curve])
        face = ou.make_face_from_wire(wire, planar=True)
        return self.doc.add_entity(Entity("face", shape=face,
                                          name=name or "Superficie da profilo"))

    def superficie_rigata(self, curve_id1: int, curve_id2: int,
                          name=None) -> Entity:
        """Superficie rigata tra due curve (ruled surface)."""
        c1, c2 = self.doc.get(curve_id1), self.doc.get(curve_id2)
        if not c1 or not c2 or c1.shape is None or c2.shape is None:
            raise DocumentError("Le due curve devono esistere")
        shell = ou.loft([c1.shape, c2.shape], solid=False, ruled=True)
        return self.doc.add_entity(Entity("face", shape=shell,
                                          name=name or "Superficie rigata"))

    # ----------------------------------------------------------------- solidi
    def box(self, dx, dy, dz, base=(0, 0, 0), name=None) -> Entity:
        """Parallelepipedo con dimensioni (dx, dy, dz) da corner ``base``."""
        shape = ou.prim_box(base, (base[0] + dx, base[1] + dy, base[2] + dz))
        return self.doc.add_entity(Entity("solid", shape=shape,
                                          name=name or f"Box {dx}x{dy}x{dz}"))

    def cilindro(self, r, h, base=(0, 0, 0), axis=(0, 0, 1), name=None) -> Entity:
        shape = ou.prim_cylinder(r, h, base, axis)
        return self.doc.add_entity(Entity("solid", shape=shape,
                                          name=name or f"Cilindro r={r} h={h}"))

    def sfera(self, r, center=(0, 0, 0), name=None) -> Entity:
        shape = ou.prim_sphere(r, center)
        return self.doc.add_entity(Entity("solid", shape=shape,
                                          name=name or f"Sfera r={r}"))

    def cono(self, r1, r2, h, base=(0, 0, 0), axis=(0, 0, 1), name=None) -> Entity:
        shape = ou.prim_cone(r1, r2, h, base, axis)
        return self.doc.add_entity(Entity("solid", shape=shape,
                                          name=name or "Cono"))

    def toro(self, r_major, r_minor, name=None) -> Entity:
        shape = ou.prim_torus(r_major, r_minor)
        return self.doc.add_entity(Entity("solid", shape=shape,
                                          name=name or "Toro"))

    def estrudi(self, profilo_id: int, dx, dy, dz, name=None) -> Entity:
        """Estrude una superficie (o curva chiusa) lungo il vettore dato."""
        prof = self.doc.get(profilo_id)
        if not prof or prof.shape is None:
            raise DocumentError("Profilo non valido per l'estrusione")
        shape = ou.prim_prism(prof.shape, (dx, dy, dz))
        e = self.doc.add_entity(Entity("solid", shape=shape,
                                       name=name or "Estrusione"))
        e.meta["parent"] = prof.id
        return e

    def rivolgi(self, profilo_id: int, px, py, pz, ax, ay, az,
                angolo_deg=360.0, name=None) -> Entity:
        """Revolve di un profilo attorno a un asse (angolo in gradi)."""
        prof = self.doc.get(profilo_id)
        if not prof or prof.shape is None:
            raise DocumentError("Profilo non valido per la rivoluzione")
        shape = ou.prim_revolve(prof.shape, (px, py, pz), (ax, ay, az), angolo_deg)
        return self.doc.add_entity(Entity("solid", shape=shape,
                                          name=name or "Rivoluzione"))

    def loft(self, sezioni_ids: List[int], solid=True, name=None) -> Entity:
        """Loft (scansione) tra sezioni curve/superfici; ``solid=True`` crea solido."""
        sezioni = []
        for i in sezioni_ids:
            e = self.doc.get(i)
            if e is None or e.shape is None:
                raise DocumentError("Sezione loft non valida")
            sezioni.append(e.shape)
        shape = ou.loft(sezioni, solid=solid, ruled=False)
        ttype = "solid" if solid else "face"
        return self.doc.add_entity(Entity(ttype, shape=shape, name=name or "Loft"))

    def tubo(self, spina_id: int, profilo_id: int, name=None) -> Entity:
        """Sweep di un profilo lungo la curva spina (pipe)."""
        spina, prof = self.doc.get(spina_id), self.doc.get(profilo_id)
        if not spina or not prof or spina.shape is None or prof.shape is None:
            raise DocumentError("Spina/profilo non validi per lo sweep")
        shape = ou.pipe(spina.shape, prof.shape)
        return self.doc.add_entity(Entity("solid", shape=shape,
                                          name=name or "Tubo"))
