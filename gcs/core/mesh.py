"""Modello dati di una mesh Gmsh e operazioni di selezione sulla mesh.

Il modulo è puro Python (nessuna dipendenza da OpenCASCADE) così che parsing,
selezione e gruppi mesh siano testabili anche in ambiente headless.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Tabella tipi elemento Gmsh -> numero di nodi "angolari" (per il display)
# ---------------------------------------------------------------------------

#: tipi elemento gmsh: {tipo: (nome, n_nodi_totali o None, n_nodi_angolari)}
ELEM_INFO: Dict[int, Tuple[str, Optional[int], int]] = {
    1: ("linea2", 2, 2),
    2: ("triangolo3", 3, 3),
    3: ("quadrilatero4", 4, 4),
    4: ("tetraedro4", 4, 4),
    5: ("esaedro8", 8, 8),
    6: ("prisma6", 6, 6),
    7: ("piramide5", 5, 5),
    8: ("linea3", 3, 2),
    9: ("triangolo6", 6, 3),
    10: ("quadrilatero9", 9, 4),
    11: ("tetraedro10", 10, 4),
    12: ("esaedro27", 27, 8),
    13: ("prisma18", 18, 6),
    14: ("piramide14", 14, 5),
    15: ("punto", 1, 1),
    16: ("quadrilatero8", 8, 4),
}

NOME_ELEMENTO_IT = {1: "Linea", 2: "Triangolo", 3: "Quadrilatero", 4: "Tetraedro",
                    5: "Esaedro", 15: "Punto"}


def corner_nodes(etype: int, nodes: List[int]) -> List[int]:
    """Nodi angolari dell'elemento (per display e topologia)."""
    info = ELEM_INFO.get(etype)
    if info is None:
        return list(nodes)
    n = min(info[2], len(nodes))
    return list(nodes[:n])


class MeshBlock:
    """Blocco entità geometrica Gmsh: elementi condividono (dim, tag).

    In Gmsh gli elementi appartengono a entità geometriche (punto, curva,
    superficie, volume) identificate da ``(dim, tag)``; ciascuna entità può
    essere marcata con uno o più gruppi fisici.
    """

    def __init__(self, dim: int, tag: int):
        self.dim = dim
        self.tag = tag
        self.element_ids: List[int] = []
        self.physical_tags: List[int] = []

    @property
    def key(self) -> Tuple[int, int]:
        return (self.dim, self.tag)

    @property
    def nome(self) -> str:
        base = {0: "Punto", 1: "Curva", 2: "Superficie", 3: "Volume"}.get(self.dim, "?")
        return f"{base} {self.tag}"


