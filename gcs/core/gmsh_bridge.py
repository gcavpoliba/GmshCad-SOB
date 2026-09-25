"""Integrazione completa con Gmsh tramite la sua API Python.

Funzionalità:
  * :func:`mesh_step` / :func:`mesh_brep` — meshing **embedded** di modelli
    creati in modalità Geometria (export STEP/BREP -> mesh -> file .msh);
  * :func:`import_msh_gmsh` — lettura di .msh **binari** o di versioni non
    supportate dal parser ASCII interno;
  * :func:`write_geo_template` — template ``.geo`` pronto per Gmsh;
  * :func:`export_msh_22` — scrittura .msh 2.2 ASCII da un MeshModel,
    con **gruppi fisici** derivati dai gruppi del documento.

Il modulo funziona anche senza ``gmsh`` installato (le funzioni che lo
richiedono segnalano l'errore con messaggio chiaro).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from .mesh import MeshModel, MeshBlock, corner_nodes


#: algoritmi 3D di gmsh (Mesh.Algorithm3D è un'opzione intera)
ALGO3D = {"delaunay": 1, "newdelaunay": 4, "initial": 2, "delquad": 3,
          "frontal": 6, "mmg3d": 7, "rtree": 9, "hxt": 10}


def _algo3d_number(algo3d) -> Optional[int]:
    """Converte il nome dell'algoritmo 3D nel codice numerico gmsh."""
    if algo3d is None or algo3d == "":
        return None
    if isinstance(algo3d, int):
        return algo3d
    chiave = str(algo3d).strip().lower()
    if chiave.isdigit():
        return int(chiave)
    return ALGO3D.get(chiave, 10)


def _require_gmsh():
    try:
        import gmsh  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Pacchetto gmsh non installato. Installare con: pip install gmsh"
        ) from exc
    import gmsh
    return gmsh


# ---------------------------------------------------------------------------
# meshing embedded
# ---------------------------------------------------------------------------

def mesh_step(step_path: str, out_msh: str, clmax: float = 5.0, clmin: float = 0.0,
              order: int = 1, algo3d: str = "HXT", msh_version: str = "4.1",
              save_physicals: bool = True) -> dict:
    """Genera la mesh di un file STEP e salva un .msh. Ritorna statistiche."""
    gmsh = _require_gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.model.occ.importShapes(str(step_path))
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", float(clmin))
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", float(clmax))
        gmsh.option.setNumber("Mesh.ElementOrder", int(order))
        if algo3d:
            gmsh.option.setNumber("Mesh.Algorithm3D", _algo3d_number(algo3d))
        gmsh.model.mesh.generate(3)
        _write_msh(gmsh, out_msh, msh_version, save_physicals)
        return _mesh_stats(gmsh)
    finally:
        gmsh.finalize()


def mesh_brep(brep_path: str, out_msh: str, clmax: float = 5.0, clmin: float = 0.0,
              order: int = 1, algo3d: str = "HXT",
              msh_version: str = "4.1") -> dict:
    gmsh = _require_gmsh()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.model.occ.importShapes(str(brep_path))
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", float(clmin))
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", float(clmax))
        gmsh.option.setNumber("Mesh.ElementOrder", int(order))
        if algo3d:
            gmsh.option.setNumber("Mesh.Algorithm3D", _algo3d_number(algo3d))
        gmsh.model.mesh.generate(3)
        _write_msh(gmsh, out_msh, msh_version, True)
        return _mesh_stats(gmsh)
    finally:
        gmsh.finalize()


def _write_msh(gmsh, out_msh: str, msh_version: str, save_physicals: bool) -> None:
    gmsh.option.setNumber("Mesh.SaveAll", 0 if save_physicals else 1)
    gmsh.option.setNumber("Mesh.Binary", 0)
    if msh_version:
        try:
            gmsh.option.setNumber("Mesh.MshFileVersion", float(str(msh_version)[:3]))
        except Exception:
            pass
    gmsh.write(str(out_msh))


def _mesh_stats(gmsh) -> dict:
    tipi, conteggi = gmsh.model.mesh.getElementCounts() if hasattr(
        gmsh.model.mesh, "getElementCounts") else ([], [])
    return {
        "nodi": gmsh.model.mesh.getNodes()[0].size if hasattr(
            gmsh.model.mesh.getNodes()[0], "size") else len(gmsh.model.mesh.getNodes()[0]),
        "conteggi_tipi": dict(zip(tipi, conteggi)),
    }


# ---------------------------------------------------------------------------
# import .msh via API gmsh (binario, versioni varie)
# ---------------------------------------------------------------------------

def import_msh_gmsh(path: str, nome: Optional[str] = None) -> MeshModel:
    """Lettura robusta di qualunque .msh (anche binario) tramite API gmsh."""
    gmsh = _require_gmsh()
    gmsh.initialize()
    model = MeshModel(nome or os.path.splitext(os.path.basename(path))[0], path)
    try:
        gmsh.open(str(path))
        # nodi
        tags, coords, _ = gmsh.model.mesh.getNodes()
        for t, c in zip(tags, coords.reshape(-1, 3)):
            model.add_node(int(t), float(c[0]), float(c[1]), float(c[2]))
        # gruppi fisici
        for dim, tag in gmsh.model.getPhysicalGroups():
            nome_p = gmsh.model.getPhysicalName(dim, tag) or f"Phys{tag}"
            model.add_physical(dim, tag, nome_p)
        # blocchi entità: itera sulle entità del modello
        for dim, tag in gmsh.model.getEntities():
            etipi, etags, enodi = gmsh.model.mesh.getElements(dim, tag)
            if not etags:
                continue
            blk_phys = [int(p) for p in gmsh.model.getPhysicalGroupsForEntity(dim, tag)]
            for etype, etag_list, enode_list in zip(etipi, etags, enodi):
                nper = _nnodi_gmsh(etype, enode_list, etag_list)
                blk = model.blocks.setdefault((dim, tag), MeshBlock(dim, tag))
                for pt in blk_phys:
                    if pt not in blk.physical_tags:
                        blk.physical_tags.append(pt)
                for i, et in enumerate(etag_list):
                    nodi = enode_list[i * nper:(i + 1) * nper].tolist()
                    model.add_element(int(et), int(etype), nodi, (dim, tag))
    finally:
        gmsh.finalize()
    return model


