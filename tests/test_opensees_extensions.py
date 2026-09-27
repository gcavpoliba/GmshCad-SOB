"""Test per le estensioni del catalogo OpenSees e fasi.

Verifica:
- Catalogo materiali/elementi/sezioni/geomTransf esteso
- Nuove classi: SectionDefinition, GeomTransfDefinition, BeamIntegrationDefinition,
  NodalMass, RayleighDamping, Region, ElementLoad, SetParameterCommand,
  UpdateMaterialsCommand
- ParameterBinding esteso con target_type (element, node, pattern, loadPattern, blank)
- PhaseManager.bridge_to_stages() - sincronizzazione con OpenSeesManager
- Phase.to_analysis_stage() - conversione fasi -> AnalysisStage
- SolverPack.comandi_opensees() genera Tcl valido (system/test/algorithm/...)
"""

from __future__ import annotations

import pytest

from gcs.core.opensees_catalog import (
    UNIAXIAL_MATERIALS, ND_MATERIALS, ELEMENT_CATALOG, SECTION_CATALOG,
    GEOM_TRANSF, BEAM_INTEGRATION, TIME_SERIES_TYPES, PATTERN_TYPES,
    CONSTRAINT_HANDLERS, NUMBERERS, SYSTEMS, ALGORITHMS, INTEGRATORS,
    TESTS, RECORDER_TYPES, PARAMETER_TARGETS, UPDATE_COMMANDS,
    ELEMENT_LOAD_TYPES, get_material_schema, is_uniaxial, is_ndmaterial,
)
from gcs.core.opensees_conditions import (
    MaterialDefinition, ElementAssignment, ParameterBinding,
    SetParameterCommand, UpdateMaterialsCommand, SectionDefinition,
    GeomTransfDefinition, BeamIntegrationDefinition, NodalMass,
    RayleighDamping, Region, ElementLoad, OpenSeesManager, SolverSettings,
    AnalysisStage,
)
from gcs.core.fases import PhaseManager, Phase, SolverPack, ElementProperty
from gcs.core.document import CADDocument


# =============================================================================
# 1. Catalogo - verifica copertura minima richiesta
# =============================================================================

def test_catalogo_materiali_esteso():
    """Il catalogo deve contenere almeno 30 materiali uniaxial e 15 nD."""
    assert len(UNIAXIAL_MATERIALS) >= 30
    assert len(ND_MATERIALS) >= 15
    # I materiali legacy devono ancora essere presenti
    for legacy in ("Elastic", "Steel01", "Concrete01",
                   "ElasticIsotropic", "PressureDependMultiYield"):
        assert legacy in UNIAXIAL_MATERIALS or legacy in ND_MATERIALS


def test_catalogo_materiali_nuovi():
    """Verifica che alcuni materiali aggiunti siano effettivamente nel catalogo."""
    for name in ("Steel02", "Concrete02", "Hysteretic", "Pinching4",
                 "J2Plasticity", "DruckerPrager", "PlaneStress", "PlateFiber",
                 "BoucWen", "PySimple1", "TzSimple1", "QzSimple1"):
        assert name in UNIAXIAL_MATERIALS or name in ND_MATERIALS, \
            f"Materiale {name} mancante"


def test_catalogo_elementi_esteso():
    """Il catalogo elementi deve includere almeno le famiglie base."""
    assert len(ELEMENT_CATALOG) >= 30
    families = {info["family"] for info in ELEMENT_CATALOG.values()}
    for fam in ("truss", "beam", "shell", "solid", "plane", "zero",
                "contact", "bearing"):
        assert fam in families, f"Famiglia {fam} mancante"


def test_catalogo_sezioni_geomtransf():
    """Sezioni e geomTransf devono essere presenti."""
    assert "Elastic" in SECTION_CATALOG
    assert "Fiber" in SECTION_CATALOG
    assert "Aggregator" in SECTION_CATALOG
    assert "Linear" in GEOM_TRANSF
    assert "PDelta" in GEOM_TRANSF
    assert "Corotational" in GEOM_TRANSF


def test_catalogo_beam_integration():
    """Le regole di integrazione beam devono essere presenti."""
    assert "Lobatto" in BEAM_INTEGRATION
    assert "Legendre" in BEAM_INTEGRATION
    assert "HingeRadau" in BEAM_INTEGRATION


