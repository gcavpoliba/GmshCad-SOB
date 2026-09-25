"""Dialoghi della GUI: parametri macro auto-generati, input numerici, gruppi,
proprietà entità e configurazione OpenSees (fix, carichi, equalDOF, solutori e fasi)."""

from __future__ import annotations

import os
from typing import Optional, List, Dict, Set, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QGridLayout, QLabel, QDoubleSpinBox, QSpinBox,
                               QLineEdit, QCheckBox, QComboBox, QDialogButtonBox,
                               QGroupBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QHeaderView, QColorDialog,
                               QTabWidget, QTextEdit, QRadioButton, QButtonGroup,
                               QListWidget, QListWidgetItem, QFileDialog,
                               QMessageBox)

from ..core import occ_utils as ou
from ..core.entities import NOME_TIPO_IT


class ParamDialog(QDialog):
    """Dialog di parametri generato automaticamente dallo schema della macro.

    Supporta i tipi Param: float, int, str, bool, choice, vec3.
    """

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setWindowTitle(f"Macro: {spec.name}")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        if spec.description:
            lbl = QLabel(spec.description)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#8892A8;")
            lay.addWidget(lbl)
        if spec.applies_to:
            lay.addWidget(QLabel(f"<b>Si applica a:</b> {spec.targets_label()}"))
        box = QGroupBox("Parametri")
        form = QFormLayout(box)
        self._widgets = {}
        for p in spec.params:
            w = self._widget_for(p)
            self._widgets[p.name] = w
            label = p.name + (f"\n<small>{p.help}</small>" if p.help else "")
            form.addRow(label.replace("\n", "<br>").replace("<small>", "<i>")
                        .replace("</small>", "</i>"), w)
        lay.addWidget(box)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _widget_for(self, p):
        if p.ptype == "float":
            w = QDoubleSpinBox()
            w.setDecimals(4)
            w.setRange(p.min if p.min is not None else -1e12,
                       p.max if p.max is not None else 1e12)
            w.setValue(float(p.default))
            return w
        if p.ptype == "int":
            w = QSpinBox()
            w.setRange(int(p.min) if p.min is not None else -10**9,
                       int(p.max) if p.max is not None else 10**9)
            w.setValue(int(p.default))
            return w
        if p.ptype == "bool":
            w = QCheckBox()
            w.setChecked(bool(p.default))
            return w
        if p.ptype == "choice":
            w = QComboBox()
            w.addItems([str(c) for c in (p.choices or ())])
            if str(p.default) in [str(c) for c in (p.choices or ())]:
                w.setCurrentText(str(p.default))
            return w
        if p.ptype == "vec3":
            w = QLineEdit()
            w.setPlaceholderText("x, y, z")
            w.setText(", ".join(str(v) for v in (p.default or (0, 0, 0))))
            return w
        w = QLineEdit()
        w.setText(str(p.default))
        return w

    def values(self) -> dict:
        out = {}
        for name, w in self._widgets.items():
            if isinstance(w, QDoubleSpinBox):
                out[name] = w.value()
            elif isinstance(w, QSpinBox):
                out[name] = w.value()
            elif isinstance(w, QCheckBox):
                out[name] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[name] = w.currentText()
            elif isinstance(w, QLineEdit):
                txt = w.text()
                if "," in txt and " " in (txt.replace(",", "")):
                    try:
                        out[name] = [float(v) for v in txt.replace(" ", "").split(",")]
                        continue
                    except Exception:
                        pass
                out[name] = txt
        return out


# =============================================================================
# Dialogo Proprietà Entità
# =============================================================================

class EntityPropertiesDialog(QDialog):
    """Dialogo interattivo per la visualizzazione e modifica dei parametri di un'entità."""

    def __init__(self, entity, doc, parent=None):
        super().__init__(parent)
        self.entity = entity
        self.doc = doc
        self._cur_color = entity.color

        self.setWindowTitle(f"Proprietà Entità — {entity.name} (ID: {entity.id})")
        self.setMinimumWidth(440)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        # Informazioni Generali
        grp_gen = QGroupBox("Parametri Generali")
        form_gen = QFormLayout(grp_gen)

        self.txt_name = QLineEdit(self.entity.name)
        form_gen.addRow("Nome entità:", self.txt_name)

        lbl_tipo = QLabel(f"<b>{NOME_TIPO_IT.get(self.entity.etype, self.entity.etype)}</b> (ID: {self.entity.id})")
        form_gen.addRow("Tipo:", lbl_tipo)

        self.chk_visible = QCheckBox("Visibile nel viewport 3D")
        self.chk_visible.setChecked(self.entity.visible)
        form_gen.addRow("Visibilità:", self.chk_visible)

        # Colore
        col_lay = QHBoxLayout()
        self.btn_color = QPushButton("Scegli Colore…")
        self.lbl_color_swatch = QLabel("    ")
        self._update_color_swatch()
        self.btn_color.clicked.connect(self._choose_color)
        col_lay.addWidget(self.lbl_color_swatch)
        col_lay.addWidget(self.btn_color)
        col_lay.addStretch()
        form_gen.addRow("Colore:", col_lay)

        # Marker Gmsh
        self.spn_marker = QSpinBox()
        self.spn_marker.setRange(0, 1000000)
        self.spn_marker.setValue(self.entity.marker or 0)
        self.spn_marker.setToolTip("Physical Tag Gmsh associato per l'export e vincoli")
        form_gen.addRow("Marker Fisico Gmsh:", self.spn_marker)

        lay.addWidget(grp_gen)

        # Informazioni Geometriche / Misura
        grp_geo = QGroupBox("Misure e Geometria")
        form_geo = QFormLayout(grp_geo)
        if self.entity.shape is not None:
            try:
                bb = ou.bbox_of(self.entity.shape)
                form_geo.addRow("Bounding Box:", QLabel(f"[{bb[0]:.2f}, {bb[1]:.2f}, {bb[2]:.2f}] → [{bb[3]:.2f}, {bb[4]:.2f}, {bb[5]:.2f}]"))
            except Exception:
                pass
            try:
                if self.entity.etype == "face":
                    form_geo.addRow("Area superficie:", QLabel(f"{ou.area_of(self.entity.shape):.4f}"))
                elif self.entity.etype == "curve":
                    form_geo.addRow("Lunghezza:", QLabel(f"{ou.length_of(self.entity.shape):.4f}"))
                elif self.entity.etype == "solid":
                    form_geo.addRow("Volume:", QLabel(f"{ou.volume_of(self.entity.shape):.4f}"))
            except Exception:
                pass
        ref = self.entity.mesh_ref()
        if ref:
            form_geo.addRow("Riferimento blocco mesh:", QLabel(f"Modello: {ref[0]}, Dim: {ref[1]}, Tag: {ref[2]}"))
            form_geo.addRow("Elementi nel blocco:", QLabel(str(self.entity.meta.get("n_elementi", "—"))))

        lay.addWidget(grp_geo)

        # Pulsanti OK / Cancel
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply_and_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _update_color_swatch(self):
        c = self._cur_color or (0.7, 0.7, 0.7)
        r, g, b = int(c[0] * 255), int(c[1] * 255), int(c[2] * 255)
        self.lbl_color_swatch.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid #555; border-radius: 3px; min-width: 32px;")

    def _choose_color(self):
        c = self._cur_color or (0.7, 0.7, 0.7)
        init_c = QColor(int(c[0]*255), int(c[1]*255), int(c[2]*255))
        qc = QColorDialog.getColor(init_c, self, "Scegli Colore Entità")
        if qc.isValid():
            self._cur_color = (qc.redF(), qc.greenF(), qc.blueF())
            self._update_color_swatch()

    def _apply_and_accept(self):
        new_name = self.txt_name.text().strip()
        if new_name:
            self.entity.name = new_name
        self.entity.visible = self.chk_visible.isChecked()
        self.entity.color = self._cur_color
        self.entity.marker = self.spn_marker.value()
        self.doc.notify("entity_changed", {"id": self.entity.id})
        self.accept()


