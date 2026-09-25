"""Modulo di esportazione per OpenSees: nodi per gruppi e connectivity list.

Garantisce:
  1. Estrazione nodi in formato .txt per tutti i gruppi definiti (gruppi del documento e
     Physical Groups Gmsh).
  2. Esportazione della connectivity list con nodi ordinati secondo le convenzioni
     di OpenSees:
       - Elementi piani 2D (triangoli tri31, quadrilateri quad): ordine antiorario (CCW).
       - Elementi 3D (tetraedri FourNodeTetrahedron): volume del determinante Jacobiano positivo (V > 0).
       - Elementi 3D (esaedri stdBrick/SSPbrick): orientamento Jacobiano destrorso positivo.
  3. Coerenza rigorosa tra numero di nodi ed elementi (nessun nodo mancante,
     numero nodi per elemento congruente alla formulazione agli elementi finiti).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set, Tuple, Any

from .mesh import MeshModel, ELEM_INFO


#: Mappatura tipo Gmsh -> info OpenSees:
#: (nome_opensees, comando_opensees, n_nodi, dimensione, template_comando)
OPENSEES_ELEM_INFO: Dict[int, Tuple[str, str, int, int, str]] = {
    1: ("Truss", "element truss", 2, 1, "element truss {eid} {n1} {n2} $A $matTag"),
    2: ("tri31", "element tri31", 3, 2, "element tri31 {eid} {n1} {n2} {n3} $thick $type $matTag"),
    3: ("quad", "element quad", 4, 2, "element quad {eid} {n1} {n2} {n3} {n4} $thick $type $matTag"),
    4: ("FourNodeTetrahedron", "element FourNodeTetrahedron", 4, 3, "element FourNodeTetrahedron {eid} {n1} {n2} {n3} {n4} $matTag"),
    5: ("stdBrick", "element stdBrick", 8, 3, "element stdBrick {eid} {n1} {n2} {n3} {n4} {n5} {n6} {n7} {n8} $matTag"),
    6: ("Prism6", "element bbarBrick", 6, 3, "element bbarBrick {eid} {n1} {n2} {n3} {n4} {n5} {n6} $matTag"),
    11: ("TenNodeTetrahedron", "element TenNodeTetrahedron", 10, 3, "element TenNodeTetrahedron {eid} {n1} {n2} {n3} {n4} {n5} {n6} {n7} {n8} {n9} {n10} $matTag"),
}


# =============================================================================
# Algoritmi di orientamento nodi per OpenSees
# =============================================================================

def reorder_triangle_opensees(nodes: List[int],
                              coords: Dict[int, Tuple[float, float, float]]) -> Tuple[List[int], bool]:
    """Ordina i 3 nodi di un triangolo in senso antiorario (CCW).

    Ritorna (nodi_ordinati, invertito).
    """
    if len(nodes) < 3:
        return list(nodes), False
    p1 = coords.get(nodes[0])
    p2 = coords.get(nodes[1])
    p3 = coords.get(nodes[2])
    if not p1 or not p2 or not p3:
        return list(nodes), False

    # Vettori v12 e v13
    v12 = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    v13 = (p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2])

    # Prodotto vettoriale (normale alla superficie)
    nx = v12[1] * v13[2] - v12[2] * v13[1]
    ny = v12[2] * v13[0] - v12[0] * v13[2]
    nz = v12[0] * v13[1] - v12[1] * v13[0]

    # Trova il piano dominante (massima componente normale)
    anx, any_, anz = abs(nx), abs(ny), abs(nz)
    invert = False
    if anz >= anx and anz >= any_:
        # Proiezione piano XY: area con segno
        # Inverti se nz < 0
        if nz < 0:
            invert = True
    elif anx >= any_ and anx >= anz:
        # Proiezione piano YZ
        if nx < 0:
            invert = True
    else:
        # Proiezione piano ZX
        if ny < 0:
            invert = True

    if invert:
        # Inverti nodi 2 e 3 mantenendo il primo
        return [nodes[0], nodes[2], nodes[1]], True
    return list(nodes), False


def reorder_quad_opensees(nodes: List[int],
                          coords: Dict[int, Tuple[float, float, float]]) -> Tuple[List[int], bool]:
    """Ordina i 4 nodi di un quadrilatero in senso antiorario (CCW).

    Ritorna (nodi_ordinati, invertito).
    """
    if len(nodes) < 4:
        return list(nodes), False
    pts = [coords.get(nid) for nid in nodes[:4]]
    if any(p is None for p in pts):
        return list(nodes), False

    # Calcolo area poligonale proiettata su XY
    area2_z = 0.0
    for i in range(4):
        p_curr = pts[i]
        p_next = pts[(i + 1) % 4]
        area2_z += (p_curr[0] * p_next[1] - p_next[0] * p_curr[1])

    invert = False
    if abs(area2_z) > 1e-12:
        if area2_z < 0:
            invert = True
    else:
        # Fallback a normale 3D da diagonali (p3-p1) x (p4-p2)
        d13 = (pts[2][0] - pts[0][0], pts[2][1] - pts[0][1], pts[2][2] - pts[0][2])
        d24 = (pts[3][0] - pts[1][0], pts[3][1] - pts[1][1], pts[3][2] - pts[1][2])
        nz = d13[0] * d24[1] - d13[1] * d24[0]
        if nz < 0:
            invert = True

    if invert:
        # Inversione ciclica mantenendo il nodo 0: 0 -> 3 -> 2 -> 1
        return [nodes[0], nodes[3], nodes[2], nodes[1]], True
    return list(nodes), False


def reorder_tetrahedron_opensees(nodes: List[int],
                                 coords: Dict[int, Tuple[float, float, float]]) -> Tuple[List[int], bool]:
    """Garantisce volume positivo per FourNodeTetrahedron in OpenSees.

    OpenSees calcola V = 1/6 * ((P2 - P1) x (P3 - P1)) . (P4 - P1).
    Se V < 0, scambia i nodi 2 e 3 per rendere V > 0.
    Ritorna (nodi_ordinati, invertito).
    """
    if len(nodes) < 4:
        return list(nodes), False
    p1 = coords.get(nodes[0])
    p2 = coords.get(nodes[1])
    p3 = coords.get(nodes[2])
    p4 = coords.get(nodes[3])
    if not p1 or not p2 or not p3 or not p4:
        return list(nodes), False

    v12 = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    v13 = (p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2])
    v14 = (p4[0] - p1[0], p4[1] - p1[1], p4[2] - p1[2])

    # (v12 x v13)
    cx = v12[1] * v13[2] - v12[2] * v13[1]
    cy = v12[2] * v13[0] - v12[0] * v13[2]
    cz = v12[0] * v13[1] - v12[1] * v13[0]

    # Prodotto scalare con v14: 6 * Volume
    det = cx * v14[0] + cy * v14[1] + cz * v14[2]

    if det < 0:
        # Scambia nodo 2 e nodo 3
        return [nodes[0], nodes[2], nodes[1], nodes[3]] + list(nodes[4:]), True
    return list(nodes), False


def reorder_hexahedron_opensees(nodes: List[int],
                                coords: Dict[int, Tuple[float, float, float]]) -> Tuple[List[int], bool]:
    """Garantisce Jacobiano positivo per stdBrick/SSPbrick in OpenSees.

    Faccia inferiore: 1-2-3-4 CCW, faccia superiore: 5-6-7-8 CCW.
    Determinante Jacobiano a nodo 1: ((P2 - P1) x (P4 - P1)) . (P5 - P1) > 0.
    Se det < 0, inverte le facce scambiando 2<->4 e 6<->8.
    """
    if len(nodes) < 8:
        return list(nodes), False
    p1 = coords.get(nodes[0])
    p2 = coords.get(nodes[1])
    p4 = coords.get(nodes[3])
    p5 = coords.get(nodes[4])
    if not p1 or not p2 or not p4 or not p5:
        return list(nodes), False

    v12 = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    v14 = (p4[0] - p1[0], p4[1] - p1[1], p4[2] - p1[2])
    v15 = (p5[0] - p1[0], p5[1] - p1[1], p5[2] - p1[2])

    cx = v12[1] * v14[2] - v12[2] * v14[1]
    cy = v12[2] * v14[0] - v12[0] * v14[2]
    cz = v12[0] * v14[1] - v12[1] * v14[0]

    det = cx * v15[0] + cy * v15[1] + cz * v15[2]
    if det < 0:
        # Scambia 2 con 4 e 6 con 8
        reordered = [nodes[0], nodes[3], nodes[2], nodes[1],
                     nodes[4], nodes[7], nodes[6], nodes[5]] + list(nodes[8:])
        return reordered, True
    return list(nodes), False


def reorder_element_nodes_for_opensees(etype: int, nodes: List[int],
                                       coords: Dict[int, Tuple[float, float, float]]) -> Tuple[List[int], bool]:
    """Ordina i nodi di un qualsiasi elemento secondo le convenzioni OpenSees."""
    if etype == 2:  # Triangolo 3 nodi
        return reorder_triangle_opensees(nodes, coords)
    elif etype == 3:  # Quadrilatero 4 nodi
        return reorder_quad_opensees(nodes, coords)
    elif etype == 4:  # Tetraedro 4 nodi
        return reorder_tetrahedron_opensees(nodes, coords)
    elif etype == 5:  # Esaedro 8 nodi
        return reorder_hexahedron_opensees(nodes, coords)
    elif etype == 11:  # Tetraedro 10 nodi
        # Riordina i primi 4 nodi angolari
        t4, inv = reorder_tetrahedron_opensees(nodes[:4], coords)
        if inv and len(nodes) >= 10:
            # Se scambiati 1 e 2 (indice 1 e 2 nella lista), i nodi di bordo si aggiornano:
            # bordi: 5(1-2), 6(2-3), 7(3-1), 8(1-4), 9(2-4), 10(3-4)
            # scambiando p2 e p3: 5 e 7 si scambiano, 9 e 10 si scambiano
            mid = [nodes[6], nodes[5], nodes[4], nodes[7], nodes[9], nodes[8]]
            return t4 + mid + list(nodes[10:]), True
        return list(nodes), False
    return list(nodes), False


# =============================================================================
# Verifica di coerenza topologica tra nodi ed elementi
# =============================================================================

def verify_mesh_coherence(model: MeshModel) -> Dict[str, Any]:
    """Verifica approfondita di coerenza tra elementi e nodi del modello mesh.

    Controlla:
      - Che tutti i nodi referenziati dagli elementi esistano nel dizionario nodi.
      - Che ogni tipo di elemento abbia il numero esatto di nodi attesi.
      - Quanti elementi richiedono correzione orientamento per OpenSees.
    """
    all_nodes = set(model.nodes.keys())
    used_nodes: Set[int] = set()
    missing_nodes: Set[int] = set()
    mismatched_elements: List[Tuple[int, int, int, int]] = []
    type_counts: Dict[str, int] = {}
    reoriented_count = 0

    for eid, (etype, nodi) in model.elements.items():
        info = ELEM_INFO.get(etype)
        expected_nodes = info[1] if info else None
        tname = info[0] if info else f"tipo_{etype}"
        type_counts[tname] = type_counts.get(tname, 0) + 1

        if expected_nodes is not None and len(nodi) != expected_nodes:
            mismatched_elements.append((eid, etype, len(nodi), expected_nodes))

        for nid in nodi:
            if nid in all_nodes:
                used_nodes.add(nid)
            else:
                missing_nodes.add(nid)

        _, inv = reorder_element_nodes_for_opensees(etype, nodi, model.nodes)
        if inv:
            reoriented_count += 1

    orphaned = all_nodes - used_nodes
    is_valid = (len(missing_nodes) == 0 and len(mismatched_elements) == 0)

    return {
        "valid": is_valid,
        "total_nodes": len(all_nodes),
        "total_elements": len(model.elements),
        "referenced_nodes_count": len(used_nodes),
        "missing_nodes_count": len(missing_nodes),
        "missing_nodes": sorted(list(missing_nodes)),
        "orphaned_nodes_count": len(orphaned),
        "orphaned_nodes": sorted(list(orphaned)),
        "mismatched_elements_count": len(mismatched_elements),
        "mismatched_elements": mismatched_elements,
        "reoriented_count": reoriented_count,
        "element_type_counts": type_counts,
    }


# =============================================================================
# Estrazione nodi per gruppi definiti (documento e fisici Gmsh)
# =============================================================================

def extract_defined_groups_nodes(doc, model: Optional[MeshModel] = None) -> Dict[str, Dict[str, Any]]:
    """Estrae i nodi per tutti i gruppi definiti nel documento o nel modello mesh.

    Considera:
      1. Gruppi creati in doc.groups (EntityGroup), risolvendo nodi espliciti,
         nodi di elementi mesh appartenenti al gruppo, o blocchi mesh collegati.
      2. Physical Groups definiti nei blocchi della mesh Gmsh (es. lato_fisso, fondazione...).
      3. Gruppo speciale 'Tutti_i_Nodi' contenente l'insieme completo dei nodi della mesh.

    Ritorna: {nome_gruppo: {'name': str, 'node_ids': List[int], 'element_ids': List[int], 'source': str}}
    """
    out: Dict[str, Dict[str, Any]] = {}

    # Seleziona il modello mesh attivo se non fornito
    if model is None:
        if getattr(doc, "mesh_models", None):
            # Prendi il primo o l'ultimo importato
            model = list(doc.mesh_models.values())[-1]

    all_model_nodes = set(model.nodes.keys()) if model else set()

    # 1. Physical Groups dal MeshModel
    if model is not None:
        for (dim, tag), blk in model.blocks.items():
            if not blk.element_ids:
                continue
            phys_tags = blk.physical_tags
            if not phys_tags:
                nome_base = blk.nome
                nomi = [nome_base]
            else:
                nomi = [model.physicals.get((dim, pt), f"Physical_{dim}D_{pt}") for pt in phys_tags]

            blk_nodes: Set[int] = set()
            for eid in blk.element_ids:
                el = model.elements.get(eid)
                if el:
                    blk_nodes.update(el[1])

            for nome in nomi:
                entry = out.setdefault(nome, {
                    "name": nome,
                    "node_ids": set(),
                    "element_ids": set(),
                    "source": "physical_group"
                })
                entry["node_ids"].update(blk_nodes)
                entry["element_ids"].update(blk.element_ids)

    # 2. Gruppi da doc.groups
    if getattr(doc, "groups", None) and hasattr(doc.groups, "groups"):
        for gname, g in doc.groups.groups.items():
            g_nodes: Set[int] = set()
            g_elems: Set[int] = set()

            # Nodi espliciti
            for mod_name, nids in g.mesh_nodes.items():
                g_nodes.update(nids)

            # Nodi da elementi mesh del gruppo
            for mod_name, eids in g.mesh_elements.items():
                g_elems.update(eids)
                m = doc.mesh_models.get(mod_name) if hasattr(doc, "mesh_models") else None
                if m is None and model is not None and model.name == mod_name:
                    m = model
                if m is not None:
                    for eid in eids:
                        el = m.elements.get(eid)
                        if el:
                            g_nodes.update(el[1])

            # Nodi da entità CAD/mesh associate (member_ids)
            for eid in g.member_ids:
                ent = doc.entities.get(eid)
                if ent and "mesh_ref" in ent.meta:
                    mname, dim, tag = ent.meta["mesh_ref"]
                    m = doc.mesh_models.get(mname, model)
                    if m is not None:
                        blk = m.blocks.get((dim, tag))
                        if blk:
                            g_elems.update(blk.element_ids)
                            for bel_id in blk.element_ids:
                                el = m.elements.get(bel_id)
                                if el:
                                    g_nodes.update(el[1])

            if g_nodes or g_elems or not g.empty():
                entry = out.setdefault(gname, {
                    "name": gname,
                    "node_ids": set(),
                    "element_ids": set(),
                    "source": "document_group"
                })
                entry["node_ids"].update(g_nodes)
                entry["element_ids"].update(g_elems)

    # 3. Gruppo master con tutti i nodi
    if all_model_nodes:
        out["Tutti_i_Nodi"] = {
            "name": "Tutti_i_Nodi",
            "node_ids": all_model_nodes,
            "element_ids": set(model.elements.keys()) if model else set(),
            "source": "all_mesh"
        }

    # Converti insiemi in liste ordinate
    res: Dict[str, Dict[str, Any]] = {}
    for name, data in out.items():
        res[name] = {
            "name": name,
            "node_ids": sorted(list(data["node_ids"])),
            "element_ids": sorted(list(data["element_ids"])),
            "source": data["source"]
        }
    return res


# =============================================================================
# Formattazione esportazioni testo (.txt) per OpenSees
# =============================================================================

def format_group_nodes_txt(group_name: str, node_ids: List[int],
                           coords: Dict[int, Tuple[float, float, float]],
                           include_opensees_cmds: bool = True) -> str:
    """Formatta i nodi di un gruppo in testo chiaro (.txt) per OpenSees."""
    lines = [
        "#" + "=" * 78,
        f"# GmshCAD Studio — Esportazione Nodi Gruppo: {group_name}",
        f"# Nodi totali nel gruppo: {len(node_ids)}",
        "#" + "=" * 78,
        "#",
        "# SEZIONE 1: TABELLA COORDINATE NODI",
        "# Formato: ID_NODO        X                 Y                 Z",
        "#" + "-" * 78,
    ]
    for nid in node_ids:
        c = coords.get(nid, (0.0, 0.0, 0.0))
        lines.append(f"{nid:<10}  {c[0]:<18.10g}  {c[1]:<18.10g}  {c[2]:<18.10g}")

    if include_opensees_cmds:
        lines += [
            "#",
            "#" + "-" * 78,
            "# SEZIONE 2: COMANDI SINTASSI OPENSEES",
            "# Sintassi: node $nodeTag $x $y $z",
            "#" + "-" * 78,
        ]
        for nid in node_ids:
            c = coords.get(nid, (0.0, 0.0, 0.0))
            lines.append(f"node {nid} {c[0]:.10g} {c[1]:.10g} {c[2]:.10g}")

    lines.append("")
    return "\n".join(lines)


def format_all_groups_nodes_txt(groups_data: Dict[str, Dict[str, Any]],
                                coords: Dict[int, Tuple[float, float, float]]) -> str:
    """Genera un unico documento .txt consolidato con tutti i gruppi e i loro nodi."""
    header = [
        "#" + "=" * 78,
        "# GmshCAD Studio — Esportazione Nodi per Tutti i Gruppi Definiti",
        f"# Numero di gruppi esportati: {len(groups_data)}",
        "#" + "=" * 78,
        "",
    ]
    parts = ["\n".join(header)]
    for gname, data in sorted(groups_data.items()):
        parts.append(format_group_nodes_txt(gname, data["node_ids"], coords, include_opensees_cmds=True))
    return "\n".join(parts)


def format_connectivity_txt(model: MeshModel, opensees_syntax: bool = True) -> str:
    """Formatta la lista di connettività degli elementi per OpenSees.

    Verifica e corregge l'ordine dei nodi:
      - Elementi 2D (tri, quad) -> CCW
      - Elementi 3D (tet, hex) -> Jacobiano/Volume positivo
    Garantisce la perfetta corrispondenza e coerenza con i nodi.
    """
    coherence = verify_mesh_coherence(model)
    righe = [
        "#" + "=" * 78,
        "# GmshCAD Studio — OpenSees Element Connectivity List",
        f"# Modello: {model.name}",
        f"# Elementi totali: {len(model.elements)} | Nodi unici utilizzati: {coherence['referenced_nodes_count']}",
        f"# Coerenza topologica: {'VALIDA (OK)' if coherence['valid'] else 'ATTENZIONE: verificare nodi'}",
        f"# Nodi corretti per OpenSees (orientamento CCW / V>0): {coherence['reoriented_count']}",
        "#",
        "# Riepilogo tipi elemento:",
    ]
    for tname, cnt in sorted(coherence["element_type_counts"].items()):
        righe.append(f"#   - {tname}: {cnt} elementi")
    righe += [
        "#" + "=" * 78,
        "",
        "# SEZIONE 1: TABELLA GENERALE DI CONNETTIVITÀ",
        "# Formato: ID_ELEMENTO  TIPO_GMSH  NUM_NODI  NODO_1  NODO_2  NODO_3 ...",
        "#" + "-" * 78,
    ]

    elements_by_type: Dict[int, List[Tuple[int, List[int]]]] = {}

    for eid in sorted(model.elements.keys()):
        etype, raw_nodes = model.elements[eid]
        # Ordina nodi secondo OpenSees
        ordered_nodes, _ = reorder_element_nodes_for_opensees(etype, raw_nodes, model.nodes)
        elements_by_type.setdefault(etype, []).append((eid, ordered_nodes))

        nodi_str = "  ".join(str(n) for n in ordered_nodes)
        righe.append(f"{eid:<8}  {etype:<4}  {len(ordered_nodes):<3}  {nodi_str}")

    if opensees_syntax:
        righe += [
            "",
            "#" + "=" * 78,
            "# SEZIONE 2: DICHIARAZIONE ELEMENTI IN SINTASSI OPENSEES",
            "# Tutti i nodi sono ordinati rigorosamente secondo la formulazione OpenSees",
            "#" + "=" * 78,
        ]

        # 1. Tetraedri 3D (FourNodeTetrahedron)
        tets = elements_by_type.get(4, [])
        if tets:
            righe += [
                "",
                "# --- 3D Solid: FourNodeTetrahedron (Volume > 0 verificato) ---",
                "# Sintassi: element FourNodeTetrahedron $eleTag $node1 $node2 $node3 $node4 $matTag",
                "#" + "-" * 78,
            ]
            for eid, nodi in tets:
                righe.append(f"element FourNodeTetrahedron {eid} {nodi[0]} {nodi[1]} {nodi[2]} {nodi[3]} $matTag")

        # 2. Esaedri 3D (stdBrick)
        bricks = elements_by_type.get(5, [])
        if bricks:
            righe += [
                "",
                "# --- 3D Solid: stdBrick / SSPbrick (Jacobiano > 0 verificato) ---",
                "# Sintassi: element stdBrick $eleTag $n1 $n2 $n3 $n4 $n5 $n6 $n7 $n8 $matTag",
                "#" + "-" * 78,
            ]
            for eid, nodi in bricks:
                n_str = " ".join(str(n) for n in nodi[:8])
                righe.append(f"element stdBrick {eid} {n_str} $matTag")

        # 3. Triangoli 2D (tri31)
        tris = elements_by_type.get(2, [])
        if tris:
            righe += [
                "",
                "# --- 2D Planar: tri31 (Senso Antiorario CCW verificato) ---",
                "# Sintassi: element tri31 $eleTag $iNode $jNode $kNode $thick $type $matTag",
                "#" + "-" * 78,
            ]
            for eid, nodi in tris:
                righe.append(f"element tri31 {eid} {nodi[0]} {nodi[1]} {nodi[2]} $thick $type $matTag")

        # 4. Quadrilateri 2D (quad)
        quads = elements_by_type.get(3, [])
        if quads:
            righe += [
                "",
                "# --- 2D Planar: quad / SSPquad / bbarQuad (Senso Antiorario CCW verificato) ---",
                "# Sintassi: element quad $eleTag $iNode $jNode $kNode $lNode $thick $type $matTag",
                "#" + "-" * 78,
            ]
            for eid, nodi in quads:
                righe.append(f"element quad {eid} {nodi[0]} {nodi[1]} {nodi[2]} {nodi[3]} $thick $type $matTag")

        # 5. Barre/Travi 1D (Truss)
        lines = elements_by_type.get(1, [])
        if lines:
            righe += [
                "",
                "# --- 1D Line: truss ---",
                "# Sintassi: element truss $eleTag $iNode $jNode $A $matTag",
                "#" + "-" * 78,
            ]
            for eid, nodi in lines:
                righe.append(f"element truss {eid} {nodi[0]} {nodi[1]} $A $matTag")

    righe.append("")
    return "\n".join(righe)


# =============================================================================
# Funzioni operative di esportazione su disco
# =============================================================================

def export_nodes_by_group(out_path: str, doc, model: Optional[MeshModel] = None,
                          separate_files: bool = False) -> List[str]:
    """Esporta i nodi per tutti i gruppi definiti in file .txt.

    Se separate_files è True (o se out_path è una cartella), crea un file .txt
    per ciascun gruppo nella cartella (es. 'nodi_lato_fisso.txt').
    Altrimenti scrive un file unico strutturato.
    """
    if model is None and getattr(doc, "mesh_models", None):
        model = list(doc.mesh_models.values())[-1]

    if model is None:
        raise ValueError("Nessun modello mesh disponibile per l'estrazione dei nodi.")

    groups_data = extract_defined_groups_nodes(doc, model)
    written_files: List[str] = []

    if separate_files or os.path.isdir(out_path) or not os.path.splitext(out_path)[1]:
        target_dir = out_path if (not os.path.splitext(out_path)[1] or os.path.isdir(out_path)) else (os.path.dirname(out_path) or ".")
        os.makedirs(target_dir, exist_ok=True)
        # Esporta ogni gruppo singolarmente
        for gname, data in groups_data.items():
            safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in gname)
            filename = f"nodi_{safe_name}.txt"
            filepath = os.path.join(target_dir, filename)
            content = format_group_nodes_txt(gname, data["node_ids"], model.nodes, include_opensees_cmds=True)
            with open(filepath, "w", encoding="utf-8") as fh:
                fh.write(content)
            written_files.append(filepath)

        # File master consolidato
        master_path = os.path.join(target_dir, "tutti_i_gruppi_nodi.txt")
        with open(master_path, "w", encoding="utf-8") as fh:
            fh.write(format_all_groups_nodes_txt(groups_data, model.nodes))
        written_files.append(master_path)
    else:
        # File unico consolidato
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        content = format_all_groups_nodes_txt(groups_data, model.nodes)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        written_files.append(out_path)

    return written_files


def export_connectivity_list(out_path: str, model: MeshModel) -> str:
    """Esporta la connectivity list coerente in formato .txt per OpenSees."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    content = format_connectivity_txt(model, opensees_syntax=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return out_path