def test_catalogo_time_series_pattern():
    """TimeSeries e pattern aggiunti."""
    assert "Rectangular" in TIME_SERIES_TYPES
    assert "Triangle" in TIME_SERIES_TYPES
    assert "Pulse" in TIME_SERIES_TYPES
    assert "UniformExcitation" in PATTERN_TYPES
    assert "MultipleSupport" in PATTERN_TYPES


def test_catalogo_solver():
    """Constraint handlers, numberers, systems, algorithms, integrators, tests."""
    assert "Penalty" in CONSTRAINT_HANDLERS
    assert "Lagrange" in CONSTRAINT_HANDLERS
    assert "Transformation" in CONSTRAINT_HANDLERS
    assert "AMD" in NUMBERERS
    assert "Mumps" in SYSTEMS
    assert "SparseSYM" in SYSTEMS
    assert "KrylovNewton" in ALGORITHMS
    assert "BFGS" in ALGORITHMS
    assert "DisplacementControl" in INTEGRATORS
    assert "HHT" in INTEGRATORS
    assert "EnergyIncr" in TESTS
    assert "FixedNumIter" in TESTS


def test_catalogo_recorders():
    """I tipi di recorder estesi devono essere presenti."""
    for r in ("Node", "Element", "EnvelopeNode", "EnvelopeElement",
              "Drift", "Pattern", "ElementRemoval"):
        assert r in RECORDER_TYPES


def test_catalogo_parameter_targets():
    """Tutti i target_type parameter devono essere presenti."""
    for t in ("element", "node", "pattern", "loadPattern", "blank"):
        assert t in PARAMETER_TARGETS


def test_catalogo_update_commands():
    """I comandi di update devono essere tutti presenti."""
    for c in ("none", "updateMaterialStage", "updateParameter",
              "updateMaterials", "setParameter"):
        assert c in UPDATE_COMMANDS


def test_helper_is_uniaxial_is_ndmaterial():
    assert is_uniaxial("Steel01") is True
    assert is_ndmaterial("Steel01") is False
    assert is_uniaxial("ElasticIsotropic") is False
    assert is_ndmaterial("ElasticIsotropic") is True


# =============================================================================
# 2. MaterialDefinition - estensione catalogo
# =============================================================================

def test_material_definition_backward_compat():
    """MaterialDefinition con 4 parametri per Concrete01 deve ancora funzionare."""
    m = MaterialDefinition(1, "Concrete", "Concrete01",
                            [-3.0e7, -0.002, -6.0e6, -0.0035])
    assert m.command == "uniaxialMaterial"
    assert m.model == "Concrete01"
    tcl = m.to_tcl()
    assert "Concrete01" in tcl and "-30000000" in tcl


def test_material_definition_steel02():
    """Steel02 ha 9 parametri - deve essere supportato."""
    m = MaterialDefinition(2, "S275", "Steel02",
                            [2.75e8, 2.1e11, 0.01, 15.0, 0.925, 0.15, 0.025, 1.0, 0.025])
    assert m.command == "uniaxialMaterial"
    tcl = m.to_tcl()
    assert "Steel02" in tcl


def test_material_definition_elastic_multilinear_uses_extra():
    """ElasticMultiLinear usa `extra` per strains/stresses."""
    m = MaterialDefinition(3, "Multi", "ElasticMultiLinear", [],
                            extra={"strains": [0.0, 0.002, 1.0],
                                   "stresses": [0.0, 4.0e8, 4.0e8]})
    tcl = m.to_tcl()
    assert "-strain" in tcl and "-stress" in tcl


def test_material_definition_init_strain():
    """InitStrainMaterial wrappa un materiale con deformazione iniziale."""
    m = MaterialDefinition(4, "Init", "InitStrainMaterial", [],
                            extra={"material_tag": 1, "strain": 0.001})
    tcl = m.to_tcl()
    assert "-material 1" in tcl and "-strain 0.001" in tcl


# =============================================================================
# 3. ElementAssignment - estensione con section_tag, transf_tag, integration_tag
# =============================================================================

