"""Test completi per l'esportazione verso OpenSees:

1. Orientamento nodi OpenSees per elementi 2D piani (tri31, quad in senso antiorario CCW)
   e 3D (FourNodeTetrahedron con V>0, stdBrick con Jacobiano positivo).
2. Coerenza rigorosa tra numero di nodi ed elementi (nessun nodo mancante o errato).
3. Estrazione nodi per gruppi definiti (Physical Groups Gmsh e gruppi CAD).
4. Generazione file .txt per nodi e connectivity list in sintassi OpenSees.
5. Funzionamento di OpenSeesExportDialog.
"""

import os
import tempfile
import pytest

from gcs.core.mesh import MeshModel
from gcs.core.document import CADDocument
from gcs.core import opensees_export as ose


def test_reorder_triangle_ccw():
    # Triangolo orario (CW) in piano XY
    # p1=(0,0,0), p2=(0,1,0), p3=(1,0,0) -> normale (0, 0, -1)
    coords = {1: (0.0, 0.0, 0.0), 2: (0.0, 1.0, 0.0), 3: (1.0, 0.0, 0.0)}
    ordered, inv = ose.reorder_triangle_opensees([1, 2, 3], coords)
    assert inv is True
    assert ordered == [1, 3, 2]

    # Triangolo già antiorario (CCW)
    # p1=(0,0,0), p2=(1,0,0), p3=(0,1,0) -> normale (0, 0, +1)
    coords_ccw = {1: (0.0, 0.0, 0.0), 2: (1.0, 0.0, 0.0), 3: (0.0, 1.0, 0.0)}
    ordered_ccw, inv_ccw = ose.reorder_triangle_opensees([1, 2, 3], coords_ccw)
    assert inv_ccw is False
    assert ordered_ccw == [1, 2, 3]


def test_reorder_quad_ccw():
    # Quadrilatero orario (CW)
    coords = {
        1: (0.0, 0.0, 0.0),
        2: (0.0, 1.0, 0.0),
        3: (1.0, 1.0, 0.0),
        4: (1.0, 0.0, 0.0)
    }
    ordered, inv = ose.reorder_quad_opensees([1, 2, 3, 4], coords)
    assert inv is True
    assert ordered == [1, 4, 3, 2]

    # Quadrilatero già antiorario (CCW)
    ordered_ccw, inv_ccw = ose.reorder_quad_opensees([1, 4, 3, 2], coords)
    assert inv_ccw is False
    assert ordered_ccw == [1, 4, 3, 2]


def test_reorder_tetrahedron_positive_volume():
    # Tetraedro con volume negativo:
    # p1=(0,0,0), p2=(0,1,0), p3=(1,0,0), p4=(0,0,1)
    # (p2-p1)x(p3-p1) = (0,0,-1) . (p4-p1) = -1 < 0
    coords = {
        1: (0.0, 0.0, 0.0),
        2: (0.0, 1.0, 0.0),
        3: (1.0, 0.0, 0.0),
        4: (0.0, 0.0, 1.0)
    }
    ordered, inv = ose.reorder_tetrahedron_opensees([1, 2, 3, 4], coords)
    assert inv is True
    # I nodi 2 e 3 devono essere scambiati per rendere positivo il volume
    assert ordered == [1, 3, 2, 4]

    # Verifica che il nuovo ordine abbia volume positivo
    _, inv2 = ose.reorder_tetrahedron_opensees(ordered, coords)
    assert inv2 is False


def test_reorder_ten_node_tetrahedron_keeps_edge_nodes_attached():
    coords = {
        1: (0.0, 0.0, 0.0),
        2: (0.0, 1.0, 0.0),
        3: (1.0, 0.0, 0.0),
        4: (0.0, 0.0, 1.0),
    }
    ordered, inverted = ose.reorder_element_nodes_for_opensees(
        11, list(range(1, 11)), coords)
    assert inverted is True
    assert ordered == [1, 3, 2, 4, 7, 6, 5, 8, 10, 9]


