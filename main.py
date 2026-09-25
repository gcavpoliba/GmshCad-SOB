#!/usr/bin/env python3
"""Punto d'ingresso GmshCAD Studio.

Uso:
    python main.py              # avvia l'interfaccia grafica
    python main.py --demo       # demo end-to-end headless (senza GUI)
    python main.py --selfcheck  # verifica rapida delle dipendenze
    python main.py --macro-template [percorso]  # genera template macro
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configurazione compatibilità Windows (console UTF-8 e risoluzione DLL Conda / PySide6)
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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


def selfcheck() -> int:
    """Verifica le dipendenze e stampa lo stato."""
    voci = []
    try:
        import numpy
        voci.append(("numpy", numpy.__version__, True))
    except ImportError:
        voci.append(("numpy", "MANCANTE", False))
    try:
        import gmsh
        voci.append(("gmsh", getattr(gmsh, "GMSH_API_VERSION", "?"), True))
    except Exception as exc:
        voci.append(("gmsh", f"non disponibile ({exc.__class__.__name__})", False))
    from gcs.core import occ_utils
    voci.append(("pythonocc-core (OCC)", "OK" if occ_utils.HAS_OCC
                 else f"MANCANTE ({occ_utils._IMPORT_ERR})", occ_utils.HAS_OCC))
    try:
        import PySide6
        voci.append(("PySide6", PySide6.__version__, True))
    except ImportError:
        voci.append(("PySide6", "MANCANTE (solo per la GUI)", False))

    print(f"GmshCAD Studio — selfcheck")
    for nome, stato, ok in voci:
        tag = "[OK]" if ok else "[KO]"
        print(f"  {tag:5s} {nome:24s} {stato}")
    print("\nCon pythonocc-core e PySide6 installati è possibile avviare la GUI: "
          "python main.py")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="GmshCAD Studio — ambiente CAD "
                                             "OpenCASCADE + Gmsh")
    ap.add_argument("--demo", action="store_true",
                    help="esegue la demo end-to-end headless e termina")
    ap.add_argument("--selfcheck", action="store_true",
                    help="verifica le dipendenze e termina")
    ap.add_argument("--macro-template", nargs="?", const="macro_template.py",
                    metavar="PERCORSO",
                    help="genera un template di macro personalizzabile")
    ap.add_argument("--out", default="output", metavar="CARTELLA",
                    help="cartella di output per --demo (default: output)")
    args = ap.parse_args()

    if args.selfcheck:
        return selfcheck()
    if args.macro_template:
        from gcs.core.macro_engine import write_macro_template
        write_macro_template(args.macro_template)
        print(f"Template macro scritto: {args.macro_template}")
        return 0
    if args.demo:
        from gcs.core.demo import run_demo
        return run_demo(args.out)

    # ---- GUI
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        print(f"PySide6 non disponibile o errore nel caricamento della GUI: {exc}\n"
              "Verificare che l'ambiente conda 'gmshcad' sia attivo.\n"
              "Oppure eseguire la demo headless: python main.py --demo")
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("GmshCAD Studio")
    from gcs.gui.main_window import MainWindow
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
