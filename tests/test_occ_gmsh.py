"""Test con OpenCASCADE e Gmsh (skip automatici se non installati):
builder, editor, booleane, selettori geometrici, macro con shape vere,
round-trip STEP -> mesh gmsh -> import .msh."""

import os

import pytest

from gcs.core.document import CADDocument

occ = pytest.importorskip("gcs.core.occ_utils")
if not occ.HAS_OCC:
    pytest.skip("pythonocc-core non installato", allow_module_level=True)

from gcs.core.builder import GeometryBuilder          # noqa: E402
from gcs.core.editors import GeometryEditor           # noqa: E402
from gcs.core import selectors as sel                 # noqa: E402
from gcs.core import gmsh_bridge as gb                # noqa: E402
from gcs.core.macro_engine import MacroEngine         # noqa: E402


@pytest.fixture
def doc():
    return CADDocument("Test OCC")


@pytest.fixture
def builder(doc):
    return GeometryBuilder(doc)


@pytest.fixture
def editor(doc):
    return GeometryEditor(doc)


# -------------------------------------------------------------------- builder
def test_punto_curva(builder, doc):
    p = builder.punto(1, 2, 3)
    assert p.etype == "point"
    assert occ.vertex_point(p.shape)[:2] == (1.0, 2.0)
    l = builder.linea((0, 0, 0), (10, 0, 0))
    assert occ.length_of(l.shape) == pytest.approx(10.0)
    s = builder.spline([(0, 0, 0), (5, 3, 0), (10, 0, 0)])
    assert len(s.meta["ctrl_points"]) == 3


def test_superfici(builder):
    sup = builder.superficie_da_punti([(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)])
    assert occ.area_of(sup.shape) == pytest.approx(100.0)
    cerchio = builder.cerchio(0, 0, 0, 5)
    assert occ.length_of(cerchio.shape) == pytest.approx(2 * 3.1415926535 * 5, rel=1e-3)


def test_solidi_e_booleane(builder, editor, doc):
    box = builder.box(10, 10, 10)
    assert occ.volume_of(box.shape) == pytest.approx(1000.0)
    cil = builder.cilindro(2, 20, base=(-1, 5, -5))
    tagliato = editor.taglia(box.id, cil.id, mantieni=True)
    v = occ.volume_of(tagliato.shape)
    assert v < 1000 and v > 900
    # fusione
    b2 = builder.box(10, 10, 10, base=(10, 0, 0))
    fusa = editor.fusa([tagliato.id, b2.id], mantieni=True)
    assert occ.volume_of(fusa.shape) > v
    # raccordo e smusso su un box semplice (tutti gli spigoli)
    b3 = builder.box(10, 10, 10)
    editor.raccorda(b3.id, raggio=0.5)
    assert occ.volume_of(b3.shape) < 1000.0
    b4 = builder.box(10, 10, 10)
    editor.smussa(b4.id, distanza=0.5)
    assert occ.volume_of(b4.shape) < 1000.0
    # esplodi
    facce = editor.esplodi([fusa.id], "face")
    assert len(facce) >= 6
    assert facce[0].etype == "face"


def test_estrudi_e_revolve(builder, doc):
    sup = builder.superficie_da_punti([(0, 0, 0), (5, 0, 0), (5, 5, 0), (0, 5, 0)])
    sol = builder.estrudi(sup.id, 0, 0, 8)
    assert occ.volume_of(sol.shape) == pytest.approx(200.0)
    # profilo L 2D su XZ revolto attorno a Z
    prof = builder.superficie_da_punti([(2, 0, 0), (4, 0, 0), (4, 0, 2), (2, 0, 2)])
    toroide = builder.rivolgi(prof.id, 0, 0, 0, 0, 0, 1, angolo_deg=360)
    assert occ.volume_of(toroide.shape) == pytest.approx(
        3.14159 * (4 * 4 - 2 * 2) * 2, rel=1e-3)