def test_element_assignment_backward_compat():
    """ElementAssignment con vecchia firma deve ancora funzionare."""
    a = ElementAssignment(entity_id=1, model_name="m", element_ids=[1, 2],
                          gmsh_type=1, material_tag=1, area=0.01)
    assert a.section_tag is None
    assert a.transf_tag is None
    d = a.to_dict()
    assert "section_tag" not in d  # campi opzionali omessi


def test_element_assignment_with_section_and_transf():
    """ElementAssignment esteso con sezione per shell/beam."""
    a = ElementAssignment(entity_id=2, model_name="m", element_ids=[10, 11],
                          gmsh_type=3, material_tag=1,
                          section_tag=5, transf_tag=3, integration_tag=2)
    d = a.to_dict()
    assert d["section_tag"] == 5
    assert d["transf_tag"] == 3
    assert d["integration_tag"] == 2


def test_element_assignment_gmsh_type_6_bbarbrick():
    """gmsh_type 6 (Prism) ora supportato con bbarBrick."""
    a = ElementAssignment(entity_id=3, model_name="m", element_ids=[20, 21],
                          gmsh_type=6, material_tag=2)
    assert a.gmsh_type == 6
    assert ElementAssignment.COMMANDS[6] == "bbarBrick"


# =============================================================================
# 4. ParameterBinding - esteso con target_type
# =============================================================================

def test_parameter_binding_element():
    """ParameterBinding per element (backward-compat)."""
    pb = ParameterBinding(tag=1, target_type="element",
                          target_id=10, path="E")
    tcl = pb.to_tcl()
    assert "parameter 1 element 10 E;" == tcl
    # Backward-compat: .element_id
    assert pb.element_id == 10


def test_parameter_binding_node():
    """ParameterBinding per node disp dof."""
    pb = ParameterBinding(tag=2, target_type="node",
                          target_id=5, dof=2)
    tcl = pb.to_tcl()
    assert "parameter 2 node 5 disp 2;" == tcl
    # Per nodi, .element_id ritorna 0 (non applicabile)
    assert pb.element_id == 0


def test_parameter_binding_pattern():
    pb = ParameterBinding(tag=3, target_type="pattern", target_id=1)
    tcl = pb.to_tcl()
    assert "lambda" in tcl


def test_parameter_binding_blank():
    pb = ParameterBinding(tag=4, target_type="blank", value=2.0e11)
    tcl = pb.to_tcl()
    assert "parameter 4 2" in tcl


def test_parameter_binding_serialization_roundtrip():
    """La serializzazione a dict e da dict deve preservare lo stato."""
    pb = ParameterBinding(tag=5, target_type="element",
                          target_id=20, path="rho")
    d = pb.to_dict()
    pb2 = ParameterBinding(**d)
    assert pb2.target_type == "element"
    assert pb2.target_id == 20
    assert pb2.path == "rho"


def test_set_parameter_command():
    """setParameter -val value -eleRange start end paramName."""
    sp = SetParameterCommand(value=2.1e11, parameter_name="E",
                              element_range=(1, 100))
    tcl = sp.to_tcl()
    assert "setParameter" in tcl
    assert "-eleRange 1 100" in tcl
    assert " E;" in tcl


def test_update_materials_command():
    """updateMaterials -material matTag paramName value."""
    um = UpdateMaterialsCommand(material_tag=2, parameter_name="soilState",
                                  value=1.0)
    tcl = um.to_tcl()
    assert "updateMaterials -material 2 soilState 1" in tcl


# =============================================================================
# 5. Sezioni, geomTransf, beamIntegration, rayleigh, mass, region, eleLoad
# =============================================================================

def test_section_elastic():
    sec = SectionDefinition(1, "WSection", "Elastic",
                             [2.1e11, 0.01, 8.33e-6, 8.33e-6, 7.7e10, 1.0e-5])
    tcl = sec.to_tcl()
    assert "section Elastic 1" in tcl


def test_section_fiber_with_fibers():
    """Section Fiber con patch/layer/fiber."""
    sec = SectionDefinition(2, "FiberSec", "Fiber", [1.0e5],
                            fibers=[
                                {"type": "patch", "sub_type": "rect",
                                 "mat_tag": 1, "params": [0.0, 0.1, 0.0, 0.1]},
                                {"type": "fiber", "y": 0.0, "z": 0.05,
                                 "area": 1.0e-4, "mat_tag": 2},
                            ])
    tcl = sec.to_tcl()
    assert "section Fiber 2" in tcl
    assert "patch rect" in tcl
    assert "fiber" in tcl


