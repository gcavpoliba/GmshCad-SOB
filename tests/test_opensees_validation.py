from gcs.core.document import CADDocument
from gcs.core.fases import ElementProperty
from gcs.core.opensees_conditions import ElementAssignment


def test_validate_model_requires_complete_element_assignments():
    doc = CADDocument("validation")
    model = type("M", (), {})()
    model.name = "m"
    model.nodes = {
        1: (0.0, 0.0, 0.0), 2: (1.0, 0.0, 0.0),
        3: (1.0, 1.0, 0.0), 4: (0.0, 1.0, 0.0),
    }
    model.elements = {10: (3, [1, 2, 3, 4])}
    model.blocks = {(2, 1): type("B", (), {"element_ids": [10]})()}
    model.physicals = {}

    from gcs.core.entities import Entity
    ent = Entity("face", None, "Surface 1")
    ent.meta["mesh_ref"] = ("m", 2, 1)
    doc.entities[ent.id] = ent
    doc.mesh_models["m"] = model

    doc.opensees.ndm = 2
    doc.opensees.ndf = 2
    doc.opensees.add_material(
        "Elastic", "ElasticIsotropic", [30000.0, 0.2, 0.0]
    )
    report = doc.opensees.validate_model(model)
    assert not report["valid"]
    assert any("senza proprieta assegnata" in e for e in report["errors"])

    doc.opensees.element_assignments.append(
        ElementAssignment(
            entity_id=ent.id,
            model_name="m",
            element_ids=[10],
            gmsh_type=3,
            material_tag=1,
            thickness=1.0,
            plane_type="PlaneStrain",
        )
    )
    report = doc.opensees.validate_model(model)
    assert report["valid"], report["errors"]


def test_validate_model_rejects_dangling_parameter_target():
    doc = CADDocument("parameter")
    from gcs.core.opensees_conditions import ParameterBinding
    doc.opensees.parameter_bindings.append(
        ParameterBinding(tag=1, target_type="element", target_id=999, path="E")
    )
    model = type("M", (), {
        "name": "m",
        "nodes": {},
        "elements": {},
        "blocks": {},
        "physicals": {},
    })()
    doc.mesh_models["m"] = model
    report = doc.opensees.validate_model(model)
    assert not report["valid"]
    assert any("Parameter 1" in e for e in report["errors"])


def test_remove_interface_api():
    doc = CADDocument("interface")
    doc.opensees.interfaces.append(type("I", (), {
        "secondary_nodes": [1, 2],
        "primary_nodes": [3, 4],
        "kn": 100.0,
        "kt": 10.0,
        "model_name": "m",
    })())
    assert doc.opensees.remove_interface(0)
    assert doc.opensees.interfaces == []
