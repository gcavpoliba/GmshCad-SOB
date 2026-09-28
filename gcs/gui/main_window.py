"""Finestra principale GmshCAD Studio (stile Salome: dock albero/proprietà/console).

Struttura:
  * centro: viewer 3D AIS;
  * dock sinistro: albero gruppi/entità; destro: proprietà;
  * dock inferiore: tab Console Python + Log;
  * menu: File, Modifica, Selezione, Gruppi, Modalità, Macro, Vista, Aiuto;
  * toolbar contestuali: creazione (modalità Geometria) e mesh (modalità Mesh).
"""

from __future__ import annotations

import os
import traceback

from PySide6.QtCore import Qt, QProcess, QSettings, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDialog, QMainWindow, QDockWidget, QTabWidget, QToolBar,
                               QMessageBox, QFileDialog, QInputDialog, QLabel,
                               QStatusBar, QApplication, QColorDialog, QComboBox)

from gcs import __app_name__, __version__
from gcs.core.document import CADDocument, DocumentError
from gcs.core.builder import GeometryBuilder
from gcs.core.editors import GeometryEditor
from gcs.core import selectors as sel
from gcs.core import gmsh_bridge as gb
from gcs.core import occ_utils as ou
from gcs.core.macro_engine import MacroEngine, write_macro_template
from gcs.core.selection_manager import SelectionManager
from gcs.core.visibility_manager import VisibilityManager
from gcs.gui.viewer import Viewer3D, NullViewer
from gcs.gui.panels import (EntityTree, PropertiesPanel, ConsolePanel,
                            LogPanel, MacroPanel, OpenSeesFlowPanel)
from gcs.gui.command_line import CommandLineWidget, CommandSpec
from gcs.gui.dialogs import ParamDialog