class MeshModel:
    """Mesh importata da un file ``.msh`` di Gmsh.

    Strutture:
      * ``nodes``      : {id: (x, y, z)}
      * ``elements``   : {id: (tipo_gmsh, [nodi])}
      * ``blocks``     : {(dim, tag): MeshBlock}
      * ``physicals``  : {(dim, tag_fisico): nome}
    Più tre insiemi di selezione corrente: ``sel_nodes``, ``sel_elements``,
    ``sel_blocks``.
    """

    def __init__(self, name: str, path: Optional[str] = None):
        self.name = name
        self.path = path
        self.nodes: Dict[int, Tuple[float, float, float]] = {}
        self.elements: Dict[int, Tuple[int, List[int]]] = {}
        self.blocks: Dict[Tuple[int, int], MeshBlock] = {}
        self.physicals: Dict[Tuple[int, int], str] = {}
        self._elem_block: Dict[int, Tuple[int, int]] = {}
        # selezioni correnti
        self.sel_nodes: Set[int] = set()
        self.sel_elements: Set[int] = set()
        self.sel_blocks: Set[Tuple[int, int]] = set()

    # ------------------------------------------------------------- costruzione
    def add_node(self, nid: int, x: float, y: float, z: float) -> None:
        self.nodes[nid] = (float(x), float(y), float(z))

    def add_element(self, eid: int, etype: int, nodes: List[int],
                    block_key: Optional[Tuple[int, int]] = None) -> None:
        self.elements[eid] = (etype, list(nodes))
        if block_key is not None:
            self._elem_block[eid] = block_key
            blk = self.blocks.setdefault(block_key, MeshBlock(*block_key))
            blk.element_ids.append(eid)

    def add_physical(self, dim: int, tag: int, nome: str) -> None:
        self.physicals[(dim, tag)] = nome

    def block_of_element(self, eid: int) -> Optional[Tuple[int, int]]:
        return self._elem_block.get(eid)

    def stats(self) -> dict:
        """Statistiche riassuntive della mesh."""
        per_dim: Dict[int, int] = {}
        per_tipo: Dict[int, int] = {}
        for etype, _ in self.elements.values():
            per_tipo[etype] = per_tipo.get(etype, 0) + 1
            info = ELEM_INFO.get(etype)
            dim = {1: 1, 8: 1, 2: 2, 3: 2, 9: 2, 10: 2, 16: 2,
                   4: 3, 5: 3, 6: 3, 7: 3, 11: 3, 12: 3, 13: 3, 14: 3}.get(etype, 0)
            per_dim[dim] = per_dim.get(dim, 0) + 1
        return {
            "nome": self.name,
            "nodi": len(self.nodes),
            "elementi": len(self.elements),
            "blocchi": len(self.blocks),
            "elementi_per_dimensione": per_dim,
            "elementi_per_tipo": per_tipo,
            "gruppi_fisici": dict(self.physicals),
        }

    # ---------------------------------------------------------------- geometria
    def nodes_of_elements(self, elem_ids) -> Set[int]:
        out: Set[int] = set()
        for eid in elem_ids:
            el = self.elements.get(eid)
            if el:
                out.update(el[1])
        return out

    def elements_bbox(self, elem_ids) -> Optional[Tuple[float, float, float, float, float, float]]:
        xs, ys, zs = [], [], []
        for nid in self.nodes_of_elements(elem_ids):
            x, y, z = self.nodes[nid]
            xs.append(x); ys.append(y); zs.append(z)
        if not xs:
            return None
        return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

    def node_in_box(self, nid, box, strict=True) -> bool:
        x, y, z = self.nodes[nid]
        xmin, ymin, zmin, xmax, ymax, zmax = box
        if strict:
            return xmin <= x <= xmax and ymin <= y <= ymax and zmin <= z <= zmax
        return (xmin - 1e-12) <= x <= (xmax + 1e-12) and (ymin - 1e-12) <= y <= \
            (ymax + 1e-12) and (zmin - 1e-12) <= z <= (zmax + 1e-12)

    # ------------------------------------------------------- selezione elementi
    def select_all_elements(self) -> int:
        self.sel_elements = set(self.elements)
        return len(self.sel_elements)

    def select_all_nodes(self) -> int:
        self.sel_nodes = set(self.nodes)
        return len(self.sel_nodes)

    def clear_selection(self) -> None:
        self.sel_nodes.clear()
        self.sel_elements.clear()
        self.sel_blocks.clear()

    def select_elements_in_box(self, box, only_selected=False) -> Set[int]:
        """Elementi il cui *baricentro* (media dei nodi angolari) cade nel box."""
        res: Set[int] = set()
        base = self.sel_elements if only_selected else self.elements
        for eid in base:
            el = self.elements[eid]
            cn = corner_nodes(el[0], el[1])
            pts = [self.nodes[n] for n in cn if n in self.nodes]
            if not pts:
                continue
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            cz = sum(p[2] for p in pts) / len(pts)
            xmin, ymin, zmin, xmax, ymax, zmax = box
            if xmin <= cx <= xmax and ymin <= cy <= ymax and zmin <= cz <= zmax:
                res.add(eid)
        self.sel_elements = res
        return res

    def select_elements_in_sphere(self, cx, cy, cz, r, only_selected=False) -> Set[int]:
        res: Set[int] = set()
        base = self.sel_elements if only_selected else self.elements
        r2 = r * r
        for eid in base:
            el = self.elements[eid]
            cn = corner_nodes(el[0], el[1])
            pts = [self.nodes[n] for n in cn if n in self.nodes]
            if not pts:
                continue
            ex = sum(p[0] for p in pts) / len(pts)
            ey = sum(p[1] for p in pts) / len(pts)
            ez = sum(p[2] for p in pts) / len(pts)
            if (ex - cx) ** 2 + (ey - cy) ** 2 + (ez - cz) ** 2 <= r2:
                res.add(eid)
        self.sel_elements = res
        return res

    def select_elements_by_type(self, etypes) -> Set[int]:
        """Selezione per tipo elemento gmsh (es. {2, 3} per triangoli+quads)."""
        etypes = set(etypes)
        res = {eid for eid, el in self.elements.items() if el[0] in etypes}
        self.sel_elements = res
        return res

    def select_elements_by_dimension(self, dim: int) -> Set[int]:
        """Selezione tutti gli elementi di una data dimensione topologica."""
        dims = {0: {15}, 1: {1, 8}, 2: {2, 3, 9, 10, 16},
                3: {4, 5, 6, 7, 11, 12, 13, 14}}.get(dim, set())
        return self.select_elements_by_type(dims)

    def select_block(self, dim: int, tag: int) -> Set[int]:
        """Selezione tutti gli elementi del blocco entità (dim, tag)."""
        blk = self.blocks.get((dim, tag))
        res = set(blk.element_ids) if blk else set()
        self.sel_elements = res
        self.sel_blocks = {(dim, tag)}
        return res

    def select_blocks_by_physical(self, fisico) -> Set[int]:
        """Selezione blocchi per tag o nome fisico (accetta int o str)."""
        res: Set[int] = set()
        blocc_sel: Set[Tuple[int, int]] = set()
        for (dim, tag), blk in self.blocks.items():
            for pt in blk.physical_tags:
                nome = self.physicals.get((dim, pt), "")
                if (isinstance(fisico, int) and pt == fisico) or \
                        (isinstance(fisico, str) and nome == fisico):
                    blocc_sel.add((dim, tag))
                    res.update(blk.element_ids)
                    break
        self.sel_elements = res
        self.sel_blocks = blocc_sel
        return res

    def select_nodes_in_box(self, box) -> Set[int]:
        self.sel_nodes = {n for n in self.nodes if self.node_in_box(n, box)}
        return self.sel_nodes

    def select_nodes_in_sphere(self, cx, cy, cz, r) -> Set[int]:
        r2 = r * r
        self.sel_nodes = {n for n, (x, y, z) in self.nodes.items()
                          if (x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2 <= r2}
        return self.sel_nodes

    def select_nodes_of_selected_elements(self) -> Set[int]:
        self.sel_nodes = self.nodes_of_elements(self.sel_elements)
        return self.sel_nodes

    # ------------------------------------------------------------- topologia
    def grow_elements(self, by: str = "nodes") -> Set[int]:
        """Espande la selezione agli elementi adiacenti (che condividono nodi).

        ``by``: "nodes" (condivisione di qualunque nodo) oppure "faces"
        (condivisione di una faccia intera, solo per elementi volumetrici).
        """
        if not self.sel_elements:
            return self.sel_elements
        if by == "faces":
            vicini = self._neighbours_by_face()
        else:
            vicini = self._neighbours_by_node()
        nuove = set(self.sel_elements)
        for eid in self.sel_elements:
            nuove.update(vicini.get(eid, ()))
        self.sel_elements = nuove
        return nuove

    def _neighbours_by_node(self) -> Dict[int, Set[int]]:
        nodi2el: Dict[int, Set[int]] = {}
        for eid, (_, nodes) in self.elements.items():
            for n in nodes:
                nodi2el.setdefault(n, set()).add(eid)
        vicini: Dict[int, Set[int]] = {}
        for eid, (_, nodes) in self.elements.items():
            s = vicini.setdefault(eid, set())
            for n in nodes:
                s.update(nodi2el[n])
            s.discard(eid)
        return vicini

    def _neighbours_by_face(self) -> Dict[int, Set[int]]:
        """Adiacenza per faccia condivisa (triangoli/tetraedri: triple ordinate)."""
        facce2el: Dict[Tuple[int, ...], Set[int]] = {}
        for eid, (etype, nodes) in self.elements.items():
            cn = corner_nodes(etype, nodes)
            if etype == 4 and len(cn) == 4:          # tetraedro: 4 facce triangolari
                tri = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]
                for t in tri:
                    f = tuple(sorted(cn[i] for i in t))
                    facce2el.setdefault(f, set()).add(eid)
            elif etype == 2 and len(cn) == 3:        # triangolo: spigoli
                for i in range(3):
                    f = tuple(sorted((cn[i], cn[(i + 1) % 3])))
                    facce2el.setdefault(f, set()).add(eid)
        vicini: Dict[int, Set[int]] = {}
        for _, els in facce2el.items():
            for e in els:
                vicini.setdefault(e, set()).update(els)
        for e in vicini:
            vicini[e].discard(e)
        return vicini

    def shrink_elements(self) -> Set[int]:
        """Rimuove dalla selezione gli elementi di contorno (a contatto con l'esterno)."""
        if not self.sel_elements:
            return self.sel_elements
        vicini = self._neighbours_by_node()
        bordo = {eid for eid in self.sel_elements
                 if not set(vicini.get(eid, ())) <= self.sel_elements}
        self.sel_elements -= bordo
        return self.sel_elements

    def invert_selection_elements(self) -> Set[int]:
        self.sel_elements = set(self.elements) - self.sel_elements
        return self.sel_elements

    def invert_selection_nodes(self) -> Set[int]:
        self.sel_nodes = set(self.nodes) - self.sel_nodes
        return self.sel_nodes

    def boundary_faces(self, elem_ids) -> Set[Tuple[int, int, int]]:
        """Facce esterne (triangoli) degli elementi volumetrici indicati.

        Per ogni tetraedro genera le 4 facce; le facce condivise da due
        elementi sono interne e vengono eliminate (compaiono una sola volta).
        """
        conteggio: Dict[Tuple[int, int, int], int] = {}
        for eid in elem_ids:
            etype, nodes = self.elements.get(eid, (None, []))
            cn = corner_nodes(etype, nodes)
            if etype == 4 and len(cn) == 4:
                for t in [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]:
                    f = tuple(sorted(cn[i] for i in t))
                    conteggio[f] = conteggio.get(f, 0) + 1
            elif etype == 2 and len(cn) == 3:
                f = tuple(sorted(cn))
                conteggio[f] = conteggio.get(f, 0) + 1
        return {f for f, n in conteggio.items() if n == 1}
