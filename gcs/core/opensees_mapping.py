"""Mapping del modello CAD/Gmsh verso OpenSees (rif. struttura OpenSees-master).

Il modulo realizza il *mapping delle proprietà per elemento*: dato un documento
(GmshCAD Studio) con entità geometriche, blocchi mesh e — facoltativamente —
fasi/proprietà assegnate (``gcs.core.fases``), produce uno script Tcl pronto
per OpenSees nella stessa organizzazione di ``OpenSees-master/mingw32/bin/tcl``
e degli esempi ``OpenSees-master/tests``:

    nodo -> node / fix          (src/node, src/element)
    materiale -> uniaxialMaterial / NDMaterial   (src/material)
    sezione -> section (elastic / GCMeshing...)  (src/section)
    elemento gmsh -> element truss/beamColumnJoint/shell... (src/element)
    vincolo -> equalDOF / rigidDiaphragm         (src/constraint)
    analisi -> analysis/numberer/system/test/algorithm/solver (src/analysis)

È puro Python (nessuna importazione di OCC/Qt/gmsh obbligatoria): l'export
funziona anche headless ed è coperto da test.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#: Tabella di mapping tipo-elemento Gmsh -> elemento OpenSees consigliato.
#: (tipo gmsh, n_nodi) -> suggerimento
MAP_GMSH_OPENSEES = {
    (1, 2): "truss",            # linea 2 nodi
    (8, 2): "truss",            # linea 3 nodi (lineare ridotta)
    (4, 4): "solidBrick|tetgen",# tetraedro (in OpenSees: TetGen4 via element)
    (11, 4): "TetGen4",         # tetraedro 10 nodi -> ordine ridotto a 4
    (5, 8): "BRICK20",          # esaedro (element user-defined BRICK)
    (2, 3): "ShellMITC4",       # triangolo -> guscio
    (3, 4): "ShellMITC4",       # quad -> guscio
    (15, 1): "node",            # punto -> solo nodo
}

#: Ordine dei nodi richiesto da OpenSees per le famiglie principali.
#: Se la connettività non rispetta l'ordine, viene riordinata qui.
ORDINE_NODI_OPENSEES = {
    "truss": list(range(2)),
    "beam": list(range(2)),
    "ShellMITC4": [0, 1, 2, 3],
    "TetGen4": [0, 1, 2, 3],
    "BRICK20": [0, 1, 2, 3, 4, 5, 6, 7],
}


def normalizza_connettivita(nodes: List[int], etype: int) -> Tuple[List[int], str]:
    """Riduce/riordina la connettività secondo l'ordine previsto da OpenSees.

    Restituisce ``(nodi_angolari, suggerimento_elemento)``. Per gli elementi
    d'ordine superiore (nodi mid-side) i nodi intermedi vengono scartati:
    OpenSees lavora con elementi lineari per quelle famiglie (salvo eccezioni).
    """
    info = MAP_GMSH_OPENSEES.get((etype, len(nodes)))
    if info is None:
        # tenta con gli angolari
        from .mesh import corner_nodes
        ang = corner_nodes(etype, nodes)
        info = MAP_GMSH_OPENSEES.get((etype, len(ang)), "unsupported")
        return ang, info
    return list(nodes), info


class ModelMapper:
    """Costruisce lo script Tcl OpenSees a partire dal documento."""

    def __init__(self, doc, phases=None):
        self.doc = doc
        self.phases = phases  # PhaseManager o None

    # ------------------------------------------------------- raccolta dati
    def _mesh_models(self):
        return list(self.doc.mesh_models.values())

    def collect_nodes(self) -> Dict[int, Tuple[float, float, float]]:
        nodi: Dict[int, Tuple[float, float, float]] = {}
        for m in self._mesh_models():
            nodi.update(m.nodes)
        return nodi

    def collect_elements(self) -> List[Tuple[int, int, List[int]]]:
        els: List[Tuple[int, int, List[int]]] = []
        for m in self._mesh_models():
            for eid, (etype, nodes) in m.elements.items():
                els.append((eid, etype, list(nodes)))
        return sorted(els)

    # ------------------------------------------------------------- export
    def header(self) -> List[str]:
        return [
            "# Script generato da GmshCAD Studio — mapping verso OpenSees",
            "# (organizzazione comandi conforme a OpenSees-master/src/*)",
            "units mm",
            "model BasicBuilder -ndm 3 -ndf 6",
        ]

    def riga_node(self, nid: int, xyz) -> str:
        return f"node {nid} {xyz[0]:.6f} {xyz[1]:.6f} {xyz[2]:.6f}"

    def riga_materiale(self, mat_id: int, E: float = 210000.0,
                       nu: float = 0.3, rho: float = 7.85e-9) -> str:
        return (f"uniaxialMaterial Elastic {mat_id} {E:g}  ;# "
                f"(NDMaterial 3D: nu={nu:g}, rho={rho:g})")

    def riga_sezione(self, sez_id: int, A: float = 100.0,
                     Iy: float = 1000.0, Iz: float = 1000.0) -> str:
        return f"section Elastic {sez_id} 1.0 {A:g} {Iy:g} {Iz:g}"

    def riga_elemento(self, eid: int, etype: int, nodes: List[int],
                      prop=None) -> Optional[str]:
        ang, sugg = normalizza_connettivita(nodes, etype)
        if sugg == "unsupported":
            return None
        if sugg in ("truss", "beam"):
            mat = getattr(prop, "mat_id", 1) or 1
            sez = getattr(prop, "sezione_id", 1) or 1
            if sugg == "truss":
                return f"element truss {eid} {' '.join(map(str, ang))} {mat} {sez}"
            return (f"element beamColumnJoint {eid} {' '.join(map(str, ang))} "
                    f"{mat} {mat} {mat} {mat}")
        if sugg == "ShellMITC4":
            mat = getattr(prop, "mat_id", 1) or 1
            sez = getattr(prop, "sezione_id", 1) or 1
            thickness = getattr(getattr(prop, "geom", None), "get", lambda k, d=None: d)("spessore", 10.0) \
                if prop is not None else 10.0
            return f"element ShellMITC4 {eid} {' '.join(map(str, ang[:4]))} {mat} {thickness:g} {sez}"
        if sugg in ("TetGen4", "BRICK20", "solidBrick|tetgen"):
            mat = getattr(prop, "mat_id", 1) or 1
            return f"element {('TetGen4' if 'tet' in sugg.lower() or sugg=='solidBrick|tetgen' else sugg)} {eid} {' '.join(map(str, ang))} {mat}"
        if sugg == "node":
            return None  # i punti diventano soli nodi
        return None

    def riga_vincolo(self, nid: int, tipo: str) -> Optional[str]:
        v = (tipo or "").lower()
        if v == "fix":
            return f"fix {nid} 1 1 1 1 1 1"
        if v == "pin":
            return f"fix {nid} 0 0 0 1 1 1"
        if v == "roller":
            return f"fix {nid} 0 0 1 0 0 0"
        return None

    def build_script(self, fino_a: Optional[int] = None) -> str:
        lines = self.header()
        nodi = self.collect_nodes()
        props = {}
        cons = {}
        attivi = None
        if self.phases is not None and self.phases.phases:
            props = self.phases.merged_properties(fino_a)
            cons = self.phases.merged_constraints(fino_a)
            attivi = self.phases.active_entities(fino_a)
            lines += ["", "# ----- fasi -----"]
            for ph in sorted(self.phases.phases, key=lambda p: p.tag):
                mark = "" if ph.enabled else "  ;# (disattivata)"
                lines.append(f"# Fase {ph.tag}: {ph.nome}{mark}")

        lines += ["", "# ----- nodi -----"]
        for nid in sorted(nodi):
            lines.append(self.riga_node(nid, nodi[nid]))

        # materiali/sezioni usati dalle proprietà
        mats = sorted({p.mat_id for p in props.values() if p.mat_id}) or [1]
        sezs = sorted({p.sezione_id for p in props.values() if p.sezione_id}) or [1]
        lines += ["", "# ----- materiali -----"]
        lines += [self.riga_materiale(m) for m in mats]
        lines += ["", "# ----- sezioni -----"]
        lines += [self.riga_sezione(s) for s in sezs]

        lines += ["", "# ----- elementi -----"]
        for eid, etype, nodes in self.collect_elements():
            r = self.riga_elemento(eid, etype, nodes, props.get(eid))
            if r:
                lines.append(r)

        lines += ["", "# ----- vincoli -----"]
        for nid, tipo in sorted(cons.items()):
            r = self.riga_vincolo(nid, tipo)
            if r:
                lines.append(r)

        if self.phases is not None:
            pk = None
            for ph in sorted(self.phases.phases, key=lambda p: p.tag):
                if ph.solver_pack and ph.tag <= (fino_a or self.phases.current_tag):
                    pk = ph.solver_pack
            if pk:
                lines += ["", f"# ----- solutore: {pk.nome} -----"]
                lines += pk.comandi_opensees()

        lines += ["", "# fine script"]
        return "\n".join(lines) + "\n"

    def write(self, path: str, fino_a: Optional[int] = None) -> str:
        txt = self.build_script(fino_a)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(txt)
        return path
