"""Widget viewer 3D basato sul viewer AIS di pythonocc (qtDisplay).

Incorpora ``qtViewerWidget`` di pythonocc (stabile e collaudato) e aggiunge:
  * sincronizzazione bidirezionale della selezione con il documento;
  * mappatura shape -> entità (anche sotto-shape: la selezione di una faccia
    di un solido risolve l'entità figlia corretta);
  * redraw incrementale dell'intero documento con colori per tipo/gruppo;
  * viste standard (iso/front/top/right), fit, ombreggiato/wireframe.
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import Qt, QObject, Signal, QEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QMenu

from gcs.core.document import CADDocument
from gcs.core import occ_utils as ou

try:
    from OCC.Display import backend as _occ_backend
    try:
        _occ_backend.load_backend("pyside6")
    except (ValueError, TypeError):
        # backend già caricato o firma diversa: prosegue con quello attivo
        try:
            _occ_backend.load_backend()
        except ValueError:
            pass
    from OCC.Display import qtDisplay as _qtDisplay
    # nelle varie versioni di pythonocc la classe cambia nome
    _canvas_cls = getattr(_qtDisplay, "qtViewer3d", None) or \
        getattr(_qtDisplay, "qtViewerWidget", None)
    if _canvas_cls is None:
        raise ImportError("qtViewer3d/qtViewerWidget non trovati in qtDisplay")
    HAS_VIEWER = True
    _VIEWER_ERR = ""
except Exception as exc:  # pragma: no cover
    HAS_VIEWER = False
    _VIEWER_ERR = str(exc)


#: colori di default per tipo (RGB 0..1)
COLORI_TIPO = {
    "point": (1.0, 0.25, 0.25),
    "curve": (0.2, 0.35, 0.9),
    "face": (0.75, 0.72, 0.45),
    "solid": (0.45, 0.62, 0.75),
    "compound": (0.6, 0.6, 0.6),
    "mesh": (0.5, 0.5, 0.5),
}

#: palette condivisa con OpenSeesManager.MATERIAL_COLORS per coerenza viewer/pannello
OpenSeesManager_COLORS = (
    (0.20, 0.62, 0.92), (0.95, 0.58, 0.18), (0.24, 0.74, 0.48),
    (0.78, 0.42, 0.82), (0.88, 0.78, 0.24), (0.18, 0.76, 0.78),
)


class Viewer3D(QWidget):
    """Viewer 3D AIS sincronizzato con un CADDocument."""

    selection_picked = Signal(list)          # lista di id entità selezionate a mouse
    #: (entità trascinata, dx, dy, dz in coordinate modello) — editing col mouse
    entity_dragged = Signal(int, float, float, float)
    entity_moved = Signal(int, float, float, float)   # fine trascinamento (commit)

    def __init__(self, doc: CADDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.ais_by_entity: Dict[int, object] = {}
        self._canvas = None
        self._display = None
        self._trihedron = None
        self._grid_active = True
        # ----- stato per il drag con mouse (editing stile AutoCAD)
        self.mouse_edit = False          # modalità "trascina entità" attiva
        self._drag_eid: Optional[int] = None
        self._drag_last = None           # ultima posizione QPoint del drag
        self._ghost = None               # AIS temporaneo di anteprima
        # ----- visualizzazione ausiliaria (toggle da menu Vista)
        self.show_node_labels = False    # etichette numeriche nodi (OpenSees tag)
        self.show_element_labels = False  # etichette numeriche elementi
        self.show_load_arrows = True     # frecce per i carichi nodali
        self.show_constraint_symbols = True  # simboli vincoli
        self._label_ais = []             # AIS delle etichette (per pulizia)
        self._arrow_ais = []             # AIS delle frecce carichi
        # ----- snapping per editing mouse (stile AutoCAD)
        self._snap_enabled = True        # snapping a griglia/vertici attivo
        self._snap_tol = 0.5             # tolleranza snap (unità modello)
        self._snap_grid_step = 1.0        # step griglia per snap
        if not HAS_VIEWER:
            raise RuntimeError(
                "Viewer pythonocc non disponibile (qtDisplay). "
                f"Verifica l'installazione di pythonocc-core ({_VIEWER_ERR})")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._canvas = _canvas_cls(self)
        lay.addWidget(self._canvas)
        self._display = getattr(self._canvas, "_display", None)
        # InitDriver può richiedere un winId valido: prova subito, altrimenti
        # viene rimandato al primo showEvent
        self._driver_ready = False
        try:
            self._init_driver()
        except Exception:
            self._driver_ready = False
        # segnale di selezione del canvas pythonocc (lista di TopoDS_Shape)
        sig = getattr(self._canvas, "sig_topods_selected", None)
        if sig is not None:
            sig.connect(self._on_canvas_selection)

        # Gestione interattiva click destro per menu contestuale granulare
        self._rclick_press_pos = None
        if hasattr(self._canvas, "installEventFilter"):
            self._canvas.installEventFilter(self)

    def _init_driver(self):
        if self._driver_ready or self._canvas is None:
            return
        init = getattr(self._canvas, "InitDriver", None)
        if init:
            init()
        self._display = getattr(self._canvas, "_display", None)
        self._driver_ready = self._display is not None
        if self._driver_ready:
            self._setup_view()

    def showEvent(self, event):  # noqa: N802 (API Qt)
        if not self._driver_ready:
            try:
                self._init_driver()
                self.redraw_all(fit=True)
            except Exception:
                pass
        super().showEvent(event)

    # ------------------------------------------------------------------ setup
    def _setup_view(self):
        if not self._driver_ready or not self._display:
            return
        try:
            self._display.SetSelectionMode()
        except Exception:
            pass
        # 1. Sfondo bianco
        try:
            self._display.set_bg_gradient_color([255, 255, 255], [255, 255, 255])
        except Exception:
            pass
        try:
            from OCC.Core.Quantity import Quantity_Color, Quantity_NOC_WHITE
            if hasattr(self._display, "View") and self._display.View:
                self._display.View.SetBackgroundColor(Quantity_Color(Quantity_NOC_WHITE))
        except Exception:
            pass
        try:
            self._display.EnableAntiAliasing()
        except Exception:
            pass
        # 2. Triedro ed assi di riferimento
        try:
            self._display.display_triedron()
        except Exception:
            pass
        self._setup_trihedron()
        # 3. Piani quadrettati (griglia attiva all'avvio)
        self._setup_grid()

    def _setup_trihedron(self):
        if not self._driver_ready or not self._display or not getattr(self._display, "Context", None):
            return
        try:
            from OCC.Core.Geom import Geom_Axis2Placement
            from OCC.Core.AIS import AIS_Trihedron
            from OCC.Core.gp import gp_Ax2, gp_Pnt, gp_Dir
            if self._trihedron is None:
                ax = Geom_Axis2Placement(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0)))
                self._trihedron = AIS_Trihedron(ax)
                self._trihedron.SetSize(30.0)
            if not self._display.Context.IsDisplayed(self._trihedron):
                self._display.Context.Display(self._trihedron, False)
        except Exception:
            self._trihedron = None

    def _setup_grid(self):
        if not self._driver_ready or not self._display or not getattr(self._display, "Viewer", None):
            return
        try:
            view = getattr(self._display, "View", None)
            if view:
                win_fn = getattr(view, "Window", None)
                if win_fn:
                    w = win_fn()
                    if w is None or (hasattr(w, "IsNull") and w.IsNull()):
                        return
            from OCC.Core.Aspect import Aspect_GT_Rectangular, Aspect_GDM_Lines
            viewer = self._display.Viewer
            viewer.SetRectangularGridValues(0.0, 0.0, 10.0, 10.0, 0.0)
            viewer.SetRectangularGridGraphicValues(500.0, 500.0, 0.0)
            viewer.ActivateGrid(Aspect_GT_Rectangular, Aspect_GDM_Lines)
            if view:
                view.SetGridActivity(True)
                view.Update()
            self._grid_active = True
        except Exception:
            pass

    def toggle_grid(self) -> bool:
        self.set_grid_active(not self._grid_active)
        return self._grid_active

    def set_grid_active(self, active: bool):
        self._grid_active = active
        if not self._driver_ready or not self._display:
            return
        try:
            view = getattr(self._display, "View", None)
            if view:
                win_fn = getattr(view, "Window", None)
                if win_fn:
                    w = win_fn()
                    if w is None or (hasattr(w, "IsNull") and w.IsNull()):
                        return
            from OCC.Core.Aspect import Aspect_GT_Rectangular, Aspect_GDM_Lines
            viewer = getattr(self._display, "Viewer", None)
            if viewer and view:
                if active:
                    viewer.ActivateGrid(Aspect_GT_Rectangular, Aspect_GDM_Lines)
                    view.SetGridActivity(True)
                else:
                    viewer.DeactivateGrid()
                    view.SetGridActivity(False)
                view.Update()
        except Exception:
            pass

    # ---------------------------------------------------------------- redraw
    def redraw_all(self, fit=True):
        """Ridisegna tutte le entità del documento dallo stato corrente."""
        if not self._display:
            return
        try:
            self._display.EraseAll()
        except Exception:
            pass
        # Pulisci overlay (frecce carichi, etichette)
        self._arrow_ais = []
        self._label_ais = []
        if self._trihedron and getattr(self._display, "Context", None):
            try:
                self._display.Context.Display(self._trihedron, False)
            except Exception:
                pass
        self.ais_by_entity.clear()
        for e in self.doc.entities.values():
            self.display_entity(e, fit=False)
        # Disegna frecce carichi e simboli dopo le entità
        self._disegna_frecce_carichi()
        # Disegna etichette numerazione nodi/elementi (se attive)
        self._disegna_etichette_numerazione()
        # Update viewer finale
        try:
            ctx = getattr(self._display, "Context", None)
            if ctx:
                ctx.UpdateCurrentViewer()
        except Exception:
            pass
        if fit:
            self.fit_all()

    def display_entity(self, ent, fit=False):
        """Mostra (o aggiorna) una singola entità nel viewer.

        Se il documento ha proprietà/vincoli associati (fasi OpenSees-style),
        l'entità viene colorata in base alla **proprietà** e marcata con un
        **simbolo di vincolo** (triangolo/cerchio/quadrato) sul primo nodo:
        è la visualizzazione dell'associazione richiesta (stile STKO).
        """
        if not self._display or not ent.visible:
            return
        shape = self._shape_for(ent)
        if shape is None:
            return
        color = (self._colore_associazione(ent) or ent.meta.get("fem_color")
                 or ent.color \
            or COLORI_TIPO.get(ent.etype, (0.7, 0.7, 0.7)))
        try:
            ais = self._display.DisplayColoredShape(shape, color=str(_hex(color)),
                                                    update=False)
        except Exception:
            try:
                ais = self._display.DisplayShape(shape, update=False)
            except Exception:
                return
        self.ais_by_entity[ent.id] = ais
        self._disegna_simbolo_vincolo(ent)
        if fit:
            self.fit_all()

    # ------------------------------------------- colori/simboli associazione
    #: palette deterministica per le proprietà (mat_id -> colore)
    _PALETTE_PROP = [(0.20, 0.55, 0.85), (0.85, 0.45, 0.20), (0.35, 0.70, 0.35),
                     (0.75, 0.30, 0.65), (0.90, 0.75, 0.20), (0.30, 0.75, 0.75)]
    #: colore dedicato per gli elementi con vincolo
    _COLORE_VINCOLO = {
        "fix": (0.10, 0.10, 0.10),
        "pin": (0.80, 0.15, 0.15),
        "roller": (0.15, 0.55, 0.15),
        "equalDOF": (0.60, 0.35, 0.80),
        "rigidDiaphragm": (0.85, 0.60, 0.10),
    }

    def _colore_associazione(self, ent):
        """Colore derivante dall'associazione proprietà/vincolo, o None.

        Legge in modo unificato da:
        - `doc.opensees` (OpenSeesManager): element_assignments, constraints,
          loads, equaldofs, prescribed_displacements, parameter_bindings.
        - `doc.phases` (PhaseManager): vincoli e proprietà STKO-style.

        La precedenza è: vincolo > carico > parameter_binding > materiale >
        equalDOF > sp (prescribed displacement).
        """
        # 1. OpenSeesManager (sorgente principale)
        osm = getattr(self.doc, "opensees", None)
        if osm is not None:
            # Vincoli fix
            for sc in osm.constraints:
                ids = osm._entity_ids_for_targets(sc.entity_ids, sc.group_names)
                if ent.id in ids:
                    return self._COLORE_VINCOLO.get("fix", (0.10, 0.10, 0.10))
            # EqualDOF
            for eq in osm.equaldofs:
                ids = osm._entity_ids_for_targets(
                    [eq.master_entity_id, eq.slave_entity_id] if eq.master_entity_id else None,
                    [eq.master_group, eq.slave_group] if eq.master_group else None)
                if ent.id in ids:
                    return self._COLORE_VINCOLO.get("equalDOF", (0.60, 0.35, 0.80))
            # Carichi
            for ld in osm.loads:
                ids = osm._entity_ids_for_targets(ld.entity_ids, ld.group_names)
                if ent.id in ids:
                    return (0.96, 0.56, 0.16)  # arancio carichi
            # Spostamenti imposti (sp)
            for sp in osm.prescribed_displacements:
                ids = osm._entity_ids_for_targets(sp.entity_ids, [])
                if ent.id in ids:
                    return (0.72, 0.34, 0.78)  # viola sp
            # Parametri
            for pb in osm.parameter_bindings:
                if pb.target_type == "element":
                    assignment = next((a for a in osm.element_assignments
                                       if pb.target_id in a.element_ids), None)
                    if assignment and assignment.entity_id == ent.id:
                        return (0.30, 0.78, 0.82)  # ciano parametri
            # Materiali (element_assignments) - più bassa priorità
            for assignment in osm.element_assignments:
                if assignment.entity_id == ent.id:
                    return OpenSeesManager_COLORS[(assignment.material_tag - 1)
                                                   % len(OpenSeesManager_COLORS)]

        # 2. PhaseManager (vincoli STKO-style)
        cons = self.doc.phases.merged_constraints()
        if ent.id in cons:
            return self._COLORE_VINCOLO.get(cons[ent.id])
        props = self.doc.phases.merged_properties()
        p = props.get(ent.id)
        if p is not None:
            return self._PALETTE_PROP[p.mat_id % len(self._PALETTE_PROP)]
        return None

    def _disegna_simbolo_vincolo(self, ent):
        """Disegna un piccolo marker geometrico sul baricentro dell'entità.

        Esteso per disegnare anche frecce per i carichi e simboli per
        spostamenti imposti. Legge da OpenSeesManager (sorgente principale)
        e da PhaseManager (vincoli STKO-style).
        """
        if not self.show_constraint_symbols:
            return
        # Cerca prima in OpenSeesManager
        osm = getattr(self.doc, "opensees", None)
        tipo = None
        if osm is not None:
            for sc in osm.constraints:
                ids = osm._entity_ids_for_targets(sc.entity_ids, sc.group_names)
                if ent.id in ids:
                    tipo = "fix"
                    break
            if tipo is None:
                for eq in osm.equaldofs:
                    ids = osm._entity_ids_for_targets(
                        [eq.master_entity_id, eq.slave_entity_id] if eq.master_entity_id else None,
                        [eq.master_group, eq.slave_group] if eq.master_group else None)
                    if ent.id in ids:
                        tipo = "equalDOF"
                        break
            if tipo is None:
                for sp in osm.prescribed_displacements:
                    ids = osm._entity_ids_for_targets(sp.entity_ids, [])
                    if ent.id in ids:
                        tipo = "roller"  # represent sp as roller
                        break
        # Fallback PhaseManager
        if tipo is None:
            cons = self.doc.phases.merged_constraints()
            tipo = cons.get(ent.id)
        if tipo is None:
            return
        centro = self._centroide(ent)
        if centro is None:
            return
        try:
            from OCC.Core.gp import gp_Pnt, gp_Dir
            from OCC.Core.BRepBuilderAPI import (BRepBuilderAPI_MakePolygon,
                                                 BRepBuilderAPI_MakeEdge)
            x, y, z = centro
            r = 3.0
            if tipo == "fix":          # triangolo
                pts = [gp_Pnt(x - r, y - r, z), gp_Pnt(x + r, y - r, z),
                       gp_Pnt(x, y + r, z), gp_Pnt(x - r, y - r, z)]
            elif tipo == "pin":        # cerchio
                from OCC.Core.GCMake import GC_MakeCircle
                from OCC.Core.gp import gp_Ax2, gp_Circ
                circ = gp_Circ(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1)), r)
                edge = BRepBuilderAPI_MakeEdge(circ).Edge()
                self._display.DisplayColoredShape(edge, color="#CC2222", update=True)
                return
            else:                      # quadrato (roller, equalDOF e altri)
                pts = [gp_Pnt(x - r, y - r, z), gp_Pnt(x + r, y - r, z),
                       gp_Pnt(x + r, y + r, z), gp_Pnt(x - r, y + r, z),
                       gp_Pnt(x - r, y - r, z)]
            poly = BRepBuilderAPI_MakePolygon(pts)
            self._display.DisplayColoredShape(poly.Wire(),
                                              color=str(_hex(self._COLORE_VINCOLO.get(tipo))),
                                              update=True)
        except Exception:
            pass  # i simboli sono decorativi: mai bloccare il redraw

    def _disegna_frecce_carichi(self):
        """Disegna frecce per i carichi nodali associati alle entità.

        Per ogni EntityLoad, calcola il baricentro dei nodi target e disegna
        una freccia che parte dal baricentro e si estende in direzione della
        forza risultante. Le frecce sono rosse per fx, verdi per fy, blu per fz.
        """
        if not self.show_load_arrows or not self._display:
            return
        osm = getattr(self.doc, "opensees", None)
        if osm is None:
            return
        try:
            from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Circ
            from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
            for ld in osm.loads:
                nodes = osm.resolve_load_nodes(ld, None)
                if not nodes:
                    continue
                # Baricentro nodi
                pts = []
                for nid in nodes:
                    for model in self.doc.mesh_models.values():
                        if nid in model.nodes:
                            pts.append(model.nodes[nid])
                            break
                if not pts:
                    continue
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                cz = sum(p[2] for p in pts) / len(pts)
                # Direzione e modulo della forza
                magnitude = (ld.fx**2 + ld.fy**2 + ld.fz**2) ** 0.5
                if magnitude < 1e-12:
                    continue
                # Scala freccia: lunghezza proporzionale al modulo
                arrow_length = max(5.0, min(50.0, magnitude * 1e-9 + 10.0))
                dx = ld.fx / magnitude * arrow_length
                dy = ld.fy / magnitude * arrow_length
                dz = ld.fz / magnitude * arrow_length
                p_start = gp_Pnt(cx, cy, cz)
                p_end = gp_Pnt(cx + dx, cy + dy, cz + dz)
                edge = BRepBuilderAPI_MakeEdge(p_start, p_end).Edge()
                color = "#E04444" if abs(ld.fz) > abs(ld.fx) and abs(ld.fz) > abs(ld.fy) \
                    else ("#44CC44" if abs(ld.fy) > abs(ld.fx) else "#4477EE")
                ais = self._display.DisplayColoredShape(edge, color=color,
                                                          update=False)
                if ais is not None:
                    self._arrow_ais.append(ais)
        except Exception:
            pass  # le frecce sono decorative

    def _disegna_etichette_numerazione(self):
        """Disegna le etichette numeriche di nodi e elementi.

        Usa AIS_TextLabel di OCC per renderizzare i tag (1-based, come da
        convenzione OpenSees). Il toggle è controllato da `show_node_labels`
        e `show_element_labels`.
        """
        if not self._display:
            return
        try:
            from OCC.Core.AIS import AIS_TextLabel
            from OCC.Core.gp import gp_Pnt
            from OCC.Core.Quantity import Quantity_NameOfColor, Quantity_Color
        except ImportError:
            return
        # Pulisci le etichette esistenti
        for ais in self._label_ais:
            try:
                self._display.Context.Remove(ais, True)
            except Exception:
                pass
        self._label_ais = []
        if not (self.show_node_labels or self.show_element_labels):
            return
        # Etichette nodi
        if self.show_node_labels:
            for model in self.doc.mesh_models.values():
                for nid, coord in model.nodes.items():
                    try:
                        lbl = AIS_TextLabel()
                        lbl.SetText(str(nid))
                        lbl.SetPosition(gp_Pnt(*coord))
                        lbl.SetColor(Quantity_Color(Quantity_NameOfColor.yellow))
                        self._display.Context.Display(lbl, True)
                        self._label_ais.append(lbl)
                    except Exception:
                        pass
            # Nodi manuali
            osm = getattr(self.doc, "opensees", None)
            if osm is not None:
                for nid, coord in osm.manual_nodes.items():
                    try:
                        lbl = AIS_TextLabel()
                        lbl.SetText(str(nid))
                        lbl.SetPosition(gp_Pnt(*coord))
                        lbl.SetColor(Quantity_Color(Quantity_NameOfColor.cyan))
                        self._display.Context.Display(lbl, True)
                        self._label_ais.append(lbl)
                    except Exception:
                        pass
        # Etichette elementi (al baricentro)
        if self.show_element_labels:
            for model in self.doc.mesh_models.values():
                for eid, (etype, nodes) in model.elements.items():
                    try:
                        coords = [model.nodes[n] for n in nodes if n in model.nodes]
                        if not coords:
                            continue
                        cx = sum(c[0] for c in coords) / len(coords)
                        cy = sum(c[1] for c in coords) / len(coords)
                        cz = sum(c[2] for c in coords) / len(coords)
                        lbl = AIS_TextLabel()
                        lbl.SetText(f"E{eid}")
                        lbl.SetPosition(gp_Pnt(cx, cy, cz))
                        lbl.SetColor(Quantity_Color(Quantity_NameOfColor.white))
                        self._display.Context.Display(lbl, True)
                        self._label_ais.append(lbl)
                    except Exception:
                        pass

    def toggle_node_labels(self, on: Optional[bool] = None) -> bool:
        """Toggle visualizzazione etichette nodi. Ritorna il nuovo stato."""
        self.show_node_labels = (not self.show_node_labels) if on is None else bool(on)
        self._disegna_etichette_numerazione()
        return self.show_node_labels

    def toggle_element_labels(self, on: Optional[bool] = None) -> bool:
        self.show_element_labels = (not self.show_element_labels) if on is None else bool(on)
        self._disegna_etichette_numerazione()
        return self.show_element_labels

    def toggle_load_arrows(self, on: Optional[bool] = None) -> bool:
        self.show_load_arrows = (not self.show_load_arrows) if on is None else bool(on)
        self.redraw_all(fit=False)
        return self.show_load_arrows

    def toggle_constraint_symbols(self, on: Optional[bool] = None) -> bool:
        self.show_constraint_symbols = (not self.show_constraint_symbols) if on is None else bool(on)
        self.redraw_all(fit=False)
        return self.show_constraint_symbols

    def _clear_overlay(self):
        """Pulisce gli oggetti decorativi (frecce, simboli, etichette)."""
        if not self._display:
            return
        for ais in self._arrow_ais:
            try:
                self._display.Context.Remove(ais, True)
            except Exception:
                pass
        self._arrow_ais = []
        for ais in self._label_ais:
            try:
                self._display.Context.Remove(ais, True)
            except Exception:
                pass
        self._label_ais = []

    def _snap_to_grid(self, x: float, y: float, z: float = 0.0):
        """Snap alle intersezioni della griglia (multiplo di _snap_grid_step)."""
        if not self._snap_enabled:
            return (x, y, z)
        step = self._snap_grid_step
        return (round(x / step) * step, round(y / step) * step, round(z / step) * step)

    def _snap_to_vertices(self, x: float, y: float, z: float = 0.0):
        """Snap al vertice più vicino tra tutte le entità visibili.

        Se nessun vertice è entro `_snap_tol`, ritorna la posizione originale.
        """
        if not self._snap_enabled:
            return (x, y, z)
        best = (x, y, z)
        best_dist = self._snap_tol
        try:
            from OCC.Core.TopExp import TopExp_Explorer
            from OCC.Core.TopAbs import TopAbs_VERTEX
            from OCC.Core.BRep import BRep_Tool
            from OCC.Core.gp import gp_Pnt
            for ent in self.doc.entities.values():
                shape = self._shape_for(ent)
                if shape is None:
                    continue
                explorer = TopExp_Explorer(shape, TopAbs_VERTEX)
                while explorer.More():
                    try:
                        v = BRep_Tool.Pnt(explorer.Current())
                        d = ((v.X() - x)**2 + (v.Y() - y)**2 + (v.Z() - z)**2) ** 0.5
                        if d < best_dist:
                            best_dist = d
                            best = (v.X(), v.Y(), v.Z())
                    except Exception:
                        pass
                    explorer.Next()
        except Exception:
            pass
        return best

    def set_snap_enabled(self, on: bool):
        self._snap_enabled = bool(on)

    def set_snap_grid_step(self, step: float):
        self._snap_grid_step = max(0.001, float(step))

    def _centroide(self, ent):
        shape = self._shape_for(ent)
        if shape is None:
            return None
        try:
            bb = ou.bbox_of(shape)
            if bb:
                (x0, y0, z0), (x1, y1, z1) = bb
                return ((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0)
        except Exception:
            pass
        return None

    def _shape_for(self, ent):
        if ent.shape is not None:
            return ent.shape
        ref = ent.mesh_ref()
        if ref:
            model = self.doc.mesh_models.get(ref[0])
            if model is not None:
                try:
                    return ou.mesh_block_shape(model, ref[1], ref[2])
                except Exception:
                    return None
        return None

    def erase_entity(self, ent_id: int):
        ais = self.ais_by_entity.pop(ent_id, None)
        if ais is not None and self._display:
            try:
                self._display.Context.Remove(ais, True)
            except Exception:
                pass

    # ------------------------------------------------------------ viste/camere
    def fit_all(self):
        if self._display:
            try:
                self._display.FitAll()
            except Exception:
                pass

    def vista(self, nome: str):
        if not self._display:
            return
        mappa = {"iso": self._display.View_Iso, "front": self._display.View_Front,
                 "top": self._display.View_Top, "left": self._display.View_Left,
                 "right": self._display.View_Right, "bottom": self._display.View_Bottom,
                 "back": self._display.View_Back}
        fn = mappa.get(nome.lower())
        if fn:
            try:
                fn()
                self.fit_all()
            except Exception:
                pass

    def set_wireframe(self, on: bool):
        if not self._display:
            return
        try:
            self._display.DefaultDrawer.SetFaceBoundaryDraw(not on)
        except Exception:
            pass
        try:
            if on:
                self._display.SetModeWireFrame()
            else:
                self._display.SetModeShaded()
        except Exception:
            pass
        self.redraw_all(fit=False)

    # ------------------------------------------------------------ editing mouse
    def set_mouse_edit(self, on: bool):
        """Attiva/disattiva la modalità 'trascina entità col mouse' (stile AutoCAD)."""
        self.mouse_edit = bool(on)

    def _eid_sotto_il_puntatore(self) -> Optional[int]:
        """Entità sotto il cursore: usa la selezione AIS del canvas."""
        try:
            ctx = getattr(self._display, "Context", None)
            if ctx is not None:
                sel = ctx.SelectedOwnedObjects()
                for obj in sel or []:
                    shape = getattr(obj, "Shape", lambda: None)()
                    eid = self._resolve_shape_owner(shape) if shape else None
                    if eid is not None:
                        return eid
        except Exception:
            pass
        # fallback: l'entità selezionata nel documento (una sola)
        if len(self.doc.selection) == 1:
            return next(iter(self.doc.selection))
        return None

    def mousePressEvent(self, event):  # noqa: N802
        if (self.mouse_edit and event.button() == Qt.LeftButton
                and self._driver_ready):
            eid = self._eid_sotto_il_puntatore()
            if eid is not None:
                self._drag_eid = eid
                self._drag_last = event.position()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_eid is not None and self._drag_last is not None:
            d = event.position() - self._drag_last
            self._drag_last = event.position()
            # stima dei delta in coordinate modello dalla scena
            dx, dy, dz = self._delta_modello(d.x(), -d.y())
            self.entity_dragged.emit(self._drag_eid, dx, dy, dz)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._drag_eid is not None:
            eid = self._drag_eid
            self._drag_eid = None
            self._drag_last = None
            d = event.position()
            if self._ghost is not None:
                try:
                    self._display.Context.Remove(self._ghost, True)
                except Exception:
                    pass
                self._ghost = None
            self.entity_moved.emit(eid, *self._delta_totale)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---------------------------------------------------------------- drag math
    @property
    def _delta_totale(self):
        return getattr(self, "_drag_acc", (0.0, 0.0, 0.0))

    @_delta_totale.setter
    def _delta_totale(self, v):
        self._drag_acc = v

    def _delta_modello(self, sx: float, sy: float):
        """Converte uno spostamento schermo (px) in offset sul piano XY.

        La scala è stimata dal bounding box della scena rispetto all'altezza
        del widget; il trascinamento avviene sul piano ortogonale alla vista
        (in iso si sposta in X/Y modello — comportamento tipo AutoCAD).

        Lo snapping è applicato se `_snap_enabled` è True: arrotonda il
        delta finale al multiplo più vicino di `_snap_grid_step`.
        """
        try:
            h = max(1.0, self.height())
            # diametro apparente della scena, se disponibile
            est = None
            try:
                from OCC.Core.Bnd import Bnd_Box
                bb = Bnd_Box()
                for e in self.doc.entities.values():
                    s = self._shape_for(e)
                    if s is not None:
                        try:
                            bbox = ou.bbox_of(s)
                            if bbox:
                                (x0, y0, z0), (x1, y1, z1) = bbox
                                bb.Update(x0, y0, z0)
                                bb.Update(x1, y1, z1)
                        except Exception:
                            continue
                if not bb.IsVoid():
                    xmn, ymn, zmn, xmx, ymx, zmx = bb.Get()
                    est = max(xmx - xmn, ymx - ymn, 1e-6)
            except Exception:
                est = None
            scala = (est or 500.0) / h
            dx = sx * scala
            dy = sy * scala
            # Applica snapping al delta (arrotonda al multiplo di _snap_grid_step)
            if self._snap_enabled:
                step = self._snap_grid_step
                dx = round(dx / step) * step
                dy = round(dy / step) * step
            acc = self._delta_totale
            self._delta_totale = (acc[0] + dx, acc[1] + dy, acc[2])
            return dx, dy, 0.0
        except Exception:
            return 0.0, 0.0, 0.0

    def resetta_drag(self):
        self._drag_eid = None
        self._drag_last = None
        self._delta_totale = (0.0, 0.0, 0.0)

    # ------------------------------------------------------------- selezione
    def _on_canvas_selection(self, shapes):
        """Sincronizza la selezione del canvas con il documento."""
        ids = set()
        for shape in shapes or []:
            ent_id = self._resolve_shape_owner(shape)
            if ent_id is not None:
                ids.add(ent_id)
        if ids != set(self.doc.selection):
            self.doc.set_selection(ids)
        self.selection_picked.emit(sorted(ids))

    def _resolve_shape_owner(self, shape) -> Optional[int]:
        """Mappa una shape selezionata all'entità del documento."""
        if shape is None:
            return None
        # 1) match esatto
        for eid, e in self.doc.entities.items():
            s = self._shape_for(e)
            if s is not None:
                try:
                    if s.IsSame(shape):
                        return eid
                except Exception:
                    continue
        # 2) sotto-shape: cerca il proprietario che la contiene
        try:
            for eid, e in self.doc.entities.items():
                s = self._shape_for(e)
                if s is None:
                    continue
                try:
                    mappa = ou.map_subshapes(s, shape.ShapeType())
                    for cand in mappa:
                        if cand.IsSame(shape):
                            return eid
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # ------------------------------------------------------------ evidenziazione
    def highlight_selection(self):
        """Best-effort: evidenzia nel viewer la selezione del documento."""
        ctx = getattr(self._display, "Context", None)
        if ctx is None:
            return
        try:
            # deseleziona tutto, poi riseleziona le entità del documento
            try:
                ctx.ClearSelected(False)
            except Exception:
                pass
            for eid in self.doc.selection:
                ais = self.ais_by_entity.get(eid)
                if ais is not None:
                    try:
                        ctx.AddOrRemoveSelected(ais, False)
                    except Exception:
                        pass
            try:
                ctx.UpdateCurrentViewer()
            except Exception:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------- menu contestuale
    def eventFilter(self, watched, event):
        if watched == self._canvas:
            etype = event.type()
            if etype == QEvent.MouseButtonPress:
                if event.button() == Qt.RightButton:
                    self._rclick_press_pos = event.pos()
            elif etype == QEvent.MouseButtonRelease:
                if event.button() == Qt.RightButton and self._rclick_press_pos is not None:
                    delta = (event.pos() - self._rclick_press_pos).manhattanLength()
                    self._rclick_press_pos = None
                    if delta <= 6:
                        # Click singolo tasto destro: apri menu contestuale
                        gpos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                        self._show_viewport_context_menu(gpos, event.pos())
                        return True
        return super().eventFilter(watched, event)

    def _show_viewport_context_menu(self, global_pos, click_pos):
        menu = QMenu(self)
        win = self.window()

        # Tentativo di rilevare la forma sotto al puntatore mouse
        if self._display and getattr(self._display, "Context", None) and getattr(self._display, "View", None):
            try:
                self._display.Context.MoveTo(click_pos.x(), click_pos.y(), self._display.View)
                self._display.Context.Select(False)
                shapes = self._display.GetSelectedShapes() if hasattr(self._display, "GetSelectedShapes") else []
                if shapes:
                    self._on_canvas_selection(shapes)
            except Exception:
                pass

        selected = self.doc.selected_entities()
        if selected:
            ent = selected[0]
            act_p = menu.addAction(f"Proprietà e parametri [{ent.name}]…")
            act_p.triggered.connect(lambda: self._open_entity_props(ent))
            menu.addSeparator()

            m_os = menu.addMenu("OpenSees")
            m_os.addAction("Associa Vincolo (fix)…", lambda: self._open_fix([e.id for e in selected]))
            m_os.addAction("Associa Carico (load)…", lambda: self._open_load([e.id for e in selected]))
            m_os.addAction("Definisci EqualDOF…", self._open_equaldof)
            menu.addSeparator()

            if hasattr(win, "macro_engine"):
                macros = win.macro_engine.applicable_to(ent.etype)
                if macros:
                    m_mac = menu.addMenu("Esegui Macro")
                    for spec in macros:
                        m_mac.addAction(spec.name, lambda s=spec: win.run_macro(s))
                    menu.addSeparator()

            m_tr = menu.addMenu("Modifica / Trasforma")
            if hasattr(win, "act_trasla_dialog"):
                m_tr.addAction("Traslazione…", win.act_trasla_dialog)
            if hasattr(win, "act_ruota_dialog"):
                m_tr.addAction("Rotazione…", win.act_ruota_dialog)
            if hasattr(win, "act_scala_dialog"):
                m_tr.addAction("Scala…", win.act_scala_dialog)
            menu.addSeparator()

            menu.addAction("Isola entità", lambda: self._isolate(ent.id))
            menu.addAction("Deseleziona tutto", lambda: self.doc.set_selection([]))
        else:
            menu.addAction("Configura Solutore e Fasi OpenSees…", self._open_analysis_dialog)
            menu.addAction("Esporta per OpenSees…", lambda: win.act_export_opensees() if hasattr(win, "act_export_opensees") else None)
            menu.addSeparator()
            menu.addAction("Adatta tutto (Fit)", self.fit_all)
            m_viste = menu.addMenu("Viste standard")
            for v in ("iso", "front", "top", "right", "left", "bottom", "back"):
                m_viste.addAction(f"Vista {v}", lambda vv=v: self.vista(vv))
            menu.addAction("Wireframe / Ombreggiato", lambda: win.act_toggle_wireframe() if hasattr(win, "act_toggle_wireframe") else None)
            menu.addAction("Mostra/Nascondi griglia", self.toggle_grid)

        menu.exec(global_pos)

    def _open_entity_props(self, ent):
        from .dialogs import EntityPropertiesDialog
        dlg = EntityPropertiesDialog(ent, self.doc, parent=self)
        if dlg.exec():
            self.redraw_all(fit=False)
            win = self.window()
            if hasattr(win, "panel_tree"):
                win.panel_tree.refresh()
            if hasattr(win, "panel_props"):
                win.panel_props.refresh()

    def _open_fix(self, eids):
        from .dialogs import OpenSeesFixDialog
        dlg = OpenSeesFixDialog(self.doc, target_entities=eids, parent=self)
        dlg.exec()

    def _open_load(self, eids):
        from .dialogs import OpenSeesLoadDialog
        dlg = OpenSeesLoadDialog(self.doc, target_entities=eids, parent=self)
        dlg.exec()

    def _open_equaldof(self):
        from .dialogs import OpenSeesEqualDOFDialog
        dlg = OpenSeesEqualDOFDialog(self.doc, parent=self)
        dlg.exec()

    def _open_analysis_dialog(self):
        from .dialogs import OpenSeesAnalysisDialog
        dlg = OpenSeesAnalysisDialog(self.doc, parent=self)
        dlg.exec()

    def _isolate(self, eid):
        for e in self.doc.entities.values():
            e.visible = (e.id == eid)
        self.redraw_all(fit=True)
        win = self.window()
        if hasattr(win, "panel_tree"):
            win.panel_tree.refresh()


class NullViewer:
    """Sostituto del viewer 3D quando non c'è display grafico.

    Tutte le chiamate (fit_all, vista, redraw_all, ...) sono no-op, così la
    finestra principale e i pannelli restano utilizzabili (console, macro,
    albero, import/export) anche senza OpenGL.
    """

    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            pass
        return _noop


def _hex(rgb) -> str:
    """Converte (r,g,b) 0..1 in stringa esadecimale usabile da pythonocc."""
    r, g, b = [max(0, min(255, int(round(float(c) * 255)))) for c in rgb]
    return f"#{r:02X}{g:02X}{b:02X}"
