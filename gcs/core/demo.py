"""Demo end-to-end headless: ``python main.py --demo``.

Percorso completo senza GUI:
  1. modalità Geometria: crea una staffa (L-bracket) con fori, raccordi,
     la esporta in STEP + template .geo;
  2. Gmsh: genera la mesh (API embedded) e la salva in .msh;
  3. modalità Mesh: reimporta il .msh, esegue selezioni per regione/tipo/
     normale, crea gruppi, espande/riduce la selezione;
  4. Macro: applica macro di esempio su punti/superfici/nodi;
  5. esporta gruppi e la mesh marcata, stampando un report completo.
"""

from __future__ import annotations

import os
import random
import sys


def _log(msg: str) -> None:
    print(msg, flush=True)


def run_demo(cartella_out: str) -> int:
    os.makedirs(cartella_out, exist_ok=True)
    from gcs.core.document import CADDocument
    from gcs.core.builder import GeometryBuilder
    from gcs.core.editors import GeometryEditor
    from gcs.core import selectors as sel
    from gcs.core import gmsh_bridge as gb
    from gcs.core.macro_engine import MacroEngine

    doc = CADDocument("Demo")
    from gcs.core import occ_utils as ou
    builder = GeometryBuilder(doc)
    editor = GeometryEditor(doc)
    _log("=" * 66)
    _log(" GMSHCAD STUDIO — DEMO END-TO-END (headless)")
    _log("=" * 66)

    # ---------------------------------------------------------------- 1) build
    _log("\n[1] MODALITÀ GEOMETRIA — creazione staffa con fori")
    base = builder.box(80, 30, 12, base=(0, 0, 0), name="Base")
    ala = builder.box(12, 30, 60, base=(0, 0, 12), name="Ala")
    fusa = editor.fusa([base.id, ala.id], mantieni=True)
    _log(f"    fusione -> {fusa.name} (volume {ou.volume_of(fusa.shape):.0f} mm³)")
    foro1 = builder.cilindro(4, 40, base=(20, -5, -5), axis=(0, 0, 1), name="Foro1")
    foro2 = builder.cilindro(4, 40, base=(50, -5, -5), axis=(0, 0, 1), name="Foro2")
    staffa1 = editor.taglia(fusa.id, foro1.id, mantieni=True)
    staffa = editor.taglia(staffa1.id, foro2.id, mantieni=True)
    editor.elimina([fusa.id, foro1.id, foro2.id, staffa1.id])
    # raccordo solo sugli spigoli concavi di giunzione (z=12): filantropia
    # selettiva, i bordi dei fori restano netti
    spigoli_giunzione = []
    for e in ou.unique_subshapes(staffa.shape, ou.TopAbs_EDGE):
        bb = ou.bbox_of(e)
        # concavi di giunzione: linea a z=12, interamente sotto l'ala (x<=12)
        if abs(bb[2] - 12) < 1e-6 and abs(bb[5] - 12) < 1e-6 \
                and ou.edge_is_line(e) and bb[3] <= 12 + 1e-6:
            spigoli_giunzione.append(e)
    nuovo = ou.fillet_edges(staffa.shape, spigoli_giunzione, 2.0)
    doc.replace_entity_shape(staffa, nuovo)
    _log(f"    staffa finita: {staffa.name}, fori + raccordo r=2 su "
         f"{len(spigoli_giunzione)} spigoli di giunzione")
    step_path = os.path.join(cartella_out, "staffa.step")
    doc.export_step(step_path)
    _log(f"    export STEP -> {step_path}")
    geo_path = os.path.join(cartella_out, "staffa.geo")
    gb.write_geo_template(step_path, geo_path, clmax=4.0,
                          physicals={"superficie_carico": "{facce superiori}",
                                     "volume_struttura": "{volume unico}"},
                          commenti="modello demo staffa")
    _log(f"    template .geo -> {geo_path}")

    # ---------------------------------------------------------------- 2) mesh
    _log("\n[2] GMSH — meshing embedded del modello")
    msh_path = os.path.join(cartella_out, "staffa.msh")
    stats = gb.mesh_step(step_path, msh_path, clmax=5.0, clmin=1.0,
                         msh_version="4.1")
    _log(f"    mesh generata -> {msh_path} ({stats})")

    # ---------------------------------------------------------------- 3) mesh mode
    _log("\n[3] MODALITÀ MESH — import .msh, selezioni, gruppi")
    doc2 = CADDocument("Demo mesh")
    model = doc2.import_msh(msh_path)
    st = model.stats()
    _log(f"    import: {st['nodi']} nodi, {st['elementi']} elementi, "
         f"{st['blocchi']} blocchi")
    facce = doc2.query().type("face").select()
    _log(f"    selezione per tipo 'superficie': {len(facce)} blocchi")
    vol_ids = doc2.query().type("solid").select()
    _log(f"    selezione per tipo 'solido' (volumi): {len(vol_ids)} blocchi")
    # regione: cubo in alto
    doc2.set_selection([])
    for e in doc2.entities.values():
        if e.etype == "solid" and e.meta.get("mesh_ref"):
            mname, dim, tag = e.meta["mesh_ref"]
            mod = doc2.mesh_models[mname]
            bb = mod.elements_bbox(mod.blocks[(dim, tag)].element_ids)
            _log(f"    volume {tag}: bbox {tuple(round(v, 1) for v in bb)}")
    # selezione per normale: superfici rivolte verso +Z
    sup = [e for e in doc2.entities.values() if e.etype == "face"]
    doc2.set_selection([e.id for e in sup])
    sel.select_by_normal(doc2, 0, 0, 1, tol_deg=20)
    grup_z = doc2.groups.group_from_selection(doc2, "superfici_superiori",
                                              color=(0.9, 0.2, 0.2))
    _log(f"    superfici ~+Z: {len(grup_z.member_ids)} -> gruppo 'superfici_superiori'")
    # selezione elementi in sfera + espansione
    for m in doc2.mesh_models.values():
        m.select_elements_in_sphere(0, 0, 70, 15)
        m.grow_elements("nodes")
        doc2.groups.add_mesh_elements("zona_foro", m.name, m.sel_elements)
        _log(f"    selezione sferica + grow: {len(m.sel_elements)} elementi "
             f"-> gruppo 'zona_foro'")
        m.clear_selection()
    # selezione per gruppo fisico
    for m in doc2.mesh_models.values():
        for key in list(m.physicals):
            n = len(m.select_blocks_by_physical(m.physicals[key]))
            _log(f"    gruppo fisico '{m.physicals[key]}': {n} elementi")
            break

    # ---------------------------------------------------------------- 4) macro
    _log("\n[4] MACRO — comandi personalizzati sulla selezione")
    engine = MacroEngine(doc2, log=_log)
    cartella_macro = os.path.join(os.path.dirname(__file__), "..", "macros")
    engine.load_folder(os.path.abspath(cartella_macro))
    _log(f"    macro caricate: {', '.join(engine.list_names())}")

    # macro 1: marca per area (superfici)
    doc2.set_selection([e.id for e in sup])
    spec = engine.by_name("Marca per area")
    if spec:
        engine.run(spec, {"soglia": 100.0})
        n_mar = sum(1 for e in doc2.entities.values()
                    if e.meta.get("marca") == "grande")
        _log(f"    superfici marcate 'grande': {n_mar}")

    # macro 2: perturba i nodi della zona selezionata
    for m in doc2.mesh_models.values():
        m.select_block(3, 1)
        m.select_nodes_of_selected_elements()
    spec2 = engine.by_name("Perturba nodi")
    if spec2:
        engine.run(spec2, {"raggio": 0.4, "seed": 42})

    # macro 3: trasla punti (crea punti demo e traslali)
    builder2 = GeometryBuilder(doc2)
    p1 = builder2.punto(0, 0, 0, "Ancora")
    p2 = builder2.punto(10, 0, 0, "Cursore")
    doc2.set_selection([p1.id, p2.id])
    spec3 = engine.by_name("Trasla punti")
    if spec3:
        engine.run(spec3, {"dx": 0.0, "dy": 0.0, "dz": 2.5})

    # ---------------------------------------------------------------- 5) export
    _log("\n[5] EXPORT — gruppi e mesh marcata")
    txt = doc2.groups.export_text(doc2)
    txt_path = os.path.join(cartella_out, "gruppi.txt")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(txt)
    _log(f"    elenco gruppi -> {txt_path}")
    out_msh22 = os.path.join(cartella_out, "staffa_export.msh")
    gb.export_msh_22(model, out_msh22)
    _log(f"    mesh con gruppi fisici -> {out_msh22}")

    _log("\nDemo completata con successo.")
    _log(f"Artefatti in: {cartella_out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_demo(sys.argv[1] if len(sys.argv) > 1 else "output"))
