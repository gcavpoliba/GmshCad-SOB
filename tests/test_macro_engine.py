"""Test del motore macro: registrazione, parametri, applicazione per bersagli,
creazione di nuove entità e gestione errori."""

import pytest

from gcs.core.document import CADDocument
from gcs.core.entities import Entity
from gcs.core.macro_engine import (MacroEngine, macro, P, Param,
                                   normalize_target, MacroSpec)
from gcs.core.mesh import MeshModel


@pytest.fixture
def doc():
    d = CADDocument("Test macro")
    # "superfici" fittizie senza OCC (shape None) per testare il dispatch sui
    # bersagli mesh; per i bersagli geometrici servono shape -> test OCC a parte
    model = MeshModel("m1")
    for i in range(1, 11):
        model.add_node(i, float(i), 0.0, 0.0)
    for i in range(1, 5):
        model.add_element(i, 1, [i, i + 1], (1, 1))
    d.mesh_models["m1"] = model
    return d


def test_param_coerce():
    p = Param("x", "float", default=1.0, min=0.0, max=10.0)
    assert p.coerce("3.5") == 3.5
    assert p.coerce(99) == 10.0        # clamp al massimo
    p2 = Param("n", "int", default=2)
    assert p2.coerce(3.7) == 4
    p3 = Param("s", "choice", default="A", choices=("A", "B"))
    assert p3.coerce("B") == "B"
    with pytest.raises(ValueError):
        p3.coerce("Z")
    p4 = Param("v", "vec3", default=(0, 0, 0))
    assert p4.coerce("1, 2, 3") == (1.0, 2.0, 3.0)


def test_normalize_target():
    assert normalize_target("superficie") == "face"
    assert normalize_target("nodo_mesh") == "mesh_node"
    assert normalize_target("entita") == "entity"
    with pytest.raises(ValueError):
        normalize_target("xyz")


def test_macro_su_nodi_mesh(doc, capsys):
    @macro(nome="Jitter test", applies_to=("nodo_mesh",),
           params=[P("k", "float", default=1.0)])
    def run(ctx, target, params):
        x, y, z = target.model.nodes[target.node_id]
        target.model.nodes[target.node_id] = (x, y, z + params["k"])

    engine = MacroEngine(doc, log=print)
    engine.register(run.__macro_spec__)
    doc.mesh_models["m1"].select_nodes_in_box((0, -1, -1, 5, 1, 1))
    spec = engine.by_name("Jitter test")
    ctx = engine.run(spec, {"k": 2.0})
    assert ctx.ok == 5                    # nodi 1..5 nel box
    assert doc.mesh_models["m1"].nodes[3][2] == 2.0


def test_macro_parametri_default(doc):
    visti = []

    @macro(nome="Default test", applies_to=("mesh_node",),
           params=[P("saluto", "str", default="ciao")])
    def run(ctx, target, params):
        visti.append(params["saluto"])

    engine = MacroEngine(doc, log=print)
    engine.register(run.__macro_spec__)
    doc.mesh_models["m1"].select_all_nodes()
    engine.run(engine.by_name("Default test"), {})
    assert visti == ["ciao"] * 10


def test_macro_errori_per_bersaglio(doc):
    @macro(nome="Errore test", applies_to=("mesh_element",))
    def run(ctx, target, params):
        if target.element_id == 2:
            raise ValueError("boom")
        return None

    engine = MacroEngine(doc, log=print)
    engine.register(run.__macro_spec__)
    doc.mesh_models["m1"].select_all_elements()
    ctx = engine.run(engine.by_name("Errore test"), {})
    assert ctx.ok == 3
    assert len(ctx.errors) == 1
    assert "boom" in ctx.errors[0][1]


def test_macro_nessun_bersaglio(doc):
    @macro(nome="Vuoto test", applies_to=("nodo_mesh",))
    def run(ctx, target, params):
        pass

    engine = MacroEngine(doc, log=print)
    engine.register(run.__macro_spec__)
    ctx = engine.run(engine.by_name("Vuoto test"), {})
    assert ctx.ok == 0 and ctx.errors == []


def test_load_folder_macro_real(doc):
    """Carica le macro vere del progetto e verifica la registrazione."""
    import os
    cartella = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "gcs", "macros")
    engine = MacroEngine(doc, log=print)
    n = engine.load_folder(cartella)
    assert n >= 5
    nomi = engine.list_names()
    assert "Trasla punti" in nomi
    assert "Perturba nodi" in nomi
    assert "Marca per area" in nomi
    spec = engine.by_name("Perturba nodi")
    assert any(p.name == "raggio" for p in spec.params)
    # esegui Perturba nodi con seed fisso su tutti i nodi
    doc.mesh_models["m1"].select_all_nodes()
    ctx = engine.run(spec, {"raggio": 0.1, "seed": 7})
    assert ctx.ok == 10 and not ctx.errors


def test_write_template(tmp_path):
    from gcs.core.macro_engine import write_macro_template
    path = str(tmp_path / "nuova_macro.py")
    write_macro_template(path, "Prova")
    testo = open(path, encoding="utf-8").read()
    assert "@macro(" in testo and "def run(ctx, target, params)" in testo
    # il template deve caricarsi senza errori
    engine = MacroEngine(CADDocument("T"), log=print)
    engine._load_file(path)
    assert not engine.load_errors
