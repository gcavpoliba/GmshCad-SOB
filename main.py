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

# --- tracking dei DLL search directory (solo Windows) ---------------------
# FIX BUG: in precedenza si tentava di enumerare gli handle via
# os._dill_dir_handles_seen, attributo che non esiste su CPython: la
# de-registrazione delle entry di terzi era quindi un no-op silenzioso.
# Ora ogni add_dll_directory() eseguita nel processo viene intercettata e
# tracciata, così da poter chiudere le entry NON appartenenti a GmshCAD.
_GCS_DLL_HANDLES = []          # [(handle_obj, path), ...] tutti quelli registrati
_GCS_NOSTRI_HANDLES = set()    # id() degli handle PySide6 gestiti da noi


def _installa_tracking_dll_directory() -> None:
    """Patch (idempotente) di os.add_dll_directory per tracciare gli handle."""
    if os.name != "nt":
        return
    originale = getattr(os, "add_dll_directory", None)
    if originale is None or getattr(originale, "_gcs_tracked", False):
        return

    def _add(path):
        h = originale(path)
        try:
            _GCS_DLL_HANDLES.append((h, str(path)))
        except Exception:
            pass
        return h

    _add._gcs_tracked = True
    _add._gcs_originale = originale
    os.add_dll_directory = _add


_installa_tracking_dll_directory()


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


def _pyside_e_conda_forge() -> bool:
    """True se PySide6 proviene dal pacchetto conda-forge (non da pip).

    Rilevamento: i pacchetti conda registrano l'history in
    <env>/conda-meta/pyside6-*.json; le installazioni pip hanno solo il
    dist-info dentro site-packages.
    """
    import glob
    try:
        import PySide6
    except Exception:
        return False
    env = os.path.dirname(os.path.dirname(sys.executable))
    if glob.glob(os.path.join(env, "conda-meta", "pyside6-*.json")):
        return True
    # fallback: percorso del pacchetto fuori da site-packages => non pip
    pkg = os.path.abspath(PySide6.__file__)
    return "site-packages" not in pkg.replace("\\", "/").lower()


def _bin_ambiente_conda() -> list:
    """Directory bin/DLL di tutti gli ambienti conda raggiunti dal PATH."""
    indesiderati = []
    visti = set()
    # ambiente attivo: da sys.prefix / base_prefix (copre anche `python main.py`
    # diretto, senza launcher) e da CONDA_PREFIX (altre eventuali attivazioni)
    candidati = []
    for prefisso in (sys.prefix, getattr(sys, "base_prefix", ""),
                    os.environ.get("CONDA_PREFIX", "")):
        if prefisso:
            candidati.append(prefisso)
    for pref in candidati:
        for sott in ("Library", "bin"):
            d = os.path.normcase(os.path.abspath(os.path.join(pref, sott)))
            if d not in visti and os.path.isdir(d):
                visti.add(d)
                indesiderati.append(d)
    # ogni voce del PATH che finisce in Library\bin o \bin e' una possibile
    # sorgente di DLL Qt concorrenti (altri ambienti, Qt di sistema, pyqt5,
    # toolchain, ecc.): le rimuoviamo tutte, perche' il conflitto non dipende
    # dall'ambiente attivo ma da QUALSIASI QtCore6.dll trovata prima.
    voci_extra = []
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if not p:
            continue
        d = os.path.normcase(os.path.abspath(p))
        if d.endswith(("\\library\\bin", "\\bin")) and d not in visti:
            visti.add(d)
            voci_extra.append(d)
    return indesiderati, voci_extra


def _sanitizza_ricerca_dll() -> int:
    """Windows: ripulisce PATH e add_dll_directory dalle DLL Qt di terzi.

    Il vero colpevole dell'errore "Impossibile trovare la procedura
    specificata" e' una QtCore6.dll INCOMPATIBILE caricata PRIMA di quella di
    PySide6. Puo' arrivare da:
      - <env>\\Library\\bin (pacchetto conda 'qt-main', trascinato da
        pythonocc-core/vtk);
      - qualsiasi altra cartella in PATH o registrata con
        os.add_dll_directory (altri ambienti conda, PyQt5, installer Qt,
        applicazioni che scrivono in PATH).
    Strategia usata qui:
      1) si importa SHIBOKEN6 PRIMA di QtCore: shiboken6 carica la sua
        MSVCP/PythonDLL e, soprattutto, PULLA la QtCore6.dll CORRETTA dalla
        cartella di PySide6 ancor prima che il loader ne trovi una sbagliata
        altrove (la prima copia caricata vince a parita' di nome);
      2) si rimuovono dai PATH del processo tutte le cartelle bin sospette;
      3) si registra SOLO la cartella di PySide6 come add_dll_directory,
        de-registrando le altre (i default search directories non toccano
        i directory di sistema, quindi OC/VC++ restano raggiungibili).
    Disattivabile con GCS_KEEP_CONDA_BIN=1 (in quel caso si salta tutto).
    Ritorna quante voci sono state rimosse/spostate.
    """
    if os.name != "nt" or os.environ.get("GCS_KEEP_CONDA_BIN") == "1":
        return 0
    rimossi = 0
    try:
        import shiboken6  # noqa: F401  (Nucleo della mitigazione: vedi doc)
    except Exception:
        pass
    indesiderati, extra = _bin_ambiente_conda()
    da_scartare = set(indesiderati) | set(extra)
    percorso = os.environ.get("PATH", "")
    parti = percorso.split(os.pathsep)
    tenute = [p for p in parti
              if not p or os.path.normcase(os.path.abspath(p)) not in da_scartare]
    n_path = len(parti) - len(tenute)
    if n_path:
        os.environ["PATH"] = os.pathsep.join(tenute)
        rimossi += n_path
    # FIX BUG (debug repo): il codice precedente leggeva l'attributo
    # os._dill_dir_handles_seen, che NON ESISTE su CPython: la de-registrazione
    # dei DLL search directory aggiunti da altri (conda, vtk, estensioni) non
    # avveniva mai e una QtCore6.dll concorrente poteva vincere al loader.
    # Ora si fa tracking diretto: patchando os.add_dll_directory ogni
    # registrazione del processo viene tracciata in _GCS_DLL_HANDLES; qui si
    # chiudono gli handle NON nostri (quelli registrati prima del nostro
    # import restano nei "default directories" del loader e non sono
    # raggiungibili dall'API, ma almeno le entry esplicite di terzi cadono).
    try:
        for h, _p in list(_GCS_DLL_HANDLES):      # (handle, path)
            if h is None or getattr(h, "closed", False):
                continue
            if id(h) in _GCS_NOSTRI_HANDLES:
                continue  # il nostro PySide6 dir: lo gestisce _prepara_dll_pyside
            try:
                h.close()
                rimossi += 1
            except Exception:
                pass
    except Exception:
        pass
    return rimossi


def _prepara_dll_pyside() -> None:
    """Windows: mitiga il conflitto DLL tra PySide6 e le Qt di conda/altri.

    pythonocc-core (conda-forge) trascina 'qt-main': le sue DLL finiscono in
    <env>\\Library\\bin, che conda antepone al PATH. Idem per qualunque altro
    ambiente/toolchain Qt presente nel PATH. Durante l'import di
    PySide6.QtWidgets Windows puo' risolvere QtCore6.dll con una versione
    incompatibile, ottenendo:
        "DLL load failed ... Impossibile trovare la procedura specificata."
    Vedi _sanitizza_ricerca_dll per la strategia completa.
    Se PySide6 arriva gia' da conda-forge ed e' l'unica fonte di DLL nel
    PATH, la sanitizzazione resta comunque applicata (le DLL di qt-main
    nella SAME environment sono compatibili e raggiungibili via default
    search directories, non via PATH).
    """
    if os.name != "nt":
        return
    try:
        import PySide6
    except ImportError:
        return
    _sanitizza_ricerca_dll()
    d = os.path.dirname(os.path.abspath(PySide6.__file__))
    # rimuove un'eventuale registrazione precedente (selfcheck poi GUI)
    for hh, _p in list(_GCS_DLL_HANDLES):
        if _p and os.path.normcase(_p) == os.path.normcase(d):
            try:
                hh.close()
            except Exception:
                pass
            _GCS_DLL_HANDLES.remove((hh, _p))
            _GCS_NOSTRI_HANDLES.discard(id(hh))
    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    try:
        h = os.add_dll_directory(d)
        _GCS_NOSTRI_HANDLES.add(id(h))
    except (AttributeError, OSError):
        pass


