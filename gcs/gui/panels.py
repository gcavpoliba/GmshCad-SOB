"""Pannelli dock della GUI: albero entità, proprietà, console, log, macro."""

from __future__ import annotations

import code
import sys
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QBrush
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTreeWidget, QTreeWidgetItem, QTableWidget,
                               QTableWidgetItem, QTextEdit, QLineEdit,
                               QPushButton, QListWidget, QListWidgetItem,
                               QHeaderView, QAbstractItemView, QMenu)

from gcs.core.entities import NOME_TIPO_IT
from gcs.core.document import CADDocument
from gcs.core import occ_utils as ou

COLORE_TIPO = {
    "point": "#E14B4B", "curve": "#3B59E6", "face": "#BFB873",
    "solid": "#739EBF", "compound": "#999999", "mesh": "#7FA07F",
}


# ---------------------------------------------------------------------------
# albero entità e gruppi
# ---------------------------------------------------------------------------

class EntityTree(QWidget):
    """Albero con gruppi ed entità; doppi click seleziona, checkbox = visibilità."""

    def __init__(self, doc: CADDocument, viewer, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.viewer = viewer
        self._updating = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(QLabel("Gruppi ed entità"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Nome", "Tipo", "Id"])
        self.tree.setColumnWidth(0, 170)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._on_double)
        self.tree.itemChanged.connect(self._on_check)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu_contesto)
        lay.addWidget(self.tree)

    # -------------------------------------------------------------- refresh
    def refresh(self):
        if self._updating:
            return
        self._updating = True
        try:
            self.tree.clear()
            # gruppi
            for nome, g in self.doc.groups.groups.items():
                it = QTreeWidgetItem([nome, "Gruppo", ""])
                it.setData(0, Qt.UserRole + 1, nome)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Checked)
                it.setForeground(0, QBrush(QColor("#D08770")))
                dati = [("geo", eid) for eid in sorted(g.member_ids)]
                for kind, eid in dati:
                    e = self.doc.entities.get(eid)
                    if e:
                        figlio = self._entity_item(e)
                        it.addChild(figlio)
                for mname, els in g.mesh_elements.items():
                    figlio = QTreeWidgetItem(
                        [f"{mname}: {len(els)} elementi", "Mesh", ""])
                    figlio.setForeground(0, QBrush(QColor("#81A1C1")))
                    it.addChild(figlio)
                for mname, nodi in g.mesh_nodes.items():
                    figlio = QTreeWidgetItem(
                        [f"{mname}: {len(nodi)} nodi", "Mesh", ""])
                    it.addChild(figlio)
                self.tree.addTopLevelItem(it)
            # entità non in gruppi
            in_gruppi = set()
            for g in self.doc.groups.groups.values():
                in_gruppi |= g.member_ids
            for e in sorted(self.doc.entities.values(), key=lambda x: x.id):
                if e.id not in in_gruppi:
                    self.tree.addTopLevelItem(self._entity_item(e))
            self.tree.expandAll()
        finally:
            self._updating = False

    def _entity_item(self, e) -> QTreeWidgetItem:
        it = QTreeWidgetItem([e.name, NOME_TIPO_IT.get(e.etype, e.etype), str(e.id)])
        it.setData(0, Qt.UserRole, e.id)
        it.setForeground(0, QBrush(QColor(COLORE_TIPO.get(e.etype, "#CCCCCC"))))
        if e.id in self.doc.selection:
            it.setBackground(0, QBrush(QColor("#434C5E")))
        return it

    # ---------------------------------------------------------------- eventi
    def _on_double(self, item, col):
        eid = item.data(0, Qt.UserRole)
        if eid is not None:
            self.doc.set_selection([eid])
            self.viewer.highlight_selection()

    def _on_check(self, item, col):
        if self._updating or col != 0:
            return
        eid = item.data(0, Qt.UserRole)
        if eid is not None:
            e = self.doc.get(eid)
            if e:
                e.visible = (item.checkState(0) == Qt.Checked)
                self.viewer.redraw_all(fit=False)

    def _menu_contesto(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        win = self.window()

        if item is not None:
            eid = item.data(0, Qt.UserRole)
            gname = item.data(0, Qt.UserRole + 1)
            if gname is None and item.text(1) == "Gruppo":
                gname = item.text(0)

            if eid is not None:
                ent = self.doc.entities.get(eid)
                if ent:
                    act_prop = menu.addAction(f"Proprietà e parametri [{ent.name}]…")
                    act_prop.triggered.connect(lambda: self._open_entity_props(ent))
                    menu.addSeparator()

                    # Sottomenu OpenSees
                    m_os = menu.addMenu("OpenSees")
                    m_os.addAction("Associa Vincolo (fix)…", lambda: self._open_fix_entity(eid))
                    m_os.addAction("Associa Carico (load)…", lambda: self._open_load_entity(eid))
                    m_os.addAction("Definisci EqualDOF…", lambda: self._open_equaldof())
                    menu.addSeparator()

                    # Sottomenu Macro applicabili
                    if hasattr(win, "macro_engine"):
                        macros = win.macro_engine.applicable_to(ent.etype)
                        if macros:
                            m_mac = menu.addMenu("Esegui Macro")
                            for spec in macros:
                                m_mac.addAction(spec.name, lambda s=spec: win.run_macro(s))
                            menu.addSeparator()

                    # Sottomenu Trasformazioni
                    m_tr = menu.addMenu("Modifica / Trasforma")
                    if hasattr(win, "act_trasla_dialog"):
                        m_tr.addAction("Traslazione…", win.act_trasla_dialog)
                    if hasattr(win, "act_ruota_dialog"):
                        m_tr.addAction("Rotazione…", win.act_ruota_dialog)
                    if hasattr(win, "act_scala_dialog"):
                        m_tr.addAction("Scala…", win.act_scala_dialog)
                    menu.addSeparator()

                    menu.addAction("Seleziona", lambda: self._select(eid))
                    menu.addAction("Isola (visualizza solo questo)", lambda: self._isolate(eid))
                    if hasattr(win, "act_elimina"):
                        menu.addAction("Elimina", win.act_elimina)

            elif gname is not None:
                act_gprop = menu.addAction(f"Proprietà e parametri gruppo [{gname}]…")
                act_gprop.triggered.connect(lambda: self._open_group_props(gname))
                menu.addSeparator()

                m_os = menu.addMenu("OpenSees")
                m_os.addAction("Associa Vincolo OpenSees (fix) al gruppo…", lambda: self._open_fix_group(gname))
                m_os.addAction("Associa Carico OpenSees (load) al gruppo…", lambda: self._open_load_group(gname))
                m_os.addAction("Definisci EqualDOF…", lambda: self._open_equaldof())
                m_os.addAction("Esporta nodi gruppo (.txt)…", lambda: self._export_group_nodes(gname))
                menu.addSeparator()

                menu.addAction("Seleziona membri del gruppo", lambda: self._select_group_members(gname))
                menu.addAction("Aggiungi selezione al gruppo", lambda: self._add_sel_to_group(gname))
                menu.addAction("Rimuovi selezione dal gruppo", lambda: self._remove_sel_from_group(gname))
                menu.addSeparator()
                menu.addAction("Rinomina gruppo…", lambda: self._rename_group(gname))
                menu.addAction("Elimina gruppo", lambda: self._delete_group(gname))

        else:
            menu.addAction("Crea nuovo gruppo dalla selezione…",
                           lambda: win.act_gruppo_da_selezione() if hasattr(win, "act_gruppo_da_selezione") else None)
            menu.addAction("Configura Solutore e Fasi OpenSees…", self._open_analysis_dialog)
            menu.addAction("Esporta per OpenSees…",
                           lambda: win.act_export_opensees() if hasattr(win, "act_export_opensees") else None)

        menu.addSeparator()
        menu.addAction("Aggiorna vista", self.viewer.redraw_all)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _open_entity_props(self, ent):
        from .dialogs import EntityPropertiesDialog
        dlg = EntityPropertiesDialog(ent, self.doc, parent=self)
        if dlg.exec():
            self.refresh()
            self.viewer.redraw_all(fit=False)

    def _open_group_props(self, gname):
        from .dialogs import GroupPropertiesDialog
        dlg = GroupPropertiesDialog(gname, self.doc, parent=self)
        if dlg.exec():
            self.refresh()
            self.viewer.redraw_all(fit=False)

    def _open_fix_entity(self, eid):
        from .dialogs import OpenSeesFixDialog
        dlg = OpenSeesFixDialog(self.doc, target_entities=[eid], parent=self)
        dlg.exec()

    def _open_fix_group(self, gname):
        from .dialogs import OpenSeesFixDialog
        dlg = OpenSeesFixDialog(self.doc, target_group=gname, parent=self)
        dlg.exec()

    def _open_load_entity(self, eid):
        from .dialogs import OpenSeesLoadDialog
        dlg = OpenSeesLoadDialog(self.doc, target_entities=[eid], parent=self)
        dlg.exec()

    def _open_load_group(self, gname):
        from .dialogs import OpenSeesLoadDialog
        dlg = OpenSeesLoadDialog(self.doc, target_group=gname, parent=self)
        dlg.exec()

    def _open_equaldof(self):
        from .dialogs import OpenSeesEqualDOFDialog
        dlg = OpenSeesEqualDOFDialog(self.doc, parent=self)
        dlg.exec()

    def _open_analysis_dialog(self):
        from .dialogs import OpenSeesAnalysisDialog
        dlg = OpenSeesAnalysisDialog(self.doc, parent=self)
        dlg.exec()

    def _select_group_members(self, gname):
        grp = self.doc.groups.get(gname)
        if grp:
            self.doc.set_selection(grp.member_ids)
            self.viewer.highlight_selection()

    def _add_sel_to_group(self, gname):
        self.doc.groups.add_geo(gname, self.doc.selection)
        self.refresh()

    def _remove_sel_from_group(self, gname):
        try:
            self.doc.groups.remove_geo(gname, self.doc.selection)
            self.refresh()
        except Exception:
            pass

    def _rename_group(self, gname):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        nuovo, ok = QInputDialog.getText(self, "Rinomina Gruppo", f"Nuovo nome per '{gname}':", text=gname)
        if ok and nuovo.strip() and nuovo.strip() != gname:
            try:
                self.doc.groups.rename(gname, nuovo.strip())
                self.refresh()
            except Exception as ex:
                QMessageBox.warning(self, "Rinomina Gruppo", str(ex))

    def _delete_group(self, gname):
        from PySide6.QtWidgets import QMessageBox
        res = QMessageBox.question(self, "Elimina Gruppo", f"Eliminare il gruppo '{gname}'?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            self.doc.groups.delete(gname)
            self.refresh()

    def _export_group_nodes(self, gname):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from ..core import opensees_export as ose
        path, _ = QFileDialog.getSaveFileName(self, f"Esporta nodi gruppo {gname}", f"nodi_{gname}.txt", "File di testo (*.txt)")
        if path:
            try:
                model = list(self.doc.mesh_models.values())[-1] if self.doc.mesh_models else None
                data = ose.extract_defined_groups_nodes(self.doc, model).get(gname)
                if not data or not model:
                    raise ValueError(f"Nessun nodo trovato per il gruppo '{gname}'")
                txt = ose.format_group_nodes_txt(gname, data["node_ids"], model.nodes)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(txt)
                QMessageBox.information(self, "Esporta Nodi Gruppo", f"Nodi salvati in:\n{path}")
            except Exception as ex:
                QMessageBox.critical(self, "Errore Export", str(ex))

    def _select(self, eid):
        self.doc.set_selection([eid])
        self.viewer.highlight_selection()

    def _isolate(self, eid):
        for e in self.doc.entities.values():
            e.visible = (e.id == eid)
        self.viewer.redraw_all(fit=True)


# ---------------------------------------------------------------------------
# pannello proprietà
# ---------------------------------------------------------------------------

class PropertiesPanel(QWidget):
    """Proprietà delle entità selezionate (geometria, misura, meta)."""

    def __init__(self, doc: CADDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(QLabel("Proprietà selezione"))
        self.table = QTableWidget(0, 2)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table)

        # Pulsanti rapidi interattivi
        btn_box = QHBoxLayout()
        self.btn_edit_prop = QPushButton("Modifica parametri…")
        self.btn_fix = QPushButton("Vincolo fix…")
        self.btn_load = QPushButton("Carico load…")
        self.btn_edit_prop.clicked.connect(self._on_edit_properties)
        self.btn_fix.clicked.connect(self._on_apply_fix)
        self.btn_load.clicked.connect(self._on_apply_load)
        btn_box.addWidget(self.btn_edit_prop)
        btn_box.addWidget(self.btn_fix)
        btn_box.addWidget(self.btn_load)
        lay.addLayout(btn_box)

    def refresh(self):
        enti = self.doc.selected_entities()
        self.table.setRowCount(0)
        has_sel = bool(enti)
        self.btn_edit_prop.setEnabled(has_sel)
        self.btn_fix.setEnabled(has_sel)
        self.btn_load.setEnabled(has_sel)
        if not enti:
            self._add_row("—", "nessuna entità selezionata")
            return
        self._add_row("Selezionate", str(len(enti)))
        for e in enti[:20]:
            self._add_row("—", f"{e.name} (id {e.id})")
            self._add_row("   tipo", NOME_TIPO_IT.get(e.etype, e.etype))
            if e.shape is not None:
                try:
                    bb = ou.bbox_of(e.shape)
                    self._add_row("   bbox",
                                  f"[{bb[0]:.2f}, {bb[1]:.2f}, {bb[2]:.2f}] → "
                                  f"[{bb[3]:.2f}, {bb[4]:.2f}, {bb[5]:.2f}]")
                except Exception:
                    pass
                try:
                    if e.etype == "face":
                        self._add_row("   area", f"{ou.area_of(e.shape):.4f}")
                    elif e.etype == "curve":
                        self._add_row("   lunghezza", f"{ou.length_of(e.shape):.4f}")
                    elif e.etype == "solid":
                        self._add_row("   volume", f"{ou.volume_of(e.shape):.4f}")
                except Exception:
                    pass
            ref = e.mesh_ref()
            if ref:
                self._add_row("   blocco mesh", f"modello={ref[0]}, dim={ref[1]}, tag={ref[2]}")
                self._add_row("   n. elementi", str(e.meta.get("n_elementi", "?")))
            if e.marker:
                self._add_row("   marker fisico", str(e.marker))
            for k, v in e.meta.items():
                if k in ("ctrl_points",):
                    v = f"{len(v)} punti"
                self._add_row(f"   {k}", str(v))

    def _add_row(self, chiave, valore):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(chiave))
        self.table.setItem(r, 1, QTableWidgetItem(str(valore)))

    def _on_edit_properties(self):
        enti = self.doc.selected_entities()
        if not enti:
            return
        from .dialogs import EntityPropertiesDialog
        dlg = EntityPropertiesDialog(enti[0], self.doc, parent=self)
        if dlg.exec():
            self.refresh()
            win = self.window()
            if hasattr(win, "viewer"):
                win.viewer.redraw_all(fit=False)
            if hasattr(win, "panel_tree"):
                win.panel_tree.refresh()

    def _on_apply_fix(self):
        enti = self.doc.selected_entities()
        eids = [e.id for e in enti]
        from .dialogs import OpenSeesFixDialog
        dlg = OpenSeesFixDialog(self.doc, target_entities=eids, parent=self)
        dlg.exec()

    def _on_apply_load(self):
        enti = self.doc.selected_entities()
        eids = [e.id for e in enti]
        from .dialogs import OpenSeesLoadDialog
        dlg = OpenSeesLoadDialog(self.doc, target_entities=eids, parent=self)
        dlg.exec()


# ---------------------------------------------------------------------------
# console Python
# ---------------------------------------------------------------------------

class ConsolePanel(QWidget):
    """Console Python con accesso diretto al documento e ai moduli di gcs."""

    def __init__(self, namespace: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(QFont("Monospace", 9))
        self.out.setStyleSheet("background-color:#2E3440;color:#D8DEE9;")
        lay.addWidget(self.out, 4)
        riga = QHBoxLayout()
        riga.addWidget(QLabel(">>>"))
        self.inp = QLineEdit()
        self.inp.setFont(QFont("Monospace", 9))
        self.inp.returnPressed.connect(self._exec)
        riga.addWidget(self.inp, 1)
        lay.addLayout(riga, 1)
        self._ns = namespace
        self._buffer: List[str] = []
        self._inter = code.InteractiveInterpreter(namespace)
        self.print_banner()

    def print_banner(self):
        self._w("GmshCAD Studio — console Python (il documento è in 'doc')")
        self._w("Vedi anche: help_cad()  |  doc.help_selection()")

    def _w(self, testo):
        self.out.append(testo)

    def log(self, msg):
        self._w(str(msg))

    def _exec(self):
        riga = self.inp.text()
        self._w(f">>> {riga}")
        self.inp.clear()
        salva_out, salva_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = self._LogWriter(self)
        try:
            if riga.strip().endswith(":"):
                self._buffer.append(riga)
            elif self._buffer:
                self._buffer.append("    " + riga)
                if not riga.strip():
                    blocco = "\n".join(self._buffer)
                    self._buffer.clear()
                    self._inter.runcode(blocco)
                return
            else:
                self._inter.runcode(riga)
        finally:
            sys.stdout, sys.stderr = salva_out, salva_err

    class _LogWriter:
        def __init__(self, panel):
            self.panel = panel

        def write(self, testo):
            if testo.strip():
                self.panel._w(testo.rstrip("\n"))

        def flush(self):
            pass


# ---------------------------------------------------------------------------
# log messaggi / pannello macro
# ---------------------------------------------------------------------------

class LogPanel(QWidget):
    """Log dei messaggi dell'applicazione (operazioni, macro, errori)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Monospace", 9))
        self.text.setStyleSheet("background-color:#2E3440;color:#A3BE8C;")
        lay.addWidget(self.text)

    def log(self, msg):
        self.text.append(str(msg))


class MacroPanel(QWidget):
    """Elenco delle macro caricate con descrizione e pulsante Esegui."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(QLabel("Macro disponibili (cartella gcs/macros)"))
        self.lista = QListWidget()
        lay.addWidget(self.lista, 2)
        self.desc = QTextEdit()
        self.desc.setReadOnly(True)
        self.desc.setMaximumHeight(150)
        lay.addWidget(self.desc, 1)
        btn = QPushButton("Esegui macro selezionata…")
        btn.clicked.connect(self._esegui)
        lay.addWidget(btn)
        self.lista.currentRowChanged.connect(self._descrizione)
        self.refresh()

    def refresh(self):
        self.lista.clear()
        for nome in self.engine.list_names():
            it = QListWidgetItem(nome)
            spec = self.engine.by_name(nome)
            it.setToolTip(spec.source_file if spec else "")
            self.lista.addItem(it)
        if self.engine.load_errors:
            self.desc.setPlainText("Errori caricamento:\n" +
                                   "\n".join(self.engine.load_errors))

    def _descrizione(self, row):
        if row < 0:
            return
        nome = self.lista.item(row).text()
        spec = self.engine.by_name(nome)
        if spec:
            params = "\n".join(
                f"  • {p.name} ({p.ptype}) default={p.default!r}"
                + (f" [{p.min}..{p.max}]" if p.min is not None or p.max is not None else "")
                + (f" — {p.help}" if p.help else "")
                for p in spec.params)
            self.desc.setPlainText(
                f"{spec.name}\n{spec.description}\n\n"
                f"Si applica a: {spec.targets_label()}\n"
                f"Parametri:\n{params or '  (nessuno)'}")

    def _esegui(self):
        row = self.lista.currentRow()
        if row < 0:
            return
        win = self.window()
        if hasattr(win, "run_macro"):
            win.run_macro(self.engine.by_name(self.lista.item(row).text()))
