"""Test di gruppi, documento e selettori a livello entità (senza OCC)."""

import pytest

from gcs.core.document import CADDocument
from gcs.core.entities import Entity, normalize_type
from gcs.core.groups import GroupError
from gcs.core import selectors as sel
from gcs.core.selection_manager import SelectionManager
from gcs.core.visibility_manager import VisibilityManager


@pytest.fixture
def doc():
    d = CADDocument("Test")
    for i in range(5):
        e = Entity("point", name=f"Punto {i + 1}")
        e.meta["mesh_ref"] = ("m", 0, i + 1)  # li rende "blocchi mesh" fittizi
        d.add_entity(e, push_undo=False)
    for i in range(4):
        d.add_entity(Entity("face", name=f"Sup {i + 1}"), push_undo=False)
    for i in range(2):
        d.add_entity(Entity("solid", name=f"Sol {i + 1}"), push_undo=False)
    return d


def test_normalizza_tipi():
    assert normalize_type("superficie") == "face"
    assert normalize_type("curva") == "curve"
    assert normalize_type("solido") == "solid"
    assert normalize_type("volume") == "solid"
    assert normalize_type("punto") == "point"
    with pytest.raises(ValueError):
        normalize_type("ciccia")


def test_undo_redo_add_remove(doc):
    e = Entity("curve", name="Temp")
    doc.add_entity(e)
    assert len(doc.entities) == 12
    doc.undo()
    assert len(doc.entities) == 11 and e.id not in doc.entities
    doc.redo()
    assert e.id in doc.entities
    doc.remove_entities([e.id])
    doc.undo()
    assert e.id in doc.entities


def test_selezione_base(doc):
    sel.select_all(doc, types=["face"])
    assert len(doc.selection) == 4
    sel.select_by_type(doc, "solido", mode="add")
    assert len(doc.selection) == 6
    sel.invert_selection(doc)
    assert len(doc.selection) == 5
    sel.select_by_name(doc, "Punto *")
    assert len(doc.selection) == 5
    sel.select_none(doc)
    assert doc.selection == set()


def test_selezione_toggle(doc):
    sel.select_by_type(doc, "face")
    prima = set(doc.selection)
    sel.select_by_type(doc, "face", mode="toggle")
    assert doc.selection == set()
    sel.select_by_type(doc, "face", mode="toggle")
    assert set(doc.selection) == prima


def test_gruppi(doc):
    sel.select_by_type(doc, "face")
    g = doc.groups.group_from_selection(doc, "sface")
    assert g.count_geo() == 4
    with pytest.raises(GroupError):
        doc.groups.create("sface")
    sel.select_by_type(doc, "solid")
    doc.groups.add_geo("sface", doc.selection)
    assert doc.groups.get("sface").count_geo() == 6
    doc.groups.rename("sface", "tutto")
    assert doc.groups.get("tutto") is not None
    sel.select_by_group(doc, "tutto")
    assert len(doc.selection) == 6
    doc.groups.delete("tutto")
    assert doc.groups.list_names() == []
    # export testuale
    doc.groups.add_geo("g1", [1, 2])
    testo = doc.groups.export_text(doc)
    assert "g1" in testo


def test_query_fluente(doc):
    ids = doc.query().type("point").ids()
    assert len(ids) == 5
    # in_sphere usa il centro dei blocchi mesh fittizi (da mesh_ref inesistente
    # qui: il modello 'm' non esiste -> centro None -> nessuna selezione)
    assert doc.query().type("solid").ids() == set(doc.query().type("solid").ids())


def test_selection_manager_unificato(doc):
    manager = SelectionManager(doc)
    manager.select(6, context="cad")
    assert manager.selected_entity_ids() == {6}
    manager.add_to_selection([7])
    assert manager.selected_entity_ids() == {6, 7}
    manager.remove_from_selection([6])
    assert manager.selected_entity_ids() == {7}
    manager.clear_selection()
    assert doc.selection == set()
    assert manager.context == "cad"


def test_visibility_manager_separa_cad_da_mesh(doc):
    manager = VisibilityManager(doc)
    face_id = 6
    mesh_id = 1

    manager.set_cad_type_visible("face", False)
    assert not manager.is_entity_visible(doc.entities[face_id])
    assert manager.is_entity_visible(doc.entities[mesh_id])

    manager.set_mesh_visible(False)
    assert not manager.is_entity_visible(doc.entities[mesh_id])
    manager.set_cad_type_visible("face", True)
    assert manager.is_entity_visible(doc.entities[face_id])


def test_mesh_stale_after_geometry_change():
    from gcs.core.document import CADDocument
    from gcs.core.entities import Entity
    from gcs.core.mesh import MeshModel

    doc = CADDocument("stale")
    geom = Entity("solid", shape=object(), name="Solido")
    doc.add_entity(geom, push_undo=False)

    model = MeshModel("mesh")
    model.mark_current(doc.geometry_revision)
    doc.mesh_models[model.name] = model

    doc.replace_entity_shape(geom, object(), push_undo=False)
    assert model.stale is True
    assert model.stale_reason == "modifica geometria"
    assert doc.mesh_status()["mesh"]["stale"] is True


def test_stale_mesh_is_not_visible(doc):
    from gcs.core.mesh import MeshModel
    from gcs.core.visibility_manager import VisibilityManager
    from gcs.core.entities import Entity

    geom = Entity("solid", shape=object(), name="geom")
    doc.add_entity(geom, push_undo=False)
    model = MeshModel("mesh")
    model.mark_current(doc.geometry_revision)
    doc.mesh_models["mesh"] = model

    block = Entity("face", shape=None, name="mesh block")
    block.meta["mesh_ref"] = ("mesh", 2, 1)
    doc.add_entity(block, push_undo=False)

    manager = VisibilityManager(doc)
    assert manager.is_entity_visible(block)

    doc.replace_entity_shape(geom, object(), push_undo=False)
    assert model.stale
    assert not manager.is_entity_visible(block)


def test_documento_mesh_entities(doc):
    """Le entità con mesh_ref hanno nome fisico e marker corretti."""
    e = doc.entities[1]
    assert e.is_mesh_block
    assert e.mesh_ref() == ("m", 0, 1)
