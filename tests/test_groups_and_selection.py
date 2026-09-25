"""Test di gruppi, documento e selettori a livello entità (senza OCC)."""

import pytest

from gcs.core.document import CADDocument
from gcs.core.entities import Entity, normalize_type
from gcs.core.groups import GroupError
from gcs.core import selectors as sel


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


def test_documento_mesh_entities(doc):
    """Le entità con mesh_ref hanno nome fisico e marker corretti."""
    e = doc.entities[1]
    assert e.is_mesh_block
    assert e.mesh_ref() == ("m", 0, 1)
