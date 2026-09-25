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

import os
import sys

# Su Windows, gli ambienti Conda possono contenere una versione di icuuc.dll in Library\bin
# incompatibile con i binari wheel PySide6/Qt6, causando:
# "ImportError: DLL load failed while importing QtCore: Impossibile trovare la procedura specificata".
# Precaricare la DLL di sistema da System32 risolve il conflitto.
if sys.platform == "win32":
    _sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    if os.path.isdir(_sys32):
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_sys32)
            except Exception:
                pass
        _icu_dll = os.path.join(_sys32, "icuuc.dll")
        if os.path.isfile(_icu_dll):
            try:
                import ctypes
                ctypes.WinDLL(_icu_dll)
            except Exception:
                pass