def test_geom_transf_linear_3d():
    gt = GeomTransfDefinition(1, "Tr1", "Linear", ndm=3,
                               vecxz=(0.0, 0.0, 1.0))
    tcl = gt.to_tcl()
    assert "geomTransf Linear 1 0 0 1" in tcl


def test_beam_integration_lobatto():
    bi = BeamIntegrationDefinition(1, "BI", "Lobatto", n_points=5, sec_tag=1)
    tcl = bi.to_tcl()
    assert "beamIntegration Lobatto 1 5 1" in tcl


def test_rayleigh_damping():
    rd = RayleighDamping(0.5, 0.0, 0.001, 0.0)
    tcl = rd.to_tcl()
    assert "rayleigh 0.5 0 0.001 0" in tcl


def test_nodal_mass():
    nm = NodalMass(node_tag=1, mass_values=[1.0, 1.0, 1.0])
    tcl = nm.to_tcl()
    assert "mass 1 1 1 1" in tcl


def test_region_with_rayleigh():
    rd = RayleighDamping(0.1, 0.0, 0.0, 0.0)
    r = Region(1, "Base", element_ids=[1, 2, 3, 4], rayleigh=rd)
    tcl = r.to_tcl()
    assert "region 1 -ele 1 2 3 4 -rayleigh" in tcl


def test_element_load_beam_uniform():
    el = ElementLoad("-beamUniform", name="W1",
                     element_ids=[10, 11, 12],
                     values=[1.0e4, 0.0, 0.0])
    tcl = el.to_tcl()
    assert "eleLoad" in tcl
    assert "-type beamUniform" in tcl
    assert "-ele 10 11 12" in tcl


# =============================================================================
# 6. OpenSeesManager - nuove API
# =============================================================================

def test_manager_add_section():
    doc = CADDocument("Test")
    sec = doc.opensees.add_section("WSection", "Elastic",
                                     [2.1e11, 0.01, 8.33e-6])
    assert sec.tag == 1
    assert len(doc.opensees.sections) == 1


def test_manager_add_geom_transf():
    doc = CADDocument("Test")
    gt = doc.opensees.add_geom_transf("Tr1", "Linear", ndm=3)
    assert gt.tag == 1
    assert len(doc.opensees.geom_transfs) == 1


def test_manager_set_rayleigh():
    doc = CADDocument("Test")
    rd = doc.opensees.set_rayleigh(0.5, 0.0, 0.001, 0.0)
    assert rd.alpha_m == 0.5
    assert doc.opensees.rayleigh is not None


def test_manager_add_nodal_mass():
    doc = CADDocument("Test")
    nm = doc.opensees.add_nodal_mass(1, [1.0, 1.0, 1.0])
    assert nm.node_tag == 1
    assert len(doc.opensees.nodal_masses) == 1


def test_manager_add_region():
    doc = CADDocument("Test")
    r = doc.opensees.add_region("Base", element_ids=[1, 2, 3])
    assert r.tag == 1
    assert len(doc.opensees.regions) == 1


def test_manager_add_element_load():
    doc = CADDocument("Test")
    el = doc.opensees.add_element_load("-beamUniform",
                                        element_ids=[10, 11, 12],
                                        values=[1.0e4, 0.0, 0.0])
    assert el.load_type == "-beamUniform"
    assert len(doc.opensees.element_loads) == 1


def test_manager_add_set_parameter():
    doc = CADDocument("Test")
    sp = doc.opensees.add_set_parameter(2.1e11, "E",
                                         element_range=(1, 100))
    assert len(doc.opensees.set_parameters) == 1


def test_manager_add_update_materials():
    doc = CADDocument("Test")
    um = doc.opensees.add_update_materials(1, "soilState", 1.0)
    assert um.material_tag == 1
    assert len(doc.opensees.update_materials_cmds) == 1


