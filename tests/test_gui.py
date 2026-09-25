"""Test della GUI: costruzione offscreen della finestra principale (skip se
PySide6/pythonocc non sono disponibili o non c'è un backend Qt)."""

import os

import pytest

pytest.importorskip("gcs.core.occ_utils")
from gcs.core import occ_utils as occ

if not occ.HAS_OCC:
    pytest.skip("pythonocc-core non installato", allow_module_level=True)

pyside = pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication          # noqa: E402


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_construisce(app):
    from gcs.gui.main_window import MainWindow
    win = MainWindow()
    assert win.doc is not None
    assert win.engine is not None
    # modalità
    win._set_mode("mesh")
    assert win.doc.mode == "mesh"
    win._set_mode("geometria")
    # creazione geometria via API (senza dialog)
    win.builder.box(10, 10, 10)
    win.builder.cilindro(2, 5, base=(0, 0, 10))
    assert len(win.doc.entities) == 2
    # refresh pannelli
    win.tree_panel.refresh()
    win.props_panel.refresh()
    # cambio modalità + import mesh demo campione
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    campione = os.path.join(root, "samples", "bracket_22.msh")
    if os.path.exists(campione):
        win.doc.import_msh(campione)
        win.tree_panel.refresh()
        assert any(e.is_mesh_block for e in win.doc.entities.values())
    # toggle griglia
    win.act_toggle_grid()
    assert hasattr(win, "act_export_opensees")
    assert hasattr(win, "act_export_opensees_gruppi")
    # chiudi pulito
    win.close()


def test_paramdialog_campi(app):
    from gcs.gui.dialogs import ParamDialog
    from gcs.core.macro_engine import MacroSpec, P

    def dummy(ctx, target, params):
        return None

    spec = MacroSpec("Test dialog", dummy,
                     applies_to=("face",),
                     params=[P("a", "float", default=1.5, min=0, max=10),
                             P("b", "int", default=2),
                             P("c", "bool", default=True),
                             P("d", "choice", default="X", choices=("X", "Y")),
                             P("e", "vec3", default=(1, 2, 3))])
    dlg = ParamDialog(spec)
    vals = dlg.values()
    assert vals["a"] == 1.5 and vals["b"] == 2 and vals["c"] is True
    assert vals["d"] == "X"
