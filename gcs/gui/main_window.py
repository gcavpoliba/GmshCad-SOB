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

from PySide6.QtCore import Qt, QProcess
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QDockWidget, QTabWidget, QToolBar,
                               QMessageBox, QFileDialog, QInputDialog, QLabel,
                               QStatusBar, QApplication, QColorDialog)

from gcs import __app_name__, __version__
from gcs.core.document import CADDocument, DocumentError
from gcs.core.builder import GeometryBuilder
from gcs.core.editors import GeometryEditor
from gcs.core import selectors as sel
from gcs.core import gmsh_bridge as gb
from gcs.core.macro_engine import MacroEngine, write_macro_template
from gcs.gui.viewer import Viewer3D, NullViewer
from gcs.gui.panels import (EntityTree, PropertiesPanel, ConsolePanel,
                            LogPanel, MacroPanel)
from gcs.gui.dialogs import ParamDialog


class MainWindow(QMainWindow):
    """Finestra principale dell'ambiente CAD."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1500, 950)
        self.doc = CADDocument()
        self.builder = GeometryBuilder(self.doc)
        self.editor = GeometryEditor(self.doc)
        self.engine = MacroEngine(self.doc, log=self._log)

        # ---------- widget centrale (viewer 3D con fallback senza display)
        try:
            self.viewer = Viewer3D(self.doc)
            self.setCentralWidget(self.viewer)
        except Exception as exc:
            self.viewer = NullViewer()
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
            except Exception:
                pass  # NullViewer non ha questi signal

        # ---------- dock
        self.tree_panel = EntityTree(self.doc, self.viewer)
        self.props_panel = PropertiesPanel(self.doc)
        self.log_panel = LogPanel()
        self.macro_panel = MacroPanel(self.engine)
        self.console = ConsolePanel(self._console_namespace())
        tabs = QTabWidget()
        tabs.addTab(self.console, "Console")
        tabs.addTab(self.log_panel, "Log")
        tabs.addTab(self.macro_panel, "Macro")

        d1 = QDockWidget("Albero", self)
        d1.setWidget(self.tree_panel)
        d1.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, d1)
        d2 = QDockWidget("Proprietà", self)
        d2.setWidget(self.props_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, d2)
        d3 = QDockWidget("Console e macro", self)
        d3.setWidget(tabs)
        self.addDockWidget(Qt.BottomDockWidgetArea, d3)
        d1.resize(320, 500)

        # ---------- menu e toolbar
        self._build_menus()
        self._build_toolbars()
        self._set_mode("geometria")
        self._status_left = QLabel("Pronto")
        self._status_right = QLabel("Modalità: Geometria | 0 entità")
        sb = QStatusBar()
        sb.addWidget(self._status_left)
        sb.addPermanentWidget(self._status_right)
        self.setStatusBar(sb)
        self._carica_macro()
        self._refresh_all()

    # ================================================================ costruzione UI
    def _build_menus(self):
        mb = self.menuBar()

        # ----- File
        m = mb.addMenu("&File")
        m.addAction(self._act("Importa &mesh .msh…", self.act_importa_msh, "Ctrl+I"))
        m.addAction(self._act("Importa STEP/IGES/BREP…", self.act_importa_cad))
        m.addSeparator()
        m.addAction(self._act("Esporta &STEP…", self.act_export_step, "Ctrl+E"))
        m.addAction(self._act("Esporta mesh .msh (gruppi fisici)…", self.act_export_msh))
        m.addAction(self._act("Esporta template .geo…", self.act_export_geo))
        m.addSeparator()
        m.addAction(self._act("Esporta per &OpenSees (nodi e connettività)…",
                              self.act_export_opensees, "Ctrl+Shift+O"))
        m.addSeparator()
        m.addAction(self._act("&Mesha il modello selezionato (gmsh)…",
                              self.act_mesha, "Ctrl+M"))
        m.addSeparator()
        m.addAction(self._act("Chiudi", self.close, "Ctrl+Q"))

        # ----- Modifica
        m = mb.addMenu("&Modifica")
        m.addAction(self._act("&Annulla", self.act_undo, "Ctrl+Z"))
        m.addAction(self._act("&Ripeti", self.act_redo, "Ctrl+Y"))
        m.addSeparator()
        m.addAction(self._act("&Elimina selezione", self.act_elimina, "Del"))
        m.addAction(self._act("&Duplica selezione", self.act_duplica, "Ctrl+D"))
        m.addSeparator()
        trasla = m.addMenu("Traslazione")
        for ax, label in (("dx", "X+"), ("dx", "X-"), ("dy", "Y+"), ("dy", "Y-"),
                          ("dz", "Z+"), ("dz", "Z-")):
            segno = 1.0 if label.endswith("+") else -1.0
            trasla.addAction(self._act(
                f"{label} di 5", lambda chk=False, a=ax, s=segno:
                self.editor.trasla(self.doc.selection, *(s * 5 if a == k else 0
                                                        for k in ("dx", "dy", "dz")))))
        m.addAction(self._act("Traslazione personalizzata…", self.act_trasla_dialog))
        m.addAction(self._act("Rotazione…", self.act_ruota_dialog))
        m.addAction(self._act("Scala…", self.act_scala_dialog))
        m.addAction(self._act("Specchia…", self.act_specchia_dialog))
        m.addSeparator()
        m.addAction(self._act("Fusione (union)…", self.act_fusa))
        m.addAction(self._act("Taglio (A - B)…", self.act_taglio))
        m.addAction(self._act("Intersezione…", self.act_inter))
        m.addAction(self._act("Raccorda spigoli…", self.act_raccorda))
        m.addAction(self._act("Smussa spigoli…", self.act_smussa))
        m.addAction(self._act("Svuota (cavity)…", self.act_svuota))
        m.addAction(self._act("Offset…", self.act_offset))
        m.addSeparator()
        m.addAction(self._act("Esplodi in superfici", self.act_esplodi_facce))
        m.addAction(self._act("Esplodi in curve", self.act_esplodi_curve))
        m.addAction(self._act("Esplodi in punti", self.act_esplodi_punti))

        # ----- Selezione
        m = mb.addMenu("&Selezione")
        m.addAction(self._act("Tutto", lambda: sel.select_all(self.doc), "Ctrl+A"))
        m.addAction(self._act("Nessuno", lambda: sel.select_none(self.doc),
                              "Ctrl+Shift+A"))
        m.addAction(self._act("Inverti", lambda: sel.invert_selection(self.doc)))
        m.addSeparator()
        for t, lab in (("point", "Punti"), ("curve", "Curve"),
                       ("face", "Superfici"), ("solid", "Solidi")):
            m.addAction(self._act(lab, lambda chk=False, tt=t:
                                  sel.select_by_type(self.doc, tt)))
        m.addAction(self._act("Per nome…", self.act_sel_nome))
        m.addAction(self._act("Per gruppo…", self.act_sel_gruppo))
        m.addAction(self._act("Per tag fisico…", self.act_sel_marker))
        m.addAction(self._act("Per colore…", self.act_sel_colore))
        m.addSeparator()
        m.addAction(self._act("In parallelepipedo…", self.act_sel_box))
        m.addAction(self._act("In sfera…", self.act_sel_sfera))
        m.addAction(self._act("Semi-spazio rispetto a piano…", self.act_sel_piano))
        m.addAction(self._act("Le N più vicine a un punto…", self.act_sel_vicine))
        m.addSeparator()
        m.addAction(self._act("Per dimensione (area/lunghezza/volume)…",
                              self.act_sel_dimensione))
        m.addAction(self._act("Superfici piane", lambda: sel.select_planar(self.doc)))
        m.addAction(self._act("Superfici curve", lambda: sel.select_curved(self.doc)))
        m.addAction(self._act("Per direzione della normale…", self.act_sel_normale))
        m.addAction(self._act("Le N più piccole…", self.act_sel_piccole))
        m.addAction(self._act("Le N più grandi…", self.act_sel_grandi))
        m.addSeparator()
        m.addAction(self._act("Espandi selezione", lambda: sel.grow_selection(self.doc),
                              "Ctrl+G"))
        m.addAction(self._act("Riduci selezione", lambda: sel.shrink_selection(self.doc),
                              "Ctrl+Shift+G"))
        m.addAction(self._act("Componente connessa", lambda: sel.select_connected(self.doc)))
        m.addSeparator()
        m.addAction(self._act("Punti della selezione", lambda: sel.select_vertices_of(self.doc)))
        m.addAction(self._act("Curve della selezione", lambda: sel.select_edges_of(self.doc)))
        m.addAction(self._act("Superfici della selezione", lambda: sel.select_faces_of(self.doc)))
        m.addAction(self._act("Bordo delle superfici", lambda: sel.select_boundary(self.doc)))

        # ----- Gruppi
        m = mb.addMenu("&Gruppi")
        m.addAction(self._act("Crea gruppo dalla selezione…",
                              self.act_gruppo_da_selezione, "Ctrl+Shift+N"))
        m.addAction(self._act("Aggiungi selezione a gruppo…", self.act_aggiungi_gruppo))
        m.addAction(self._act("Rimuovi selezione da gruppo…", self.act_rimuovi_gruppo))
        m.addSeparator()
        m.addAction(self._act("Gruppo automatico: superfici piane",
                              self.act_gruppo_piane))
        m.addAction(self._act("Gruppo automatico: superfici curve",
                              self.act_gruppo_curve))
        m.addAction(self._act("Gruppo automatico: per tag fisico…",
                              self.act_gruppo_marker))
        m.addSeparator()
        m.addAction(self._act("Rinomina gruppo…", self.act_rinomina_gruppo))
        m.addAction(self._act("Elimina gruppo…", self.act_elimina_gruppo))
        m.addAction(self._act("Esporta elenco gruppi…", self.act_export_gruppi))
        m.addAction(self._act("Esporta nodi gruppi (OpenSees .txt)…",
                              self.act_export_opensees_gruppi))

        # ----- OpenSees
        m_os = mb.addMenu("&OpenSees")
        m_os.addAction(self._act("Esporta per &OpenSees (bundle completo)…",
                                self.act_export_opensees, "Ctrl+Shift+O"))
        m_os.addAction(self._act("Esporta script OpenSees (fasi e parametri)…",
                    self.act_export_phase_model))
        m_os.addAction(self._act("Configura &Solutore e Fasi (Gravity / Elastoplastica)…",
                                self.act_opensees_solver_stages))
        m_os.addAction(self._act("Modello FEM: materiali, elementi, nodi e recorder…",
                    self.act_opensees_fem))
        m_os.addAction(self._act("Esegui script Tcl con OpenSees…",
                    self.act_run_opensees))
        m_os.addSeparator()
        m_os.addAction(self._act("Associa &Vincolo (fix) a gruppi o selezione…",
                                self.act_opensees_fix))
        m_os.addAction(self._act("Associa &Carico (load) a gruppi o selezione…",
                                self.act_opensees_load))
        m_os.addAction(self._act("Associa &EqualDOF (multi-point constraint)…",
                                self.act_opensees_equaldof))
        m_os.addSeparator()
        # --- Nuovi comandi estesi (catalogo allargato) ---
        m_os_cat = m_os.addMenu("Catalogo esteso")
        m_os_cat.addAction(self._act("Definisci sezione (section)…",
                                       self.act_define_section))
        m_os_cat.addAction(self._act("Definisci geomTransf…",
                                       self.act_define_geom_transf))
        m_os_cat.addAction(self._act("Definisci beamIntegration…",
                                       self.act_define_beam_integration))
        m_os_cat.addAction(self._act("Definisci carico su elemento (eleLoad)…",
                                       self.act_define_ele_load))
        m_os_cat.addAction(self._act("Definisci region (con rayleigh opzionale)…",
                                       self.act_define_region))
        m_os.addSeparator()
        # --- Parametri (updateParameter, setParameter, updateMaterials) ---
        m_os_param = m_os.addMenu("Parametri (update)")
        m_os_param.addAction(self._act("Definisci parameter (element/node/pattern)…",
                                         self.act_define_parameter))
        m_os_param.addAction(self._act("setParameter (batch elementi)…",
                                         self.act_set_parameter))
        m_os_param.addAction(self._act("updateMaterials (state change)…",
                                         self.act_update_materials))
        m_os_param.addAction(self._act("Update parameters globali…",
                                         self.act_update_parameters))
        m_os_param.addAction(self._act("Smorzamento Rayleigh…",
                                         self.act_set_rayleigh))
        m_os_param.addAction(self._act("Massa nodale…",
                                         self.act_add_nodal_mass))
        m_os.addSeparator()
        # --- Fasi (PhaseManager unificato) ---
        m_os_phase = m_os.addMenu("Fasi (update model)")
        m_os_phase.addAction(self._act("Nuova fase…", self.act_nuova_fase))
        m_os_phase.addAction(self._act("Cambia fase corrente…", self.act_cambia_fase))
        m_os_phase.addAction(self._act("Mostra fasi", self.act_mostra_fasi))
        m_os_phase.addAction(self._act("Assegna proprietà elemento…",
                                         self.act_assegna_proprieta))
        m_os_phase.addAction(self._act("Assegna vincolo fase…",
                                         self.act_assegna_vincolo))
        m_os_phase.addAction(self._act("Pacchetto solutore fase…",
                                         self.act_solver_pack))
        m_os_phase.addAction(self._act("Bridge fasi → OpenSeesManager",
                                         self.act_bridge_phases))
        m_os.addSeparator()
        m_os.addAction(self._act("Esporta nodi gruppi (OpenSees .txt)…",
                                self.act_export_opensees_gruppi))

        # ----- Modalità
        m = mb.addMenu("&Modalità")
        self._mgeo = self._act("Modalità &Geometria", lambda: self._set_mode("geometria"))
        self._mgeo.setCheckable(True)
        self._mmesh = self._act("Modalità &Mesh", lambda: self._set_mode("mesh"))
        self._mmesh.setCheckable(True)
        m.addAction(self._mgeo)
        m.addAction(self._mmesh)

        # ----- Macro
        m = mb.addMenu("M&acro")
        m.addAction(self._act("Ricarica macro da cartella", self._carica_macro, "F5"))
        m.addAction(self._act("Nuova macro da template…", self.act_nuova_macro))
        m.addAction(self._act("Apri cartella macro…", self.act_apri_cartella_macro))
        self._menu_macro = m.addMenu("Esegui macro…")
        self._menu_macro.aboutToShow.connect(self._riempi_menu_macro)

        # ----- Vista
        m = mb.addMenu("&Vista")
        for v in ("iso", "front", "top", "right", "left", "bottom", "back"):
            m.addAction(self._act(f"Vista {v}", lambda chk=False, vv=v:
                                  self.viewer.vista(vv)))
        m.addAction(self._act("Adatta tutto", self.viewer.fit_all, "Home"))
        m.addAction(self._act("Wireframe / Ombreggiato",
                              self.act_toggle_wireframe, "W"))
        m.addAction(self._act("Mostra/Nascondi griglia quadrettata",
                              self.act_toggle_grid, "G"))
        m.addSeparator()
        # --- Toggle di visualizzazione OpenSees ---
        m_vis = m.addMenu("Visualizzazione OpenSees")
        self._act_node_labels = self._act("Etichette nodi (tag OpenSees)",
                                            self.act_toggle_node_labels)
        self._act_node_labels.setCheckable(True)
        m_vis.addAction(self._act_node_labels)
        self._act_elem_labels = self._act("Etichette elementi (E<id>)",
                                            self.act_toggle_element_labels)
        self._act_elem_labels.setCheckable(True)
        m_vis.addAction(self._act_elem_labels)
        self._act_load_arrows = self._act("Frecce carichi nodali",
                                            self.act_toggle_load_arrows)
        self._act_load_arrows.setCheckable(True)
        self._act_load_arrows.setChecked(True)
        m_vis.addAction(self._act_load_arrows)
        self._act_constraint_sym = self._act("Simboli vincoli",
                                               self.act_toggle_constraint_symbols)
        self._act_constraint_sym.setCheckable(True)
        self._act_constraint_sym.setChecked(True)
        m_vis.addAction(self._act_constraint_sym)
        m.addSeparator()
        # --- Snapping ---
        self._act_snap = self._act("Snapping a griglia/vertici",
                                     self.act_toggle_snap)
        self._act_snap.setCheckable(True)
        self._act_snap.setChecked(True)
        m.addAction(self._act_snap)
        m.addAction(self._act("Imposta step griglia snap…",
                                self.act_set_snap_step))

        # ----- Aiuto
        m = mb.addMenu("&Aiuto")
        m.addAction(self._act("Guida rapida", self.act_guida))
        m.addAction(self._act("Comandi di selezione", self.act_guida_selezione))
        m.addAction(self._act("Informazioni", self.act_info))

    def _build_toolbars(self):
        # ----- toolbar creazione (modalità geometria)
        tb = QToolBar("Creazione geometria")
        tb.setObjectName("toolbar_creazione")
        tb.addAction(self._act("Punto", lambda: self._crea_dialog("punto")))
        tb.addAction(self._act("Linea", lambda: self._crea_dialog("linea")))
        tb.addAction(self._act("Spline", lambda: self._crea_dialog("spline")))
        tb.addAction(self._act("Cerchio", lambda: self._crea_dialog("cerchio")))
        tb.addAction(self._act("Arco", lambda: self._crea_dialog("arco")))
        tb.addAction(self._act("Superficie da punti", lambda: self._crea_dialog("superficie")))
        tb.addAction(self._act("Rettangolo", lambda: self._crea_dialog("rettangolo")))
        tb.addSeparator()
        tb.addAction(self._act("Box", lambda: self._crea_dialog("box")))
        tb.addAction(self._act("Cilindro", lambda: self._crea_dialog("cilindro")))
        tb.addAction(self._act("Sfera", lambda: self._crea_dialog("sfera")))
        tb.addAction(self._act("Cono", lambda: self._crea_dialog("cono")))
        tb.addAction(self._act("Toro", lambda: self._crea_dialog("toro")))
        tb.addAction(self._act("Estrudi", self.act_estrudi_dialog))
        tb.addAction(self._act("Rivolgi", self.act_rivolgi_dialog))
        self._tb_geometria = tb
        self.addToolBar(tb)

        # ----- toolbar mesh (modalità mesh)
        tb2 = QToolBar("Mesh")
        tb2.setObjectName("toolbar_mesh")
        tb2.addAction(self._act("Importa .msh", self.act_importa_msh))
        tb2.addAction(self._act("OpenSees Export", self.act_export_opensees))
        tb2.addAction(self._act("Fix", self.act_opensees_fix))
        tb2.addAction(self._act("Carico", self.act_opensees_load))
        tb2.addAction(self._act("EqualDOF", self.act_opensees_equaldof))
        tb2.addAction(self._act("Solutore e Fasi", self.act_opensees_solver_stages))
        tb2.addSeparator()
        tb2.addAction(self._act("Sel. tutti gli elementi",
                                lambda: self._mesh_action("all")))
        tb2.addAction(self._act("Sel. in parallelepipedo…",
                                lambda: self._mesh_action("box")))
        tb2.addAction(self._act("Sel. in sfera…",
                                lambda: self._mesh_action("sfera")))
        tb2.addAction(self._act("Sel. per gruppo fisico…",
                                lambda: self._mesh_action("fisico")))
        tb2.addAction(self._act("Espandi (mesh)",
                                lambda: self._mesh_action("grow")))
        tb2.addAction(self._act("Riduci (mesh)",
                                lambda: self._mesh_action("shrink")))
        tb2.addAction(self._act("Nodi della selezione",
                                lambda: self._mesh_action("nodi")))
        tb2.addAction(self._act("Gruppo mesh dalla selezione…",
                                self.act_gruppo_mesh))
        self._tb_mesh = tb2
        self.addToolBar(tb2)

        tb3 = QToolBar("Principale")
        tb3.setObjectName("toolbar_principale")
        tb3.addAction(self._act("Annulla", self.act_undo))
        tb3.addAction(self._act("Ripeti", self.act_redo))
        tb3.addSeparator()
        tb3.addAction(self._act("Elimina", self.act_elimina))
        tb3.addAction(self._act("Gruppo da selezione", self.act_gruppo_da_selezione))
        tb3.addSeparator()
        tb3.addAction(self._act("Fit", self.viewer.fit_all))
        tb3.addAction(self._act("Iso", lambda: self.viewer.vista("iso")))
        tb3.addSeparator()
        # ----- editing col mouse (stile AutoCAD): trascina le entità
        try:
            a_drag = QAction("Trascina col mouse", self)
            a_drag.setCheckable(True)
            a_drag.setToolTip("Attiva il trascinamento delle entità col "
                              "mouse sinistro (anteprima + traslazione)")
            a_drag.toggled.connect(self.act_mouse_edit)
            tb3.addAction(a_drag)
            self._act_drag = a_drag
        except Exception:
            pass
        self.addToolBar(tb3)

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
        chiavi = sorted(self.doc.parameters) or ["h", "L", "R"]

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

        doc_par = self.doc.parameters
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
            self._log(f"Snapping: {'ON' if new_state else 'OFF'}")
            if hasattr(self, "_act_snap"):
                self._act_snap.setChecked(new_state)

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
    def _act(self, testo, slot, shortcut=None) -> QAction:
        a = QAction(testo, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        return a

    def _log(self, msg):
        if hasattr(self, "log_panel"):
            self.log_panel.log(msg)
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
        elif event == "selection_changed":
            self.props_panel.refresh()
            self.tree_panel.refresh()
            if self.viewer is not None:
                self.viewer.highlight_selection()
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
        """Selezione pickata dal viewer: aggiorna il documento."""
        if not isinstance(ids, (list, tuple, set)):
            return
        try:
            self.doc.set_selection(set(ids))
        except Exception:
            pass

    def _refresh_all(self):
        self.tree_panel.refresh()
        self.props_panel.refresh()
        if self.viewer is not None:
            self.viewer.redraw_all(fit=False)
        self._update_status()

    def _update_status(self):
        enti = len(self.doc.selected_entities())
        mesh_info = ""
        for m in self.doc.mesh_models.values():
            mesh_info += (f" | {m.name}: {len(m.sel_nodes)} nodi, "
                          f"{len(m.sel_elements)} elem. sel.")
        self._status_right.setText(
            f"Modalità: {'Geometria' if self.doc.mode == 'geometria' else 'Mesh'} | "
            f"{enti} entità selezionate{mesh_info}")

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

    def _set_mode(self, modo):
        self.doc.mode = modo
        self._tb_geometria.setVisible(modo == "geometria")
        self._tb_mesh.setVisible(modo == "mesh")
        self._mgeo.setChecked(modo == "geometria")
        self._mmesh.setChecked(modo == "mesh")
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

    def act_export_opensees(self):
        """Esportazione OpenSees: nodi per gruppi definiti e connectivity list coerente."""
        if not getattr(self.doc, "mesh_models", None):
            QMessageBox.warning(self, "Esporta OpenSees",
                                "Nessun modello mesh presente nel documento.\n"
                                "Importa o genera prima una mesh (File > Mesha o Importa mesh).")
            return
        active_model = list(self.doc.mesh_models.values())[-1]
        assignments = [item for item in self.doc.opensees.element_assignments
                       if item.model_name == active_model.name]
        if not assignments:
            QMessageBox.warning(
                self, "Assegnazioni FEM mancanti",
                "Prima dell'export Tcl assegna un materiale e un tipo OpenSees "
                "alle entità meshate da OpenSees > Modello FEM.")
            return
        validation = self.doc.opensees.validate_element_assignments(active_model)
        if not validation["valid"]:
            details = "\n".join(validation["errors"][:12])
            QMessageBox.warning(self, "Assegnazioni FEM non valide", details)
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