class MainWindow(QMainWindow):
    """Finestra principale dell'ambiente CAD."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.setMinimumSize(640, 560)
        self.resize(1500, 900)
        self.doc = CADDocument()
        self.builder = GeometryBuilder(self.doc)
        self.editor = GeometryEditor(self.doc)
        self.selection_manager = SelectionManager(self.doc)
        self.engine = MacroEngine(self.doc, log=self._log)
        self.macro_engine = self.engine

        # ---------- widget centrale (viewer 3D con fallback senza display)
        try:
            self.visibility_manager = VisibilityManager(self.doc)
            self.viewer = Viewer3D(
                self.doc,
                selection_manager=self.selection_manager,
                visibility_manager=self.visibility_manager,
            )
            self.visibility_manager.attach_viewer(self.viewer)
            # pythonocc può assegnare al viewer un minimumSize molto alto, che
            # impedisce alla finestra di adattarsi a monitor con poca altezza.
            self.viewer.setMinimumSize(240, 220)
            self.setCentralWidget(self.viewer)
        except Exception as exc:
            self.visibility_manager = VisibilityManager(self.doc)
            self.viewer = NullViewer()
            self.visibility_manager.attach_viewer(self.viewer)
            placeholder = QLabel(
                "Viewer 3D non disponibile in questo ambiente:\n" + str(exc) +
                "\n\nAvviare l'applicazione da un ambiente desktop grafico.")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setWordWrap(True)
            self.setCentralWidget(placeholder)
            self._log(f"Viewer 3D non disponibile: {exc}")
        self.doc.add_listener(self._on_doc_event)

        # ----- Collegamento dei signal di drag del viewer (editing mouse stile AutoCAD)
        # I signal erano definiti in viewer.py ma non erano mai connessi (orfaned).
        if hasattr(self.viewer, "entity_dragged"):
            try:
                self.viewer.entity_dragged.connect(self._on_entity_dragged)
                self.viewer.entity_moved.connect(self._on_entity_moved)
                self.viewer.selection_picked.connect(self._on_selection_picked)
                self.viewer.hover_info.connect(self._on_hover_info)
            except Exception:
                pass  # NullViewer non ha questi signal

        # ---------- dock
        self.tree_panel = EntityTree(
            self.doc,
            self.viewer,
            selection_manager=self.selection_manager,
            visibility_manager=self.visibility_manager,
        )
        self.props_panel = PropertiesPanel(self.doc)
        self.log_panel = LogPanel()
        self.macro_panel = MacroPanel(self.engine)
        self.console = ConsolePanel(self._console_namespace())
        tabs = QTabWidget()
        tabs.addTab(self.console, "Console")
        tabs.addTab(self.log_panel, "Log")
        tabs.addTab(self.macro_panel, "Macro")

        d1 = QDockWidget("Albero", self)
        d1.setObjectName("dock_entity_tree")
        d1.setMinimumSize(180, 120)
        d1.setWidget(self.tree_panel)
        d1.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, d1)

        self.flow_panel = OpenSeesFlowPanel(self.doc)
        self.flow_dock = QDockWidget("Workflow OpenSees — Fasi / Tcl", self)
        self.flow_dock.setObjectName("dock_opensees_workflow")
        self.flow_dock.setMinimumSize(180, 100)
        self.flow_dock.setWidget(self.flow_panel)
        self.flow_dock.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.flow_dock)
        self.splitDockWidget(d1, self.flow_dock, Qt.Vertical)

        d2 = QDockWidget("Proprietà", self)
        d2.setObjectName("dock_properties")
        d2.setMinimumSize(180, 120)
        d2.setWidget(self.props_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, d2)
        d3 = QDockWidget("Console e macro", self)
        d3.setObjectName("dock_console_log_macro")
        d3.setMinimumSize(240, 90)
        d3.setWidget(tabs)
        self.addDockWidget(Qt.BottomDockWidgetArea, d3)

        self.command_line = CommandLineWidget()
        self._command_dock = QDockWidget("Command line", self)
        self._command_dock.setObjectName("dock_command_line")
        self._command_dock.setMinimumSize(240, 44)
        self._command_dock.setWidget(self.command_line)
        self._command_dock.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._command_dock)
        self.splitDockWidget(self._command_dock, d3, Qt.Vertical)
        self.command_line.command_issued.connect(self.command_line.execute)
        self.command_line.command_finished.connect(self._on_command_finished)
        self.command_line.cancelled.connect(
            lambda: self._log("Command line: operazione annullata"))

        d1.resize(320, 500)
        self._dock_tree = d1
        self._dock_flow = self.flow_dock
        self._dock_props = d2
        self._dock_console = d3
        self._dock_command = self._command_dock

        # ---------- menu e toolbar
        self._gui_actions = []
        self._setup_command_registry()
        self._build_menus()
        self._build_toolbars()
        self._register_gui_action_commands()
        self._set_mode("geometria")
        self._status_left = QLabel("Pronto")
        self._status_right = QLabel("Modalità: Geometria | 0 entità")
        sb = QStatusBar()
        sb.addWidget(self._status_left)
        sb.addPermanentWidget(self._status_right)
        self.setStatusBar(sb)
        self._restore_ui_state()
        # La finestra CAD deve occupare lo schermo; lo stato salvato in QSettings
        # non deve lasciare il viewer confinato in una geometria precedente.
        self.setWindowState(self.windowState() | Qt.WindowMaximized)
        self._carica_macro()
        self._refresh_all()
        QTimer.singleShot(0, self._apply_startup_layout)

    # ================================================================ costruzione UI
    def _build_menus(self):
        """Organizza i comandi reali secondo workflow CAD/CAE."""
        mb = self.menuBar()

        m = mb.addMenu("&File")
        m.addAction(self._act("Importa CAD…", self.act_importa_cad, "Ctrl+O"))
        m.addAction(self._act("Importa mesh .msh…", self.act_importa_msh, "Ctrl+I"))
        m.addSeparator()
        m.addAction(self._act("Esporta STEP…", self.act_export_step, "Ctrl+E"))
        m.addAction(self._act("Esporta BREP…", self._export_brep_command))
        m.addAction(self._act("Esporta mesh .msh…", self.act_export_msh))
        m.addAction(self._act("Esporta template .geo…", self.act_export_geo))
        m.addSeparator()
        m.addAction(self._act("Esporta OpenSees…", self.act_export_opensees, "Ctrl+Shift+O"))
        m.addSeparator()
        m.addAction(self._act("Chiudi", self.close, "Ctrl+Q"))

        m = mb.addMenu("&Edit")
        m.addAction(self._act("Undo", self.act_undo, "Ctrl+Z"))
        m.addAction(self._act("Redo", self.act_redo, "Ctrl+Y"))
        m.addSeparator()
        m.addAction(self._act("Elimina selezione", self.act_elimina, "Del"))
        m.addAction(self._act("Duplica selezione", self.act_duplica, "Ctrl+D"))
        t = m.addMenu("Transform")
        t.addAction(self._act("Move…", self.act_trasla_dialog, "M"))
        t.addAction(self._act("Rotate…", self.act_ruota_dialog, "R"))
        t.addAction(self._act("Scale…", self.act_scala_dialog, "S"))
        t.addAction(self._act("Mirror…", self.act_specchia_dialog))
        t.addAction(self._act("Offset…", self.act_offset))
        b = m.addMenu("Solid Modeling")
        b.addAction(self._act("Union", self.act_fusa))
        b.addAction(self._act("Difference", self.act_taglio))
        b.addAction(self._act("Intersection", self.act_inter))
        b.addAction(self._act("Fillet", self.act_raccorda))
        b.addAction(self._act("Chamfer", self.act_smussa))
        b.addAction(self._act("Cavity", self.act_svuota))
        e = m.addMenu("Explode")
        e.addAction(self._act("Faces", self.act_esplodi_facce))
        e.addAction(self._act("Edges / Curves", self.act_esplodi_curve))
        e.addAction(self._act("Vertices / Points", self.act_esplodi_punti))

        m = mb.addMenu("&View")
        for v in ("iso","front","top","right","left","bottom","back"):
            m.addAction(self._act(
                f"Vista {v}", lambda checked=False,vv=v:self.viewer.vista(vv)))
        m.addAction(self._act("Zoom Extents", self.viewer.fit_all, "Home"))
        m.addAction(self._act("Fit Selection", self._fit_selection, "F"))
        m.addAction(self._act("Wireframe / Shaded", self.act_toggle_wireframe, "W"))
        self._act_grid = self._act("Grid", self.act_toggle_grid, "G")
        self._act_grid.setCheckable(True)
        self._act_grid.setChecked(bool(getattr(self.viewer,"_grid_active",True)))
        m.addAction(self._act_grid)
        self._act_trihedron = self._act(
            "Axes / Trihedron", self.act_toggle_trihedron)
        self._act_trihedron.setCheckable(True)
        self._act_trihedron.setChecked(
            bool(getattr(self.viewer, "_trihedron_active", True)))
        m.addAction(self._act_trihedron)
        m.addAction(self._act("Snap", self.act_toggle_snap))
        m.addAction(self._act("Snap step…", self.act_set_snap_step))
        vis = m.addMenu("Visibility")
        cad = vis.addMenu("CAD / OpenCASCADE")
        self._cad_visibility_actions = {}
        for label,etype in (("Vertices","point"),("Edges / Curves","curve"),
                             ("Surfaces","face"),("Solids","solid")):
            a=self._act(label,lambda checked=False,t=etype:
                        self._set_cad_type_visibility(t,checked))
            a.setCheckable(True)
            a.setChecked(self.visibility_manager.is_cad_type_visible(etype))
            cad.addAction(a)
            self._cad_visibility_actions[etype]=a
        cad.addSeparator()
        cad.addAction(self._act("Show all CAD",lambda:self._set_all_cad_visibility(True)))
        cad.addAction(self._act("Hide all CAD",lambda:self._set_all_cad_visibility(False)))
        cad.addAction(self._act("Invert CAD",self._invert_cad_visibility))
        meshv=vis.addMenu("Mesh / Gmsh")
        self._act_mesh_visible=self._act("Mesh blocks",self.act_toggle_mesh_visibility)
        self._act_mesh_visible.setCheckable(True)
        self._act_mesh_visible.setChecked(self.visibility_manager.is_mesh_visible())
        meshv.addAction(self._act_mesh_visible)
        self._act_node_labels=self._act("Node labels",self.act_toggle_node_labels)
        self._act_node_labels.setCheckable(True)
        meshv.addAction(self._act_node_labels)
        self._act_elem_labels=self._act("Element labels",self.act_toggle_element_labels)
        self._act_elem_labels.setCheckable(True)
        meshv.addAction(self._act_elem_elem_labels) if False else meshv.addAction(self._act_elem_labels)
        osv=vis.addMenu("OpenSees")
        self._act_load_arrows=self._act("Load arrows",self.act_toggle_load_arrows)
        self._act_load_arrows.setCheckable(True)
        self._act_load_arrows.setChecked(True)
        osv.addAction(self._act_load_arrows)
        self._act_constraint_sym=self._act(
            "Constraint symbols",self.act_toggle_constraint_symbols)
        self._act_constraint_sym.setCheckable(True)
        self._act_constraint_sym.setChecked(True)
        osv.addAction(self._act_constraint_sym)

        m = mb.addMenu("&Geometry")
        cr=m.addMenu("Create")
        for k,label in (
            ("punto","Point"),("linea","Line"),("spline","Spline"),
            ("cerchio","Circle"),("arco","Arc"),("superficie","Surface"),
            ("rettangolo","Rectangle"),("box","Box"),("cilindro","Cylinder"),
            ("sfera","Sphere"),("cono","Cone"),("toro","Torus")):
            cr.addAction(self._act(
                label,lambda checked=False,kk=k:self._crea_dialog(kk)))
        cr.addSeparator()
        cr.addAction(self._act("Extrude…",self.act_estrudi_dialog))
        cr.addAction(self._act("Revolve…",self.act_rivolgi_dialog))
        m.addSeparator()
        for label,action in (
            ("Move…",self.act_trasla_dialog),("Rotate…",self.act_ruota_dialog),
            ("Scale…",self.act_scala_dialog),("Mirror…",self.act_specchia_dialog),
            ("Offset…",self.act_offset),("Measure",self._measure_selection),
            ("Geometry validation",self._geometry_validation),
            ("Import STEP/IGES/BREP…",self.act_importa_cad),
            ("Export STEP…",self.act_export_step),
        ):
            m.addAction(self._act(label,action))

        m = mb.addMenu("&Mesh")
        m.addAction(self._act("Import .msh…",self.act_importa_msh))
        m.addAction(self._act("Generate mesh…",self.act_mesha,"Ctrl+M"))
        m.addAction(self._act(
            "Structured quad/hex…",self.act_mesha_structured,"Ctrl+Shift+M"))
        ins=m.addMenu("Mesh Inspection")
        for label,action in (
            ("All elements",lambda:self._mesh_action("all")),
            ("Elements in box…",lambda:self._mesh_action("box")),
            ("Elements in sphere…",lambda:self._mesh_action("sfera")),
            ("By physical group…",lambda:self._mesh_action("fisico")),
            ("Grow",lambda:self._mesh_action("grow")),
            ("Shrink",lambda:self._mesh_action("shrink")),
            ("Nodes of selection",lambda:self._mesh_action("nodi")),
        ):
            ins.addAction(self._act(label,action))
        m.addSeparator()
        m.addAction(self._act("Export .msh…",self.act_export_msh))
        m.addAction(self._act("OpenSees FEM assignment…",self.act_opensees_fem))

        m=mb.addMenu("Physical &Groups")
        for label,action in (
            ("Create from selection…",self.act_gruppo_da_selezione),
            ("Add selection to group…",self.act_aggiungi_gruppo),
            ("Remove selection from group…",self.act_rimuovi_gruppo),
            ("Automatic: planar surfaces",self.act_gruppo_piane),
            ("Automatic: curved surfaces",self.act_gruppo_curve),
            ("By physical tag…",self.act_gruppo_marker),
            ("Mesh group from selection…",self.act_gruppo_mesh),
            ("Rename…",self.act_rinomina_gruppo),
            ("Delete…",self.act_elimina_gruppo),
            ("Export group list…",self.act_export_gruppi),
            ("Export OpenSees nodes…",self.act_export_opensees_gruppi),
        ):
            m.addAction(self._act(label,action))

        m=mb.addMenu("&Tools")
        sm=m.addMenu("Selection")
        sm.addAction(self._act("All",lambda:sel.select_all(self.doc),"Ctrl+A"))
        sm.addAction(self._act("None",lambda:sel.select_none(self.doc),"Ctrl+Shift+A"))
        sm.addAction(self._act("Invert",lambda:sel.invert_selection(self.doc)))
        for t,label in (("point","Points"),("curve","Curves"),
                        ("face","Surfaces"),("solid","Solids")):
            sm.addAction(self._act(label,lambda checked=False,tt=t:
                                   sel.select_by_type(self.doc,tt)))
        for label,action in (
            ("By name…",self.act_sel_nome),("By group…",self.act_sel_gruppo),
            ("By physical tag…",self.act_sel_marker),("By color…",self.act_sel_colore),
            ("In box…",self.act_sel_box),("In sphere…",self.act_sel_sfera),
            ("By plane half-space…",self.act_sel_piano),("Nearest N…",self.act_sel_vicine),
            ("By size…",self.act_sel_dimensione),("By normal…",self.act_sel_normale),
            ("Smallest N…",self.act_sel_piccole),("Largest N…",self.act_sel_grandi),
        ):
            sm.addAction(self._act(label,action))
        sm.addSeparator()
        sm.addAction(self._act("Grow",lambda:sel.grow_selection(self.doc),"Ctrl+G"))
        sm.addAction(self._act("Shrink",lambda:sel.shrink_selection(self.doc),"Ctrl+Shift+G"))
        sm.addAction(self._act("Connected component",lambda:sel.select_connected(self.doc)))
        mac=m.addMenu("Macros")
        mac.addAction(self._act("Reload",self._carica_macro,"F5"))
        mac.addAction(self._act("New macro…",self.act_nuova_macro))
        mac.addAction(self._act("Open macro folder…",self.act_apri_cartella_macro))
        self._menu_macro=mac.addMenu("Run macro…")
        self._menu_macro.aboutToShow.connect(self._riempi_menu_macro)

        osmenu=m.addMenu("OpenSees / CAE")
        for label,action in (
            ("FEM model…",self.act_opensees_fem),
            ("Solver and stages…",self.act_opensees_solver_stages),
            ("Workflow phases / Tcl…",self.act_show_opensees_flow),
            ("Validate model…",self.act_validate_opensees_model),
            ("Run Tcl…",self.act_run_opensees),
            ("Fix…",self.act_opensees_fix),("Loads…",self.act_opensees_load),
            ("EqualDOF…",self.act_opensees_equaldof),
        ):
            osmenu.addAction(self._act(label,action))
        adv=osmenu.addMenu("Advanced catalog")
        for label,action in (
            ("Command browser…",self.act_opensees_command_browser),
            ("Section…",self.act_define_section),("geomTransf…",self.act_define_geom_transf),
            ("beamIntegration…",self.act_define_beam_integration),
            ("eleLoad…",self.act_define_ele_load),("region…",self.act_define_region),
            ("parameter…",self.act_define_parameter),("setParameter…",self.act_set_parameter),
            ("updateMaterials…",self.act_update_materials),("Rayleigh damping…",self.act_set_rayleigh),
            ("Nodal mass…",self.act_add_nodal_mass),
        ):
            adv.addAction(self._act(label,action))
        ph=adv.addMenu("Stages / phases")
        for label,action in (
            ("New phase…",self.act_nuova_fase),("Change phase…",self.act_cambia_fase),
            ("Assign phase property…",self.act_assegna_proprieta),
            ("Assign phase constraint…",self.act_assegna_vincolo),
        ):
            ph.addAction(self._act(label,action))

        m=mb.addMenu("&Window")
        for dock in (self._dock_tree,self._dock_flow,self._dock_props,
                     self._dock_command,self._dock_console):
            m.addAction(dock.toggleViewAction())

        m=mb.addMenu("&Settings")
        self._act_settings_snap=self._act("Snap enabled",self.act_toggle_snap)
        self._act_settings_snap.setCheckable(True)
        self._act_settings_snap.setChecked(True)
        m.addAction(self._act_settings_snap)
        self._act_settings_grid=self._act("Grid enabled",self.act_toggle_grid)
        self._act_settings_grid.setCheckable(True)
        self._act_settings_grid.setChecked(True)
        m.addAction(self._act_settings_grid)
        m.addSeparator()
        m.addAction(self._act("Save UI layout",self._save_ui_state))
        m.addAction(self._act("Restore saved UI layout",self._restore_ui_state))
        m.addAction(self._act("Reset UI layout",self._reset_ui_layout))

        m=mb.addMenu("&Help")
        m.addAction(self._act("Quick guide",self.act_guida))
        m.addAction(self._act("Selection commands",self.act_guida_selezione))
        m.addAction(self._act("Keyboard / Command line",self._show_command_help))
        m.addAction(self._act("About",self.act_info))

    def _build_toolbars(self):
        tbw=QToolBar("Workspace",self)
        tbw.setObjectName("toolbar_workspace")
        tbw.setMovable(False)
        tbw.addWidget(QLabel(" Workspace: "))
        self._workspace_combo=QComboBox()
        self._workspace_combo.addItems(["CAD","Mesh"])
        self._workspace_combo.currentTextChanged.connect(
            lambda v:self._set_mode("mesh" if v=="Mesh" else "geometria"))
        tbw.addWidget(self._workspace_combo)
        tbw.addSeparator()
        tbw.addAction(self._act("Undo",self.act_undo,"Ctrl+Z"))
        tbw.addAction(self._act("Redo",self.act_redo,"Ctrl+Y"))
        tbw.addAction(self._act("Delete",self.act_elimina,"Del"))
        tbw.addSeparator()
        tbw.addAction(self._act("Fit",self.viewer.fit_all,"Home"))
        tbw.addAction(self._act("Fit Selection",self._fit_selection,"F"))
        tbw.addAction(self._act("Iso",lambda:self.viewer.vista("iso")))
        tbw.addSeparator()
        tbw.addWidget(QLabel(" Filter: "))
        self._selection_filter_combo=QComboBox()
        self._selection_filter_combo.addItems(["All","Points","Curves","Surfaces","Solids"])
        self._selection_filter_combo.currentTextChanged.connect(
            self._on_selection_filter_changed)
        tbw.addWidget(self._selection_filter_combo)
        tbw.addSeparator()
        tbw.addAction(self._act("Command line",self._focus_command_line))
        self.addToolBar(tbw)
        self._tb_workspace=tbw

        tb=QToolBar("CAD · Create / Modify",self)
        tb.setObjectName("toolbar_cad")
        for k,label in (("punto","Point"),("linea","Line"),("spline","Spline"),
                        ("cerchio","Circle"),("arco","Arc"),("rettangolo","Rectangle"),
                        ("box","Box"),("cilindro","Cylinder"),("sfera","Sphere")):
            tb.addAction(self._act(label,lambda checked=False,kk=k:self._crea_dialog(kk)))
        tb.addSeparator()
        for label,action in (
            ("Move",self.act_trasla_dialog),("Rotate",self.act_ruota_dialog),
            ("Scale",self.act_scala_dialog),("Mirror",self.act_specchia_dialog),
            ("Offset",self.act_offset),("Measure",self._measure_selection),
        ):
            tb.addAction(self._act(label,action))
        tb.addSeparator()
        tb.addAction(self._act("Union",self.act_fusa))
        tb.addAction(self._act("Difference",self.act_taglio))
        tb.addAction(self._act("Intersection",self.act_inter))
        tb.addAction(self._act("Validate",self._geometry_validation))
        self._tb_geometria=tb
        self.addToolBar(tb)

        tb2=QToolBar("Mesh · Setup / Inspection",self)
        tb2.setObjectName("toolbar_mesh")
        for label,action in (
            ("Import",self.act_importa_msh),("Generate",self.act_mesha),
            ("Structured",self.act_mesha_structured),
            ("All",lambda:self._mesh_action("all")),("Box",lambda:self._mesh_action("box")),
            ("Sphere",lambda:self._mesh_action("sfera")),("Physical",lambda:self._mesh_action("fisico")),
            ("Grow",lambda:self._mesh_action("grow")),("Shrink",lambda:self._mesh_action("shrink")),
            ("Nodes",lambda:self._mesh_action("nodi")),
            ("Physical Groups",self.act_gruppo_da_selezione),
            ("OpenSees FEM",self.act_opensees_fem),
        ):
            tb2.addAction(self._act(label,action))
        self._tb_mesh=tb2
        self.addToolBar(tb2)

        tb3=QToolBar("Interaction",self)
        tb3.setObjectName("toolbar_interaction")
        self._act_drag=self._act(
            "Drag edit",lambda:self.act_mouse_edit(self._act_drag.isChecked()))
        self._act_drag.setCheckable(True)
        tb3.addAction(self._act_drag)
        self._act_snap_toolbar=self._act("Snap",self.act_toggle_snap)
        self._act_snap_toolbar.setCheckable(True)
        self._act_snap_toolbar.setChecked(True)
        tb3.addAction(self._act_snap_toolbar)
        tb3.addAction(self._act("Grid",self.act_toggle_grid))
        self._act_trihedron_toolbar = self._act(
            "Trihedro", self.act_toggle_trihedron)
        self._act_trihedron_toolbar.setCheckable(True)
        self._act_trihedron_toolbar.setChecked(
            bool(getattr(self.viewer, "_trihedron_active", True)))
        tb3.addAction(self._act_trihedron_toolbar)
        self.addToolBar(tb3)
        self._tb_interaction=tb3

    # ==================================================================== fasi
    def act_nuova_fase(self):
        nome, ok = QInputDialog.getText(self, "Nuova fase",
                                        "Nome della fase (es. 'Getto pilastri'):")
        if not ok or not nome.strip():
            return
        ph = self.doc.phases.add_phase(nome.strip())
        self._log(ph.summary())
        self.doc.notify("phases_changed", {"tag": ph.tag})
        self._refresh_all()

    def act_cambia_fase(self):
        tags = [p.tag for p in sorted(self.doc.phases.phases, key=lambda x: x.tag)]
        if not tags:
            return self._log("Nessuna fase definita (Fasi ▸ Nuova fase)")
        scelte = [f"{p.tag}: {p.nome}" for p in
                  sorted(self.doc.phases.phases, key=lambda x: x.tag)]
        s, ok = QInputDialog.getItem(self, "Fase corrente", "Seleziona fase:",
                                     scelte, 0, False)
        if ok and s:
            tag = int(s.split(":")[0])
            self.doc.phases.set_current(tag)
            self._log(f"Fase corrente: {tag} — attive: "
                      f"{len(self.doc.phases.active_entities())} entità")
            self.doc.notify("phases_changed", {"tag": tag})
            self._refresh_all()

    def act_assegna_proprieta(self):
        """Associa una proprietà fisica (tipo elemento/materiale/sezione) alle
        entità selezionate nella fase corrente."""
        from gcs.core.fases import ElementProperty, TIPI_ELEMENTO_FISICO
        enti = self.doc.selected_entities()
        if not enti:
            return self._log("Seleziona prima le entità da associare")
        kinds = list(TIPI_ELEMENTO_FISICO)
        k, ok = QInputDialog.getItem(self, "Tipo elemento fisico",
                                     "Classe dell'elemento:", kinds, 0, False)
        if not ok:
            return
        mat, ok1 = QInputDialog.getInt(self, "Materiale", "ID materiale:", 1, 1)
        sez, ok2 = QInputDialog.getInt(self, "Sezione", "ID sezione:", 1, 1)
        if not (ok1 and ok2):
            return
        ph = self.doc.phases.get(self.doc.phases.current_tag) \
            or self.doc.phases.add_phase(f"Fase {self.doc.phases.current_tag}")
        prop = ElementProperty(k, f"{k}-{mat}", mat, sez)
        for e in enti:
            ph.set_property(e.id, prop)
        self._log(f"Associata proprietà {prop!r} a {len(enti)} entità "
                  f"(fase {ph.tag})")
        self.doc.notify("phases_changed", {"tag": ph.tag})
        self._refresh_all()

    def act_assegna_vincolo(self):
        from gcs.core.fases import VINCOLI
        enti = self.doc.selected_entities()
        if not enti:
            return self._log("Seleziona prima i nodi/entità da vincolare")
        v, ok = QInputDialog.getItem(self, "Vincolo", "Tipo di vincolo:",
                                     VINCOLI, 0, False)
        if not ok:
            return
        ph = self.doc.phases.get(self.doc.phases.current_tag) \
            or self.doc.phases.add_phase(f"Fase {self.doc.phases.current_tag}")
        for e in enti:
            ph.assign_constraint(e.id, v)
        self._log(f"Vincolo '{v}' assegnato a {len(enti)} entità (fase {ph.tag})")
        self.doc.notify("phases_changed", {"tag": ph.tag})
        self._refresh_all()

    def act_solver_pack(self):
        """Assegna un pacchetto solutore alla fase corrente."""
        from PySide6.QtWidgets import QDialog
        from gcs.gui.dialogs import ParamDialog
        from gcs.core.macro_engine import Param
        from gcs.core.fases import SolverPack
        ph = self.doc.phases.get(self.doc.phases.current_tag) \
            or self.doc.phases.add_phase(f"Fase {self.doc.phases.current_tag}")
        old = ph.solver_pack

        class _Spec:
            name = f"Solutore fase {ph.tag}"
            description = ("Pacchetto solutore OpenSees per questa fase "
                           "(analysis/numberer/system/test/algorithm/solver).")
            applies_to = ()
            params = [Param("nome", "str", old.nome if old else "Umfpack-Static"),
                      Param("analisatore", "choice",
                            old.analisatore if old else "Static",
                            choices=("Static", "Transient", "Modal", "Eigen")),
                      Param("soluzione", "choice",
                            old.soluzione if old else "Umfpack",
                            choices=("Umfpack", "SparseGeneral", "BandGeneral",
                                     "ProfileSPD", "LDLT", "ARPACK")),
                      Param("numero", "choice",
                            old.numero if old else "BandGeneral",
                            choices=("BandGeneral", "RCM", "AMD",
                                     "OriginalNumberer")),
                      Param("sistema", "choice",
                            old.sistema if old else "SparseSymmetric",
                            choices=("SparseSymmetric", "SparseGeneral",
                                     "BandGeneral", "FullGeneral"))]
            @staticmethod
            def targets_label():
                return "fase corrente"

        dlg = ParamDialog(_Spec, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        vals = dlg.values()
        ph.solver_pack = SolverPack(vals["nome"], vals["analisatore"],
                                    vals["soluzione"], vals["numero"],
                                    vals["sistema"])
        self._log(f"Solutore '{vals['nome']}' assegnato alla fase {ph.tag}")
        self.doc.notify("phases_changed", {"tag": ph.tag})

    def act_update_parameters(self):
        """Aggiorna i parametri globali del modello (comando update parameters)."""
        from PySide6.QtWidgets import QDialog
        from gcs.gui.dialogs import ParamDialog
        from gcs.core.macro_engine import Param
        doc_par = self.doc.parameters
        chiavi = sorted(doc_par) or ["h", "L", "R"]

        class _Spec:
            name = "Update parameters"
            description = ("Aggiorna i parametri assegnati al modello; dopo "
                           "l'ok il documento notifica 'parameters_changed'.")
            applies_to = ()
            params = [Param(k, "float", float(doc_par.get(k, 1.0)))
                      for k in chiavi]
            @staticmethod
            def targets_label():
                return "modello globale"
        dlg = ParamDialog(_Spec, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        nuovi = dlg.values()
        self.doc.update_parameters(**{k: float(v) for k, v in nuovi.items()})
        self._log("Parametri aggiornati: "
                  + ", ".join(f"{k}={v:g}" for k, v in self.doc.parameters.items()))

    def act_export_phase_model(self):
        """Esporta il modello come script Tcl per OpenSees."""
        from gcs.core.opensees_mapping import ModelMapper
        path, _ = QFileDialog.getSaveFileName(self, "Esporta script OpenSees",
                                              "modello.tcl",
                                              "Script Tcl (*.tcl);;Tutti (*)")
        if not path:
            return
        try:
            ModelMapper(self.doc, self.doc.phases).write(path)
            self._log(f"Script OpenSees scritto in {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Export OpenSees", str(exc))

    def act_mostra_fasi(self):
        self._log(self.doc.phases.summary())

    def act_bridge_phases(self):
        """Sincronizza PhaseManager con OpenSeesManager.stages."""
        try:
            self.doc.phases.bridge_to_stages(self.doc.opensees)
            self._log(f"Bridge completato: {len(self.doc.opensees.stages)} fasi sincronizzate.")
        except Exception as exc:
            self._log(f"Errore bridge fasi: {exc}")

    # --- Toggle visualizzazioni OpenSees ---
    def _set_cad_type_visibility(self, etype, visible):
        self.visibility_manager.set_cad_type_visible(etype, visible)
        self._sync_visibility_actions()
        self._log(f"Visibilità CAD {etype}: {'ON' if visible else 'OFF'}")

    def _set_all_cad_visibility(self, visible):
        self.visibility_manager.set_all_cad_visible(visible)
        self.tree_panel.refresh()
        self._log(f"Visibilità CAD: {'ON' if visible else 'OFF'}")

    def _invert_cad_visibility(self):
        self.visibility_manager.invert_cad_visibility()
        self.tree_panel.refresh()
        self._log("Visibilità CAD: invertita")

    def act_toggle_mesh_visibility(self):
        on = not self.visibility_manager.is_mesh_visible()
        self.visibility_manager.set_mesh_visible(on)
        self._sync_visibility_actions()
        self._log(f"Visibilità blocchi mesh: {'ON' if on else 'OFF'}")

    def act_toggle_trihedron(self):
        if hasattr(self.viewer, "toggle_trihedron"):
            on = self.viewer.toggle_trihedron()
            for action_name in ("_act_trihedron", "_act_trihedron_toolbar"):
                action = getattr(self, action_name, None)
                if action is not None:
                    action.blockSignals(True)
                    action.setChecked(on)
                    action.blockSignals(False)
            self._log(f"Trihedro: {'ON' if on else 'OFF'}")

    def _sync_visibility_actions(self):
        for etype, action in getattr(self, "_cad_visibility_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(self.visibility_manager.is_cad_type_visible(etype))
            action.blockSignals(False)
        action = getattr(self, "_act_mesh_visible", None)
        if action is not None:
            action.blockSignals(True)
            action.setChecked(self.visibility_manager.is_mesh_visible())
            action.blockSignals(False)


    def act_toggle_node_labels(self):
        if hasattr(self.viewer, "toggle_node_labels"):
            on = self.viewer.toggle_node_labels()
            self._log(f"Etichette nodi: {'ON' if on else 'OFF'}")
            if hasattr(self, "_act_node_labels"):
                self._act_node_labels.setChecked(on)

    def act_toggle_element_labels(self):
        if hasattr(self.viewer, "toggle_element_labels"):
            on = self.viewer.toggle_element_labels()
            self._log(f"Etichette elementi: {'ON' if on else 'OFF'}")
            if hasattr(self, "_act_elem_labels"):
                self._act_elem_labels.setChecked(on)

    def act_toggle_load_arrows(self):
        if hasattr(self.viewer, "toggle_load_arrows"):
            on = self.viewer.toggle_load_arrows()
            self._log(f"Frecce carichi: {'ON' if on else 'OFF'}")
            if hasattr(self, "_act_load_arrows"):
                self._act_load_arrows.setChecked(on)

    def act_toggle_constraint_symbols(self):
        if hasattr(self.viewer, "toggle_constraint_symbols"):
            on = self.viewer.toggle_constraint_symbols()
            self._log(f"Simboli vincoli: {'ON' if on else 'OFF'}")
            if hasattr(self, "_act_constraint_sym"):
                self._act_constraint_sym.setChecked(on)

    def act_toggle_snap(self):
        if hasattr(self.viewer, "set_snap_enabled"):
            new_state = not getattr(self.viewer, "_snap_enabled", True)
            self.viewer.set_snap_enabled(new_state)
            self._sync_visual_preferences()
            self._log(f"Snapping: {'ON' if new_state else 'OFF'}")

    def act_set_snap_step(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        if not hasattr(self.viewer, "set_snap_grid_step"):
            return
        cur = getattr(self.viewer, "_snap_grid_step", 1.0)
        val, ok = QInputDialog.getDouble(self, "Step griglia snap",
                                          "Step (unità modello):",
                                          value=cur, min=0.001,
                                          max=1000.0, decimals=4)
        if ok:
            self.viewer.set_snap_grid_step(val)
            self._log(f"Snap step impostato a {val}")

    # --- Nuovi comandi estesi: sezioni, geomTransf, beamIntegration, eleLoad, region ---
    def act_define_section(self):
        from .dialogs import SectionDialog
        try:
            dlg = SectionDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("Sezione definita e aggiunta al modello.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore definizione sezione: {exc}")

    def act_define_geom_transf(self):
        from .dialogs import GeomTransfDialog
        try:
            dlg = GeomTransfDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("geomTransf definita.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore definizione geomTransf: {exc}")

    def act_define_beam_integration(self):
        from .dialogs import BeamIntegrationDialog
        try:
            dlg = BeamIntegrationDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("beamIntegration definita.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore definizione beamIntegration: {exc}")

    def act_define_ele_load(self):
        from .dialogs import ElementLoadDialog
        try:
            dlg = ElementLoadDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("eleLoad aggiunto.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore definizione eleLoad: {exc}")

    def act_define_region(self):
        from .dialogs import RegionDialog
        try:
            dlg = RegionDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("Region definita.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore definizione region: {exc}")

    # --- Parametri ---
    def act_define_parameter(self):
        from .dialogs import ParameterDialog
        try:
            dlg = ParameterDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("Parameter definito.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore definizione parameter: {exc}")

    def act_set_parameter(self):
        from .dialogs import SetParameterDialog
        try:
            dlg = SetParameterDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("setParameter aggiunto.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore setParameter: {exc}")

    def act_update_materials(self):
        from .dialogs import UpdateMaterialsDialog
        try:
            dlg = UpdateMaterialsDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("updateMaterials aggiunto.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore updateMaterials: {exc}")

    def act_set_rayleigh(self):
        from .dialogs import RayleighDialog
        try:
            dlg = RayleighDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("Smorzamento Rayleigh impostato.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore Rayleigh: {exc}")

    def act_add_nodal_mass(self):
        from .dialogs import NodalMassDialog
        try:
            dlg = NodalMassDialog(self.doc, parent=self)
            if dlg.exec():
                self._log("Massa nodale aggiunta.")
                self._refresh_all()
        except Exception as exc:
            self._log(f"Errore massa nodale: {exc}")

    def act_mouse_edit(self, on: bool):
        setter = getattr(self.viewer, "set_mouse_edit", None)
        if callable(setter):
            setter(on)
            self._log("Editing mouse attivo: trascina un'entità per spostarla"
                      if on else "Editing mouse disattivato")

    # ==================================================================== utility
    # ========================================================= command line / UX
    def _setup_command_registry(self):
        specs = [
            CommandSpec("HELP", lambda a: self._command_help_text(),
                        "Elenco comandi", "HELP"),
            CommandSpec("CANCEL", lambda a: "Annullato",
                        "Annulla", "CANCEL"),
            CommandSpec("UNDO", lambda a: self.act_undo(), "Undo", "UNDO"),
            CommandSpec("REDO", lambda a: self.act_redo(), "Redo", "REDO"),
            CommandSpec("POINT", self._cmd_point, "Crea punto",
                        "POINT x y z", aliases=("P",)),
            CommandSpec("LINE", self._cmd_line, "Crea linea",
                        "LINE x1 y1 z1 x2 y2 z2", aliases=("L",)),
            CommandSpec("CIRCLE", self._cmd_circle, "Crea cerchio",
                        "CIRCLE cx cy cz r [nx ny nz]"),
            CommandSpec("BOX", self._cmd_box, "Crea box",
                        "BOX dx dy dz [bx by bz]"),
            CommandSpec("SPHERE", self._cmd_sphere, "Crea sfera",
                        "SPHERE r [cx cy cz]"),
            CommandSpec("ARC", self._cmd_arc, "Crea arco",
                        "ARC x1 y1 z1 xm ym zm x2 y2 z2"),
            CommandSpec("POLYLINE", self._cmd_polyline, "Crea polilinea",
                        "POLYLINE x1 y1 z1 x2 y2 z2 ..."),
            CommandSpec("RECTANGLE", self._cmd_rectangle, "Crea rettangolo",
                        "RECTANGLE cx cy width height [z]"),
            CommandSpec("CYLINDER", self._cmd_cylinder, "Crea cilindro",
                        "CYLINDER r h [bx by bz] [ax ay az]"),
            CommandSpec("CONE", self._cmd_cone, "Crea cono",
                        "CONE r1 r2 h [bx by bz] [ax ay az]"),
            CommandSpec("TORUS", self._cmd_torus, "Crea toro",
                        "TORUS rmajor rminor"),
            CommandSpec("EXTRUDE", self._cmd_extrude, "Estrudi un profilo",
                        "EXTRUDE profile_id dx dy dz"),
            CommandSpec("REVOLVE", self._cmd_revolve, "Rivoluzione di un profilo",
                        "REVOLVE profile_id px py pz ax ay az angle"),
            CommandSpec("MOVE", self._cmd_move, "Muove la selezione",
                        "MOVE dx dy dz", aliases=("M",)),
            CommandSpec("ROTATE", self._cmd_rotate, "Ruota la selezione",
                        "ROTATE px py pz ax ay az angle", aliases=("R",)),
            CommandSpec("SCALE", self._cmd_scale, "Scala la selezione",
                        "SCALE factor", aliases=("S",)),
            CommandSpec("DELETE", lambda a: self.act_elimina(),
                        "Elimina", "DELETE", aliases=("DEL",)),
            CommandSpec("COPY", lambda a: self.act_duplica(), "Duplica", "COPY"),
            CommandSpec("SELECT", self._cmd_select, "Selezione",
                        "SELECT ALL|NONE|VISIBLE|TYPE <type>"),
            CommandSpec("WORKSPACE", self._cmd_workspace, "Workspace",
                        "WORKSPACE CAD|MESH", aliases=("WS",)),
            CommandSpec("VIEW", self._cmd_view, "Vista",
                        "VIEW ISO|FRONT|TOP|RIGHT|LEFT|BOTTOM|BACK"),
            CommandSpec("ZOOM", self._cmd_zoom, "Zoom",
                        "ZOOM EXTENTS|SELECTION"),
            CommandSpec("GRID", self._cmd_grid, "Griglia", "GRID ON|OFF"),
            CommandSpec("SNAP", self._cmd_snap, "Snap", "SNAP ON|OFF"),
            CommandSpec("WIRE", self._cmd_wire, "Display", "WIRE ON|OFF"),
            CommandSpec("FIT", lambda a: self.viewer.fit_all(), "Fit", "FIT"),
            CommandSpec("MESH", self._cmd_mesh, "Mesh",
                        "MESH IMPORT path|MESH GENERATE"),
            CommandSpec("GROUP", self._cmd_group, "Gruppo",
                        "GROUP CREATE name"),
            CommandSpec("MACRO", self._cmd_macro, "Macro", "MACRO name"),
            CommandSpec("SAVE", self._cmd_save, "Export",
                        "SAVE STEP|BREP|MSH TO path"),
            CommandSpec("VALIDATE", lambda a: self.act_validate_opensees_model(),
                        "Validazione OpenSees", "VALIDATE"),
        ]
        self._base_command_specs = list(specs)
        self.command_line.set_commands(self._base_command_specs)

    def _register_gui_action_commands(self):
        """Espone ogni QAction anche dalla command line, senza duplicare la logica.

        I comandi GUI_* attivano esattamente la stessa QAction di menu/toolbar;
        quindi dialoghi, controlli di stato e logica restano condivisi.
        """
        specs = list(getattr(self, "_base_command_specs", []))
        used = {spec.name.upper() for spec in specs}
        self._gui_action_command_names = {}
        for action in getattr(self, "_gui_actions", []):
            label = action.text().replace("&", "").replace("…", "")
            import re
            stem = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_").upper()
            stem = stem or "ACTION"
            name = "GUI_" + stem
            suffix = 2
            while name in used:
                name = f"GUI_{stem}_{suffix}"
                suffix += 1
            used.add(name)
            self._gui_action_command_names[id(action)] = name
            specs.append(CommandSpec(
                name,
                lambda args, act=action: act.trigger(),
                f"Esegue l'azione GUI: {label}",
                name,
            ))
        self.command_line.set_commands(specs)
        self._log(f"Command line pronta: {len(specs)} comandi disponibili (HELP per l'elenco).")

    def _apply_startup_layout(self):
        """Massimizza la finestra e ripristina proporzioni utili delle palette."""
        try:
            self.showMaximized()
            # Le palette restano laterali/inferiori; il viewer centrale assorbe
            # tutto lo spazio residuo invece di conservare dimensioni obsolete.
            self.resizeDocks([self._dock_tree], [250], Qt.Horizontal)
            self.resizeDocks([self._dock_props], [285], Qt.Horizontal)
            self.resizeDocks([self._dock_tree, self._dock_flow], [300, 190], Qt.Vertical)
            self.resizeDocks([self._dock_command, self._dock_console], [42, 165], Qt.Vertical)
            self.viewer.updateGeometry()
            canvas = getattr(self.viewer, "_canvas", None)
            if canvas is not None:
                canvas.updateGeometry()
                canvas.update()
        except Exception as exc:
            self._log(f"Layout iniziale: {type(exc).__name__}: {exc}")

    def _trace_gui_action(self, label, slot, action=None):
        callback = getattr(slot, "__name__", None) or type(slot).__name__
        command = getattr(self, "_gui_action_command_names", {}).get(id(action), "")
        route = f"{command} | " if command else ""
        self._log(f"[GUI] {route}{label} → {callback}")
        if hasattr(self, "command_line"):
            self.command_line.set_state(f"GUI: {label}")

    def _command_help_text(self):
        seen=set(); lines=[]
        for spec in sorted(self.command_line.commands.values(),key=lambda x:x.name):
            if spec.name in seen: continue
            seen.add(spec.name)
            lines.append(f"{spec.name:10s} {spec.usage:42s} {spec.description}")
        self._log("\n".join(lines))
        return "HELP scritto nel log"

    def _on_command_finished(self,raw,ok,message):
        self._log(f"[CMD {'OK' if ok else 'ERR'}] {raw}"
                  + (f" → {message}" if message else ""))

    def _focus_command_line(self):
        self._command_dock.show()
        self._command_dock.raise_()
        self.command_line.focus_input()

    @staticmethod
    def _floats(args,n,usage):
        if len(args)!=n:
            raise ValueError(f"Uso: {usage}")
        try:
            return [float(str(x).strip("\"'")) for x in args]
        except ValueError as exc:
            raise ValueError(
                f"Parametri numerici non validi. Uso: {usage}") from exc

    def _cmd_point(self,args):
        x,y,z=self._floats(args,3,"POINT x y z")
        e=self.builder.punto(x,y,z)
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creato Punto {e.id}"

    def _cmd_line(self,args):
        v=self._floats(args,6,"LINE x1 y1 z1 x2 y2 z2")
        e=self.builder.linea(v[:3],v[3:6])
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creata Linea {e.id}"

    def _cmd_circle(self,args):
        if len(args) not in (4,7):
            raise ValueError("Uso: CIRCLE cx cy cz r [nx ny nz]")
        v=self._floats(args,len(args),"CIRCLE cx cy cz r [nx ny nz]")
        n=tuple(v[4:7]) if len(v)==7 else (0.0,0.0,1.0)
        e=self.builder.cerchio(*v[:4],normal=n)
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creato Cerchio {e.id}"

    def _cmd_box(self,args):
        if len(args) not in (3,6):
            raise ValueError("Uso: BOX dx dy dz [bx by bz]")
        v=self._floats(args,len(args),"BOX dx dy dz [bx by bz]")
        base=tuple(v[3:6]) if len(v)==6 else (0.0,0.0,0.0)
        e=self.builder.box(*v[:3],base=base)
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creato Box {e.id}"

    def _cmd_sphere(self,args):
        if len(args) not in (1,4):
            raise ValueError("Uso: SPHERE r [cx cy cz]")
        v=self._floats(args,len(args),"SPHERE r [cx cy cz]")
        center=tuple(v[1:4]) if len(v)==4 else (0.0,0.0,0.0)
        e=self.builder.sfera(v[0],center=center)
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creata Sfera {e.id}"

    def _cmd_arc(self,args):
        v=self._floats(args,9,"ARC x1 y1 z1 xm ym zm x2 y2 z2")
        e=self.builder.arco(v[:3],v[3:6],v[6:9])
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creato Arco {e.id}"

    def _cmd_polyline(self,args):
        if len(args)<6 or len(args)%3:
            raise ValueError("Uso: POLYLINE x1 y1 z1 x2 y2 z2 ...")
        v=self._floats(args,len(args),"POLYLINE x1 y1 z1 x2 y2 z2 ...")
        pts=[v[i:i+3] for i in range(0,len(v),3)]
        created=self.builder.polilinea(pts)
        self.selection_manager.set_selection([e.id for e in created],context="cad")
        return f"Create {len(created)} segmenti di polilinea"

    def _cmd_rectangle(self,args):
        if len(args) not in (4,5):
            raise ValueError("Uso: RECTANGLE cx cy width height [z]")
        v=self._floats(args,len(args),"RECTANGLE cx cy width height [z]")
        z=v[4] if len(v)==5 else 0.0
        e=self.builder.rettangolo(v[0],v[1],v[2],v[3],z=z)
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creato Rettangolo {e.id}"

    def _cmd_cylinder(self,args):
        if len(args) not in (2,5,8):
            raise ValueError("Uso: CYLINDER r h [bx by bz] [ax ay az]")
        v=self._floats(args,len(args),"CYLINDER r h [bx by bz] [ax ay az]")
        base=tuple(v[2:5]) if len(v)>=5 else (0.0,0.0,0.0)
        axis=tuple(v[5:8]) if len(v)==8 else (0.0,0.0,1.0)
        e=self.builder.cilindro(v[0],v[1],base=base,axis=axis)
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creato Cilindro {e.id}"

    def _cmd_cone(self,args):
        if len(args) not in (3,6,9):
            raise ValueError("Uso: CONE r1 r2 h [bx by bz] [ax ay az]")
        v=self._floats(args,len(args),"CONE r1 r2 h [bx by bz] [ax ay az]")
        base=tuple(v[3:6]) if len(v)>=6 else (0.0,0.0,0.0)
        axis=tuple(v[6:9]) if len(v)==9 else (0.0,0.0,1.0)
        e=self.builder.cono(v[0],v[1],v[2],base=base,axis=axis)
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creato Cono {e.id}"

    def _cmd_torus(self,args):
        v=self._floats(args,2,"TORUS rmajor rminor")
        e=self.builder.toro(v[0],v[1])
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creato Toro {e.id}"

    def _cmd_extrude(self,args):
        if len(args)!=4:
            raise ValueError("Uso: EXTRUDE profile_id dx dy dz")
        try:
            profile_id=int(float(args[0]))
        except ValueError as exc:
            raise ValueError("profile_id deve essere un intero") from exc
        v=self._floats(args[1:],3,"EXTRUDE profile_id dx dy dz")
        e=self.builder.estrudi(profile_id,*v)
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creata Estrusione {e.id}"

    def _cmd_revolve(self,args):
        if len(args)!=8:
            raise ValueError("Uso: REVOLVE profile_id px py pz ax ay az angle")
        try:
            profile_id=int(float(args[0]))
        except ValueError as exc:
            raise ValueError("profile_id deve essere un intero") from exc
        v=self._floats(args[1:],7,
                       "REVOLVE profile_id px py pz ax ay az angle")
        e=self.builder.rivolgi(profile_id,*v)
        self.selection_manager.set_selection([e.id],context="cad")
        return f"Creata Rivoluzione {e.id}"

    def _cmd_move(self,args):
        v=self._floats(args,3,"MOVE dx dy dz")
        ids=sorted(self.doc.selection)
        if not ids:
            raise ValueError("MOVE richiede una selezione")
        self.editor.trasla(ids,*v)
        return f"Traslate {len(ids)} entità"

    def _cmd_rotate(self,args):
        v=self._floats(args,7,"ROTATE px py pz ax ay az angle")
        ids=sorted(self.doc.selection)
        if not ids:
            raise ValueError("ROTATE richiede una selezione")
        self.editor.ruota(ids,*v)
        return f"Ruotate {len(ids)} entità"

    def _cmd_scale(self,args):
        v=self._floats(args,1,"SCALE factor")
        if not self.doc.selection:
            raise ValueError("SCALE richiede una selezione")
        self.editor.scala(self.doc.selection,v[0])
        return f"Scalate {len(self.doc.selection)} entità"

    def _cmd_select(self,args):
        if not args:
            raise ValueError("Uso: SELECT ALL|NONE|VISIBLE|TYPE <type>")
        h=args[0].upper()
        if h=="ALL": sel.select_all(self.doc)
        elif h in ("NONE","CLEAR"): sel.select_none(self.doc)
        elif h=="VISIBLE":
            self.selection_manager.set_selection(
                [e.id for e in self.doc.entities.values() if e.visible],
                context="cad")
        elif h=="TYPE" and len(args)==2:
            sel.select_by_type(self.doc,args[1].lower())
        else:
            raise ValueError("Uso: SELECT ALL|NONE|VISIBLE|TYPE <type>")
        return f"Selezionate {len(self.doc.selection)} entità"

    def _cmd_workspace(self,args):
        if len(args)!=1 or args[0].upper() not in ("CAD","MESH"):
            raise ValueError("Uso: WORKSPACE CAD|MESH")
        self._set_mode("mesh" if args[0].upper()=="MESH" else "geometria")
        return f"Workspace: {args[0].upper()}"

    def _cmd_view(self,args):
        if len(args)!=1:
            raise ValueError("Uso: VIEW ISO|FRONT|TOP|RIGHT|LEFT|BOTTOM|BACK")
        v=args[0].lower()
        if v not in ("iso","front","top","right","left","bottom","back"):
            raise ValueError("Vista non riconosciuta")
        self.viewer.vista(v)
        return f"Vista {v}"

    def _cmd_zoom(self,args):
        if len(args)!=1 or args[0].upper() not in ("EXTENTS","SELECTION"):
            raise ValueError("Uso: ZOOM EXTENTS|SELECTION")
        result=self.viewer.fit_all() if args[0].upper()=="EXTENTS" else self._fit_selection()
        if result is False: raise ValueError("Nessuna selezione")
        return "Zoom eseguito"

    def _cmd_grid(self,args):
        if len(args)!=1 or args[0].upper() not in ("ON","OFF"):
            raise ValueError("Uso: GRID ON|OFF")
        self.viewer.set_grid_active(args[0].upper()=="ON")
        self._sync_visual_preferences()
        return f"Grid {args[0].upper()}"

    def _cmd_snap(self,args):
        if len(args)!=1 or args[0].upper() not in ("ON","OFF"):
            raise ValueError("Uso: SNAP ON|OFF")
        self.viewer.set_snap_enabled(args[0].upper()=="ON")
        self._sync_visual_preferences()
        return f"Snap {args[0].upper()}"

    def _cmd_wire(self,args):
        if len(args)!=1 or args[0].upper() not in ("ON","OFF"):
            raise ValueError("Uso: WIRE ON|OFF")
        self.viewer.set_wireframe(args[0].upper()=="ON")
        return f"Wireframe {args[0].upper()}"

    def _cmd_mesh(self,args):
        if len(args)==2 and args[0].upper()=="IMPORT":
            model=self.doc.import_msh(args[1].strip("\"'"))
            self._set_mode("mesh")
            return f"Mesh importata: {model.name}"
        if len(args)==1 and args[0].upper()=="GENERATE":
            self.act_mesha()
            return "Dialog generazione mesh aperto"
        raise ValueError("Uso: MESH IMPORT path | MESH GENERATE")

    def _cmd_group(self,args):
        if len(args)>=2 and args[0].upper()=="CREATE":
            name=" ".join(args[1:]).strip("\"'")
            if not name: raise ValueError("Nome gruppo vuoto")
            self.doc.groups.group_from_selection(self.doc,name)
            return f"Gruppo '{name}' creato"
        raise ValueError("Uso: GROUP CREATE name")

    def _cmd_macro(self,args):
        if not args: raise ValueError("Uso: MACRO name")
        name=" ".join(args).strip("\"'")
        spec=self.engine.by_name(name)
        if spec is None: raise ValueError(f"Macro non trovata: {name}")
        self.run_macro(spec)
        return f"Macro '{spec.name}' avviata"

    def _cmd_save(self,args):
        if len(args)!=3 or args[1].upper()!="TO":
            raise ValueError("Uso: SAVE STEP|BREP|MSH TO path")
        kind=args[0].upper()
        path=args[2].strip("\"'")
        if kind=="STEP":
            self.doc.export_step(path)
        elif kind=="BREP":
            self.doc.export_brep(path)
        elif kind=="MSH":
            model=next(iter(self.doc.mesh_models.values()),None)
            if model is None: raise ValueError("Nessuna mesh")
            if model.stale: raise ValueError(f"Mesh '{model.name}' è STALE")
            gb.export_msh_22(model,path)
        else:
            raise ValueError("Formato non supportato")
        return f"Esportato {kind}: {path}"

    def _on_selection_filter_changed(self,text):
        mapping={"All":"all","Points":"point","Curves":"curve",
                 "Surfaces":"face","Solids":"solid"}
        if hasattr(self.viewer,"set_selection_filter"):
            self.viewer.set_selection_filter(mapping.get(text,"all"))
        self._update_status()

    def _sync_visual_preferences(self):
        for name,value in (
            ("_act_settings_snap",getattr(self.viewer,"_snap_enabled",True)),
            ("_act_settings_grid",getattr(self.viewer,"_grid_active",True)),
        ):
            action=getattr(self,name,None)
            if action is not None:
                action.blockSignals(True)
                action.setChecked(bool(value))
                action.blockSignals(False)
        if hasattr(self,"_act_snap_toolbar"):
            self._act_snap_toolbar.setChecked(
                bool(getattr(self.viewer,"_snap_enabled",True)))
        if hasattr(self,"_act_grid"):
            self._act_grid.setChecked(
                bool(getattr(self.viewer,"_grid_active",True)))

    def _fit_selection(self):
        fn=getattr(self.viewer,"fit_selection",None)
        return bool(fn and fn())

    def _measure_selection(self):
        entities=self.doc.selected_entities()
        if not entities:
            self._log("Seleziona un'entità da misurare"); return
        lines=[]
        for e in entities:
            if e.shape is None: continue
            try:
                if e.etype=="curve": lines.append(f"{e.name}: Length={ou.length_of(e.shape):.6g}")
                elif e.etype=="face": lines.append(f"{e.name}: Area={ou.area_of(e.shape):.6g}")
                elif e.etype=="solid": lines.append(f"{e.name}: Volume={ou.volume_of(e.shape):.6g}")
                else: lines.append(f"{e.name}: Point")
            except Exception as exc:
                lines.append(f"{e.name}: misura non disponibile ({exc})")
        self._log("\n".join(lines) if lines else "Misura non disponibile")

    def _geometry_validation(self):
        entities=[e for e in self.doc.selected_entities() if e.shape is not None]
        if not entities:
            self._log("Nessuna geometria selezionata da validare"); return
        try:
            from OCC.Core.BRepCheck import BRepCheck_Analyzer
        except ImportError:
            self._log("Validator OCC non disponibile"); return
        invalid=[]
        for e in entities:
            try:
                if not BRepCheck_Analyzer(e.shape).IsValid(): invalid.append(e.name)
            except Exception:
                invalid.append(e.name)
        self._log("Geometria valida" if not invalid else
                  "Geometrie non valide: "+", ".join(invalid))

    def _export_brep_command(self):
        path,_=QFileDialog.getSaveFileName(self,"Esporta BREP","","BREP (*.brep)")
        if path:
            try:
                self.doc.export_brep(path)
                self._log(f"Esportato BREP: {path}")
            except Exception as exc:
                self._errore("Export BREP",exc)

    def _show_command_help(self):
        self._focus_command_line()
        self._command_help_text()

    def _save_ui_state(self):
        s=QSettings("GmshCad-SOB","GmshCAD Studio")
        s.setValue("geometry",self.saveGeometry())
        s.setValue("windowState",self.saveState())
        s.setValue("workspace",self.doc.mode)
        s.setValue("snap_enabled",bool(getattr(self.viewer,"_snap_enabled",True)))
        s.setValue("snap_step",float(getattr(self.viewer,"_snap_grid_step",1.0)))
        s.setValue("grid_enabled",bool(getattr(self.viewer,"_grid_active",True)))
        s.setValue("selection_filter",getattr(self.viewer,"selection_filter","all"))

    def _restore_ui_state(self):
        s=QSettings("GmshCad-SOB","GmshCAD Studio")
        g=s.value("geometry"); st=s.value("windowState")
        if g:
            try:self.restoreGeometry(g)
            except Exception:pass
        if st:
            try:self.restoreState(st)
            except Exception:pass
        self._set_mode(
            "mesh" if str(s.value("workspace","geometria")).lower()=="mesh"
            else "geometria")
        if s.contains("snap_enabled"):
            self.viewer.set_snap_enabled(
                str(s.value("snap_enabled")).lower()=="true")
        if s.contains("snap_step"):
            try:self.viewer.set_snap_grid_step(float(s.value("snap_step")))
            except Exception:pass
        if s.contains("grid_enabled"):
            self.viewer.set_grid_active(
                str(s.value("grid_enabled")).lower()=="true")
        filt=s.value("selection_filter")
        if filt:
            mapping={"all":"All","point":"Points","curve":"Curves",
                     "face":"Surfaces","solid":"Solids"}
            self._selection_filter_combo.setCurrentText(
                mapping.get(str(filt),"All"))
        self._sync_visual_preferences()

    def _reset_ui_layout(self):
        for d in (self._dock_tree,self._dock_flow,self._dock_props,
                  self._dock_command,self._dock_console):
            d.show()
            d.setFloating(False)
        self.resize(1500, 900)
        # Mantiene il layout entro l'area disponibile dopo il ripristino dei dock.
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(self.width(), available.width()),
                        min(self.height(), available.height()))
        self._set_mode("geometria")
        self._log("Layout UI ripristinato")

    def closeEvent(self,event):  # noqa: N802
        self._save_ui_state()
        event.accept()

    def _act(self, testo, slot, shortcut=None) -> QAction:
        a = QAction(testo, self)
        # La traccia viene scritta prima dell'esecuzione, sia per menu sia per
        # toolbar e menu contestuali costruiti con questa factory.
        a.triggered.connect(
            lambda checked=False, label=testo, callback=slot, action=a:
            self._trace_gui_action(label, callback, action)
        )
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if hasattr(self, "_gui_actions"):
            self._gui_actions.append(a)
        return a

    def _log(self, msg):
        # Tutti gli eventi e i percorsi dei comandi sono visibili anche nella
        # Console Python, oltre che nel tab Log e nella barra di stato.
        if hasattr(self, "log_panel"):
            self.log_panel.log(msg)
        if hasattr(self, "console"):
            self.console.log(msg)
        if hasattr(self, "_status_left"):
            self._status_left.setText(str(msg))

    def _on_doc_event(self, event, data):
        if event in ("entity_added", "entities_removed", "entity_updated",
                     "entities_changed", "history_changed", "macro_completed",
                     "mesh_imported", "entities_added_batch"):
            self._refresh_all()
        elif event == "opensees_condition_added":
            self.doc.opensees.refresh_entity_metadata()
            self._refresh_all()
        elif event == "opensees_flow_changed":
            if hasattr(self, "flow_panel"):
                self.flow_panel.refresh()
            self._update_status()
        elif event == "selection_changed":
            self.props_panel.refresh()
            self.tree_panel.refresh()
            if self.viewer is not None:
                self.viewer.highlight_selection()
            self._update_status()
        elif event == "visibility_changed":
            self.tree_panel.refresh()
            self._sync_visibility_actions()
            self._update_status()
        elif event == "mesh_stale":
            self.tree_panel.refresh()
            models = ", ".join(data.get("models", [])) if isinstance(data, dict) else ""
            if self.viewer is not None:
                self.viewer.redraw_all(fit=False)
            self._log(
                "ATTENZIONE: la mesh non è più coerente con la geometria"
                + (f" ({models})" if models else "")
                + ". La mesh stale è nascosta; rigenerare/reimportare prima dell'analisi/export.")
            self._update_status()

    # ----- handler per il drag del mouse (editing interattivo stile AutoCAD)
    def _on_entity_dragged(self, eid, dx, dy, dz):
        """Aggiornamento live durante il drag: trasla l'entità senza push undo."""
        if eid is None or eid not in self.doc.entities:
            return
        try:
            # Trasla l'entità senza registrare undo a ogni delta (troppi record)
            self.editor.trasla([eid], dx, dy, dz, push_undo=False)
            if self.viewer is not None:
                self.viewer.redraw_all(fit=False)
        except Exception:
            pass

    def _on_entity_moved(self, eid, dx, dy, dz):
        """Commit finale del drag: una singola operazione con undo."""
        if eid is None or eid not in self.doc.entities:
            return
        try:
            # L'entità è già stata traslata durante il drag;
            # qui registriamo l'undo entry per il blocco completo.
            self.doc.push_history(f"Trascina entità {eid}")
            self._update_status()
        except Exception:
            pass

    def _on_selection_picked(self, ids):
        """Aggiorna la selezione logica dal pick CAD."""
        if not isinstance(ids, (list, tuple, set)):
            return
        try:
            values = {int(i) for i in ids}
            self.selection_manager.set_context("cad")
            if values != set(self.doc.selection):
                self.selection_manager.set_selection(values)
        except Exception:
            pass

    def _on_hover_info(self, text):
        if hasattr(self, "_status_left"):
            self._status_left.setText(str(text) if text else "Pronto")

    def _refresh_all(self):
        self.tree_panel.refresh()
        self.props_panel.refresh()
        if hasattr(self, "flow_panel"):
            self.flow_panel.refresh()
        if self.viewer is not None:
            self.viewer.redraw_all(fit=False)
        self._update_status()

    def _update_status(self):
        enti = len(self.doc.selected_entities())
        filt = getattr(self.viewer, "selection_filter", "all")
        mesh_info = ""
        stale = []
        for m in self.doc.mesh_models.values():
            mesh_info += (
                f" | {m.name}: {len(m.sel_nodes)} nodi, "
                f"{len(m.sel_elements)} elem.")
            if m.stale:
                stale.append(m.name)
        stale_text = f" | MESH STALE: {', '.join(stale)}" if stale else ""
        context = getattr(self.selection_manager, "context", "cad")
        self._status_right.setText(
            f"Workspace: {'CAD' if self.doc.mode == 'geometria' else 'Mesh'} | "
            f"Selection: {context.upper()} | Filtro: {filt} | "
            f"{enti} entità selezionate{mesh_info}{stale_text}")

    def _console_namespace(self):
        import gcs.core.selectors as sel_mod
        ns = {
            "doc": self.doc, "builder": self.builder, "editor": self.editor,
            "engine": self.engine, "sel": sel_mod, "gb": gb,
            "select_all": sel_mod.select_all, "select_by_type": sel_mod.select_by_type,
            "select_box": sel_mod.select_box, "select_sphere": sel_mod.select_sphere,
            "select_by_normal": sel_mod.select_by_normal,
            "select_planar": sel_mod.select_planar, "select_curved": sel_mod.select_curved,
            "grow_selection": sel_mod.grow_selection,
            "shrink_selection": sel_mod.shrink_selection,
            "invert_selection": sel_mod.invert_selection,
            "select_none": sel_mod.select_none,
            "run_macro": self.run_macro,
            "help_cad": self.doc.help_selection,
        }
        return ns

    def _carica_macro(self):
        cartella = os.path.join(os.path.dirname(__file__), "..", "macros")
        try:
            self.engine.load_folder(os.path.abspath(cartella))
        except Exception as exc:
            if hasattr(self, "log_panel"):
                self._log(f"Errore caricamento macro: {exc}")
        if hasattr(self, "macro_panel"):
            self.macro_panel.refresh()

    def _riempi_menu_macro(self):
        self._menu_macro.clear()
        for nome in self.engine.list_names():
            self._menu_macro.addAction(
                self._act(nome, lambda chk=False, s=self.engine.by_name(nome):
                          self.run_macro(s)))

    def act_show_opensees_flow(self):
        """Mostra e porta in primo piano il pannello workflow OpenSees."""
        dock = getattr(self, "flow_dock", None)
        if dock is not None:
            dock.show()
            dock.raise_()
            self._log("Workflow OpenSees: pannello Fasi / Tcl attivo.")

    def _set_mode(self, modo):
        modo = "mesh" if str(modo).lower() == "mesh" else "geometria"
        self.doc.mode = modo
        if hasattr(self, "selection_manager"):
            self.selection_manager.set_context(
                "mesh" if modo == "mesh" else "cad")
        if hasattr(self, "_tb_geometria"):
            self._tb_geometria.setVisible(modo == "geometria")
        if hasattr(self, "_tb_mesh"):
            self._tb_mesh.setVisible(modo == "mesh")
        if hasattr(self, "_workspace_combo"):
            blocker = self._workspace_combo.blockSignals(True)
            self._workspace_combo.setCurrentText(
                "Mesh" if modo == "mesh" else "CAD")
            self._workspace_combo.blockSignals(blocker)
        if hasattr(self, "_status_right"):
            self._update_status()

    # ==================================================================== azioni File
    def act_importa_msh(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importa mesh Gmsh", "", "Mesh Gmsh (*.msh);;Tutti i file (*)")
        if not path:
            return
        try:
            model = self.doc.import_msh(path)
            self._set_mode("mesh")
            self._log(f"Importato {path}: {model.stats()['nodi']} nodi, "
                      f"{model.stats()['elementi']} elementi")
        except Exception as exc:
            self._errore("Import mesh", exc)

    def act_importa_cad(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importa geometria", "",
            "CAD (*.step *.stp *.iges *.igs *.brep);;Tutti i file (*)")
        if not path:
            return
        try:
            enti = self.doc.import_cad(path)
            self._set_mode("geometria")
            self._log(f"Importate {len(enti)} entità da {path}")
        except Exception as exc:
            self._errore("Import CAD", exc)

    def act_export_step(self):
        if not self.doc.selected_entities():
            self._log("Seleziona prima le entità da esportare")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Esporta STEP",
                                              "", "STEP (*.step *.stp)")
        if not path:
            return
        try:
            self.doc.export_step(path)
            self._log(f"Esportato STEP: {path}")
        except Exception as exc:
            self._errore("Export STEP", exc)

    def act_export_msh(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta mesh .msh 2.2 (ASCII)", "", "Mesh Gmsh (*.msh)")
        if not path:
            return
        try:
            model = next(iter(self.doc.mesh_models.values()), None)
            if model is None:
                raise DocumentError("Nessuna mesh importata da esportare")
            gb.export_msh_22(model, path)
            self._log(f"Esportata mesh con gruppi fisici: {path}")
        except Exception as exc:
            self._errore("Export mesh", exc)

    def act_export_geo(self):
        path, _ = QFileDialog.getSaveFileName(self, "Esporta template .geo",
                                              "", "Gmsh geo (*.geo)")
        if not path:
            return
        step_src, _ = QFileDialog.getOpenFileName(
            self, "Geometria sorgente (STEP)", "", "STEP (*.step *.stp)")
        try:
            gb.write_geo_template(step_src or "modello.step", path, clmax=5.0)
            self._log(f"Template .geo scritto: {path}")
        except Exception as exc:
            self._errore("Export .geo", exc)

    def act_mesha(self):
        """Meshing embedded: il modello selezionato (o export corrente) -> .msh."""
        try:
            step_tmp = os.path.join(os.path.expanduser("~"), "gmshcad_tmp.step")
            self.doc.export_step(step_tmp)
            out, _ = QFileDialog.getSaveFileName(
                self, "Salva mesh come", "modello.msh", "Mesh Gmsh (*.msh)")
            if not out:
                return
            clmax, ok = QInputDialog.getDouble(self, "Meshing gmsh",
                                               "Dimensione elemento (clmax):",
                                               5.0, 0.01, 1e6, 2)
            if not ok:
                return
            stats = gb.mesh_step(step_tmp, out, clmax=clmax, clmin=clmax / 5,
                                 msh_version="4.1")
            self._log(f"Mesh generata con gmsh: {out} ({stats})")
            if QMessageBox.question(self, "Riimporta",
                                    "Aprire ora la mesh generata in modalità Mesh?") \
                    == QMessageBox.Yes:
                self.doc.import_msh(out)
                self._set_mode("mesh")
                if QMessageBox.question(
                        self, "Esporta OpenSees",
                        "Mesh importata con successo!\n\n"
                        "Vuoi procedere all'estrazione dei nodi per i gruppi definiti "
                        "e della connectivity list coerente per OpenSees?") \
                        == QMessageBox.Yes:
                    self.act_export_opensees()
        except Exception as exc:
            self._errore("Meshing gmsh", exc)

    def act_mesha_structured(self):
        """Genera una mesh transfinite strutturata quad/hex dalla geometria corrente."""
        from .dialogs import StructuredMeshDialog
        try:
            if not self.doc.selected_entities():
                self._log("Seleziona prima una superficie o un solido da meshare")
                return
            step_tmp = os.path.join(os.path.expanduser("~"), "gmshcad_structured.step")
            self.doc.export_step(step_tmp)
            dlg = StructuredMeshDialog(self)
            if dlg.exec() != QDialog.Accepted:
                return
            vals = dlg.values()
            out = vals["output"] or "modello_structured.msh"
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            stats = gb.mesh_structured(
                step_tmp, out, dimension=vals["dimension"],
                nodes_per_curve=vals["nodes_per_curve"],
                recombine=vals["recombine"], msh_version="4.1")
            self._log(f"Mesh strutturata generata: {out} ({stats})")
            if QMessageBox.question(self, "Riimporta",
                                    "Aprire ora la mesh strutturata in modalità Mesh?") == QMessageBox.Yes:
                self.doc.import_msh(out)
                self._set_mode("mesh")
        except Exception as exc:
            self._errore("Mesh strutturata", exc)

    def act_opensees_command_browser(self):
        """Apre il browser centralizzato del catalogo OpenSees/SRC."""
        try:
            from .dialogs import OpenSeesCommandBrowserDialog
            dlg = OpenSeesCommandBrowserDialog(self)
            dlg.exec()
        except Exception as exc:
            self._errore("OpenSees Command Browser", exc)

    def act_validate_opensees_model(self):
        """Esegue la validazione pre-export e mostra errori/warning separati."""
        model = list(self.doc.mesh_models.values())[-1] if self.doc.mesh_models else None
        report = self.doc.opensees.validate_model(model)
        lines = [
            "VALIDAZIONE MODELLO OPENSEES",
            "",
            f"Stato: {'VALIDO' if report['valid'] else 'NON VALIDO'}",
            "",
            "Statistiche:",
        ]
        for key, value in report["stats"].items():
            lines.append(f"  {key}: {value}")
        if report["errors"]:
            lines.extend(["", "ERRORI BLOCCANTI:"])
            lines.extend(f"  • {msg}" for msg in report["errors"])
        if report["warnings"]:
            lines.extend(["", "WARNING:"])
            lines.extend(f"  • {msg}" for msg in report["warnings"])
        if not report["errors"] and not report["warnings"]:
            lines.extend(["", "Nessuna anomalia rilevata."])
        QMessageBox.information(
            self, "Validazione OpenSees", "\n".join(lines)
        )

    def act_remove_opensees_constraint(self):
        """Rimuove un vincolo statico o EqualDOF scelto dall'utente."""
        choices = []
        for item in self.doc.opensees.constraints:
            choices.append(f"FIX {item.cid}: {item.name}")
        for item in self.doc.opensees.equaldofs:
            choices.append(f"EqualDOF {item.eid}: {item.name}")
        if not choices:
            self._log("Nessun vincolo/OpenSees EqualDOF definito.")
            return
        selected, ok = QInputDialog.getItem(
            self, "Rimuovi vincolo", "Seleziona il vincolo da eliminare:",
            choices, 0, False
        )
        if not ok:
            return
        if selected.startswith("FIX "):
            cid = int(selected.split(":", 1)[0].split()[1])
            removed = self.doc.opensees.remove_constraint(cid)
        else:
            eid = int(selected.split(":", 1)[0].split()[-1])
            removed = self.doc.opensees.remove_equaldof(eid)
        if removed:
            self.doc.opensees.refresh_entity_metadata()
            self.doc.notify("opensees_condition_added", {"type": "constraint_removed"})
            self._log(f"Condizione OpenSees rimossa: {selected}")
        else:
            self._log(f"Impossibile rimuovere: {selected}")

    def act_remove_opensees_interface(self):
        """Rimuove un'interfaccia definita nel documento."""
        interfaces = self.doc.opensees.interfaces
        if not interfaces:
            self._log("Nessuna interfaccia definita.")
            return
        choices = []
        for i, item in enumerate(interfaces):
            choices.append(
                f"{i}: secondaria={item.secondary_entity_id}, primaria={item.primary_entity_id}, "
                f"segmenti={max(0, len(item.secondary_nodes)-1)}"
            )
        selected, ok = QInputDialog.getItem(
            self, "Rimuovi interfaccia", "Seleziona l'interfaccia:",
            choices, 0, False
        )
        if not ok:
            return
        idx = int(selected.split(":", 1)[0])
        if self.doc.opensees.remove_interface(idx):
            self.doc.notify("opensees_condition_added", {"type": "interface_removed"})
            self._log(f"Interfaccia {idx} rimossa.")
        else:
            self._log(f"Impossibile rimuovere interfaccia {idx}.")

    def act_export_opensees(self):
        """Esportazione OpenSees: nodi per gruppi definiti e connectivity list coerente."""
        if not getattr(self.doc, "mesh_models", None):
            QMessageBox.warning(self, "Esporta OpenSees",
                                "Nessun modello mesh presente nel documento.\n"
                                "Importa o genera prima una mesh (File > Mesha o Importa mesh).")
            return
        active_model = list(self.doc.mesh_models.values())[-1]
        if active_model.stale:
            QMessageBox.warning(
                self, "Mesh non aggiornata",
                f"La mesh '{active_model.name}' non corrisponde più alla geometria corrente.\n\n"
                "Rigenera/reimporta la mesh prima dell'export OpenSees.")
            return
        assignments = [item for item in self.doc.opensees.element_assignments
                       if item.model_name == active_model.name]
        if not assignments:
            QMessageBox.warning(
                self, "Assegnazioni FEM mancanti",
                "Prima dell'export Tcl assegna un materiale e un tipo OpenSees "
                "alle entità meshate da OpenSees > Modello FEM.")
            return
        validation = self.doc.opensees.validate_model(active_model)
        if not validation["valid"]:
            details = "\n".join(validation["errors"][:20])
            QMessageBox.warning(self, "Modello OpenSees non valido",
                                "L'export e stato bloccato.\n\n" + details)
            return
        if validation["warnings"]:
            details = "\n".join(validation["warnings"][:12])
            answer = QMessageBox.question(
                self, "Warning OpenSees",
                "Il modello e valido ma presenta warning:\n\n" + details +
                "\n\nProcedere comunque con l'export?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if answer != QMessageBox.Yes:
                return
        from .dialogs import OpenSeesExportDialog
        from ..core import opensees_export as ose

        dlg = OpenSeesExportDialog(self.doc, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        vals = dlg.values()
        out_dir = vals["output_dir"]
        if not out_dir:
            out_dir = os.path.join(os.getcwd(), "output", "opensees")
        os.makedirs(out_dir, exist_ok=True)

        model = dlg.model
        written = []

        try:
            # 1. Connectivity list
            if vals["export_connectivity"]:
                conn_path = os.path.join(out_dir, "connectivity_list.txt")
                ose.export_connectivity_list(conn_path, model)
                written.append(conn_path)

            # 2. Nodi per gruppi
            if vals["export_nodes"]:
                all_groups = ose.extract_defined_groups_nodes(self.doc, model)
                sel_groups = {g: all_groups[g] for g in vals["selected_groups"] if g in all_groups}
                if sel_groups:
                    master_nodes_path = os.path.join(out_dir, "nodi_tutti_i_gruppi.txt")
                    content = ose.format_all_groups_nodes_txt(sel_groups, model.nodes)
                    with open(master_nodes_path, "w", encoding="utf-8") as fh:
                        fh.write(content)
                    written.append(master_nodes_path)

                    if vals["separate_files"]:
                        nodi_dir = os.path.join(out_dir, "nodi_per_gruppo")
                        os.makedirs(nodi_dir, exist_ok=True)
                        for gname, gdata in sel_groups.items():
                            safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in gname)
                            gpath = os.path.join(nodi_dir, f"nodi_{safe}.txt")
                            gcontent = ose.format_group_nodes_txt(gname, gdata["node_ids"], model.nodes)
                            with open(gpath, "w", encoding="utf-8") as fh:
                                fh.write(gcontent)
                            written.append(gpath)

            # 3. TCL script
            if vals["generate_tcl"]:
                bundle = ose.export_opensees_bundle(out_dir, self.doc, model)
                if "tcl_script" in bundle and bundle["tcl_script"] not in written:
                    written.append(bundle["tcl_script"])

            coherence = ose.verify_mesh_coherence(model)
            msg = (
                f"Esportazione OpenSees completata con successo!\n\n"
                f"Cartella: {out_dir}\n"
                f"File generati: {len(written)}\n"
                f"• Coerenza: {coherence['referenced_nodes_count']} nodi utilizzati su {coherence['total_elements']} elementi\n"
                f"• Ordine nodi OpenSees verificato (CCW 2D / Det(J)>0 3D)"
            )
            self._log(f"OpenSees export: salvati {len(written)} file in {out_dir}")
            QMessageBox.information(self, "OpenSees Export", msg)
        except Exception as exc:
            self._errore("Esportazione OpenSees", exc)

    def act_run_opensees(self):
        tcl_path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona modello Tcl", os.path.join(os.getcwd(), "output"),
            "Script Tcl (*.tcl)")
        if not tcl_path:
            return
        default_executable = os.environ.get("OPENSEES_EXECUTABLE", "")
        executable, _ = QFileDialog.getOpenFileName(
            self, "Seleziona eseguibile OpenSees", default_executable,
            "OpenSees (OpenSees.exe);;Eseguibili (*)")
        if not executable:
            return
        if getattr(self, "_opensees_process", None) and \
                self._opensees_process.state() != QProcess.NotRunning:
            QMessageBox.warning(self, "OpenSees", "È già in corso un'analisi OpenSees.")
            return

        process = QProcess(self)
        process.setProgram(executable)
        process.setArguments([tcl_path])
        process.setWorkingDirectory(os.path.dirname(os.path.abspath(tcl_path)))
        process.readyReadStandardOutput.connect(self._read_opensees_stdout)
        process.readyReadStandardError.connect(self._read_opensees_stderr)
        process.errorOccurred.connect(self._opensees_process_error)
        process.finished.connect(self._opensees_process_finished)
        self._opensees_process = process
        self._log(f"Avvio OpenSees: {executable} {tcl_path}")
        process.start()

    def _read_opensees_stdout(self):
        text = bytes(self._opensees_process.readAllStandardOutput()).decode(
            "utf-8", errors="replace").strip()
        if text:
            self._log(text)

    def _read_opensees_stderr(self):
        text = bytes(self._opensees_process.readAllStandardError()).decode(
            "utf-8", errors="replace").strip()
        if text:
            self._log(f"[OpenSees] {text}")

    def _opensees_process_error(self, error):
        self._log(f"Errore avvio OpenSees: {self._opensees_process.errorString()}")

    def _opensees_process_finished(self, exit_code, exit_status):
        self._read_opensees_stdout()
        self._read_opensees_stderr()
        status = "completata" if exit_status == QProcess.NormalExit and exit_code == 0 else "terminata con errori"
        self._log(f"Analisi OpenSees {status} (codice {exit_code}).")

    def act_export_opensees_gruppi(self):
        """Esporta rapidamente i nodi per i gruppi definiti in un file .txt per OpenSees."""
        if not getattr(self.doc, "mesh_models", None):
            QMessageBox.warning(self, "Esporta Nodi OpenSees",
                                "Nessun modello mesh disponibile nel documento.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta Nodi Gruppi OpenSees (.txt)", "nodi_gruppi_opensees.txt",
            "File di testo (*.txt)")
        if not path:
            return
        from ..core import opensees_export as ose
        try:
            files = ose.export_nodes_by_group(path, self.doc)
            self._log(f"Nodi per gruppi OpenSees esportati: {path}")
            QMessageBox.information(self, "Export Nodi",
                                    f"Nodi per tutti i gruppi definiti esportati in:\n{path}")
        except Exception as exc:
            self._errore("Export Nodi OpenSees", exc)

    def act_opensees_fix(self):
        """Apre il dialogo per associare vincoli statici (fix) a gruppi o entità."""
        from .dialogs import OpenSeesFixDialog
        sel_ids = list(self.doc.selection)
        dlg = OpenSeesFixDialog(self.doc, target_entities=sel_ids, parent=self)
        dlg.exec()

    def act_opensees_load(self):
        """Apre il dialogo per associare carichi (load) a gruppi o entità."""
        from .dialogs import OpenSeesLoadDialog
        sel_ids = list(self.doc.selection)
        dlg = OpenSeesLoadDialog(self.doc, target_entities=sel_ids, parent=self)
        dlg.exec()

    def act_opensees_equaldof(self):
        """Apre il dialogo per associare vincoli cinematici equalDOF."""
        from .dialogs import OpenSeesEqualDOFDialog
        dlg = OpenSeesEqualDOFDialog(self.doc, parent=self)
        dlg.exec()

    def act_opensees_solver_stages(self):
        """Apre il dialogo per configurare solutore e fasi di calcolo (Gravity ed Elastoplastica)."""
        from .dialogs import OpenSeesAnalysisDialog
        dlg = OpenSeesAnalysisDialog(self.doc, parent=self)
        dlg.exec()

    def act_opensees_fem(self):
        from .dialogs import OpenSeesFEMDialog
        dlg = OpenSeesFEMDialog(self.doc, parent=self)
        dlg.exec()
        self.doc.opensees.refresh_entity_metadata()
        self._refresh_all()

    def act_toggle_grid(self):
        """Attiva o disattiva la griglia quadrettata 3D nel viewer."""
        if hasattr(self.viewer, "toggle_grid"):
            active = self.viewer.toggle_grid()
            if hasattr(self, "_act_grid"):
                self._act_grid.setChecked(active)
            stato = "attivata" if active else "disattivata"
            self._log(f"Griglia 3D quadrettata {stato}")

    # ==================================================================== azioni Modifica
    def act_undo(self):
        if not self.doc.undo():
            self._log("Niente da annullare")

    def act_redo(self):
        if not self.doc.redo():
            self._log("Niente da ripetere")

    def act_elimina(self):
        n = self.editor.elimina(self.doc.selection)
        self._log(f"Eliminate {n} entità")

    def act_duplica(self):
        nuove = self.editor.copia(self.doc.selection)
        self.doc.set_selection([e.id for e in nuove])
        self._log(f"Duplicate {len(nuove)} entità")

    def act_trasla_dialog(self):
        if not self.doc.selection:
            return self._log("Nessuna selezione")
        dx, ok1 = QInputDialog.getDouble(self, "Traslazione", "dX:", 0.0, -1e6, 1e6, 3)
        dy, ok2 = QInputDialog.getDouble(self, "Traslazione", "dY:", 0.0, -1e6, 1e6, 3)
        dz, ok3 = QInputDialog.getDouble(self, "Traslazione", "dZ:", 0.0, -1e6, 1e6, 3)
        if ok1 and ok2 and ok3:
            self.editor.trasla(self.doc.selection, dx, dy, dz)
            self._log(f"Traslate {len(self.doc.selection)} entità di ({dx}, {dy}, {dz})")

    def act_ruota_dialog(self):
        if not self.doc.selection:
            return self._log("Nessuna selezione")
        testo, ok = QInputDialog.getText(
            self, "Rotazione",
            "Asse: punto px,py,pz; direzione ax,ay,az; angolo° (es. 0,0,0;0,0,1;90):")
        if not ok:
            return
        try:
            p, d, a = [s.strip() for s in testo.split(";")]
            px, py, pz = map(float, p.split(","))
            ax, ay, az = map(float, d.split(","))
            ang = float(a)
            self.editor.ruota(self.doc.selection, px, py, pz, ax, ay, az, ang)
        except Exception as exc:
            self._errore("Rotazione", exc)

    def act_scala_dialog(self):
        if not self.doc.selection:
            return self._log("Nessuna selezione")
        f, ok = QInputDialog.getDouble(self, "Scala", "Fattore:", 1.0, 0.001, 1000, 3)
        if ok:
            self.editor.scala(self.doc.selection, f)

    def act_specchia_dialog(self):
        if not self.doc.selection:
            return self._log("Nessuna selezione")
        testo, ok = QInputDialog.getText(
            self, "Specchia", "Piano: punto px,py,pz; normale nx,ny,nz (es. 0,0,0;0,0,1):")
        if not ok:
            return
        try:
            p, n = [s.strip() for s in testo.split(";")]
            px, py, pz = map(float, p.split(","))
            nx, ny, nz = map(float, n.split(","))
            self.editor.specchia(self.doc.selection, px, py, pz, nx, ny, nz)
        except Exception as exc:
            self._errore("Specchia", exc)

    def act_fusa(self):
        try:
            res = self.editor.fusa(list(self.doc.selection))
            self.doc.set_selection([res.id])
        except Exception as exc:
            self._errore("Fusione", exc)

    def act_taglio(self):
        ids = sorted(self.doc.selection)
        if len(ids) != 2:
            return self._log("Seleziona esattamente 2 entità (A tagliato da B)")
        try:
            res = self.editor.taglia(ids[0], ids[1])
            self.doc.set_selection([res.id])
        except Exception as exc:
            self._errore("Taglio", exc)

    def act_inter(self):
        ids = sorted(self.doc.selection)
        if len(ids) != 2:
            return self._log("Seleziona esattamente 2 entità")
        try:
            res = self.editor.intersezione(ids[0], ids[1])
            self.doc.set_selection([res.id])
        except Exception as exc:
            self._errore("Intersezione", exc)

    def act_raccorda(self):
        try:
            r, ok = QInputDialog.getDouble(self, "Raccordo", "Raggio:", 1.0, 0.001, 1e4, 3)
            if not ok:
                return
            solidi = [e for e in self.doc.selected_entities() if e.etype == "solid"]
            for s in solidi:
                self.editor.raccorda(s.id, raggio=r)
            self._log(f"Raccordati {len(solidi)} solidi (r={r})")
        except Exception as exc:
            self._errore("Raccordo", exc)

    def act_smussa(self):
        try:
            d, ok = QInputDialog.getDouble(self, "Smusso", "Distanza:", 1.0, 0.001, 1e4, 3)
            if not ok:
                return
            for s in [e for e in self.doc.selected_entities() if e.etype == "solid"]:
                self.editor.smussa(s.id, distanza=d)
        except Exception as exc:
            self._errore("Smusso", exc)

    def act_svuota(self):
        try:
            t, ok = QInputDialog.getDouble(self, "Svuota", "Spessore parete:", 1.0,
                                           0.01, 1e3, 3)
            if not ok:
                return
            for s in [e for e in self.doc.selected_entities() if e.etype == "solid"]:
                self.editor.svuota(s.id, t)
        except Exception as exc:
            self._errore("Svuota", exc)

    def act_offset(self):
        try:
            d, ok = QInputDialog.getDouble(self, "Offset", "Distanza (+fuori / -dentro):",
                                           1.0, -1e4, 1e4, 3)
            if not ok or not self.doc.selection:
                return
            for e in list(self.doc.selected_entities()):
                self.editor.offset(e.id, d)
        except Exception as exc:
            self._errore("Offset", exc)

    def act_esplodi_facce(self):
        self.editor.esplodi(self.doc.selection, "face")
        self._log("Superfici estratte come entità")

    def act_esplodi_curve(self):
        self.editor.esplodi(self.doc.selection, "curve")
        self._log("Curve estratte come entità")

    def act_esplodi_punti(self):
        self.editor.esplodi(self.doc.selection, "point")
        self._log("Punti estratti come entità")

    # ==================================================================== azioni Selezione
    def act_sel_nome(self):
        testo, ok = QInputDialog.getText(self, "Selezione per nome",
                                         "Pattern (es. *foro* o regex):")
        if ok and testo:
            sel.select_by_name(self.doc, testo, regex="*" not in testo)

    def act_sel_gruppo(self):
        nomi = self.doc.groups.list_names()
        if not nomi:
            return self._log("Nessun gruppo esistente")
        nome, ok = QInputDialog.getItem(self, "Selezione per gruppo", "Gruppo:",
                                        nomi, 0, False)
        if ok:
            sel.select_by_group(self.doc, nome)

    def act_sel_marker(self):
        m, ok = QInputDialog.getInt(self, "Selezione per tag fisico",
                                    "Tag fisico gmsh:", 1, 0, 1e6)
        if ok:
            sel.select_by_marker(self.doc, m)

    def act_sel_colore(self):
        c = QColorDialog.getColor(parent=self, title="Colore da cercare")
        if not c.isValid():
            return
        sel.select_by_color(self.doc, (c.redF(), c.greenF(), c.blueF()))

    def act_sel_box(self):
        testo, ok = QInputDialog.getText(
            self, "Selezione in parallelepipedo",
            "xmin, ymin, zmin, xmax, ymax, zmax:")
        if not ok:
            return
        try:
            v = [float(x) for x in testo.split(",")]
            sel.select_box(self.doc, *v)
            self._log(f"Selezione box: {len(self.doc.selection)} entità")
        except Exception as exc:
            self._errore("Selezione box", exc)

    def act_sel_sfera(self):
        testo, ok = QInputDialog.getText(self, "Selezione in sfera",
                                         "cx, cy, cz, raggio:")
        if not ok:
            return
        try:
            v = [float(x) for x in testo.split(",")]
            sel.select_sphere(self.doc, *v)
            self._log(f"Selezione sferica: {len(self.doc.selection)} entità")
        except Exception as exc:
            self._errore("Selezione sferica", exc)

    def act_sel_piano(self):
        testo, ok = QInputDialog.getText(
            self, "Semi-spazio", "punto px,py,pz; normale nx,ny,nz (es. 0,0,5;0,0,1):")
        if not ok:
            return
        try:
            p, n = [s.strip() for s in testo.split(";")]
            sel.select_plane(self.doc, *map(float, p.split(",")),
                             *map(float, n.split(",")))
        except Exception as exc:
            self._errore("Semi-spazio", exc)

    def act_sel_vicine(self):
        try:
            p, ok = QInputDialog.getText(self, "N più vicine", "x, y, z:")
            if not ok:
                return
            n, ok2 = QInputDialog.getInt(self, "N più vicine", "Quante:", 1, 1, 100)
            if ok2:
                sel.select_nearest(self.doc, *map(float, p.split(",")), n=n)
        except Exception as exc:
            self._errore("Vicine", exc)

    def act_sel_dimensione(self):
        try:
            t, ok = QInputDialog.getItem(self, "Per dimensione", "Tipo:",
                                         ["superficie", "curva", "solido"], 0, False)
            if not ok:
                return
            v, ok2 = QInputDialog.getText(self, "Per dimensione",
                                          "vmin, vmax (area/lunghezza/volume):")
            if ok2:
                vmin, vmax = map(float, v.split(","))
                sel.select_by_size(self.doc, t, vmin, vmax)
        except Exception as exc:
            self._errore("Per dimensione", exc)

    def act_sel_normale(self):
        try:
            testo, ok = QInputDialog.getText(
                self, "Per normale", "direzione dx,dy,dz; tolleranza° (es. 0,0,1;15):")
            if not ok:
                return
            d, t = [s.strip() for s in testo.split(";")]
            sel.select_by_normal(self.doc, *map(float, d.split(",")), tol_deg=float(t))
            self._log(f"Selezione per normale: {len(self.doc.selection)} superfici")
        except Exception as exc:
            self._errore("Per normale", exc)

    def act_sel_piccole(self):
        n, ok = QInputDialog.getInt(self, "Le più piccole", "Quante:", 1, 1, 100)
        if ok:
            sel.select_smallest(self.doc, n)

    def act_sel_grandi(self):
        n, ok = QInputDialog.getInt(self, "Le più grandi", "Quante:", 1, 1, 100)
        if ok:
            sel.select_largest(self.doc, n)

    # ==================================================================== azioni Gruppi
    def act_gruppo_da_selezione(self):
        nome, ok = QInputDialog.getText(self, "Nuovo gruppo", "Nome del gruppo:")
        if ok and nome:
            try:
                g = self.doc.groups.group_from_selection(self.doc, nome)
                self._log(f"Gruppo '{nome}': {g.count_geo()} entità")
            except Exception as exc:
                self._errore("Gruppo", exc)

    def act_aggiungi_gruppo(self):
        nomi = self.doc.groups.list_names()
        if not nomi or not self.doc.selection:
            return self._log("Serve un gruppo esistente e una selezione")
        nome, ok = QInputDialog.getItem(self, "Aggiungi a gruppo", "Gruppo:",
                                        nomi, 0, False)
        if ok:
            self.doc.groups.add_geo(nome, self.doc.selection)

    def act_rimuovi_gruppo(self):
        nomi = self.doc.groups.list_names()
        if not nomi:
            return
        nome, ok = QInputDialog.getItem(self, "Rimuovi da gruppo", "Gruppo:",
                                        nomi, 0, False)
        if ok:
            self.doc.groups.remove_geo(nome, self.doc.selection)

    def act_gruppo_piane(self):
        ids = sel.select_planar(self.doc, mode="replace")
        self.doc.groups.group_from_selection(self.doc, "superfici_piane")
        self._log(f"Gruppo 'superfici_piane' creato ({len(ids)} entità)")

    def act_gruppo_curve(self):
        ids = sel.select_curved(self.doc, mode="replace")
        self.doc.groups.group_from_selection(self.doc, "superfici_curve")
        self._log(f"Gruppo 'superfici_curve' creato ({len(ids)} entità)")

    def act_gruppo_marker(self):
        m, ok = QInputDialog.getInt(self, "Gruppo per tag fisico", "Tag:", 1, 0, 1e6)
        if ok:
            sel.select_by_marker(self.doc, m)
            self.doc.groups.group_from_selection(self.doc, f"tag_{m}")

    def act_gruppo_mesh(self):
        model = next(iter(self.doc.mesh_models.values()), None)
        if model is None:
            return self._log("Nessuna mesh importata")
        nome, ok = QInputDialog.getText(self, "Gruppo mesh", "Nome gruppo:")
        if ok and nome:
            self.doc.groups.add_mesh_elements(nome, model.name, model.sel_elements)
            self.doc.groups.add_mesh_nodes(nome, model.name, model.sel_nodes)
            self._log(f"Gruppo mesh '{nome}' creato "
                      f"({len(model.sel_elements)} elementi, {len(model.sel_nodes)} nodi)")

    def act_rinomina_gruppo(self):
        nomi = self.doc.groups.list_names()
        if not nomi:
            return
        vecchio, ok = QInputDialog.getItem(self, "Rinomina gruppo", "Gruppo:",
                                           nomi, 0, False)
        if not ok:
            return
        nuovo, ok2 = QInputDialog.getText(self, "Rinomina gruppo", "Nuovo nome:",
                                          text=vecchio)
        if ok2:
            self.doc.groups.rename(vecchio, nuovo)

    def act_elimina_gruppo(self):
        nomi = self.doc.groups.list_names()
        if not nomi:
            return
        nome, ok = QInputDialog.getItem(self, "Elimina gruppo", "Gruppo:",
                                        nomi, 0, False)
        if ok:
            self.doc.groups.delete(nome)

    def act_export_gruppi(self):
        path, _ = QFileDialog.getSaveFileName(self, "Esporta gruppi",
                                              "gruppi.txt", "Testo (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.doc.groups.export_text(self.doc))
            self._log(f"Gruppi esportati: {path}")

    # ==================================================================== azioni Mesh
    def _mesh_action(self, tipo):
        model = next(iter(self.doc.mesh_models.values()), None)
        if model is None:
            return self._log("Importa prima una mesh .msh")
        try:
            if tipo == "all":
                n = model.select_all_elements()
                self._log(f"{n} elementi selezionati")
            elif tipo == "box":
                testo, ok = QInputDialog.getText(
                    self, "Selezione mesh in parallelepipedo",
                    "xmin, ymin, zmin, xmax, ymax, zmax:")
                if ok:
                    bb = tuple(float(x) for x in testo.split(","))
                    model.select_elements_in_box(bb)
                    self._log(f"{len(model.sel_elements)} elementi nel box")
            elif tipo == "sfera":
                testo, ok = QInputDialog.getText(self, "Selezione mesh in sfera",
                                                 "cx, cy, cz, raggio:")
                if ok:
                    v = [float(x) for x in testo.split(",")]
                    model.select_elements_in_sphere(*v)
                    self._log(f"{len(model.sel_elements)} elementi nella sfera")
            elif tipo == "fisico":
                nomi = [v for _, v in model.physicals.items()] or \
                    [b.nome for b in model.blocks.values()]
                nome, ok = QInputDialog.getItem(self, "Gruppo fisico", "Nome:",
                                                nomi, 0, False)
                if ok:
                    model.select_blocks_by_physical(nome)
                    self._log(f"{len(model.sel_elements)} elementi del gruppo fisico")
            elif tipo == "grow":
                model.grow_elements("nodes")
                self._log(f"Espansione: {len(model.sel_elements)} elementi")
            elif tipo == "shrink":
                model.shrink_elements()
                self._log(f"Riduzione: {len(model.sel_elements)} elementi")
            elif tipo == "nodi":
                model.select_nodes_of_selected_elements()
                self._log(f"{len(model.sel_nodes)} nodi selezionati")
            self._update_status()
        except Exception as exc:
            self._errore("Operazione mesh", exc)

    _last_box_values = (0, 0, 0, 10, 10, 10)

    # ==================================================================== azioni Macro
    def run_macro(self, spec):
        if spec is None:
            return
        if not self.doc.selection and not any(
                m.sel_nodes or m.sel_elements for m in self.doc.mesh_models.values()):
            self._log("Nessuna selezione: la macro verrà eseguita senza bersagli")
        dlg = ParamDialog(spec, self)
        if dlg.exec() != ParamDialog.Accepted:
            return
        try:
            self.engine.run(spec, dlg.values())
        except Exception as exc:
            self._errore(f"Macro '{spec.name}'", exc)
        self._refresh_all()

    def act_nuova_macro(self):
        nome, ok = QInputDialog.getText(self, "Nuova macro", "Nome:")
        if not ok:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva macro", os.path.join(os.path.dirname(__file__), "..",
                                              "macros", f"{nome or 'macro'}.py"),
            "Python (*.py)")
        if path:
            write_macro_template(path, nome or "La mia macro")
            self._log(f"Template macro scritto: {path} — premi F5 per ricaricare")

    def act_apri_cartella_macro(self):
        cartella = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "macros"))
        os.startfile(cartella) if hasattr(os, "startfile") else \
            self._log(f"Cartella macro: {cartella}")

    # ==================================================================== azioni Vista/Aiuto
    def act_toggle_wireframe(self):
        self._wire = not getattr(self, "_wire", False)
        self.viewer.set_wireframe(self._wire)

    def act_guida(self):
        QMessageBox.information(self, "Guida rapida", GUIDA_TESTO)

    def act_guida_selezione(self):
        QMessageBox.information(self, "Comandi di selezione",
                                self.doc.help_selection())

    def act_info(self):
        QMessageBox.about(self, "Informazioni",
                          f"<b>{__app_name__}</b> {__version__}<br>"
                          "Ambiente CAD basato su OpenCASCADE (pythonocc-core) "
                          "con import Gmsh .msh, gruppi, macro personalizzate "
                          "e meshing embedded.<br><br>"
                          "Modalità Mesh: importa .msh, seleziona punti/curve/"
                          "superfici/volumi, crea gruppi.<br>"
                          "Modalità Geometria: crea e modifica punti, curve, "
                          "superfici e solidi, poi esporta per gmsh o mesh "
                          "direttamente.")

    # ==================================================================== creazione
    def _crea_dialog(self, tipo):
        titolo = tipo.capitalize()
        testo, ok = QInputDialog.getText(
            self, f"Crea {titolo}", _HINT_CREAZIONE.get(tipo, ""))
        if not ok or not testo:
            return
        try:
            v = [float(x.strip()) for x in testo.split(",")]
            if tipo == "punto":
                self.builder.punto(v[0], v[1], v[2])
            elif tipo == "linea":
                self.builder.linea(v[0:3], v[3:6])
            elif tipo == "spline":
                self.builder.spline([v[i:i + 3] for i in range(0, len(v) - 2, 3)])
            elif tipo == "cerchio":
                self.builder.cerchio(v[0], v[1], v[2], v[3])
            elif tipo == "arco":
                self.builder.arco(v[0:3], v[3:6], v[6:9])
            elif tipo == "superficie":
                self.builder.superficie_da_punti([v[i:i + 3]
                                                  for i in range(0, len(v) - 2, 3)])
            elif tipo == "rettangolo":
                self.builder.rettangolo(v[0], v[1], v[2], v[3],
                                        z=v[4] if len(v) > 4 else 0.0)
            elif tipo == "box":
                self.builder.box(v[0], v[1], v[2],
                                 base=tuple(v[3:6]) if len(v) > 5 else (0, 0, 0))
            elif tipo == "cilindro":
                self.builder.cilindro(v[0], v[1],
                                      base=tuple(v[2:5]) if len(v) > 4 else (0, 0, 0))
            elif tipo == "sfera":
                self.builder.sfera(v[0],
                                   center=tuple(v[1:4]) if len(v) > 3 else (0, 0, 0))
            elif tipo == "cono":
                self.builder.cono(v[0], v[1], v[2])
            elif tipo == "toro":
                self.builder.toro(v[0], v[1])
            self.viewer.fit_all()
        except Exception as exc:
            self._errore(f"Crea {titolo}", exc)

    def act_estrudi_dialog(self):
        if not self.doc.selection:
            return self._log("Seleziona il profilo da estrarre")
        testo, ok = QInputDialog.getText(self, "Estrudi", "Vettore dx, dy, dz:")
        if not ok:
            return
        try:
            dx, dy, dz = map(float, testo.split(","))
            res = self.builder.estrudi(list(self.doc.selection)[0], dx, dy, dz)
            self.doc.set_selection([res.id])
            self.viewer.fit_all()
        except Exception as exc:
            self._errore("Estrudi", exc)

    def act_rivolgi_dialog(self):
        if not self.doc.selection:
            return self._log("Seleziona il profilo da rivolgere")
        testo, ok = QInputDialog.getText(
            self, "Rivolgi", "asse punto ax,ay,az; direzione dx,dy,dz; angolo°:")
        if not ok:
            return
        try:
            p, d, a = [s.strip() for s in testo.split(";")]
            res = self.builder.rivolgi(list(self.doc.selection)[0],
                                       *map(float, p.split(",")),
                                       *map(float, d.split(",")), float(a))
            self.doc.set_selection([res.id])
            self.viewer.fit_all()
        except Exception as exc:
            self._errore("Rivolgi", exc)

    # ==================================================================== misc
    def _errore(self, titolo, exc):
        self._log(f"ERRORE {titolo}: {exc}")
        self.log_panel.log(traceback.format_exc(limit=3))
        QMessageBox.critical(self, titolo, str(exc))


