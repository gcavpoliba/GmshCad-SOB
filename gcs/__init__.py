"""
GmshCAD Studio (gcs)
====================

Ambiente CAD 3D basato su OpenCASCADE (pythonocc-core) con integrazione Gmsh.

Due modalità operative:
  * **Modalità Mesh**  — import di mesh gmsh ``.msh`` (formati 2.2 e 4.1),
    selezione di punti/curve/superfici/volumi, creazione e gestione gruppi.
  * **Modalità Geometria** — creazione, modifica ed editing di punti, linee,
    superfici e solidi (B-Rep OpenCASCADE) con export verso Gmsh
    (STEP, template ``.geo`` e meshing embedded via API gmsh).

Motore macro: comandi personalizzati dichiarati in file ``.py`` (cartella
``gcs/macros``) con decorator ``@macro`` e applicazione automatica ad ogni
punto, curva, superficie, solido o nodo mesh delle entità selezionate.
"""

__version__ = "1.0.0"
__app_name__ = "GmshCAD Studio"
