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


class Viewer3D(QWidget):
    """Viewer 3D AIS sincronizzato con un CADDocument."""

    selection_picked = Signal(list)          # lista di id entità selezionate a mouse

    def __init__(self, doc: CADDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.ais_by_entity: Dict[int, object] = {}
        self._canvas = None
        self._display = None
        self._trihedron = None
        self._grid_active = True
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
        if self._trihedron and getattr(self._display, "Context", None):
            try:
                self._display.Context.Display(self._trihedron, False)
            except Exception:
                pass
        self.ais_by_entity.clear()
        for e in self.doc.entities.values():
            self.display_entity(e, fit=False)
        if fit:
            self.fit_all()

    def display_entity(self, ent, fit=False):
        """Mostra (o aggiorna) una singola entità nel viewer."""
        if not self._display or not ent.visible:
            return
        shape = self._shape_for(ent)
        if shape is None:
            return
        color = ent.color or COLORI_TIPO.get(ent.etype, (0.7, 0.7, 0.7))
        try:
            ais = self._display.DisplayColoredShape(shape, color=str(_hex(color)),
                                                    update=False)
        except Exception:
            try:
                ais = self._display.DisplayShape(shape, update=False)
            except Exception:
                return
        self.ais_by_entity[ent.id] = ais
        if fit:
            self.fit_all()

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