def test_manager_global_parameters():
    doc = CADDocument("Test")
    doc.opensees.set_global_parameter("E0", 2.1e11)
    doc.opensees.update_global_parameters({"fy": 3.45e8, "E0": 2.0e11})
    assert doc.opensees.global_parameters["E0"] == 2.0e11
    assert doc.opensees.global_parameters["fy"] == 3.45e8


def test_manager_add_parameter_node():
    """add_parameter con target_type='node' (esteso)."""
    doc = CADDocument("Test")
    pb = doc.opensees.add_parameter(target_type="node", target_id=5, dof=2)
    assert pb.target_type == "node"
    assert pb.target_id == 5


def test_manager_update_parameter_string():
    """update_parameter ritorna il comando Tcl corretto."""
    doc = CADDocument("Test")
    # Aggiungo un binding parameter -> elemento dummy (simulato)
    doc.opensees.parameter_bindings.append(
        ParameterBinding(tag=1, target_type="blank", value=0.0)
    )
    cmd = doc.opensees.update_parameter(1, 2.5e11)
    assert "updateParameter 1 250000000000" in cmd


def test_manager_to_dict_includes_new_fields():
    """La serializzazione del manager include i nuovi campi."""
    doc = CADDocument("Test")
    doc.opensees.set_rayleigh(0.5, 0.0, 0.001, 0.0)
    doc.opensees.add_section("S", "Elastic", [1.0, 2.0, 3.0])
    d = doc.opensees.to_dict()
    assert "rayleigh" in d
    assert "sections" in d
    assert "geom_transfs" in d
    assert "beam_integrations" in d
    assert "nodal_masses" in d
    assert "regions" in d
    assert "element_loads" in d
    assert "set_parameters" in d
    assert "update_materials_cmds" in d
    assert "global_parameters" in d


def test_manager_from_dict_roundtrip_with_new_fields():
    """from_dict ricrea correttamente i nuovi campi."""
    doc = CADDocument("Test")
    doc.opensees.set_rayleigh(0.5, 0.0, 0.001, 0.0)
    doc.opensees.add_section("S", "Elastic", [2.1e11, 0.01, 8.33e-6])
    doc.opensees.add_geom_transf("Tr1", "Linear", ndm=3)
    doc.opensees.add_nodal_mass(1, [1.0, 1.0, 1.0])
    doc.opensees.add_region("Base", element_ids=[1, 2])
    d = doc.opensees.to_dict()

    doc2 = CADDocument("Test2")
    doc2.opensees = OpenSeesManager.from_dict(doc2, d)
    assert doc2.opensees.rayleigh is not None
    assert doc2.opensees.rayleigh.alpha_m == 0.5
    assert len(doc2.opensees.sections) == 1
    assert doc2.opensees.sections[0].model == "Elastic"
    assert len(doc2.opensees.geom_transfs) == 1
    assert len(doc2.opensees.nodal_masses) == 1
    assert len(doc2.opensees.regions) == 1


# =============================================================================
# 7. Backward-compat serializzazione
# =============================================================================

def test_manager_from_dict_old_format_parameter_binding():
    """Il vecchio formato di ParameterBinding deve ancora deserializzarsi."""
    doc = CADDocument("Test")
    old_format = {
        "parameter_bindings": [
            {"tag": 1, "element_id": 10, "path": "E"}
        ]
    }
    mgr = OpenSeesManager.from_dict(doc, old_format)
    assert len(mgr.parameter_bindings) == 1
    pb = mgr.parameter_bindings[0]
    assert pb.target_type == "element"
    assert pb.target_id == 10
    assert pb.path == "E"
    assert pb.element_id == 10  # backward-compat property


def test_manager_from_dict_old_format_element_assignment():
    """Il vecchio formato di ElementAssignment (senza section_tag ecc.)."""
    doc = CADDocument("Test")
    old_format = {
        "element_assignments": [
            {"entity_id": 1, "model_name": "m", "element_ids": [1, 2],
             "gmsh_type": 1, "material_tag": 1, "area": 0.01,
             "thickness": 1.0, "plane_type": "PlaneStress"}
        ]
    }
    mgr = OpenSeesManager.from_dict(doc, old_format)
    assert len(mgr.element_assignments) == 1
    assert mgr.element_assignments[0].area == 0.01