def _nnodi_gmsh(etype, enode_list, etag_list) -> int:
    try:
        from gmsh import getElementTypeInfo
        _, _, nper, _, _ = getElementTypeInfo(etype)
        return int(nper)
    except Exception:
        n_el = len(etag_list)
        return len(enode_list) // max(1, n_el)


# ---------------------------------------------------------------------------
# template .geo
# ---------------------------------------------------------------------------

def write_geo_template(step_path: str, out_geo: str, clmax: float = 5.0,
                       clmin: float = 0.0, order: int = 1,
                       physicals: Optional[Dict[str, str]] = None,
                       commenti: str = "") -> None:
    """Scrive un template ``.geo`` che importa la geometria e imposta i parametri.

    I gruppi del documento possono essere riportati come commenti con le
    bounding box per facilitare l'assegnazione dei Physical Groups.
    """
    righe = [
        f'// Template .geo generato da GmshCAD Studio — {os.path.basename(step_path)}',
        f'// {commenti}' if commenti else '',
        'SetFactory("OpenCASCADE");',
        f'Merge "{os.path.basename(step_path)}";',
        '',
        f'Mesh.CharacteristicLengthMin = {float(clmin):g};',
        f'Mesh.CharacteristicLengthMax = {float(clmax):g};',
        f'Mesh.ElementOrder = {int(order)};',
        'Mesh.Algorithm3D = 10;   // HXT (parallelo); 1=Delaunay',
        'Mesh.Optimize = 1;',
        '',
    ]
    if physicals:
        righe.append('// Gruppi del documento (da assegnare ai tag reali di gmsh:')
        righe.append('//   vedi Tools > Options, o usa Surface{...} / Volume{...}):')
        for nome, suggerimento in physicals.items():
            righe.append(f'// {nome} -> {suggerimento}')
        righe.append('')
    righe += [
        '// Esempi di definizione gruppi fisici:',
        '// Physical Surface("carico") = {1};',
        '// Physical Volume("struttura") = {1};',
        '',
        '// Generazione mesh:',
        '// Mesh 3;',
        '// Save "modello.msh";',
        '',
    ]
    with open(out_geo, "w", encoding="utf-8") as fh:
        fh.write("\n".join(righe))


# ---------------------------------------------------------------------------
# export .msh 2.2 ASCII da MeshModel (con gruppi fisici)
# ---------------------------------------------------------------------------

def export_msh_22(model: MeshModel, path: str,
                  fisici: Optional[Dict[Tuple[int, int], Tuple[int, str]]] = None) -> None:
    """Scrive un file ``.msh`` versione 2.2 ASCII dal MeshModel.

    ``fisici`` mappa blocchi ``(dim, tag)`` -> ``(tag_fisico, nome)``:
    se assente, usa i gruppi fisici già presenti nel modello.
    """
    # raccogli nodi ed elementi usati
    el_ids = sorted(model.elements)
    usati = model.nodes_of_elements(el_ids) if el_ids else set(model.nodes)
    nodi = sorted(usati)

    # assegna tag fisici
    fis: Dict[Tuple[int, int], int] = {}
    nomi: Dict[Tuple[int, int, str], None] = {}   # (dim, tag_fisico, nome)
    if fisici is None:
        for (dim, tag), blk in model.blocks.items():
            for pt in blk.physical_tags:
                fis[(dim, tag)] = pt
                nome = model.physicals.get((dim, pt), f"phys{pt}")
                nomi[(dim, pt, nome)] = None
    else:
        for (dim, tag), (pt, nome) in fisici.items():
            fis[(dim, tag)] = pt
            nomi[(dim, pt, nome)] = None

    # rinumera nodi in modo compatto
    renum = {n: i + 1 for i, n in enumerate(nodi)}

    righe = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat"]
    if nomi:
        righe.append("$PhysicalNames")
        righe.append(str(len(nomi)))
        for (dim, pt, nome) in nomi:
            righe.append(f'{dim} {pt} "{nome}"')
        righe.append("$EndPhysicalNames")
    righe.append("$Nodes")
    righe.append(str(len(nodi)))
    for n in nodi:
        x, y, z = model.nodes[n]
        righe.append(f"{renum[n]} {x:.10g} {y:.10g} {z:.10g}")
    righe.append("$EndNodes")

    righe.append("$Elements")
    righe.append(str(len(el_ids)))
    for eid in el_ids:
        etype, nodi_el = model.elements[eid]
        blk = model.block_of_element(eid)
        fisico = fis.get(blk, 0) if blk else 0
        entita = blk[1] if blk else 0
        nodi_compatti = " ".join(str(renum[n]) for n in nodi_el if n in renum)
        righe.append(f"{eid} {etype} 2 {fisico} {entita} {nodi_compatti}")
    righe.append("$EndElements")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(righe) + "\n")
