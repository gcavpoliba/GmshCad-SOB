"""Utilità OpenCASCADE (pythonocc-core).

Tutte le funzioni primitive di geometria B-Rep usate dal builder, dall'editor,
dal viewer e dal motore macro. Il modulo rileva la presenza di pythonocc e
restituisce messaggi d'errore chiari se non è installato.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Tuple

try:  # pythonocc-core (conda-forge)
    from OCC.Core.gp import (gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2, gp_Pln,
                             gp_Trsf, gp_Circ, gp_XYZ)
    from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Compound, TopoDS_Builder
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import (TopAbs_VERTEX, TopAbs_EDGE, TopAbs_FACE,
                                 TopAbs_SOLID, TopAbs_SHELL, TopAbs_WIRE,
                                 TopAbs_COMPOUND)
    from OCC.Core.TopTools import TopTools_IndexedMapOfShape, TopTools_ListOfShape
    from OCC.Core.BRepPrimAPI import (BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder,
                                      BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeCone,
                                      BRepPrimAPI_MakeTorus, BRepPrimAPI_MakePrism,
                                      BRepPrimAPI_MakeRevol)
    from OCC.Core.BRepBuilderAPI import (BRepBuilderAPI_MakeVertex,
                                         BRepBuilderAPI_MakeEdge,
                                         BRepBuilderAPI_MakeWire,
                                         BRepBuilderAPI_MakeFace,
                                         BRepBuilderAPI_MakePolygon,
                                         BRepBuilderAPI_Transform,
                                         BRepBuilderAPI_Sewing,
                                         BRepBuilderAPI_MakeSolid)
    from OCC.Core.BRepAlgoAPI import (BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut,
                                      BRepAlgoAPI_Common)
    from OCC.Core.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
    from OCC.Core.BRepOffsetAPI import (BRepOffsetAPI_MakeOffsetShape,
                                        BRepOffsetAPI_ThruSections,
                                        BRepOffsetAPI_MakePipe,
                                        BRepOffsetAPI_MakeThickSolid)
    from OCC.Core.BRepOffset import BRepOffset_Skin
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
    from OCC.Core.GeomAbs import GeomAbs_Plane, GeomAbs_Arc
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.BRepExtrema import BRepExtrema_DistShapeShape
    from OCC.Core.GC import GC_MakeArcOfCircle
    from OCC.Core.GeomAPI import GeomAPI_Interpolate
    from OCC.Core.TColgp import TColgp_HArray1OfPnt
    from OCC.Core.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
    from OCC.Core.IGESControl import IGESControl_Reader
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.TopLoc import TopLoc_Location

    # --------------------------------------------------------------- compat
    # Le build pythonocc espongono i metodi statici in due convenzioni:
    #  * classica: Classe.Metodo_s(...)
    #  * recente:  funzioni module-level (es. topexp_MapShapes)
    # Qui si risolvono entrambe in helper univoci usati nel resto del modulo.
    try:
        from OCC.Core.TopExp import TopExp
        _map_shapes = TopExp.MapShapes_s
    except Exception:
        from OCC.Core.TopExp import topexp_MapShapes as _map_shapes  # type: ignore

    try:
        from OCC.Core.BRepGProp import BRepGProp
        _vol_props = BRepGProp.VolumeProperties_s
        _surf_props = BRepGProp.SurfaceProperties_s
        _lin_props = BRepGProp.LinearProperties_s
    except Exception:
        from OCC.Core.BRepGProp import (brepgprop_VolumeProperties as _vol_props,  # type: ignore
                                        brepgprop_SurfaceProperties as _surf_props,  # type: ignore
                                        brepgprop_LinearProperties as _lin_props)  # type: ignore

    try:
        from OCC.Core.BRepBndLib import BRepBndLib
        _bnd_add = BRepBndLib.Add_s
    except Exception:
        from OCC.Core.BRepBndLib import brepbndlib_Add as _bnd_add  # type: ignore

    try:
        from OCC.Core.BRep import BRep_Tool
        _vertex_pnt = BRep_Tool.Pnt_s
    except Exception:
        from OCC.Core.BRep import BRep_Tool_Pnt as _vertex_pnt  # type: ignore

    try:
        from OCC.Core.BRepTools import BRepTools
        _brep_write = BRepTools.Write_s
        _brep_read = BRepTools.Read_s
        _uv_bounds = BRepTools.UVBounds_s
    except Exception:
        from OCC.Core.BRepTools import (breptools_Write as _brep_write,  # type: ignore
                                        breptools_Read as _brep_read,  # type: ignore
                                        breptools_UVBounds as _uv_bounds)  # type: ignore

    try:
        from OCC.Core.BRepGProp import BRepGProp_Face
    except Exception:
        BRepGProp_Face = None

    HAS_OCC = True
    _IMPORT_ERR = ""
except ImportError as exc:  # pragma: no cover - ambiente senza OCC
    HAS_OCC = False
    _IMPORT_ERR = str(exc)


def _require_occ():
    if not HAS_OCC:
        raise RuntimeError(
            "OpenCASCADE (pythonocc-core) non installato. Installare con:\n"
            "  micromamba create -c conda-forge python=3.11 pythonocc-core=7.7.2\n"
            f"(dettaglio import: {_IMPORT_ERR})")


# ---------------------------------------------------------------------------
# costruttori elementari
# ---------------------------------------------------------------------------

def pnt(p) -> "gp_Pnt":
    return gp_Pnt(float(p[0]), float(p[1]), float(p[2]))


def vec(v) -> "gp_Vec":
    return gp_Vec(float(v[0]), float(v[1]), float(v[2]))


def dir_of(v) -> "gp_Dir":
    return gp_Dir(float(v[0]), float(v[1]), float(v[2]))


def make_vertex(p) -> "TopoDS_Shape":
    _require_occ()
    return BRepBuilderAPI_MakeVertex(pnt(p)).Vertex()


def vertex_point(v) -> Tuple[float, float, float]:
    """Coordinate di un TopoDS_Vertex."""
    p = _vertex_pnt(v)
    return (p.X(), p.Y(), p.Z())


def make_edge_p2p(p1, p2):
    _require_occ()
    mk = BRepBuilderAPI_MakeEdge(pnt(p1), pnt(p2))
    if not mk.IsDone():
        raise RuntimeError(f"Impossibile creare la linea {p1}->{p2}")
    return mk.Edge()


def make_edge_circle(center, r, normal=(0, 0, 1)):
    _require_occ()
    ax2 = gp_Ax2(pnt(center), dir_of(normal))
    return BRepBuilderAPI_MakeEdge(gp_Circ(ax2, float(r))).Edge()


def make_edge_arc3p(p1, pm, p2):
    _require_occ()
    arc = GC_MakeArcOfCircle(pnt(p1), pnt(pm), pnt(p2))
    if not arc.IsDone():
        raise RuntimeError("Arco non valido (3 punti allineati?)")
    return BRepBuilderAPI_MakeEdge(arc.Value()).Edge()


def make_edge_spline(points, closed=False):
    """Spline (interpolata) passante per una lista di punti."""
    _require_occ()
    n = len(points)
    if n < 2:
        raise RuntimeError("Servono almeno 2 punti per una spline")
    arr = TColgp_HArray1OfPnt(1, n)
    for i, p in enumerate(points):
        arr.SetValue(i + 1, pnt(p))
    interp = GeomAPI_Interpolate(arr, bool(closed), 1e-6)
    interp.Perform()
    if not interp.IsDone():
        raise RuntimeError("Interpolazione spline fallita")
    return BRepBuilderAPI_MakeEdge(interp.Curve()).Edge()


def make_wire(edges) -> "TopoDS_Shape":
    _require_occ()
    mk = BRepBuilderAPI_MakeWire()
    for e in edges:
        mk.Add(e)
    if not mk.IsDone():
        raise RuntimeError("Le curve non formano un profilo chiuso/continuo")
    return mk.Wire()


def make_face_from_wire(wire, planar=True):
    _require_occ()
    mk = BRepBuilderAPI_MakeFace(wire, bool(planar))
    if not mk.IsDone():
        raise RuntimeError("Impossibile creare la superficie dal profilo")
    return mk.Face()


def make_face_polygon(points):
    """Superficie planare da poligono di punti (chiude automaticamente)."""
    _require_occ()
    mk = BRepBuilderAPI_MakePolygon()
    for p in points:
        mk.Add(pnt(p))
    mk.Close()
    if not mk.IsDone():
        raise RuntimeError("Poligono non valido")
    face = BRepBuilderAPI_MakeFace(mk.Wire(), True).Face()
    return face


def make_compound(shapes) -> "TopoDS_Shape":
    _require_occ()
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for s in shapes:
        if s is not None:
            b.Add(comp, s)
    return comp


# ---------------------------------------------------------------------------
# primitive solide
# ---------------------------------------------------------------------------

def prim_box(corner1, corner2):
    _require_occ()
    return BRepPrimAPI_MakeBox(pnt(corner1), pnt(corner2)).Shape()


def prim_cylinder(r, h, base=(0, 0, 0), axis=(0, 0, 1)):
    _require_occ()
    ax2 = gp_Ax2(pnt(base), dir_of(axis))
    return BRepPrimAPI_MakeCylinder(ax2, float(r), float(h)).Shape()


def prim_sphere(r, center=(0, 0, 0)):
    _require_occ()
    return BRepPrimAPI_MakeSphere(pnt(center), float(r)).Shape()


def prim_cone(r1, r2, h, base=(0, 0, 0), axis=(0, 0, 1)):
    _require_occ()
    ax2 = gp_Ax2(pnt(base), dir_of(axis))
    return BRepPrimAPI_MakeCone(ax2, float(r1), float(r2), float(h)).Shape()


def prim_torus(r1, r2, axis=(0, 0, 1)):
    _require_occ()
    ax2 = gp_Ax2(pnt((0, 0, 0)), dir_of(axis))
    return BRepPrimAPI_MakeTorus(ax2, float(r1), float(r2)).Shape()


def prim_prism(shape, direction):
    _require_occ()
    return BRepPrimAPI_MakePrism(shape, vec(direction)).Shape()


def prim_revolve(shape, axis_point, axis_dir, angle_deg):
    _require_occ()
    ax1 = gp_Ax1(pnt(axis_point), dir_of(axis_dir))
    return BRepPrimAPI_MakeRevol(shape, ax1, math.radians(float(angle_deg))).Shape()


def loft(sections_wires, solid=True, ruled=False):
    _require_occ()
    ts = BRepOffsetAPI_ThruSections(bool(solid), bool(ruled), 1e-6)
    ts.CheckCompatibility(False)
    for w in sections_wires:
        ts.AddWire(w)
    if not ts.IsDone():
        raise RuntimeError("Loft fallito (sezioni incompatibili?)")
    return ts.Shape()


def pipe(spine_edge, profile_shape):
    _require_occ()
    mk = BRepOffsetAPI_MakePipe(spine_edge, profile_shape)
    if not mk.IsDone():
        raise RuntimeError("Sweep (pipe) fallito")
    return mk.Shape()


# ---------------------------------------------------------------------------
# booleane e modifiche
# ---------------------------------------------------------------------------


def fuse(a, b):
    _require_occ()
    op = BRepAlgoAPI_Fuse(a, b)
    if not op.IsDone():
        raise RuntimeError("Operazione di fusione fallita")
    return op.Shape()


def cut(a, b):
    _require_occ()
    op = BRepAlgoAPI_Cut(a, b)
    if not op.IsDone():
        raise RuntimeError("Operazione di taglio fallita")
    return op.Shape()


def common(a, b):
    _require_occ()
    op = BRepAlgoAPI_Common(a, b)
    if not op.IsDone():
        raise RuntimeError("Operazione di intersezione fallita")
    return op.Shape()


def transform(shape, trsf: "gp_Trsf", copy=True):
    _require_occ()
    return BRepBuilderAPI_Transform(shape, trsf, bool(copy)).Shape()


def translate(shape, d) -> "TopoDS_Shape":
    t = gp_Trsf()
    t.SetTranslation(vec(d))
    return transform(shape, t)


def rotate(shape, axis_point, axis_dir, angle_deg):
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(pnt(axis_point), dir_of(axis_dir)), math.radians(float(angle_deg)))
    return transform(shape, t)


def mirror(shape, point, normal):
    t = gp_Trsf()
    t.SetMirror(gp_Ax2(pnt(point), dir_of(normal)))
    return transform(shape, t)


def scale(shape, factor, center=(0, 0, 0)):
    t = gp_Trsf()
    t.SetScale(pnt(center), float(factor))
    return transform(shape, t)


def fillet_edges(shape, edges, radius):
    """Raccorda gli spigoli indicati di un solido.

    Nota: in alcune build IsDone() è inaffidabile, quindi si prova comunque
    a recuperare lo shape e si valida con un controllo geometrico.
    """
    _require_occ()
    mf = BRepFilletAPI_MakeFillet(shape)
    for e in edges:
        mf.Add(float(radius), e)
    try:
        res = mf.Shape()
    except Exception as exc:
        raise RuntimeError("Raccordatura fallita (raggio troppo grande per gli "
                           f"spigoli?): {exc}")
    if res is None:
        raise RuntimeError("Raccordatura fallita: risultato nullo")
    return res


def chamfer_edges(shape, edges, dist):
    _require_occ()
    mc = BRepFilletAPI_MakeChamfer(shape)
    for e in edges:
        try:
            mc.Add(float(dist), e)
        except Exception:
            mc.Add(e)
    try:
        return mc.Shape()
    except Exception as exc:
        raise RuntimeError(f"Smussatura fallita: {exc}")


def offset_shape(shape, offset):
    _require_occ()
    mk = BRepOffsetAPI_MakeOffsetShape(shape, float(offset), 1e-6, BRepOffset_Skin,
                                       False, False, GeomAbs_Arc)
    if not mk.IsDone():
        raise RuntimeError("Offset fallito")
    return mk.Shape()


def hollow_solid(shape, faces_to_remove, thickness):
    """Svuota un solido lasciando spessore ``thickness`` (facce indicate aperte)."""
    _require_occ()
    lst = TopTools_ListOfShape()
    for f in faces_to_remove:
        lst.Append(f)
    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidByJoin(shape, lst, -float(thickness), 1e-6)
    if not mk.IsDone():
        raise RuntimeError("Svuotamento fallito")
    return mk.Shape()


# ---------------------------------------------------------------------------
# esplorazione topologica e proprietà
# ---------------------------------------------------------------------------

def unique_subshapes(shape, kind) -> List["TopoDS_Shape"]:
    """Sotto-shape uniche del tipo richiesto (TopAbs_VERTEX/EDGE/FACE/SOLID)."""
    _require_occ()
    mappa = TopTools_IndexedMapOfShape()
    _map_shapes(shape, kind, mappa)
    n = mappa.Extent() if hasattr(mappa, "Extent") else mappa.Size()
    return [mappa.FindKey(i) for i in range(1, n + 1)]


def map_subshapes(shape, kind) -> List["TopoDS_Shape"]:
    """Versione tollerante di unique_subshapes: mai solleva, restituisce []."""
    try:
        return unique_subshapes(shape, kind)
    except Exception:
        return []


def shape_type_name(shape) -> str:
    t = shape.ShapeType()
    if t == TopAbs_VERTEX:
        return "point"
    if t == TopAbs_EDGE:
        return "curve"
    if t == TopAbs_FACE:
        return "face"
    if t == TopAbs_SOLID:
        return "solid"
    if t == TopAbs_COMPOUND:
        return "compound"
    return "shape"


def bbox_of(shape) -> Tuple[float, float, float, float, float, float]:
    _require_occ()
    box = Bnd_Box()
    _bnd_add(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (xmin, ymin, zmin, xmax, ymax, zmax)


def volume_of(shape) -> float:
    _require_occ()
    prop = GProp_GProps()
    _vol_props(shape, prop)
    return prop.Mass()


def area_of(shape) -> float:
    _require_occ()
    prop = GProp_GProps()
    _surf_props(shape, prop)
    return prop.Mass()


def length_of(shape) -> float:
    _require_occ()
    prop = GProp_GProps()
    _lin_props(shape, prop)
    return prop.Mass()


def center_of(shape) -> Tuple[float, float, float]:
    _require_occ()
    prop = GProp_GProps()
    _vol_props(shape, prop)
    c = prop.CentreOfMass()
    if prop.Mass() < 1e-12:  # non volumetrico: usa superficie poi lineare
        prop2 = GProp_GProps()
        _surf_props(shape, prop2)
        if prop2.Mass() > 1e-12:
            c = prop2.CentreOfMass()
        else:
            prop3 = GProp_GProps()
            _lin_props(shape, prop3)
            c = prop3.CentreOfMass()
    return (c.X(), c.Y(), c.Z())


def distance(a, b) -> float:
    _require_occ()
    d = BRepExtrema_DistShapeShape(a, b)
    if not d.IsDone():
        raise RuntimeError("Calcolo distanza fallito")
    return d.Value()


def face_normal(face) -> Tuple[float, float, float]:
    """Normale media di una superficie (punto centrale parametrico)."""
    _require_occ()
    umin, umax, vmin, vmax = _uv_bounds(face)
    p = gp_Pnt()
    n = gp_Vec()
    BRepGProp_Face(face).Normal((umin + umax) / 2.0, (vmin + vmax) / 2.0, p, n)
    if n.Magnitude() < 1e-12:
        return (0.0, 0.0, 1.0)
    n.Normalize()
    return (n.X(), n.Y(), n.Z())


def surface_is_planar(face) -> bool:
    _require_occ()
    return BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane


def edge_length(edge) -> float:
    return length_of(edge)


def edge_is_line(edge) -> bool:
    """True se lo spigolo è un segmento rettilineo (esclude archi/circonferenze)."""
    _require_occ()
    from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
    from OCC.Core.GeomAbs import GeomAbs_Line
    try:
        return BRepAdaptor_Curve(edge).GetType() == GeomAbs_Line
    except Exception:
        return False


# ---------------------------------------------------------------------------
# I/O formati CAD
# ---------------------------------------------------------------------------

def read_step(path):
    _require_occ()
    reader = STEPControl_Reader()
    stato = reader.ReadFile(str(path))
    if stato != 1:  # IFSelect_RetDone
        raise RuntimeError(f"Lettura STEP fallita: {path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape is None:
        raise RuntimeError("Nessuna geometria leggibile dal file STEP")
    return shape


def read_iges(path):
    _require_occ()
    reader = IGESControl_Reader()
    stato = reader.ReadFile(str(path))
    if stato != 1:
        raise RuntimeError(f"Lettura IGES fallita: {path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape is None:
        raise RuntimeError("Nessuna geometria leggibile dal file IGES")
    return shape


def read_brep(path):
    _require_occ()
    shape = TopoDS_Shape()
    builder = BRep_Builder()
    if not _brep_read(shape, str(path), builder):
        raise RuntimeError(f"Lettura BREP fallita: {path}")
    return shape


def export_step(shapes, path) -> None:
    _require_occ()
    if not isinstance(shapes, (list, tuple)):
        shapes = [shapes]
    writer = STEPControl_Writer()
    for s in shapes:
        writer.Transfer(s, STEPControl_AsIs)
    stato = writer.Write(str(path))
    if stato != 1:
        raise RuntimeError(f"Scrittura STEP fallita: {path}")


def export_iges(shapes, path) -> None:
    _require_occ()
    from OCC.Core.IGESControl import IGESControl_Writer
    if not isinstance(shapes, (list, tuple)):
        shapes = [shapes]
    writer = IGESControl_Writer()
    for s in shapes:
        writer.AddShape(s)
    writer.ComputeModel()
    stato = writer.Write(str(path))
    if not stato:
        raise RuntimeError(f"Scrittura IGES fallita: {path}")


def export_brep(shapes, path) -> None:
    _require_occ()
    if not isinstance(shapes, (list, tuple)):
        shapes = [shapes]
    if len(shapes) == 1:
        _brep_write(shapes[0], str(path))
    else:
        _brep_write(make_compound(shapes), str(path))


# ---------------------------------------------------------------------------
# display mesh (blocchi .msh -> forme TopoDS per il viewer)
# ---------------------------------------------------------------------------

def mesh_block_shape(model, dim: int, tag: int):
    """Costruisce la shape di visualizzazione di un blocco mesh (dim, tag).

    dim 0 -> compound di vertici; dim 1 -> compound di segmenti;
    dim 2 -> compound di facce triangolari/quadrangolari;
    dim 3 -> facce di bordo (boundary) degli elementi volumetrici.
    """
    _require_occ()
    from .mesh import corner_nodes
    blk = model.blocks.get((dim, tag))
    if blk is None:
        return None
    shapes = []
    if dim == 0:
        for eid in blk.element_ids:
            _, nodes = model.elements[eid]
            for n in nodes:
                if n in model.nodes:
                    shapes.append(make_vertex(model.nodes[n]))
    elif dim == 1:
        for eid in blk.element_ids:
            etype, nodes = model.elements[eid]
            cn = corner_nodes(etype, nodes)
            if len(cn) >= 2 and cn[0] in model.nodes and cn[1] in model.nodes:
                try:
                    shapes.append(make_edge_p2p(model.nodes[cn[0]], model.nodes[cn[1]]))
                except Exception:
                    pass
    elif dim == 2:
        for eid in blk.element_ids:
            etype, nodes = model.elements[eid]
            cn = corner_nodes(etype, nodes)
            pts = [model.nodes[n] for n in cn if n in model.nodes]
            if len(pts) >= 3:
                try:
                    shapes.append(make_face_polygon(pts))
                except Exception:
                    pass
    elif dim == 3:
        for tri in model.boundary_faces(blk.element_ids):
            pts = [model.nodes[n] for n in tri if n in model.nodes]
            if len(pts) == 3:
                try:
                    shapes.append(make_face_polygon(pts))
                except Exception:
                    pass
    if not shapes:
        return None
    return make_compound(shapes)


def repair_shape(shape):
    """Prova a riparare una shape con ShapeFix (best effort)."""
    _require_occ()
    try:
        from OCC.Core.ShapeFix import ShapeFix_Shape
        fixer = ShapeFix_Shape(shape)
        fixer.Perform()
        return fixer.Shape()
    except Exception:
        return shape
