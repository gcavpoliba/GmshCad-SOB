import shutil
import subprocess

import pytest
from PySide6.QtWidgets import QApplication

from gcs.core.document import CADDocument
from gcs.gui.dialogs import OpenSeesFEMDialog


def _app():
    return QApplication.instance() or QApplication([])


def test_fem_dialog_exports_assigned_plane_material_sp_and_recorder():
    _app()
    doc = CADDocument("fem_dialog")
    model = doc.import_msh("samples/bracket_22.msh")
    face = next(entity for entity in doc.entities.values()
                if entity.name == "fondazione"
                and entity.meta.get("mesh_ref", (None,))[1:2] == (2,))

    dialog = OpenSeesFEMDialog(doc)
    dialog.material_model.setCurrentText("ElasticIsotropic")
    dialog.material_name.setText("Piano")
    dialog.material_tag.setValue(1)
    dialog._add_material()

    dialog.element_entity.setCurrentIndex(dialog.element_entity.findData(face.id))
    dialog.element_material.setCurrentIndex(dialog.element_material.findData(1))
    dialog.dimension.setCurrentIndex(0)
    dialog.element_thickness.setValue(0.25)
    dialog._assign_elements()

    dialog.sp_entity.setCurrentIndex(dialog.sp_entity.findData(face.id))
    dialog.sp_value.setValue(0.01)
    dialog._add_displacement()

    dialog.recorder_entity.setCurrentIndex(dialog.recorder_entity.findData(face.id))
    dialog.recorder_kind.setCurrentText("Node")
    dialog.recorder_response.setCurrentText("disp")
    dialog.recorder_dofs.setText("1,2")
    dialog.recorder_path.setText("output/disp.out")
    dialog._add_recorder()

    tcl = doc.opensees.generate_tcl_script(model)
    assert "model BasicBuilder -ndm 2 -ndf 2;" in tcl
    assert "nDMaterial ElasticIsotropic 1" in tcl
    assert "element tri31 " in tcl or "element quad " in tcl
    assert "sp " in tcl
    assert 'file mkdir "output";' in tcl
    assert "recorder Node" in tcl
    assert "-dof 1 2 disp;" in tcl
    assert "if {$ok_stage1 == 0} {" in tcl


def test_manual_cad_point_resolves_and_exports_as_opensees_node():
    _app()
    doc = CADDocument("manual_node")
    dialog = OpenSeesFEMDialog(doc)
    dialog.node_x.setValue(1.25)
    dialog.node_y.setValue(-2.0)
    dialog.node_z.setValue(3.5)
    dialog._add_node()

    point = next(entity for entity in doc.entities.values()
                 if "opensees_node_tag" in entity.meta)
    node_tag = point.meta["opensees_node_tag"]
    assert doc.opensees.resolve_entity_nodes(point.id) == [node_tag]
    assert f"node {node_tag} 1.25 -2 3.5;" in doc.opensees.generate_tcl_script()


def test_generated_tcl_parses_with_tclsh(tmp_path):
    tclsh = shutil.which("tclsh")
    if not tclsh:
        pytest.skip("tclsh non disponibile")

    doc = CADDocument("tcl_syntax")
    model = doc.import_msh("samples/bracket_22.msh")
    face = next(entity for entity in doc.entities.values()
                if entity.name == "fondazione"
                and entity.meta.get("mesh_ref", (None,))[1:2] == (2,))
    material = doc.opensees.add_material("Piano", "ElasticIsotropic", [30000, 0.2, 0])
    doc.opensees.ndm = 2
    doc.opensees.ndf = 2
    doc.opensees.assign_entity_elements(face.id, material.tag, model, thickness=0.25)
    doc.opensees.add_prescribed_displacement("Ux", [face.id], 1, 0.01)
    doc.opensees.add_recorder("Node", [face.id], "results/disp.out", "disp", [1, 2])

    stubs = "proc unknown {command args} {return 0}\n"
    stubs += "proc pattern {kind tag series body} {uplevel 1 $body}\n"
    result = subprocess.run(
        [tclsh], input=stubs + doc.opensees.generate_tcl_script(model),
        cwd=tmp_path, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr