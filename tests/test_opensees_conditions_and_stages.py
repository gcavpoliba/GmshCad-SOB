"""Test per condizioni, vincoli su gruppi, comandi OpenSees, solutori e fasi di calcolo:

1. Associazione del comando fix di OpenSees ai gruppi di entità.
2. Risoluzione dei nodi da gruppi CAD e gruppi fisici Gmsh.
3. Carichi OpenSees (load) e vincoli cinematici (equalDOF) su entità e gruppi.
4. Definizione del blocco risolutore e opzioni (constraints, numberer, system, test, algorithm, integrator).
5. Fasi di calcolo sequenziali:
   - Fase 1: Gravity Loading con updateMaterialStage -stage 0 e loadConst -time 0.0
   - Fase 2: Fase Elastoplastica con updateMaterialStage -stage 1
6. Dialoghi interattivi per la compilazione granulare dei parametri.
"""

import os
import tempfile
import pytest

from gcs.core.mesh import MeshModel
from gcs.core.document import CADDocument
from gcs.core.opensees_conditions import (
    StaticConstraint, EqualDOFConstraint, EntityLoad,
    SolverSettings, AnalysisStage, OpenSeesManager
)


def _load_bracket():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    campione = os.path.join(root, "samples", "bracket_22.msh")
    if not os.path.exists(campione):
        pytest.skip("File di test bracket_22.msh non trovato")
    doc = CADDocument("test_doc")
    model = doc.import_msh(campione)
    return doc, model


def test_fix_on_groups_resolution():
    doc, model = _load_bracket()

    # Associa un vincolo statico (fix) al gruppo fisico "fondazione"
    sc = doc.opensees.add_constraint(
        name="Vincolo_Fondazione",
        fix_x=True, fix_y=True, fix_z=True,
        fix_rx=False, fix_ry=False, fix_rz=False,
        group_names=["fondazione"]
    )

    nodes = doc.opensees.resolve_constraint_nodes(sc, model)
    assert len(nodes) == 184
    assert sc.dof_flags(ndf=3) == [1, 1, 1]
    assert sc.dof_flags(ndf=6) == [1, 1, 1, 0, 0, 0]

    # Genera TCL e verifica la presenza del comando fix sui nodi del gruppo
    tcl = doc.opensees.generate_tcl_script(model)
    assert "Vincolo 'Vincolo_Fondazione' su gruppi: fondazione (184 nodi):" in tcl
    assert "fix $node 1 1 1;" in tcl


def test_fix_on_custom_group():
    doc, model = _load_bracket()

    # Crea un gruppo personalizzato
    doc.groups.create("vincolo_muro")
    doc.groups.add_mesh_nodes("vincolo_muro", model.name, [10, 20, 30, 40])

    sc = doc.opensees.add_constraint(
        name="Fix_Muro",
        fix_x=True, fix_y=False, fix_z=True,
        group_names=["vincolo_muro"]
    )

    nodes = doc.opensees.resolve_constraint_nodes(sc, model)
    assert nodes == [10, 20, 30, 40]

    tcl = doc.opensees.generate_tcl_script(model)
    assert "Vincolo 'Fix_Muro' su gruppi: vincolo_muro (4 nodi):" in tcl
    assert "foreach node { 10 20 30 40 } {" in tcl
    assert "fix $node 1 0 1;" in tcl


def test_load_on_groups():
    doc, model = _load_bracket()

    # Associa un carico al gruppo fisico "superfici_carico"
    ld = doc.opensees.add_load(
        name="Carico_Gravita_Superficie",
        fz=-500.0,
        load_type="total",
        group_names=["superfici_carico"]
    )

    nodes = doc.opensees.resolve_load_nodes(ld, model)
    assert len(nodes) == 40

    tcl = doc.opensees.generate_tcl_script(model)
    assert "pattern Plain 1 1 {" in tcl
    assert "Carico 'Carico_Gravita_Superficie' (total) su gruppi: superfici_carico:" in tcl
    # Quota per nodo: -500 / 40 = -12.5
    assert "load 2 0 0 -12.5;" in tcl


def test_equaldof_on_groups():
    doc, model = _load_bracket()

    # Crea due gruppi di nodi per testare equalDOF
    doc.groups.create("master_grp")
    doc.groups.add_mesh_nodes("master_grp", model.name, [1, 2, 3])
    doc.groups.create("slave_grp")
    doc.groups.add_mesh_nodes("slave_grp", model.name, [4, 5, 6])

    eq = doc.opensees.add_equaldof(
        name="EqualDOF_Grp",
        dofs=[1, 2, 3],
        pairing_mode="spatial_match",
        master_group="master_grp",
        slave_group="slave_grp"
    )

    pairs = doc.opensees.resolve_equaldof_pairs(eq, model)
    assert len(pairs) == 3

    tcl = doc.opensees.generate_tcl_script(model)
    assert "EqualDOF 'EqualDOF_Grp' tra Master (Gruppo 'master_grp') e Slave (Gruppo 'slave_grp'): 3 coppie" in tcl
    assert "equalDOF " in tcl