def export_opensees_bundle(output_dir: str, doc, model: Optional[MeshModel] = None) -> Dict[str, str]:
    """Pacchetto completo di esportazione per OpenSees:

    - nodi_gruppi.txt: nodi suddivisi per ciascun gruppo definito.
    - connectivity_list.txt: connettività coerente (2D CCW e 3D V>0).
    - Cartella nodi_singoli/ con un file .txt per ciascun gruppo.
    - template_opensees.tcl: script pronto con tutti i nodi ed elementi.
    """
    if model is None and getattr(doc, "mesh_models", None):
        model = list(doc.mesh_models.values())[-1]

    if model is None:
        raise ValueError("Nessun modello mesh disponibile per l'esportazione OpenSees.")

    os.makedirs(output_dir, exist_ok=True)
    results: Dict[str, str] = {}

    # 1. Connettività elementi
    conn_path = os.path.join(output_dir, "connectivity_list.txt")
    export_connectivity_list(conn_path, model)
    results["connectivity"] = conn_path

    # 2. Nodi per gruppi (consolidato)
    nodes_all_path = os.path.join(output_dir, "nodi_tutti_i_gruppi.txt")
    export_nodes_by_group(nodes_all_path, doc, model, separate_files=False)
    results["nodes_consolidated"] = nodes_all_path

    # 3. File singoli per gruppo
    sub_dir = os.path.join(output_dir, "nodi_per_gruppo")
    single_files = export_nodes_by_group(sub_dir, doc, model, separate_files=True)
    results["nodes_dir"] = sub_dir

    # 4. Script OpenSees .tcl completo (con vincoli, carichi e fasi di calcolo)
    tcl_path = os.path.join(output_dir, "modello_opensees.tcl")
    if hasattr(doc, "opensees") and doc.opensees is not None:
        tcl_content = doc.opensees.generate_tcl_script(model)
    else:
        groups_data = extract_defined_groups_nodes(doc, model)
        tcl_lines = [
            "# ==============================================================================",
            "# OpenSees Model Script generato da GmshCAD Studio",
            f"# Modello: {model.name}",
            "# ==============================================================================",
            "wipe;",
            "model BasicBuilder -ndm 3 -ndf 3;",
            "",
            "# ------------------------------------------------------------------------------",
            "# DEFINIZIONE NODI",
            "# ------------------------------------------------------------------------------",
        ]
        for nid in sorted(model.nodes.keys()):
            c = model.nodes[nid]
            tcl_lines.append(f"node {nid} {c[0]:.10g} {c[1]:.10g} {c[2]:.10g};")

        tcl_lines += [
            "",
            "# ------------------------------------------------------------------------------",
            "# GRUPPI DI VINCOLO E CARICO (ID Nodi)",
            "# ------------------------------------------------------------------------------",
        ]
        for gname, data in sorted(groups_data.items()):
            if gname == "Tutti_i_Nodi":
                continue
            nids_str = " ".join(str(n) for n in data["node_ids"])
            safe_var = "".join(c if c.isalnum() else "_" for c in gname)
            tcl_lines.append(f"# Gruppo '{gname}' ({len(data['node_ids'])} nodi):")
            tcl_lines.append(f"set group_{safe_var} [list {nids_str}];")
            tcl_lines.append(f"# Esempio vincolo: foreach n $group_{safe_var} {{ fix $n 1 1 1; }}")

        tcl_lines += [
            "",
            "# ------------------------------------------------------------------------------",
            "# DEFINIZIONE ELEMENTI (Connettività verificata)",
            "# ------------------------------------------------------------------------------",
            "set matTag 1; # Definire il materiale prima degli elementi",
        ]
        for eid in sorted(model.elements.keys()):
            etype, raw_nodes = model.elements[eid]
            ordered, _ = reorder_element_nodes_for_opensees(etype, raw_nodes, model.nodes)
            if etype == 4:
                tcl_lines.append(f"element FourNodeTetrahedron {eid} {ordered[0]} {ordered[1]} {ordered[2]} {ordered[3]} $matTag;")
            elif etype == 5:
                n_str = " ".join(str(n) for n in ordered[:8])
                tcl_lines.append(f"element stdBrick {eid} {n_str} $matTag;")
            elif etype == 2:
                tcl_lines.append(f"element tri31 {eid} {ordered[0]} {ordered[1]} {ordered[2]} 1.0 \"PlaneStress\" $matTag;")
            elif etype == 3:
                tcl_lines.append(f"element quad {eid} {ordered[0]} {ordered[1]} {ordered[2]} {ordered[3]} 1.0 \"PlaneStress\" $matTag;")
        tcl_content = "\n".join(tcl_lines) + "\n"

    with open(tcl_path, "w", encoding="utf-8") as fh:
        fh.write(tcl_content)
    results["tcl_script"] = tcl_path

    return results