_HINT_CREAZIONE = {
    "punto": "x, y, z",
    "linea": "x1, y1, z1, x2, y2, z2",
    "spline": "x1,y1,z1, x2,y2,z2, ... (min 2 punti)",
    "cerchio": "cx, cy, cz, raggio",
    "arco": "estremo1 x,y,z; punto medio x,y,z; estremo2 x,y,z",
    "superficie": "x1,y1,z1, x2,y2,z2, ... (poligono, min 3 punti)",
    "rettangolo": "cx, cy, larghezza, altezza [, z]",
    "box": "dx, dy, dz [, base_x, base_y, base_z]",
    "cilindro": "raggio, altezza [, base_x, base_y, base_z]",
    "sfera": "raggio [, cx, cy, cz]",
    "cono": "raggio1, raggio2, altezza",
    "toro": "raggio_anello, raggio_tubo",
}

GUIDA_TESTO = """GUIDA RAPIDA — GmshCAD Studio

MODALITÀ MESH (lettura modelli .msh):
  • File > Importa mesh .msh: legge formati ASCII 2.2 e 4.1 di Gmsh.
  • Ogni blocco entità diventa una "entità" del documento (punto/curva/
    superficie/volume) con il nome del gruppo fisico se presente.
  • Selezione: menu Selezione (per tipo, gruppo fisico, regione box/sfera,
    semi-spazio, normale, dimensione, più vicine, espandi/riduci, connessa,
    sotto-entità, bordo) o toolbar Mesh per gli elementi della mesh.
  • Gruppi: crea gruppi dalla selezione, gruppi automatici (superfici piane/
    curve, per tag fisico), gruppi di elementi/nodi mesh; export testuale.

MODALITÀ GEOMETRIA (creazione modelli da meshare):
  • Toolbar Creazione: punto, linea, spline, cerchio, arco, superficie
    da punti, rettangolo, box, cilindro, sfera, cono, toro, estrudi, rivolgi.
  • Modifica: trasla/ruota/scala/specchia, booleane (fusione/taglio/
    intersezione), raccordo/smussato/svuotato/offset, esplodi, editing
    parametrico dei punti di controllo.
  • File > Mesha il modello (gmsh): genera la mesh direttamente dall'app
    via API gmsh e riimporta il risultato in modalità Mesh.
  • Export: STEP per gmsh, template .geo con parametri mesh.

MACRO E COMANDI PERSONALIZZATI:
  • Cartella gcs/macros: file .py con decorator @macro; auto-caricati (F5).
  • Ogni macro dichiara i bersagli (punto/curva/superficie/solido/nodo_mesh/
    elemento_mesh/entita) e i propri parametri (dialog auto-generato).
  • La funzione viene applicata a OGNI sotto-entità della selezione corrente.
  • "Nuova macro da template…" genera un file pronto da personalizzare.

CONSOLE: il documento è 'doc'; esempio:
  doc.query().type("superficie").planar().in_box(0,0,0,50,50,50).select()
"""