# =============================================================================
# Dialogo Proprietà Gruppo
# =============================================================================

class GroupPropertiesDialog(QDialog):
    """Dialogo interattivo per la gestione e compilazione parametri di un gruppo."""

    def __init__(self, group_name: str, doc, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.doc = doc
        self.group = doc.groups.get(group_name)
        self._cur_color = getattr(self.group, "color", None) if self.group else None

        self.setWindowTitle(f"Proprietà Gruppo — {group_name}")
        self.setMinimumWidth(460)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        # Informazioni Gruppo
        grp_box = QGroupBox("Parametri Gruppo")
        form = QFormLayout(grp_box)

        self.txt_name = QLineEdit(self.group_name)
        form.addRow("Nome gruppo:", self.txt_name)

        col_lay = QHBoxLayout()
        self.lbl_color = QLabel("    ")
        self._update_color_swatch()
        btn_c = QPushButton("Scegli Colore…")
        btn_c.clicked.connect(self._choose_color)
        col_lay.addWidget(self.lbl_color)
        col_lay.addWidget(btn_c)
        col_lay.addStretch()
        form.addRow("Colore:", col_lay)

        lay.addWidget(grp_box)

        # Membri Gruppo
        mem_box = QGroupBox("Membri e Topologia")
        mem_form = QFormLayout(mem_box)

        n_geo = len(self.group.member_ids) if self.group else 0
        nel, nno = self.group.count_mesh() if self.group else (0, 0)

        mem_form.addRow("Entità geometriche:", QLabel(f"<b>{n_geo}</b> (ID: {sorted(list(self.group.member_ids)) if self.group else []})"))
        mem_form.addRow("Elementi mesh associati:", QLabel(f"<b>{nel}</b>"))
        mem_form.addRow("Nodi mesh associati:", QLabel(f"<b>{nno}</b>"))

        # Calcolo nodi totali risolti per OpenSees
        resolved_nodes = []
        if hasattr(self.doc, "opensees"):
            resolved_nodes = self.doc.opensees.resolve_group_nodes(self.group_name)
        mem_form.addRow("Nodi risolti per OpenSees:", QLabel(f"<span style='color:green;'><b>{len(resolved_nodes)} nodi</b></span>"))

        lay.addWidget(mem_box)

        # Azioni rapide OpenSees
        act_box = QGroupBox("Azioni Rapide OpenSees per questo Gruppo")
        act_lay = QHBoxLayout(act_box)
        btn_fix = QPushButton("Associa Vincolo (fix)…")
        btn_load = QPushButton("Associa Carico (load)…")
        btn_fix.clicked.connect(self._open_fix)
        btn_load.clicked.connect(self._open_load)
        act_lay.addWidget(btn_fix)
        act_lay.addWidget(btn_load)
        lay.addWidget(act_box)

        # Pulsanti OK / Cancel
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply_and_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _update_color_swatch(self):
        c = self._cur_color or (0.8, 0.5, 0.4)
        r, g, b = int(c[0] * 255), int(c[1] * 255), int(c[2] * 255)
        self.lbl_color.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid #555; border-radius: 3px; min-width: 32px;")

    def _choose_color(self):
        c = self._cur_color or (0.8, 0.5, 0.4)
        qc = QColorDialog.getColor(QColor(int(c[0]*255), int(c[1]*255), int(c[2]*255)), self, "Colore Gruppo")
        if qc.isValid():
            self._cur_color = (qc.redF(), qc.greenF(), qc.blueF())
            self._update_color_swatch()

    def _open_fix(self):
        dlg = OpenSeesFixDialog(self.doc, target_group=self.group_name, parent=self)
        dlg.exec()

    def _open_load(self):
        dlg = OpenSeesLoadDialog(self.doc, target_group=self.group_name, parent=self)
        dlg.exec()

    def _apply_and_accept(self):
        new_name = self.txt_name.text().strip()
        if new_name and new_name != self.group_name:
            try:
                self.doc.groups.rename(self.group_name, new_name)
                self.group_name = new_name
            except Exception as ex:
                QMessageBox.warning(self, "Rinomina Gruppo", f"Errore durante la rinomina: {ex}")
                return
        if self.group:
            self.group.color = self._cur_color
        self.doc.notify("group_changed", {"name": self.group_name})
        self.accept()


# =============================================================================
# Dialogo Vincolo OpenSees (fix) su Gruppi o Entità
# =============================================================================

class OpenSeesFixDialog(QDialog):
    """Dialogo per compilare i parametri del comando fix di OpenSees associato a gruppi o entità."""

    def __init__(self, doc, target_group: Optional[str] = None,
                 target_entities: Optional[List[int]] = None, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.init_group = target_group
        self.init_entities = list(target_entities or [])
        if not self.init_entities and not self.init_group and doc.selection:
            self.init_entities = list(doc.selection)

        self.setWindowTitle("Associa Vincolo OpenSees (fix)")
        self.setMinimumWidth(480)
        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        # 1. Nome e Bersaglio
        box_target = QGroupBox("Bersaglio del Vincolo")
        form_target = QFormLayout(box_target)

        default_name = f"Fix_{self.init_group or ('Entita_' + str(self.init_entities[0]) if self.init_entities else '1')}"
        self.txt_name = QLineEdit(default_name)
        form_target.addRow("Nome identificativo:", self.txt_name)

        # Tipo bersaglio: Gruppo vs Entità
        self.rad_group = QRadioButton("Applica a Gruppo di entità determinate")
        self.rad_ent = QRadioButton("Applica a Entità geometriche selezionate")
        if self.init_group or not self.init_entities:
            self.rad_group.setChecked(True)
        else:
            self.rad_ent.setChecked(True)

        self.rad_group.toggled.connect(self._on_target_mode_changed)
        target_mode_lay = QHBoxLayout()
        target_mode_lay.addWidget(self.rad_group)
        target_mode_lay.addWidget(self.rad_ent)
        form_target.addRow("Tipo destinazione:", target_mode_lay)

        # Combo gruppi disponibili
        self.cmb_groups = QComboBox()
        available_groups = set()
        if hasattr(self.doc, "groups"):
            available_groups.update(self.doc.groups.list_names())
        for m in self.doc.mesh_models.values():
            for (dim, pt), pname in getattr(m, "physicals", {}).items():
                if pname:
                    available_groups.add(pname)
        for gname in sorted(available_groups):
            self.cmb_groups.addItem(gname)
        if self.init_group and self.init_group in available_groups:
            self.cmb_groups.setCurrentText(self.init_group)
        self.cmb_groups.currentTextChanged.connect(self._update_preview)
        form_target.addRow("Gruppo selezionato:", self.cmb_groups)

        # LineEdit entità
        self.txt_entities = QLineEdit(", ".join(str(i) for i in self.init_entities))
        self.txt_entities.textChanged.connect(self._update_preview)
        form_target.addRow("ID Entità (es. 1, 2, 3):", self.txt_entities)

        lay.addWidget(box_target)

        # 2. Gradi di Libertà (DOFs)
        box_dof = QGroupBox("Gradi di Libertà Vincolati (fix = 1)")
        form_dof = QVBoxLayout(box_dof)

        preset_lay = QHBoxLayout()
        preset_lay.addWidget(QLabel("Preset rapidi:"))
        self.cmb_preset = QComboBox()
        self.cmb_preset.addItems([
            "Personalizzato",
            "Incastro Completo (Ux, Uy, Uz, Rx, Ry, Rz)",
            "Cerniera Sferica (Ux, Uy, Uz)",
            "Carrello X (Uy, Uz bloccati)",
            "Carrello Y (Ux, Uz bloccati)",
            "Carrello Z (Ux, Uy bloccati)",
            "Piano XY (Uz bloccato)",
            "Tutto Libero (0 0 0 0 0 0)",
        ])
        self.cmb_preset.currentIndexChanged.connect(self._apply_preset)
        preset_lay.addWidget(self.cmb_preset)
        form_dof.addLayout(preset_lay)

        grid_dof = QGridLayout()
        self.chk_x = QCheckBox("Traslazione X (Ux)")
        self.chk_y = QCheckBox("Traslazione Y (Uy)")
        self.chk_z = QCheckBox("Traslazione Z (Uz)")
        self.chk_rx = QCheckBox("Rotazione X (Rx)")
        self.chk_ry = QCheckBox("Rotazione Y (Ry)")
        self.chk_rz = QCheckBox("Rotazione Z (Rz)")

        self.chk_x.setChecked(True)
        self.chk_y.setChecked(True)
        self.chk_z.setChecked(True)

        for chk in (self.chk_x, self.chk_y, self.chk_z, self.chk_rx, self.chk_ry, self.chk_rz):
            chk.toggled.connect(self._update_preview)

        grid_dof.addWidget(self.chk_x, 0, 0)
        grid_dof.addWidget(self.chk_y, 0, 1)
        grid_dof.addWidget(self.chk_z, 0, 2)
        grid_dof.addWidget(self.chk_rx, 1, 0)
        grid_dof.addWidget(self.chk_ry, 1, 1)
        grid_dof.addWidget(self.chk_rz, 1, 2)
        form_dof.addLayout(grid_dof)

        lay.addWidget(box_dof)

        # 3. Anteprima Nodi e Sintassi OpenSees
        box_prev = QGroupBox("Anteprima Nodi e Sintassi OpenSees")
        prev_lay = QVBoxLayout(box_prev)
        self.lbl_nodes_cnt = QLabel("Nodi coinvolti: calcolo in corso…")
        self.lbl_nodes_cnt.setStyleSheet("color:#A3BE8C; font-weight:bold;")
        self.txt_tcl_prev = QTextEdit()
        self.txt_tcl_prev.setReadOnly(True)
        self.txt_tcl_prev.setMaximumHeight(85)
        self.txt_tcl_prev.setStyleSheet("background:#2E3440; color:#D8DEE9; font-family:Monospace; font-size:11px;")
        prev_lay.addWidget(self.lbl_nodes_cnt)
        prev_lay.addWidget(self.txt_tcl_prev)
        lay.addWidget(box_prev)

        # 4. Pulsanti OK / Cancel
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply_and_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._on_target_mode_changed()

    def _on_target_mode_changed(self):
        is_group = self.rad_group.isChecked()
        self.cmb_groups.setEnabled(is_group)
        self.txt_entities.setEnabled(not is_group)
        self._update_preview()

    def _apply_preset(self, idx):
        if idx == 1:  # Incastro
            self._set_dofs(True, True, True, True, True, True)
        elif idx == 2:  # Cerniera
            self._set_dofs(True, True, True, False, False, False)
        elif idx == 3:  # Carrello X
            self._set_dofs(False, True, True, False, False, False)
        elif idx == 4:  # Carrello Y
            self._set_dofs(True, False, True, False, False, False)
        elif idx == 5:  # Carrello Z
            self._set_dofs(True, True, False, False, False, False)
        elif idx == 6:  # Piano XY
            self._set_dofs(False, False, True, False, False, False)
        elif idx == 7:  # Libero
            self._set_dofs(False, False, False, False, False, False)

    def _set_dofs(self, x, y, z, rx, ry, rz):
        self.chk_x.setChecked(x)
        self.chk_y.setChecked(y)
        self.chk_z.setChecked(z)
        self.chk_rx.setChecked(rx)
        self.chk_ry.setChecked(ry)
        self.chk_rz.setChecked(rz)

    def _get_target_nodes(self) -> List[int]:
        if not hasattr(self.doc, "opensees"):
            return []
        nodes: Set[int] = set()
        if self.rad_group.isChecked():
            gname = self.cmb_groups.currentText()
            if gname:
                nodes.update(self.doc.opensees.resolve_group_nodes(gname))
        else:
            txt = self.txt_entities.text()
            for part in txt.replace(";", ",").split(","):
                part = part.strip()
                if part.isdigit():
                    nodes.update(self.doc.opensees.resolve_entity_nodes(int(part)))
        return sorted(list(nodes))

    def _update_preview(self):
        nodes = self._get_target_nodes()
        self.lbl_nodes_cnt.setText(f"Nodi della mesh coinvolti: {len(nodes)}")
        flags = [
            1 if self.chk_x.isChecked() else 0,
            1 if self.chk_y.isChecked() else 0,
            1 if self.chk_z.isChecked() else 0,
            1 if self.chk_rx.isChecked() else 0,
            1 if self.chk_ry.isChecked() else 0,
            1 if self.chk_rz.isChecked() else 0,
        ]
        flags_str = " ".join(str(f) for f in flags)
        if nodes:
            sample_nodes = " ".join(str(n) for n in nodes[:8])
            if len(nodes) > 8:
                sample_nodes += f" ... ({len(nodes)} nodi in totale)"
            tcl = f"# Esempio comando OpenSees generato:\nforeach node {{ {sample_nodes} }} {{\n    fix $node {flags_str};\n}}"
        else:
            tcl = f"# Nessun nodo risolto al momento con i bersagli selezionati.\n# Sintassi: fix $nodeTag {flags_str};"
        self.txt_tcl_prev.setPlainText(tcl)

    def _apply_and_accept(self):
        name = self.txt_name.text().strip() or "Vincolo"
        group_names = [self.cmb_groups.currentText()] if self.rad_group.isChecked() and self.cmb_groups.currentText() else []
        entity_ids = []
        if self.rad_ent.isChecked():
            for p in self.txt_entities.text().replace(";", ",").split(","):
                if p.strip().isdigit():
                    entity_ids.append(int(p.strip()))

        if not group_names and not entity_ids:
            QMessageBox.warning(self, "Attenzione", "Specificare almeno un gruppo o un'entità bersaglio.")
            return

        sc = self.doc.opensees.add_constraint(
            name=name,
            entity_ids=entity_ids,
            fix_x=self.chk_x.isChecked(),
            fix_y=self.chk_y.isChecked(),
            fix_z=self.chk_z.isChecked(),
            fix_rx=self.chk_rx.isChecked(),
            fix_ry=self.chk_ry.isChecked(),
            fix_rz=self.chk_rz.isChecked(),
            group_names=group_names
        )
        self.doc.notify("opensees_condition_added", {"type": "constraint", "cid": sc.cid})
        self.accept()


# =============================================================================
# Dialogo Carico OpenSees (load) su Gruppi o Entità
# =============================================================================

class OpenSeesLoadDialog(QDialog):
    """Dialogo per definire e applicare carichi nodali e distribuiti (load) per OpenSees."""

    def __init__(self, doc, target_group: Optional[str] = None,
                 target_entities: Optional[List[int]] = None, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.init_group = target_group
        self.init_entities = list(target_entities or [])
        if not self.init_entities and not self.init_group and doc.selection:
            self.init_entities = list(doc.selection)

        self.setWindowTitle("Associa Carico OpenSees (load)")
        self.setMinimumWidth(480)
        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        # 1. Bersaglio e Nome
        box_target = QGroupBox("Bersaglio del Carico")
        form_target = QFormLayout(box_target)

        default_name = f"Carico_{self.init_group or ('Entita_' + str(self.init_entities[0]) if self.init_entities else '1')}"
        self.txt_name = QLineEdit(default_name)
        form_target.addRow("Nome identificativo:", self.txt_name)

        self.rad_group = QRadioButton("Applica a Gruppo di entità")
        self.rad_ent = QRadioButton("Applica a Entità geometriche")
        if self.init_group or not self.init_entities:
            self.rad_group.setChecked(True)
        else:
            self.rad_ent.setChecked(True)
        self.rad_group.toggled.connect(self._on_target_mode_changed)

        rad_lay = QHBoxLayout()
        rad_lay.addWidget(self.rad_group)
        rad_lay.addWidget(self.rad_ent)
        form_target.addRow("Destinazione:", rad_lay)

        self.cmb_groups = QComboBox()
        available_groups = set()
        if hasattr(self.doc, "groups"):
            available_groups.update(self.doc.groups.list_names())
        for m in self.doc.mesh_models.values():
            for (dim, pt), pname in getattr(m, "physicals", {}).items():
                if pname:
                    available_groups.add(pname)
        for gname in sorted(available_groups):
            self.cmb_groups.addItem(gname)
        if self.init_group and self.init_group in available_groups:
            self.cmb_groups.setCurrentText(self.init_group)
        self.cmb_groups.currentTextChanged.connect(self._update_preview)
        form_target.addRow("Gruppo:", self.cmb_groups)

        self.txt_entities = QLineEdit(", ".join(str(i) for i in self.init_entities))
        self.txt_entities.textChanged.connect(self._update_preview)
        form_target.addRow("ID Entità:", self.txt_entities)

        lay.addWidget(box_target)

        # 2. Forze e Momenti
        box_forces = QGroupBox("Forze e Momenti Applicati")
        grid_f = QGridLayout(box_forces)

        self.spn_fx = QDoubleSpinBox()
        self.spn_fy = QDoubleSpinBox()
        self.spn_fz = QDoubleSpinBox()
        self.spn_mx = QDoubleSpinBox()
        self.spn_my = QDoubleSpinBox()
        self.spn_mz = QDoubleSpinBox()

        for spn in (self.spn_fx, self.spn_fy, self.spn_fz, self.spn_mx, self.spn_my, self.spn_mz):
            spn.setRange(-1e12, 1e12)
            spn.setDecimals(4)
            spn.valueChanged.connect(self._update_preview)

        self.spn_fz.setValue(-100.0)  # default carico verso il basso

        grid_f.addWidget(QLabel("Fx:"), 0, 0)
        grid_f.addWidget(self.spn_fx, 0, 1)
        grid_f.addWidget(QLabel("Fy:"), 0, 2)
        grid_f.addWidget(self.spn_fy, 0, 3)
        grid_f.addWidget(QLabel("Fz:"), 0, 4)
        grid_f.addWidget(self.spn_fz, 0, 5)

        grid_f.addWidget(QLabel("Mx:"), 1, 0)
        grid_f.addWidget(self.spn_mx, 1, 1)
        grid_f.addWidget(QLabel("My:"), 1, 2)
        grid_f.addWidget(self.spn_my, 1, 3)
        grid_f.addWidget(QLabel("Mz:"), 1, 4)
        grid_f.addWidget(self.spn_mz, 1, 5)

        lay.addWidget(box_forces)

        # 3. Tipo Ripartizione e TimeSeries
        box_opt = QGroupBox("Distribuzione e Legge Temporale (timeSeries)")
        form_opt = QFormLayout(box_opt)

        self.cmb_dist = QComboBox()
        self.cmb_dist.addItem("Carico TOTALE ripartito uniformemente sui nodi", "total")
        self.cmb_dist.addItem("Carico PUNTUALE applicato a ciascun nodo", "per_node")
        self.cmb_dist.currentIndexChanged.connect(self._update_preview)
        form_opt.addRow("Distribuzione:", self.cmb_dist)

        self.cmb_ts = QComboBox()
        if hasattr(self.doc, "opensees"):
            for tag, ts in sorted(self.doc.opensees.time_series.items()):
                self.cmb_ts.addItem(f"Tag {tag}: {ts.name} ({ts.stype})", tag)
        form_opt.addRow("Legge nel tempo:", self.cmb_ts)

        self.spn_pattern = QSpinBox()
        self.spn_pattern.setRange(1, 1000)
        self.spn_pattern.setValue(1)
        form_opt.addRow("Pattern Tag:", self.spn_pattern)

        lay.addWidget(box_opt)

        # 4. Anteprima
        box_prev = QGroupBox("Anteprima Carico")
        prev_lay = QVBoxLayout(box_prev)
        self.lbl_prev_info = QLabel("Nodi coinvolti: ...")
        self.lbl_prev_info.setStyleSheet("color:#A3BE8C; font-weight:bold;")
        self.txt_prev = QTextEdit()
        self.txt_prev.setReadOnly(True)
        self.txt_prev.setMaximumHeight(80)
        self.txt_prev.setStyleSheet("background:#2E3440; color:#D8DEE9; font-family:Monospace; font-size:11px;")
        prev_lay.addWidget(self.lbl_prev_info)
        prev_lay.addWidget(self.txt_prev)
        lay.addWidget(box_prev)

        # 5. Pulsanti
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply_and_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._on_target_mode_changed()

    def _on_target_mode_changed(self):
        is_group = self.rad_group.isChecked()
        self.cmb_groups.setEnabled(is_group)
        self.txt_entities.setEnabled(not is_group)
        self._update_preview()

    def _get_target_nodes(self) -> List[int]:
        if not hasattr(self.doc, "opensees"):
            return []
        nodes: Set[int] = set()
        if self.rad_group.isChecked():
            gname = self.cmb_groups.currentText()
            if gname:
                nodes.update(self.doc.opensees.resolve_group_nodes(gname))
        else:
            for part in self.txt_entities.text().replace(";", ",").split(","):
                part = part.strip()
                if part.isdigit():
                    nodes.update(self.doc.opensees.resolve_entity_nodes(int(part)))
        return sorted(list(nodes))

    def _update_preview(self):
        nodes = self._get_target_nodes()
        n_cnt = len(nodes)
        dist_mode = self.cmb_dist.currentData()

        fx, fy, fz = self.spn_fx.value(), self.spn_fy.value(), self.spn_fz.value()
        if dist_mode == "total" and n_cnt > 0:
            fx_i, fy_i, fz_i = fx / n_cnt, fy / n_cnt, fz / n_cnt
            info = f"Nodi: {n_cnt} | Quota per singolo nodo: Fx={fx_i:.4g}, Fy={fy_i:.4g}, Fz={fz_i:.4g}"
        else:
            fx_i, fy_i, fz_i = fx, fy, fz
            info = f"Nodi: {n_cnt} | Carico su ogni nodo: Fx={fx_i:.4g}, Fy={fy_i:.4g}, Fz={fz_i:.4g}"

        self.lbl_prev_info.setText(info)
        if nodes:
            sample = f"load {nodes[0]} {fx_i:.6g} {fy_i:.6g} {fz_i:.6g};"
            tcl = f"# Sintassi OpenSees all'interno del pattern Plain:\n{sample}\n# (...applicato a tutti i {n_cnt} nodi del bersaglio)"
        else:
            tcl = f"load $node {fx_i:.6g} {fy_i:.6g} {fz_i:.6g};"
        self.txt_prev.setPlainText(tcl)

    def _apply_and_accept(self):
        name = self.txt_name.text().strip() or "Carico"
        group_names = [self.cmb_groups.currentText()] if self.rad_group.isChecked() and self.cmb_groups.currentText() else []
        entity_ids = []
        if self.rad_ent.isChecked():
            for p in self.txt_entities.text().replace(";", ",").split(","):
                if p.strip().isdigit():
                    entity_ids.append(int(p.strip()))

        if not group_names and not entity_ids:
            QMessageBox.warning(self, "Attenzione", "Specificare almeno un gruppo o un'entità bersaglio.")
            return

        ts_tag = self.cmb_ts.currentData() or 1
        ld = self.doc.opensees.add_load(
            name=name,
            entity_ids=entity_ids,
            fx=self.spn_fx.value(),
            fy=self.spn_fy.value(),
            fz=self.spn_fz.value(),
            mx=self.spn_mx.value(),
            my=self.spn_my.value(),
            mz=self.spn_mz.value(),
            load_type=self.cmb_dist.currentData(),
            time_series_tag=ts_tag,
            pattern_tag=self.spn_pattern.value(),
            group_names=group_names
        )
        self.doc.notify("opensees_condition_added", {"type": "load", "lid": ld.lid})
        self.accept()


# =============================================================================
# Dialogo EqualDOF OpenSees (multi-point constraint)
# =============================================================================

class OpenSeesEqualDOFDialog(QDialog):
    """Dialogo per definire multi-point constraints equalDOF tra entità o gruppi."""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle("Vincolo EqualDOF OpenSees (equalDOF)")
        self.setMinimumWidth(500)
        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        form_top = QFormLayout()
        self.txt_name = QLineEdit("EqualDOF_1")
        form_top.addRow("Nome vincolo:", self.txt_name)
        lay.addLayout(form_top)

        # Selezione Master e Slave
        grid_sel = QGridLayout()

        # Master
        box_m = QGroupBox("Nodo/Entità/Gruppo MASTER")
        lay_m = QVBoxLayout(box_m)
        self.rad_m_grp = QRadioButton("Da Gruppo")
        self.rad_m_ent = QRadioButton("Da Entità (ID)")
        self.rad_m_grp.setChecked(True)
        self.cmb_m_grp = QComboBox()
        self.txt_m_ent = QLineEdit()
        self.txt_m_ent.setPlaceholderText("Es. 1")
        lay_m.addWidget(self.rad_m_grp)
        lay_m.addWidget(self.cmb_m_grp)
        lay_m.addWidget(self.rad_m_ent)
        lay_m.addWidget(self.txt_m_ent)
        grid_sel.addWidget(box_m, 0, 0)

        # Slave
        box_s = QGroupBox("Nodo/Entità/Gruppo SLAVE")
        lay_s = QVBoxLayout(box_s)
        self.rad_s_grp = QRadioButton("Da Gruppo")
        self.rad_s_ent = QRadioButton("Da Entità (ID)")
        self.rad_s_grp.setChecked(True)
        self.cmb_s_grp = QComboBox()
        self.txt_s_ent = QLineEdit()
        self.txt_s_ent.setPlaceholderText("Es. 2")
        lay_s.addWidget(self.rad_s_grp)
        lay_s.addWidget(self.cmb_s_grp)
        lay_s.addWidget(self.rad_s_ent)
        lay_s.addWidget(self.txt_s_ent)
        grid_sel.addWidget(box_s, 0, 1)

        lay.addLayout(grid_sel)

        # Popola combo gruppi
        available_groups = set()
        if hasattr(self.doc, "groups"):
            available_groups.update(self.doc.groups.list_names())
        for m in self.doc.mesh_models.values():
            for (dim, pt), pname in getattr(m, "physicals", {}).items():
                if pname:
                    available_groups.add(pname)
        for g in sorted(available_groups):
            self.cmb_m_grp.addItem(g)
            self.cmb_s_grp.addItem(g)

        # DOFs da accoppiare
        box_dofs = QGroupBox("Gradi di Libertà Accoppiati (equalDOF)")
        lay_dofs = QHBoxLayout(box_dofs)
        self.chk_1 = QCheckBox("1: Ux")
        self.chk_2 = QCheckBox("2: Uy")
        self.chk_3 = QCheckBox("3: Uz")
        self.chk_4 = QCheckBox("4: Rx")
        self.chk_5 = QCheckBox("5: Ry")
        self.chk_6 = QCheckBox("6: Rz")
        self.chk_1.setChecked(True)
        self.chk_2.setChecked(True)
        self.chk_3.setChecked(True)
        for chk in (self.chk_1, self.chk_2, self.chk_3, self.chk_4, self.chk_5, self.chk_6):
            lay_dofs.addWidget(chk)
            chk.toggled.connect(self._update_preview)
        lay.addWidget(box_dofs)

        # Modalità accoppiamento
        box_mode = QGroupBox("Modalità di Associazione Nodi")
        lay_mode = QVBoxLayout(box_mode)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("Accoppiamento spaziale automatico (spatial_match per vicinanza)", "spatial_match")
        self.cmb_mode.addItem("Master singolo vincola tutti i nodi slave (master_to_all)", "master_to_all")
        self.cmb_mode.currentIndexChanged.connect(self._update_preview)
        lay_mode.addWidget(self.cmb_mode)
        lay.addWidget(box_mode)

        # Anteprima
        box_prev = QGroupBox("Anteprima Coppie e Sintassi")
        lay_prev = QVBoxLayout(box_prev)
        self.lbl_pairs = QLabel("Calcolo coppie nodi...")
        self.lbl_pairs.setStyleSheet("color:#A3BE8C; font-weight:bold;")
        self.txt_prev = QTextEdit()
        self.txt_prev.setReadOnly(True)
        self.txt_prev.setMaximumHeight(75)
        self.txt_prev.setStyleSheet("background:#2E3440; color:#D8DEE9; font-family:Monospace; font-size:11px;")
        lay_prev.addWidget(self.lbl_pairs)
        lay_prev.addWidget(self.txt_prev)
        lay.addWidget(box_prev)

        # Segnali
        self.rad_m_grp.toggled.connect(self._update_preview)
        self.rad_s_grp.toggled.connect(self._update_preview)
        self.cmb_m_grp.currentIndexChanged.connect(self._update_preview)
        self.cmb_s_grp.currentIndexChanged.connect(self._update_preview)
        self.txt_m_ent.textChanged.connect(self._update_preview)
        self.txt_s_ent.textChanged.connect(self._update_preview)

        # Pulsanti
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply_and_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _get_master_slave_nodes(self):
        m_nodes = []
        s_nodes = []
        if not hasattr(self.doc, "opensees"):
            return m_nodes, s_nodes

        # Master
        if self.rad_m_grp.isChecked():
            mg = self.cmb_m_grp.currentText()
            if mg:
                m_nodes = self.doc.opensees.resolve_group_nodes(mg)
        else:
            txt = self.txt_m_ent.text().strip()
            if txt.isdigit():
                m_nodes = self.doc.opensees.resolve_entity_nodes(int(txt))

        # Slave
        if self.rad_s_grp.isChecked():
            sg = self.cmb_s_grp.currentText()
            if sg:
                s_nodes = self.doc.opensees.resolve_group_nodes(sg)
        else:
            txt = self.txt_s_ent.text().strip()
            if txt.isdigit():
                s_nodes = self.doc.opensees.resolve_entity_nodes(int(txt))

        return m_nodes, s_nodes

    def _update_preview(self):
        m_nodes, s_nodes = self._get_master_slave_nodes()
        model = list(self.doc.mesh_models.values())[-1] if self.doc.mesh_models else None
        pairing_mode = self.cmb_mode.currentData()
        pairs = []
        if hasattr(self.doc, "opensees") and model:
            pairs = self.doc.opensees.match_equaldof_nodes(m_nodes, s_nodes, model.nodes, pairing_mode)

        dofs = []
        if self.chk_1.isChecked(): dofs.append(1)
        if self.chk_2.isChecked(): dofs.append(2)
        if self.chk_3.isChecked(): dofs.append(3)
        if self.chk_4.isChecked(): dofs.append(4)
        if self.chk_5.isChecked(): dofs.append(5)
        if self.chk_6.isChecked(): dofs.append(6)
        dof_str = " ".join(str(d) for d in dofs)

        self.lbl_pairs.setText(f"Nodi Master: {len(m_nodes)} | Nodi Slave: {len(s_nodes)} | Coppie equalDOF: {len(pairs)}")
        if pairs:
            m0, s0 = pairs[0]
            self.txt_prev.setPlainText(f"equalDOF {m0} {s0} {dof_str};\n# (...generate {len(pairs)} coppie equalDOF)")
        else:
            self.txt_prev.setPlainText(f"# Sintassi OpenSees: equalDOF $masterNode $slaveNode {dof_str};")

    def _apply_and_accept(self):
        name = self.txt_name.text().strip() or "EqualDOF"
        m_grp = self.cmb_m_grp.currentText() if self.rad_m_grp.isChecked() else None
        m_ent = int(self.txt_m_ent.text().strip()) if (self.rad_m_ent.isChecked() and self.txt_m_ent.text().strip().isdigit()) else None

        s_grp = self.cmb_s_grp.currentText() if self.rad_s_grp.isChecked() else None
        s_ent = int(self.txt_s_ent.text().strip()) if (self.rad_s_ent.isChecked() and self.txt_s_ent.text().strip().isdigit()) else None

        dofs = []
        if self.chk_1.isChecked(): dofs.append(1)
        if self.chk_2.isChecked(): dofs.append(2)
        if self.chk_3.isChecked(): dofs.append(3)
        if self.chk_4.isChecked(): dofs.append(4)
        if self.chk_5.isChecked(): dofs.append(5)
        if self.chk_6.isChecked(): dofs.append(6)

        eq = self.doc.opensees.add_equaldof(
            name=name,
            master_entity_id=m_ent,
            slave_entity_id=s_ent,
            dofs=dofs,
            pairing_mode=self.cmb_mode.currentData(),
            master_group=m_grp,
            slave_group=s_grp
        )
        self.doc.notify("opensees_condition_added", {"type": "equaldof", "eid": eq.eid})
        self.accept()


# =============================================================================
# Dialogo Risolutore OpenSees e Fasi di Calcolo (Gravity / Elastoplastica)
# =============================================================================

class OpenSeesAnalysisDialog(QDialog):
    """Configurazione avanzata del solutore e delle fasi di calcolo sequenziali per OpenSees.

    Supporta le fasi di calcolo:
      1. Gravity Loading (fase elastica preliminare)
      2. Transizione allo stato plastico tramite updateMaterialStage (wiki OpenSees)
      3. Personalizzazione completa di constraints, numberer, system, test, algorithm, integrator.
    """

    def __init__(self, doc, model=None, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.model = model
        if self.model is None and getattr(doc, "mesh_models", None):
            self.model = list(doc.mesh_models.values())[-1]

        self.setWindowTitle("Configurazione Solutore OpenSees e Fasi di Calcolo")
        self.setMinimumWidth(580)
        self.setMinimumHeight(520)
        self._build_ui()
        self._refresh_tcl_preview()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        self.tabs = QTabWidget()

        # Tab 1: Fasi di Calcolo (Multi-stage)
        tab_stages = QWidget()
        lay_stg = QVBoxLayout(tab_stages)

        self.chk_multi = QCheckBox("Abilita Analisi Sequenziale a Due Fasi (Gravity Loading → Fase Elastoplastica)")
        self.chk_multi.setChecked(getattr(self.doc.opensees, "multi_stage", True))
        self.chk_multi.setStyleSheet("font-weight:bold; font-size:12px; color:#88C0D0;")
        self.chk_multi.toggled.connect(self._on_multi_toggled)
        lay_stg.addWidget(self.chk_multi)

        # Fase 1: Gravity
        self.box_g = QGroupBox("FASE 1: Gravity Loading (Stato Elastico)")
        form_g = QFormLayout(self.box_g)
        self.txt_g_name = QLineEdit("Gravity Loading (Stato Elastico)")
        self.chk_g_stage = QCheckBox("Aggiorna stage materiale a 0 (updateMaterialStage -material 1 -stage 0)")
        self.chk_g_stage.setChecked(True)
        self.spn_g_steps = QSpinBox()
        self.spn_g_steps.setRange(1, 1000)
        self.spn_g_steps.setValue(10)
        self.chk_g_const = QCheckBox("Esegui 'loadConst -time 0.0' al termine della gravità (fissa il carico costante)")
        self.chk_g_const.setChecked(True)

        form_g.addRow("Nome fase 1:", self.txt_g_name)
        form_g.addRow("Comando Wiki OpenSees:", self.chk_g_stage)
        form_g.addRow("Numero step gravità:", self.spn_g_steps)
        form_g.addRow("Mantenimento carico:", self.chk_g_const)
        lay_stg.addWidget(self.box_g)

        # Fase 2: Elastoplastica
        self.box_ep = QGroupBox("FASE 2: Fase Elastoplastica (Plastic Stage)")
        form_ep = QFormLayout(self.box_ep)
        self.txt_ep_name = QLineEdit("Fase Elastoplastica (Plastic Stage)")
        self.chk_ep_stage = QCheckBox("Aggiorna stage materiale a 1 (updateMaterialStage -material 1 -stage 1)")
        self.chk_ep_stage.setChecked(True)
        self.spn_ep_steps = QSpinBox()
        self.spn_ep_steps.setRange(1, 1000)
        self.spn_ep_steps.setValue(20)

        form_ep.addRow("Nome fase 2:", self.txt_ep_name)
        form_ep.addRow("Comando Wiki OpenSees:", self.chk_ep_stage)
        form_ep.addRow("Numero step elastoplastici:", self.spn_ep_steps)
        lay_stg.addWidget(self.box_ep)

        self.tabs.addTab(tab_stages, "Fasi di Calcolo")

        # Tab 2: Parametri Solutore (Resolver Settings)
        tab_solver = QWidget()
        lay_sol = QFormLayout(tab_solver)

        self.cmb_constraints = QComboBox()
        self.cmb_constraints.addItems(["Transformation", "Plain", "Penalty 1.0e12 1.0e12", "Lagrange"])
        lay_sol.addRow("Constraints Handler:", self.cmb_constraints)

        self.cmb_numberer = QComboBox()
        self.cmb_numberer.addItems(["RCM", "Plain", "AMD"])
        lay_sol.addRow("Numberer (ordinamento nodi):", self.cmb_numberer)

        self.cmb_system = QComboBox()
        self.cmb_system.addItems(["BandGeneral", "BandSPD", "ProfileSPD", "UmfPack", "FullGeneral", "SparseSYM"])
        lay_sol.addRow("System (risolutore equazioni):", self.cmb_system)

        self.cmb_test = QComboBox()
        self.cmb_test.addItems(["NormDispIncr", "NormUnbalance", "EnergyIncr", "RelativeNormDispIncr"])
        lay_sol.addRow("Test di convergenza:", self.cmb_test)

        self.spn_tol = QDoubleSpinBox()
        self.spn_tol.setDecimals(8)
        self.spn_tol.setRange(1e-12, 1.0)
        self.spn_tol.setValue(1e-6)
        lay_sol.addRow("Tolleranza convergenza:", self.spn_tol)

        self.spn_iter = QSpinBox()
        self.spn_iter.setRange(1, 500)
        self.spn_iter.setValue(25)
        lay_sol.addRow("Iterazioni massime test:", self.spn_iter)

        self.cmb_algo = QComboBox()
        self.cmb_algo.addItems(["Newton", "ModifiedNewton", "NewtonLineSearch", "KrylovNewton", "BFGS", "Broyden"])
        lay_sol.addRow("Algoritmo non-lineare:", self.cmb_algo)

        self.cmb_integrator = QComboBox()
        self.cmb_integrator.addItems(["LoadControl", "DisplacementControl", "Newmark"])
        lay_sol.addRow("Integratore:", self.cmb_integrator)

        self.spn_step_val = QDoubleSpinBox()
        self.spn_step_val.setDecimals(4)
        self.spn_step_val.setRange(0.0001, 1000.0)
        self.spn_step_val.setValue(0.1)
        lay_sol.addRow("Passo di integrazione (dLambda / dt):", self.spn_step_val)

        self.cmb_analysis = QComboBox()
        self.cmb_analysis.addItems(["Static", "Transient"])
        lay_sol.addRow("Tipo di analisi:", self.cmb_analysis)

        self.tabs.addTab(tab_solver, "Parametri Solutore")

        # Tab 3: Anteprima Script TCL
        tab_tcl = QWidget()
        lay_tcl = QVBoxLayout(tab_tcl)
        self.txt_tcl = QTextEdit()
        self.txt_tcl.setReadOnly(True)
        self.txt_tcl.setFontFamily("Monospace")
        self.txt_tcl.setStyleSheet("background:#282C34; color:#ABB2BF; font-size:11px;")
        lay_tcl.addWidget(self.txt_tcl)

        btn_tcl_row = QHBoxLayout()
        btn_refresh = QPushButton("Aggiorna Anteprima")
        btn_copy = QPushButton("Copia Script TCL")
        btn_save = QPushButton("Esporta Script .tcl…")
        btn_refresh.clicked.connect(self._refresh_tcl_preview)
        btn_copy.clicked.connect(self._copy_tcl)
        btn_save.clicked.connect(self._save_tcl)
        btn_tcl_row.addWidget(btn_refresh)
        btn_tcl_row.addWidget(btn_copy)
        btn_tcl_row.addWidget(btn_save)
        lay_tcl.addLayout(btn_tcl_row)

        self.tabs.addTab(tab_tcl, "Anteprima TCL Completa")

        lay.addWidget(self.tabs)

        # Pulsanti OK / Cancel
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply_and_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        # Connessione per auto-refresh preview al cambio tab
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_multi_toggled(self, checked):
        self.box_g.setEnabled(checked)
        self.box_ep.setEnabled(checked)
        self._refresh_tcl_preview()

    def _on_tab_changed(self, idx):
        if idx == 2:
            self._refresh_tcl_preview()

    def _refresh_tcl_preview(self):
        if not hasattr(self.doc, "opensees"):
            return
        # Applica temporaneamente i parametri per generare l'anteprima
        self._sync_to_manager()
        tcl = self.doc.opensees.generate_tcl_script(self.model)
        self.txt_tcl.setPlainText(tcl)

    def _copy_tcl(self):
        from PySide6.QtGui import QGuiApplication
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self.txt_tcl.toPlainText())
            QMessageBox.information(self, "Copia", "Script OpenSees TCL copiato negli appunti!")

    def _save_tcl(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva Script OpenSees", "modello_opensees.tcl", "TCL Scripts (*.tcl);;Tutti i file (*.*)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt_tcl.toPlainText())
            QMessageBox.information(self, "Esportazione Script", f"Script salvato con successo:\n{path}")

    def _sync_to_manager(self):
        from ..core.opensees_conditions import SolverSettings, AnalysisStage
        mgr = self.doc.opensees
        mgr.multi_stage = self.chk_multi.isChecked()

        # Solutore globale / default
        mgr.default_solver = SolverSettings(
            constraints=self.cmb_constraints.currentText(),
            numberer=self.cmb_numberer.currentText(),
            system=self.cmb_system.currentText(),
            test_type=self.cmb_test.currentText(),
            test_tol=self.spn_tol.value(),
            test_iter=self.spn_iter.value(),
            algorithm=self.cmb_algo.currentText(),
            integrator_type=self.cmb_integrator.currentText(),
            integrator_step=self.spn_step_val.value(),
            analysis_type=self.cmb_analysis.currentText(),
            n_steps=10
        )

        # Fasi di calcolo
        stg1 = AnalysisStage(
            stage_id=1,
            name=self.txt_g_name.text().strip() or "Gravity Loading",
            stage_type="gravity",
            material_stage=0,
            mat_tag=1,
            update_stage_cmd=self.chk_g_stage.isChecked(),
            load_const=self.chk_g_const.isChecked(),
            solver=SolverSettings(
                constraints=self.cmb_constraints.currentText(),
                numberer=self.cmb_numberer.currentText(),
                system=self.cmb_system.currentText(),
                test_type=self.cmb_test.currentText(),
                test_tol=self.spn_tol.value(),
                test_iter=self.spn_iter.value(),
                algorithm=self.cmb_algo.currentText(),
                integrator_type="LoadControl",
                integrator_step=1.0 / max(1, self.spn_g_steps.value()),
                analysis_type="Static",
                n_steps=self.spn_g_steps.value()
            )
        )

        stg2 = AnalysisStage(
            stage_id=2,
            name=self.txt_ep_name.text().strip() or "Fase Elastoplastica",
            stage_type="elastoplastic",
            material_stage=1,
            mat_tag=1,
            update_stage_cmd=self.chk_ep_stage.isChecked(),
            load_const=False,
            solver=SolverSettings(
                constraints=self.cmb_constraints.currentText(),
                numberer=self.cmb_numberer.currentText(),
                system=self.cmb_system.currentText(),
                test_type=self.cmb_test.currentText(),
                test_tol=self.spn_tol.value(),
                test_iter=self.spn_iter.value() + 10,
                algorithm=self.cmb_algo.currentText(),
                integrator_type="LoadControl",
                integrator_step=1.0 / max(1, self.spn_ep_steps.value()),
                analysis_type="Static",
                n_steps=self.spn_ep_steps.value()
            )
        )

        mgr.stages = [stg1, stg2]

    def _apply_and_accept(self):
        self._sync_to_manager()
        self.doc.notify("opensees_solver_changed", {})
        self.accept()


# =============================================================================
# Dialogo Esportazione OpenSees
# =============================================================================

class OpenSeesExportDialog(QDialog):
    """Dialogo per l'esportazione di nodi per gruppi e connectivity list per OpenSees."""

    def __init__(self, doc, model=None, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.model = model
        if self.model is None and getattr(doc, "mesh_models", None):
            self.model = list(doc.mesh_models.values())[-1]

        from ..core import opensees_export as ose
        self.groups_data = ose.extract_defined_groups_nodes(doc, self.model) if self.model else {}
        self.coherence = ose.verify_mesh_coherence(self.model) if self.model else None

        self.setWindowTitle("Esportazione per OpenSees — Nodi e Connettività")
        self.setMinimumWidth(500)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        # 1. Box Informazioni e Coerenza mesh
        if self.coherence:
            badge_text = (
                f"<b>Modello Mesh:</b> {self.model.name}<br>"
                f"• Elementi totali: <b>{self.coherence['total_elements']}</b> | "
                f"Nodi utilizzati: <b>{self.coherence['referenced_nodes_count']}</b><br>"
                f"• Stato topologico: <span style='color:green;'><b>{'✓ VALIDO (Nodi coerenti con elementi)' if self.coherence['valid'] else '⚠ Attenzione nodi mancanti'}</b></span><br>"
                f"• Elementi riorientati secondo regole OpenSees (2D CCW / 3D V>0): <b>{self.coherence['reoriented_count']}</b>"
            )
            lbl_badge = QLabel(badge_text)
            lbl_badge.setStyleSheet("background:#282C34; color:#ABB2BF; border-radius:4px; padding:8px;")
            lay.addWidget(lbl_badge)

        # 2. Selezione Gruppi da esportare
        grp_box = QGroupBox("Gruppi definiti per l'estrazione nodi (.txt)")
        grp_lay = QVBoxLayout(grp_box)
        self.list_groups = QListWidget()
        for gname, data in sorted(self.groups_data.items()):
            n_cnt = len(data["node_ids"])
            item = QListWidgetItem(f"{gname} ({n_cnt} nodi) — [{data['source']}]")
            item.setData(Qt.UserRole, gname)
            item.setCheckState(Qt.Checked)
            self.list_groups.addItem(item)
        grp_lay.addWidget(self.list_groups)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("Seleziona tutti")
        btn_none = QPushButton("Deseleziona tutti")
        btn_all.clicked.connect(lambda: self._set_all_checks(Qt.Checked))
        btn_none.clicked.connect(lambda: self._set_all_checks(Qt.Unchecked))
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        grp_lay.addLayout(btn_row)
        lay.addWidget(grp_box)

        # 3. Opzioni di esportazione
        opt_box = QGroupBox("Opzioni file")
        opt_lay = QVBoxLayout(opt_box)
        self.chk_conn = QCheckBox("Esporta connectivity list con nodi ordinati per OpenSees (connectivity_list.txt)")
        self.chk_conn.setChecked(True)
        self.chk_nodes = QCheckBox("Esporta file .txt nodi per i gruppi selezionati")
        self.chk_nodes.setChecked(True)
        self.chk_single = QCheckBox("Crea anche file singoli per ciascun gruppo (cartella 'nodi_per_gruppo/')")
        self.chk_single.setChecked(True)
        self.chk_tcl = QCheckBox("Genera script OpenSees eseguibile (.tcl)")
        self.chk_tcl.setChecked(True)

        opt_lay.addWidget(self.chk_conn)
        opt_lay.addWidget(self.chk_nodes)
        opt_lay.addWidget(self.chk_single)
        opt_lay.addWidget(self.chk_tcl)

        btn_cfg_sol = QPushButton("Configura Solutore e Fasi di calcolo (Gravity / Elastoplastica)…")
        btn_cfg_sol.clicked.connect(self._open_solver_config)
        opt_lay.addWidget(btn_cfg_sol)

        lay.addWidget(opt_box)

        # 4. Cartella di output
        dest_box = QGroupBox("Cartella di destinazione")
        dest_lay = QHBoxLayout(dest_box)
        default_dir = os.path.join(os.getcwd(), "output", "opensees")
        self.txt_dir = QLineEdit(default_dir)
        btn_browse = QPushButton("Sfoglia…")
        btn_browse.clicked.connect(self._browse_dir)
        dest_lay.addWidget(self.txt_dir)
        dest_lay.addWidget(btn_browse)
        lay.addWidget(dest_box)

        # 5. Pulsanti standard
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Esporta")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _open_solver_config(self):
        dlg = OpenSeesAnalysisDialog(self.doc, self.model, parent=self)
        dlg.exec()

    def _set_all_checks(self, state):
        for i in range(self.list_groups.count()):
            self.list_groups.item(i).setCheckState(state)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella di destinazione", self.txt_dir.text())
        if d:
            self.txt_dir.setText(d)

    def values(self) -> dict:
        selected = []
        for i in range(self.list_groups.count()):
            item = self.list_groups.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return {
            "output_dir": self.txt_dir.text().strip(),
            "selected_groups": selected,
            "export_connectivity": self.chk_conn.isChecked(),
            "export_nodes": self.chk_nodes.isChecked(),
            "separate_files": self.chk_single.isChecked(),
            "generate_tcl": self.chk_tcl.isChecked(),
        }
