#!/usr/bin/env python3
"""Genera i campioni .msh del progetto usando l'API gmsh.

Crea una staffa (L-bracket con fori), la mesha e salva:
  * samples/bracket_22.msh  — formato 2.2 ASCII con gruppi fisici;
  * samples/bracket_41.msh  — formato 4.1 ASCII con gruppi fisici.

Uso:  python samples/make_samples.py
"""

import os
import sys

import gmsh


def crea_staffa(cartella: str) -> None:
    out22 = os.path.join(cartella, "bracket_22.msh")
    out41 = os.path.join(cartella, "bracket_41.msh")

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        # ----- geometria via kernel OpenCASCADE di gmsh
        base = gmsh.model.occ.addBox(0, 0, 0, 60, 30, 10)
        ala = gmsh.model.occ.addBox(0, 0, 10, 10, 30, 40)
        gmsh.model.occ.fuse([(3, base)], [(3, ala)])
        gmsh.model.occ.synchronize()
        fori = []
        for x in (18, 32, 46):
            fori.append((3, gmsh.model.occ.addCylinder(x, 15, -5, 0, 0, 20, 4)))
        gmsh.model.occ.cut([(3, base)], fori)
        gmsh.model.occ.synchronize()

        # ----- gruppi fisici con nomi significativi
        superfici = gmsh.model.getEntities(2)
        volumi = gmsh.model.getEntities(3)
        # classificazione per centro di massa delle facce
        pavimento, superiori, lato_fisso = [], [], []
        for (dim, tag) in superfici:
            com = gmsh.model.occ.getCenterOfMass(dim, tag)
            area = gmsh.model.occ.getMass(dim, tag)
            if com[2] < 1e-6 and area > 10:
                pavimento.append(tag)
            if com[2] > 45:
                superiori.append(tag)
            if com[0] < 1e-6 and area > 10:
                lato_fisso.append(tag)
        if pavimento:
            gmsh.model.addPhysicalGroup(2, pavimento, name="fondazione")
        if superiori:
            gmsh.model.addPhysicalGroup(2, superiori, name="superfici_carico")
        if lato_fisso:
            gmsh.model.addPhysicalGroup(2, lato_fisso, name="lato_fisso")
        gmsh.model.addPhysicalGroup(3, [t for _, t in volumi], name="struttura")

        # ----- mesh
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", 1.5)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", 4.0)
        gmsh.option.setNumber("Mesh.SaveAll", 0)
        gmsh.model.mesh.generate(3)

        # ----- salvataggio nei due formati
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.write(out22)
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        gmsh.write(out41)
        nodi, _ = len(gmsh.model.mesh.getNodes()[0]), 0
        print(f"Creati: {out22} e {out41} ({nodi} nodi)")
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    cartella = os.path.dirname(os.path.abspath(__file__))
    crea_staffa(cartella)