def test_solver_settings_to_tcl():
    sol = SolverSettings(
        constraints="Penalty 1.0e14 1.0e14",
        numberer="Plain",
        system="BandSPD",
        test_type="EnergyIncr",
        test_tol=1e-8,
        test_iter=50,
        test_pflag=1,
        algorithm="ModifiedNewton",
        integrator_type="LoadControl",
        integrator_step=0.02,
        analysis_type="Static",
        n_steps=25
    )

    lines = sol.to_tcl(res_var="ok_test")
    joined = "\n".join(lines)
    assert "constraints Penalty 1.0e14 1.0e14;" in joined
    assert "numberer Plain;" in joined
    assert "system BandSPD;" in joined
    assert "test EnergyIncr 1e-08 50 1;" in joined
    assert "algorithm ModifiedNewton;" in joined
    assert "integrator LoadControl 0.02;" in joined
    assert "analysis Static;" in joined
    assert "set ok_test [analyze 25];" in joined


def test_multi_stage_gravity_and_elastoplastic_generation():
    doc, model = _load_bracket()

    # Aggiungi vincolo su fondazione e carico su superfici_carico
    doc.opensees.add_constraint("Vincolo_Base", group_names=["fondazione"])
    doc.opensees.add_load("Carico_Q", fz=-1000.0, group_names=["superfici_carico"])
    doc.opensees.add_material(
        "Terreno_PDMY", "PressureDependMultiYield",
        [3, 1.8, 70000, 140000, 30, 0.1, 100, 0.5, 20,
         0.1, 0.2, 0.3, 100, 0, 0, 0.0001, 0.0001])

    # Verifica che multi_stage sia attivo per default
    assert doc.opensees.multi_stage is True
    assert len(doc.opensees.stages) == 2

    stg1 = doc.opensees.stages[0]
    stg2 = doc.opensees.stages[1]

    assert stg1.stage_type == "gravity"
    assert stg1.material_stage == 0
    assert stg1.load_const is True

    assert stg2.stage_type == "elastoplastic"
    assert stg2.material_stage == 1

    tcl = doc.opensees.generate_tcl_script(model)

    # 1. Verifica stage 1 (Gravity Loading)
    assert "FASE 1: GRAVITY LOADING (STATO ELASTICO)" in tcl
    assert "updateMaterialStage -material 1 -stage 0;" in tcl
    assert "set ok_stage1 [analyze 10];" in tcl
    assert "loadConst -time 0.0;" in tcl

    # 2. Verifica stage 2 (Elastoplastica con updateMaterialStage 1)
    assert "FASE 2: FASE ELASTOPLASTICA (PLASTIC STAGE)" in tcl
    assert "updateMaterialStage -material 1 -stage 1;" in tcl
    assert "set ok_stage2 [analyze 20];" in tcl


def test_serialization_of_manager():
    doc, model = _load_bracket()
    doc.opensees.add_constraint("Fix_Test", fix_x=True, fix_y=False, fix_z=True, group_names=["fondazione"])
    doc.opensees.add_load("Load_Test", fz=-200.0, group_names=["superfici_carico"])

    data = doc.opensees.to_dict()
    assert "constraints" in data
    assert "loads" in data
    assert "stages" in data
    assert data["multi_stage"] is True

    new_mgr = OpenSeesManager.from_dict(doc, data)
    assert len(new_mgr.constraints) == 1
    assert new_mgr.constraints[0].group_names == ["fondazione"]
    assert len(new_mgr.loads) == 1
    assert len(new_mgr.stages) == 2


def test_dialogs_instantiation():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    doc, model = _load_bracket()

    from gcs.gui.dialogs import (
        EntityPropertiesDialog, GroupPropertiesDialog,
        OpenSeesFixDialog, OpenSeesLoadDialog, OpenSeesEqualDOFDialog,
        OpenSeesAnalysisDialog
    )

    # 1. EntityPropertiesDialog
    ent = list(doc.entities.values())[0]
    dlg_ent = EntityPropertiesDialog(ent, doc)
    assert dlg_ent.txt_name.text() == ent.name
    dlg_ent.close()

    # 2. GroupPropertiesDialog
    dlg_grp = GroupPropertiesDialog("fondazione", doc)
    assert dlg_grp.group_name == "fondazione"
    dlg_grp.close()

    # 3. OpenSeesFixDialog
    dlg_fix = OpenSeesFixDialog(doc, target_group="fondazione")
    assert dlg_fix.cmb_groups.currentText() == "fondazione"
    nodes = dlg_fix._get_target_nodes()
    assert len(nodes) == 184
    dlg_fix.close()

    # 4. OpenSeesLoadDialog
    dlg_load = OpenSeesLoadDialog(doc, target_group="superfici_carico")
    assert dlg_load.cmb_groups.currentText() == "superfici_carico"
    dlg_load.close()

    # 5. OpenSeesEqualDOFDialog
    dlg_eq = OpenSeesEqualDOFDialog(doc)
    dlg_eq.close()

    # 6. OpenSeesAnalysisDialog
    doc.opensees.add_material(
        "Terreno_PDMY", "PressureDependMultiYield",
        [3, 1.8, 70000, 140000, 30, 0.1, 100, 0.5, 20,
         0.1, 0.2, 0.3, 100, 0, 0, 0.0001, 0.0001])
    dlg_an = OpenSeesAnalysisDialog(doc, model)
    assert dlg_an.chk_multi.isChecked() is True
    assert "updateMaterialStage" in dlg_an.txt_tcl.toPlainText()
    dlg_an.close()