def selfcheck() -> int:
    """Verifica le dipendenze e stampa lo stato."""
    _prepara_dll_pyside()
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
        from PySide6 import QtWidgets  # noqa: F401 — import effettivo usato dalla GUI
        origine = "conda-forge" if _pyside_e_conda_forge() else "pip"
        voci.append(("PySide6 (QtWidgets)",
                     f"{PySide6.__version__} [{origine}]", True))
    except ImportError as exc:
        voci.append(("PySide6 (QtWidgets)", f"non caricabile: {exc}", False))
    except Exception as exc:  # DLL corrotte, conflitti con Qt di conda, ecc.
        note = ""
        try:
            import PySide6
            if not _pyside_e_conda_forge():
                note = ("\n      → PySide6 arriva da PIP e coesiste con qt-main "
                        "di conda (conflitto DLL).\n        Rimedio:\n"
                        "          python -m pip uninstall -y PySide6 "
                        "PySide6-Essentials PySide6-Addons shiboken6\n"
                        "          conda install -c conda-forge pyside6")
            else:
                note = ("\n      → PySide6 è già da conda-forge: ambiente misto/"
                        "corrotto. Ricostruirlo:\n"
                        "          conda env remove -n gmshcad\n"
                        "          conda env create -f environment.yml -n gmshcad")
        except Exception:
            pass
        voci.append(("PySide6 (QtWidgets)", f"ERRORE: {exc}{note}", False))

    print(f"GmshCAD Studio — selfcheck")
    for nome, stato, ok in voci:
        print(f"  [{'✓' if ok else '✗'}] {nome:24s} {stato}")
    mancanti = [v for v in voci if not v[2]]
    if mancanti:
        print("\nPer completare l'installazione (ambiente attivo 'gmshcad'):")
        print("  PySide6: NON via pip se l'ambiente ha qt-main/pythonocc-core,")
        print("    ma da conda-forge (evita il conflitto DLL su Windows):")
        print("      conda install -c conda-forge pyside6")
        print("  il resto può convivere via pip:")
        print("      python -m pip install gmsh numpy pytest")
        print("  pythonocc-core NON è su PyPI, solo via conda-forge:")
        print("      conda install -c conda-forge pythonocc-core=7.7.2")
        print("  In alternativa ricostruire tutto l'ambiente dal file:")
        print("      conda env create -f environment.yml -n gmshcad")
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
    _prepara_dll_pyside()
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        print(f"PySide6 non avviabile: {exc}\n")
        if "DLL load failed" in str(exc) or "specified module" in str(exc) \
                or "Impossibile trovare" in str(exc):
            da_conda = False
            try:
                import PySide6  # il pacchetto puro Python di solito si carica
                da_conda = _pyside_e_conda_forge()
            except Exception:
                pass
            if not da_conda:
                print("PySide6 è presente ma QtWidgets non si carica. Conflitto")
                print("DLL Qt: una QtCore6.dll incompatibile (conda 'qt-main',")
                print("altro ambiente conda, o cartella nel PATH) viene caricata")
                print("prima di quella di PySide6.")
                print("Diagnostica utile (trova le copie concorrenti di Qt):")
                print("     where QtCore6.dll")
                print("     conda list | findstr /i \"pyside qt-main shiboken\"")
                print("Rimedio definitivo (ambiente attivo):\n")
                print("     python -m pip uninstall -y PySide6 PySide6-Essentials PySide6-Addons shiboken6")
                print("     conda install -c conda-forge pyside6")
                print("\nAlternative, se il passo sopra non fosse possibile:")
                print("  a) runtime Microsoft Visual C++ Redistributable (x64):")
                print("     https://aka.ms/vs/17/release/vc_redist.x64.exe")
                print("  b) reinstallazione pulita via pip:")
                print("     python -m pip install --force-reinstall --no-cache-dir PySide6")
                print("  c) versione stabile precedente:")
                print('     python -m pip install "PySide6==6.8.*"')
                print("\nNOTA: non rimuovere 'qt-main' se conda propone di eliminare")
                print("anche pythonocc-core: ne ha bisogno.")
            else:
                print("PySide6 risulta già installato da conda-forge eppure non")
                print("si carica: probabile ambiente corrotto o misto pip+conda.")
                print("Ricostruisci l'ambiente dal file environment.yml:")
                print("     conda env remove -n gmshcad")
                print("     conda env create -f environment.yml -n gmshcad")
                print("(environment.yml installa PySide6 da conda-forge, non da pip)")
                print("Verifica poi che il prompt mostri (gmshcad) e non altri")
                print("ambienti prima di lanciare run.bat.")
        else:
            print("Rimedio consigliato (con l'ambiente conda attivo, come ora):")
            print("    conda install -c conda-forge pyside6")
            print("    python main.py")
            print("\nAlternativa via pip (solo se NON hai qt-main/pythonocc-core:")
            print("usa un ambiente separato, altrimenti le due Qt confliggono):")
            print("    python -m pip install PySide6")
        print("\nPer verificare tutte le dipendenze:  python main.py --selfcheck")
        print("Demo headless senza GUI:             python main.py --demo")
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("GmshCAD Studio")
    from gcs.gui.main_window import MainWindow
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
