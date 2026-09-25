import os
import sys

# rende importabile il package gcs dal root del progetto
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

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

