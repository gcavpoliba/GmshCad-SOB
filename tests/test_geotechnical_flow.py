from gcs.core.geotech_catalog import (
    GEOTECH_ELEMENTS,
    GEOTECH_ND_MATERIALS,
    GEOTECH_UNIAXIAL,
    geotech_element_options,
    is_up_element,
)
from gcs.core.opensees_conditions import ElementAssignment
from gcs.core.opensees_flow import FlowCommand, FlowPhase, OpenSeesFlow


def test_geotechnical_up_catalog_is_present():
    required_elements = {
        "quadUP", "bbarQuadUP", "9_4_QuadUP", "SSPquadUP",
        "brickUP", "bbarBrickUP", "20_8_BrickUP", "SSPbrickUP",
    }
    assert required_elements.issubset(GEOTECH_ELEMENTS)
    assert {"PressureDependMultiYield02", "PressureDependMultiYield03",
            "PM4Sand", "PM4Silt", "ManzariDafalias",
            "FluidSolidPorousMaterial"}.issubset(GEOTECH_ND_MATERIALS)
    assert {"PyLiq1", "TzLiq1", "QzLiq1"}.issubset(GEOTECH_UNIAXIAL)


def test_up_direct_mesh_options_are_conservative():
    assert "quadUP" in geotech_element_options(3)
    assert "9_4_QuadUP" in geotech_element_options(10)
    assert "brickUP" in geotech_element_options(5)
    # Gmsh 6 is a six-node prism: never silently map it to an eight-node brick.
    assert geotech_element_options(6) == []
    assert 6 not in ElementAssignment.COMMANDS


def test_explicit_up_assignment_persists():
    assignment = ElementAssignment(
        7, "mesh", [11, 12, 13, 14], 3, 2,
        thickness=1.0,
        element_command="quadUP",
        element_args="1.0 {matTag} 2.2e6 1000 1e-5 1e-5 0 0 0",
    )
    assert assignment.effective_command() == "quadUP"
    assert assignment.is_up
    restored = ElementAssignment(**assignment.to_dict())
    assert restored.effective_command() == "quadUP"
    assert "{matTag}" in restored.element_args


def test_flow_supports_editable_order_and_custom_tcl():
    flow = OpenSeesFlow()
    phase = flow.get_phase(1)
    assert phase is not None
    cmd_a = flow.add_custom(1, "Vincolo base", "fix 1 1 1 1;")
    cmd_b = flow.add_custom(1, "Attivazione", "updateMaterialStage -material 2 -stage 1;")
    assert flow.move_command(1, 1, -1)
    assert phase.commands[-2:] == [cmd_b, cmd_a]
    assert flow.remove_command(1, 0) is True


def test_flow_serialization_preserves_edits():
    flow = OpenSeesFlow()
    cmd = flow.add_custom(1, "Comando Tcl", "set K 10;")
    cmd.enabled = False
    cmd.overridden = True
    phase = flow.get_phase(1)
    phase.name = "Sisma - fase dinamica"
    phase.name_overridden = True
    restored = OpenSeesFlow.from_dict(flow.to_dict())
    rcmd = next(c for c in restored.get_phase(1).commands if c.label == "Comando Tcl")
    assert rcmd.tcl == "set K 10;"
    assert not rcmd.enabled
    assert rcmd.overridden
    assert restored.get_phase(1).name == "Sisma - fase dinamica"
    assert restored.get_phase(1).name_overridden


def test_up_element_identification():
    assert is_up_element("quadUP")
    assert is_up_element("brickUP")
    assert not is_up_element("stdBrick")


def test_gmsh_topology_catalog_includes_20_node_hex():
    from gcs.core.mesh import ELEM_INFO
    assert ELEM_INFO[17][0] == "esaedro20"
    assert ELEM_INFO[17][1] == 20
    assert ELEM_INFO[17][2] == 8


def test_geotechnical_liquefaction_schemas_are_complete():
    assert len(GEOTECH_ND_MATERIALS["PressureDependMultiYield03"]["params"]) == 23
    assert len(GEOTECH_UNIAXIAL["PyLiq1"]["params"]) == 8
    assert len(GEOTECH_UNIAXIAL["TzLiq1"]["params"]) == 6
    assert len(GEOTECH_UNIAXIAL["QzLiq1"]["params"]) == 8


def test_explicit_standard_20_node_brick_is_allowed():
    assignment = ElementAssignment(
        7, "mesh", [11], 17, 2, element_command="20NodeBrick"
    )
    assert assignment.effective_command() == "20NodeBrick"