# =============================================================================
# 8. PhaseManager - bridge a OpenSeesManager.stages
# =============================================================================

def test_phase_to_solver_settings():
    sp = SolverPack("Test", analisatore="Static", sistema="SparseSymmetric")
    ph = Phase(1, "Phase 1", solver_pack=sp)
    sol = ph.to_solver_settings()
    assert sol.system == "SparseSYM"
    assert sol.analysis_type == "Static"


def test_phase_to_analysis_stage():
    sp = SolverPack("Test", analisatore="Transient")
    ph = Phase(1, "Phase 1", solver_pack=sp)
    ph.set_update_command("updateMaterialStage",
                           material_tag=1, material_stage=0)
    stage = ph.to_analysis_stage()
    assert stage.name == "Phase 1"
    assert stage.stage_type in ("static", "transient", "gravity")
    assert stage.update_command == "updateMaterialStage"


def test_solver_pack_comandi_opensees_valid_tcl():
    """SolverPack.comandi_opensees() ora genera Tcl valido."""
    sp = SolverPack("Test", analisatore="Static", sistema="SparseSymmetric",
                     params={"tol": 1e-8, "maxIter": 25})
    cmds = sp.comandi_opensees()
    # Ogni comando deve essere valido (non più `solver ...` o `test Linear NormUnf ...`)
    for cmd in cmds:
        assert not cmd.startswith("solver "), f"Tcl invalido: {cmd}"
    # I comandi chiave devono essere presenti
    full = "\n".join(cmds)
    assert "constraints " in full
    assert "numberer " in full
    assert "system " in full
    assert "test " in full
    assert "algorithm " in full
    assert "integrator " in full
    assert "analysis " in full
    assert "analyze " in full


def test_phase_manager_bridge_to_stages():
    """bridge_to_stages sincronizza PhaseManager con OpenSeesManager.stages."""
    doc = CADDocument("Test")
    pm = PhaseManager()
    pm.add_phase("Fase 1", solver_pack=SolverPack("Static",
                                                   analisatore="Static"))
    pm.add_phase("Fase 2", solver_pack=SolverPack("Transient",
                                                   analisatore="Transient"))
    pm.bridge_to_stages(doc.opensees)
    # Ora OpenSeesManager.stages deve avere 2 fasi
    assert len(doc.opensees.stages) == 2
    assert doc.opensees.stages[0].name == "Fase 1"
    assert doc.opensees.stages[1].name == "Fase 2"
    assert doc.opensees.multi_stage is True


def test_phase_manager_bridge_no_phases_keeps_defaults():
    """Se non ci sono fasi, bridge non modifica gli stages di default."""
    doc = CADDocument("Test")
    pm = PhaseManager()
    n_default = len(doc.opensees.stages)
    pm.bridge_to_stages(doc.opensees)
    assert len(doc.opensees.stages) == n_default


def test_phase_add_remove_elements():
    """Phase.add_elements / remove_elements gestiscono l'update_model."""
    ph = Phase(1, "P1")
    ph.add_elements(1, 2, 3)
    assert set(ph.update_model["add_elements"]) == {1, 2, 3}
    ph.remove_elements(2)
    assert 2 not in ph.update_model["add_elements"]
    assert 2 in ph.update_model["remove_elements"]


def test_phase_set_update_command_validates():
    """set_update_command rifiuta comandi non validi."""
    ph = Phase(1, "P1")
    with pytest.raises(ValueError):
        ph.set_update_command("invalid_command")
    # Comandi validi
    for cmd in ("none", "updateMaterialStage", "updateParameter",
                "updateMaterials", "setParameter"):
        ph.set_update_command(cmd)


def test_phase_serialization_roundtrip_with_new_fields():
    """Phase serializza/deserializza con i nuovi campi update_command ecc."""
    ph = Phase(1, "P1")
    ph.set_update_command("updateMaterialStage",
                           material_tag=2, material_stage=1)
    ph.add_elements(1, 2)
    d = ph.to_dict()
    ph2 = Phase.from_dict(d)
    assert ph2.update_command == "updateMaterialStage"
    assert ph2.material_tag == 2
    assert ph2.material_stage == 1
    assert set(ph2.update_model["add_elements"]) == {1, 2}