# ------------------------------------------------------------------ selettori
def test_selettori_geometrici(builder, editor, doc):
    b1 = builder.box(10, 10, 10)
    b2 = builder.box(10, 10, 10, base=(20, 0, 0))
    editor.fusa([b1.id, b2.id], mantieni=True)
    sel.select_by_type(doc, "solid")
    assert len(doc.selection) == 3
    # per dimensione: solo i box unitari (volume 1000)
    sel.select_by_size(doc, "solido", 0, 1000)
    assert len(doc.selection) == 2
    # box di selezione
    sel.select_box(doc, -1, -1, -1, 15, 15, 15)
    assert len(doc.selection) == 1          # solo b1
    sel.select_box(doc, -1, -1, -1, 15, 15, 15, inside=False)
    assert len(doc.selection) >= 2
    # superfici piane del fusione
    facce = doc.query().type("face")
    fusa = [e for e in doc.entities.values() if e.name.startswith("Fusione")][0]
    doc.set_selection([fusa.id])
    sel.select_faces_of(doc)
    piane = sel.select_planar(doc)
    assert len(piane) >= 8                  # box unitario ha facce piane
    # per normale +Z
    doc.set_selection([fusa.id])
    sel.select_faces_of(doc)
    sel.select_by_normal(doc, 0, 0, 1, tol_deg=10)
    assert len(doc.selection) >= 1


def test_undo_trasla(builder, editor):
    b = builder.box(10, 10, 10)
    v0 = occ.center_of(b.shape)
    editor.trasla([b.id], 5, 0, 0)
    v1 = occ.center_of(b.shape)
    assert v1[0] == pytest.approx(v0[0] + 5)
    doc = builder.doc
    doc.undo()
    assert occ.center_of(b.shape)[0] == pytest.approx(v0[0])


def test_macro_con_shape_vera(builder, editor, doc):
    """Macro che sostituisce la geometria di ogni superficie selezionata."""
    box = builder.box(10, 10, 10)
    doc.set_selection([box.id])
    sel.select_faces_of(doc)
    n_facce = len(doc.selection)

    from gcs.core.macro_engine import macro, P
    from gcs.core import occ_utils as ou

    @macro(nome="Colore e meta", applies_to=("superficie",),
           params=[P("spessore", "float", default=1.0)])
    def run(ctx, target, params):
        area = ou.area_of(target.shape)
        target.entity.meta["area_calcolata"] = round(area, 3)
        ctx.log(f"{target.label}: {area:.2f}")

    engine = MacroEngine(doc, log=print)
    engine.register(run.__macro_spec__)
    ctx = engine.run(engine.by_name("Colore e meta"), {"spessore": 2.0})
    assert ctx.ok == n_facce and not ctx.errors
    marcate = [e for e in doc.entities.values() if "area_calcolata" in e.meta]
    assert len(marcate) == n_facce


# -------------------------------------------------------------- gmsh roundtrip
def test_roundtrip_step_gmsh_msh(builder, editor, doc, tmp_path):
    pytest.importorskip("gmsh")
    step = os.path.join(str(tmp_path), "modello.step")
    msh = os.path.join(str(tmp_path), "modello.msh")

    box = builder.box(20, 20, 20)
    cil = builder.cilindro(4, 30, base=(5, 5, -5))
    editor.taglia(box.id, cil.id)
    doc.export_step(step)
    assert os.path.exists(step)

    stats = gb.mesh_step(step, msh, clmax=6.0, clmin=1.0, msh_version="4.1")
    assert os.path.exists(msh)

    from gcs.core.msh_importer import parse_msh
    model = parse_msh(msh)
    assert len(model.nodes) > 50
    assert any(d == 3 for (d, _) in model.blocks)

    # reimport nel documento -> entità blocchi
    doc2 = CADDocument("re")
    doc2.import_msh(msh)
    assert len(doc2.entities) >= 1

    # export 2.2 con gruppi fisici e rilettura
    out22 = os.path.join(str(tmp_path), "out22.msh")
    gb.export_msh_22(model, out22)
    model22 = parse_msh(out22)
    assert len(model22.nodes) == len(model.nodes)


def test_read_step_import(builder, doc, tmp_path):
    step = os.path.join(str(tmp_path), "imp.step")
    builder.box(5, 5, 5)
    doc.export_step(step)
    doc2 = CADDocument("import")
    enti = doc2.import_cad(step)
    assert len(enti) == 1
    assert occ.volume_of(enti[0].shape) == pytest.approx(125.0)