def test_reorder_hexahedron_positive_jacobian():
    # Esaedro unitario [0,1]^3
    # Nodi 1..4 piano z=0, 5..8 piano z=1
    coords = {
        1: (0.0, 0.0, 0.0), 2: (1.0, 0.0, 0.0), 3: (1.0, 1.0, 0.0), 4: (0.0, 1.0, 0.0),
        5: (0.0, 0.0, 1.0), 6: (1.0, 0.0, 1.0), 7: (1.0, 1.0, 1.0), 8: (0.0, 1.0, 1.0)
    }
    # Ordine CCW corretto
    ordered, inv = ose.reorder_hexahedron_opensees([1, 2, 3, 4, 5, 6, 7, 8], coords)
    assert inv is False
    assert ordered == [1, 2, 3, 4, 5, 6, 7, 8]

    # Ordine errato con faccia capovolta
    bad_nodes = [1, 4, 3, 2, 5, 8, 7, 6]
    corrected, inv_bad = ose.reorder_hexahedron_opensees(bad_nodes, coords)
    assert inv_bad is True
    assert corrected == [1, 2, 3, 4, 5, 6, 7, 8]


def test_coherence_verification_bracket_sample():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    campione = os.path.join(root, "samples", "bracket_22.msh")
    if not os.path.exists(campione):
        pytest.skip("File di test bracket_22.msh non trovato")

    doc = CADDocument("test_bracket")
    model = doc.import_msh(campione)

    coherence = ose.verify_mesh_coherence(model)
    assert coherence["valid"] is True
    assert coherence["total_nodes"] == 910
    assert coherence["referenced_nodes_count"] == 910
    assert coherence["missing_nodes_count"] == 0
    assert len(coherence["missing_nodes"]) == 0
    assert len(coherence["mismatched_elements"]) == 0


def test_coherence_flags_missing_nodes():
    model = MeshModel("incoherent_test")
    model.add_node(1, 0.0, 0.0, 0.0)
    model.add_node(2, 1.0, 0.0, 0.0)
    # Elemento che referenzia nodo inesistente 999
    model.add_element(1, 2, [1, 2, 999])

    coherence = ose.verify_mesh_coherence(model)
    assert coherence["valid"] is False
    assert 999 in coherence["missing_nodes"]


def test_extract_defined_groups_and_export():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    campione = os.path.join(root, "samples", "bracket_22.msh")
    if not os.path.exists(campione):
        pytest.skip("File di test bracket_22.msh non trovato")

    doc = CADDocument("test_groups")
    model = doc.import_msh(campione)

    # Aggiungi anche un gruppo personalizzato in doc.groups
    doc.groups.create("vincolo_speciale")
    doc.groups.add_mesh_nodes("vincolo_speciale", model.name, [1, 2, 3, 4, 5])

    groups = ose.extract_defined_groups_nodes(doc, model)
    assert "fondazione" in groups
    assert "lato_fisso" in groups
    assert "superfici_carico" in groups
    assert "struttura" in groups
    assert "Tutti_i_Nodi" in groups
    assert "vincolo_speciale" in groups

    assert len(groups["fondazione"]["node_ids"]) == 184
    assert len(groups["lato_fisso"]["node_ids"]) == 146
    assert len(groups["vincolo_speciale"]["node_ids"]) == 5

    # Test esportazione bundle su file
    with tempfile.TemporaryDirectory() as tmpdir:
        res = ose.export_opensees_bundle(tmpdir, doc, model)
        assert os.path.isfile(res["connectivity"])
        assert os.path.isfile(res["nodes_consolidated"])
        assert os.path.isdir(res["nodes_dir"])
        assert os.path.isfile(res["tcl_script"])

        # Verifica contenuto del file di connettività
        with open(res["connectivity"], "r", encoding="utf-8") as f:
            txt_conn = f.read()
            assert "OpenSees Element Connectivity List" in txt_conn
            assert "element FourNodeTetrahedron" in txt_conn
            assert "element tri31" in txt_conn

        # Verifica contenuto nodi per gruppi
        with open(res["nodes_consolidated"], "r", encoding="utf-8") as f:
            txt_nodes = f.read()
            assert "fondazione" in txt_nodes
            assert "lato_fisso" in txt_nodes
            assert "node " in txt_nodes  # comandi opensees generati


def test_dialog_opensees_export():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from gcs.gui.dialogs import OpenSeesExportDialog
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    campione = os.path.join(root, "samples", "bracket_22.msh")
    if not os.path.exists(campione):
        pytest.skip("File di test bracket_22.msh non trovato")

    doc = CADDocument("test_dlg")
    model = doc.import_msh(campione)

    dlg = OpenSeesExportDialog(doc, model)
    vals = dlg.values()
    assert vals["export_connectivity"] is True
    assert vals["export_nodes"] is True
    assert "fondazione" in vals["selected_groups"]
    assert "lato_fisso" in vals["selected_groups"]
    dlg.close()
