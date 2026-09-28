"""Pannelli dock della GUI: albero entità, proprietà, console, log, macro."""

from __future__ import annotations

import code
import sys
from typing import List, Optional

from PySide6.QtCore import Qt
from gcs.core.selection_manager import SelectionManager
from gcs.core.visibility_manager import VisibilityManager
from PySide6.QtGui import QFont, QColor, QBrush
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTreeWidget, QTreeWidgetItem, QTableWidget,
                               QTableWidgetItem, QTextEdit, QLineEdit,
                               QPushButton, QListWidget, QListWidgetItem,
                               QHeaderView, QAbstractItemView, QMenu, QInputDialog, QMessageBox)

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

    def __init__(self, doc: CADDocument, viewer,
                 selection_manager: Optional[SelectionManager] = None,
                 visibility_manager: Optional[VisibilityManager] = None,
                 parent=None):
        super().__init__(parent)
        self.doc = doc
        self.viewer = viewer
        self.selection_manager = selection_manager or SelectionManager(doc)
        self.visibility_manager = visibility_manager or VisibilityManager(doc, viewer)
        self._updating = False
        self._entity_items = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(QLabel("Gruppi ed entità"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Visibilità / Entità", "Tipo", "Id", "FEM"])
        self.tree.setColumnWidth(0, 230)
        self.tree.headerItem().setToolTip(0, "Checkbox = visibilità CAD/OpenCascade; doppio click = selezione")
        self.tree.setColumnWidth(1, 95)
        self.tree.setColumnWidth(2, 70)
        self.tree.setColumnWidth(3, 95)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._on_double)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.tree.itemChanged.connect(self._on_check)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu_contesto)
        lay.addWidget(self.tree, 3)

        self.fem_details = QTextEdit()
        self.fem_details.setReadOnly(True)
        self.fem_details.setPlaceholderText("Seleziona un'entità o un ramo FEM per vedere proprietà e Tcl associato.")
        self.fem_details.setFontFamily("Monospace")
        self.fem_details.setMaximumHeight(260)
        lay.addWidget(QLabel("Dettaglio FEM / Tcl"))
        lay.addWidget(self.fem_details, 1)

    # -------------------------------------------------------------- refresh
    def refresh(self):
        if self._updating:
            return
        self._updating = True
        self._entity_items = {}
        try:
            self.tree.blockSignals(True)
            self.tree.clear()
            children = {}
            for entity in self.doc.entities.values():
                parent_id = entity.meta.get("parent")
                if parent_id is not None and int(parent_id) in self.doc.entities:
                    children.setdefault(int(parent_id), []).append(entity)

            def build_entity_item(entity, include_fem=True):
                item = self._entity_item(entity)
                self._entity_items[int(entity.id)] = item
                if include_fem:
                    self._populate_entity_fem(item, entity)
                for child in sorted(children.get(int(entity.id), []), key=lambda x: x.id):
                    item.addChild(build_entity_item(child, include_fem=False))
                return item

            grouped = set()
            for nome, g in self.doc.groups.groups.items():
                it = QTreeWidgetItem([nome, "Gruppo", "", ""])
                it.setData(0, Qt.UserRole + 1, nome)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                members = [self.doc.entities[eid] for eid in sorted(g.member_ids)
                           if eid in self.doc.entities]
                it.setCheckState(0, Qt.Checked if members and all(e.visible for e in members)
                                 else Qt.Unchecked)
                it.setForeground(0, QBrush(QColor("#D08770")))
                member_ids = {int(entity.id) for entity in members}
                for entity in members:
                    grouped.add(entity.id)
                    parent_id = entity.meta.get("parent")
                    if parent_id is not None and int(parent_id) in member_ids:
                        continue
                    it.addChild(build_entity_item(entity))
                for mname, els in g.mesh_elements.items():
                    figlio = QTreeWidgetItem([f"{mname}: {len(els)} elementi", "Mesh", "", ""])
                    figlio.setData(0, Qt.UserRole + 2, mname)
                    figlio.setData(0, Qt.UserRole + 3, sorted(int(e) for e in els))
                    figlio.setToolTip(0, "Doppio click: seleziona gli elementi mesh e i relativi blocchi")
                    figlio.setForeground(0, QBrush(QColor("#81A1C1")))
                    it.addChild(figlio)
                for mname, nodi in g.mesh_nodes.items():
                    figlio = QTreeWidgetItem([f"{mname}: {len(nodi)} nodi", "Mesh", "", ""])
                    figlio.setData(0, Qt.UserRole + 2, mname)
                    figlio.setData(0, Qt.UserRole + 4, sorted(int(n) for n in nodi))
                    figlio.setToolTip(0, "Doppio click: seleziona i nodi mesh e i blocchi associati")
                    figlio.setForeground(0, QBrush(QColor("#81A1C1")))
                    it.addChild(figlio)
                self.tree.addTopLevelItem(it)

            for entity in sorted(self.doc.entities.values(), key=lambda x: x.id):
                if entity.id in grouped or entity.meta.get("parent") is not None:
                    continue
                self.tree.addTopLevelItem(build_entity_item(entity))

            self.tree.expandToDepth(2)
            self._sync_tree_selection()
        finally:
            self.tree.blockSignals(False)
            self._updating = False

    def _sync_tree_selection(self):
        """Allinea la selezione Qt al Document Entity ID."""
        self.tree.blockSignals(True)
        try:
            selected = {int(i) for i in self.doc.selection}
            first = None
            for eid, item in self._entity_items.items():
                item.setSelected(eid in selected)
                if eid in selected and first is None:
                    first = item
                    parent = item.parent()
                    while parent is not None:
                        parent.setExpanded(True)
                        parent = parent.parent()
            if first is not None:
                self.tree.setCurrentItem(first)
        finally:
            self.tree.blockSignals(False)

    def _on_tree_selection_changed(self):
        if self._updating:
            return
        ids = set()
        for item in self.tree.selectedItems():
            if item.data(0, Qt.UserRole + 5) != "entity":
                continue
            eid = item.data(0, Qt.UserRole)
            if eid is not None:
                ids.add(int(eid))
        if ids != set(self.doc.selection):
            self.selection_manager.set_context("cad")
            self.selection_manager.set_selection(ids)

    def _entity_item(self, e) -> QTreeWidgetItem:
        fem_marks = e.meta.get("fem_marks", [])
        suffix = f" [{', '.join(fem_marks)}]" if fem_marks else ""
        status = self._entity_fem_status(e)
        it = QTreeWidgetItem([
            e.name + suffix,
            NOME_TIPO_IT.get(e.etype, e.etype),
            str(e.id),
            status,
        ])
        it.setData(0, Qt.UserRole, e.id)
        it.setData(0, Qt.UserRole + 5, "entity")
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(0, Qt.Checked if e.visible else Qt.Unchecked)
        fem_color = e.meta.get("fem_color")
        color = QColor.fromRgbF(*fem_color) if fem_color else QColor(
            COLORE_TIPO.get(e.etype, "#CCCCCC"))
        it.setForeground(0, QBrush(color))
        it.setToolTip(0, "Checkbox = visibilità CAD/OpenCascade; doppio click = selezione. "
                         "Il ramo FEM mostra ciò che verrà scritto nel Tcl.")
        it.setToolTip(3, status)
        if fem_marks:
            it.setToolTip(0, "Associazioni FEM: " + "; ".join(fem_marks))
        return it

    def _entity_groups(self, entity_id):
        return [
            name for name, group in self.doc.groups.groups.items()
            if int(entity_id) in {int(x) for x in group.member_ids}
        ]

    def _entity_fem_status(self, entity):
        manager = getattr(self.doc, "opensees", None)
        if manager is None:
            return "CAD"
        ref = entity.meta.get("mesh_ref")
        if ref:
            model = self.doc.mesh_models.get(str(ref[0]))
            if model is not None and model.stale:
                return "⚠ STALE"
        assignments = [a for a in manager.element_assignments
                       if int(a.entity_id) == int(entity.id)]
        if ref and not assignments:
            return "⚠ FEM"
        if assignments:
            material_tags = {int(a.material_tag) for a in assignments}
            defined = {int(m.tag) for m in manager.materials}
            if not material_tags.issubset(defined):
                return "⚠ MAT"
            if any(a.is_up and not str(a.element_args).strip() for a in assignments):
                return "⚠ u-p"
            if ref:
                total = len(self._mesh_element_ids(entity))
                assigned = len({int(eid) for a in assignments for eid in a.element_ids})
                if total and assigned < total:
                    return "⚠ PART"
            return "OK"
        return "CAD"

    def _add_category(self, parent, label, kind, eid):
        item = QTreeWidgetItem([label, kind, "", ""])
        item.setData(0, Qt.UserRole, int(eid))
        item.setData(0, Qt.UserRole + 5, "category")
        parent.addChild(item)
        item.setExpanded(True)
        return item

    def _add_leaf(self, parent, label, kind, value="", eid=None,
                  extra_kind="", model_name="", element_ids=None):
        item = QTreeWidgetItem([label, kind, str(value), ""])
        if eid is not None:
            item.setData(0, Qt.UserRole, int(eid))
        if extra_kind:
            item.setData(0, Qt.UserRole + 5, extra_kind)
        if model_name:
            item.setData(0, Qt.UserRole + 6, str(model_name))
        if element_ids is not None:
            item.setData(0, Qt.UserRole + 7, [int(x) for x in element_ids])
        parent.addChild(item)
        return item

    def _populate_entity_fem(self, root, entity):
        """Costruisce la vista relazionale CAD → mesh → FEM → condizioni → fase."""
        manager = getattr(self.doc, "opensees", None)
        if manager is None:
            return

        assignments = [a for a in manager.element_assignments
                       if int(a.entity_id) == int(entity.id)]
        ref = entity.meta.get("mesh_ref")
        model = self.doc.mesh_models.get(ref[0]) if ref else None
        mesh_elements = []
        if ref and model is not None:
            block = model.blocks.get((int(ref[1]), int(ref[2])))
            if block:
                mesh_elements = sorted(int(x) for x in block.element_ids)

        if ref:
            mesh_node = self._add_category(
                root,
                f"Mesh → {ref[0]} · dim {ref[1]} · tag {ref[2]}",
                "MESH", entity.id)
            self._add_leaf(
                mesh_node, f"Elementi mesh: {len(mesh_elements)}", "Gmsh",
                f"{mesh_elements[:8]}{' …' if len(mesh_elements) > 8 else ''}",
                entity.id, "mesh", ref[0], mesh_elements)
            if model is not None:
                nodes = sorted(model.nodes_of_elements(mesh_elements)) if mesh_elements else []
                self._add_leaf(
                    mesh_node, f"Nodi mesh: {len(nodes)}", "Gmsh",
                    f"{nodes[:8]}{' …' if len(nodes) > 8 else ''}", entity.id)

        if assignments:
            fem_node = self._add_category(
                root, f"Elementi FEM ({len(assignments)} assegnazioni)", "FEM", entity.id)
            for assignment in assignments:
                cmd = assignment.effective_command()
                item = self._add_leaf(
                    fem_node, f"{cmd} · {len(assignment.element_ids)} elem.",
                    "OpenSees", assignment.material_tag, entity.id,
                    "assignment", assignment.model_name, assignment.element_ids)
                item.setToolTip(
                    0, f"Gmsh {assignment.gmsh_type} → OpenSees {cmd} | "
                        f"materiale {assignment.material_tag} | "
                        f"area={assignment.area:g} | thickness={assignment.thickness:g}")
                mat = next((m for m in manager.materials
                            if int(m.tag) == int(assignment.material_tag)), None)
                self._add_leaf(
                    item, f"Materiale {assignment.material_tag} — "
                          f"{mat.name if mat else 'NON DEFINITO'}",
                    "Materiale", mat.model if mat else "ERRORE", entity.id)
                if assignment.section_tag is not None:
                    sec = next((s for s in manager.sections
                                if int(s.tag) == int(assignment.section_tag)), None)
                    self._add_leaf(
                        item, f"Sezione {assignment.section_tag} — "
                              f"{sec.model if sec else 'NON DEFINITA'}",
                        "Section", sec.name if sec else "ERRORE", entity.id)
                if assignment.gmsh_type in (2, 3) or float(assignment.thickness) != 1.0:
                    self._add_leaf(item, f"Thickness = {assignment.thickness:g}",
                                   "Property", "", entity.id)
                if assignment.gmsh_type == 1 or float(assignment.area) != 1.0:
                    self._add_leaf(item, f"Area = {assignment.area:g}",
                                   "Property", "", entity.id)
                self._add_leaf(
                    item,
                    "u-p = YES · DOF pressione presente" if assignment.is_up else "u-p = NO",
                    "u-p", assignment.element_args if assignment.is_up else "",
                    entity.id)
                if assignment.transf_tag is not None:
                    transf = next((t for t in manager.geom_transfs
                                   if int(t.tag) == int(assignment.transf_tag)), None)
                    self._add_leaf(
                        item, f"geomTransf {assignment.transf_tag}", "geomTransf",
                        transf.transf_type if transf else "NON DEFINITA", entity.id)
                if assignment.integration_tag is not None:
                    integ = next((b for b in manager.beam_integrations
                                  if int(b.tag) == int(assignment.integration_tag)), None)
                    self._add_leaf(
                        item, f"beamIntegration {assignment.integration_tag}", "Integration",
                        integ.integration_type if integ else "NON DEFINITA", entity.id)
                self._add_phase_nodes(item, [assignment.material_tag], entity.id)

        groups = set(self._entity_groups(entity.id))
        constraint_items = []
        for cons in manager.constraints:
            if entity.id in cons.entity_ids or groups.intersection(str(x) for x in cons.group_names):
                constraint_items.append((
                    f"FIX {cons.cid} · {cons.name}",
                    f"DOF {cons.dof_flags(manager.ndf)}"))
        for eq in manager.equaldofs:
            if (eq.master_entity_id == entity.id or eq.slave_entity_id == entity.id
                    or (eq.master_group and eq.master_group in groups)
                    or (eq.slave_group and eq.slave_group in groups)):
                role = "Master" if (
                    eq.master_entity_id == entity.id or
                    (eq.master_group and eq.master_group in groups)
                ) else "Slave"
                constraint_items.append((
                    f"EqualDOF {eq.eid} · {eq.name}",
                    role + f" · DOF {eq.dofs}"))
        for disp in manager.prescribed_displacements:
            if entity.id in disp.entity_ids:
                constraint_items.append((
                    f"SP · {disp.name}", f"DOF {disp.dof} = {disp.value:g}"))
        if constraint_items:
            cnode = self._add_category(
                root, f"Vincoli ({len(constraint_items)})", "BC", entity.id)
            for label, value in constraint_items:
                self._add_leaf(cnode, label, "OpenSees", value, entity.id)

        load_items = []
        for load in manager.loads:
            if (entity.id in load.entity_ids or
                    groups.intersection(str(x) for x in load.group_names)):
                load_items.append((
                    f"LOAD {load.lid} · {load.name}",
                    f"F=({load.fx:g}, {load.fy:g}, {load.fz:g}) · "
                    f"pattern {load.pattern_tag}"))
        entity_element_ids = set(int(x) for a in assignments for x in a.element_ids)
        for cmd in manager.element_loads:
            if entity_element_ids.intersection(int(x) for x in cmd.element_ids):
                load_items.append((
                    f"eleLoad · {cmd.name}",
                    f"{cmd.load_type} · pattern {cmd.pattern_tag}"))
        if load_items:
            lnode = self._add_category(
                root, f"Load / Carichi ({len(load_items)})", "LOAD", entity.id)
            for label, value in load_items:
                self._add_leaf(lnode, label, "OpenSees", value, entity.id)

        rec_items = []
        for idx, recorder in enumerate(manager.recorders):
            if entity.id in recorder.entity_ids:
                rec_items.append(
                    f"Recorder {idx} · {recorder.kind} · {recorder.response}")
        if rec_items:
            rnode = self._add_category(
                root, f"Recorders ({len(rec_items)})", "REC", entity.id)
            for label in rec_items:
                self._add_leaf(rnode, label, "OpenSees", "", entity.id)

        param_items = []
        for binding in manager.parameter_bindings:
            if (binding.target_type == "element" and
                    int(binding.target_id) in entity_element_ids):
                param_items.append(f"parameter {binding.tag} → {binding.path}")
        if param_items:
            pnode = self._add_category(
                root, f"Parameter ({len(param_items)})", "PARAM", entity.id)
            for label in param_items:
                self._add_leaf(pnode, label, "OpenSees", "", entity.id)

        interface_items = []
        for interface in manager.interfaces:
            if entity.id in (interface.secondary_entity_id, interface.primary_entity_id):
                role = "secondary" if entity.id == interface.secondary_entity_id else "primary"
                interface_items.append(
                    f"Interface {role} · {len(interface.secondary_nodes) - 1} segmenti")
        if interface_items:
            inode = self._add_category(
                root, f"Interfacce ({len(interface_items)})", "IF", entity.id)
            for label in interface_items:
                self._add_leaf(inode, label, "OpenSees", "", entity.id)

        self._add_phase_nodes(
            root, [a.material_tag for a in assignments], entity.id,
            include_default=bool(assignments or ref or constraint_items or load_items))

    def _add_phase_nodes(self, parent, material_tags, eid, include_default=True):
        manager = getattr(self.doc, "opensees", None)
        if manager is None:
            return
        tags = {int(x) for x in (material_tags if isinstance(material_tags, (list, tuple, set))
                                 else [material_tags]) if x is not None}
        phases = []
        if include_default:
            phases.append((0, "00 · Definizione modello", "FEM/materiali/elementi"))
        if tags:
            for stage in manager.stages:
                if int(stage.mat_tag) in tags:
                    phases.append((int(stage.stage_id), stage.name, "updateMaterialStage"))
        first_stage = min((int(s.stage_id) for s in manager.stages), default=1)
        groups = set(self._entity_groups(eid))
        if any(
            int(eid) in {int(x) for x in c.entity_ids}
            or groups.intersection(str(x) for x in c.group_names)
            for c in manager.constraints
        ) or any(
            int(eid) in {int(x) for x in ld.entity_ids}
            or groups.intersection(str(x) for x in ld.group_names)
            for ld in manager.loads
        ):
            phases.append((first_stage, manager.stages[0].name if manager.stages else "Fase", "boundary/load"))
        seen = set()
        for phase_id, name, reason in phases:
            key = (int(phase_id), str(name), str(reason))
            if key in seen:
                continue
            seen.add(key)
            pnode = self._add_category(
                parent, f"Phase {phase_id:02d} · {name}", "PHASE", eid)
            self._add_leaf(pnode, reason, "Tcl", "", eid, "phase")

    def _on_current_item_changed(self, current, previous):
        if current is None:
            self.fem_details.clear()
            return
        eid = current.data(0, Qt.UserRole)
        if eid is None:
            self.fem_details.setPlainText(current.text(0))
            return
        entity = self.doc.entities.get(int(eid))
        if entity is None:
            self.fem_details.setPlainText(current.text(0))
            return
        self._show_entity_fem_details(entity, current)

    def _show_entity_fem_details(self, entity, item=None):
        manager = getattr(self.doc, "opensees", None)
        if manager is None:
            self.fem_details.setPlainText(
                f"{entity.name}\nTipo: {entity.etype}\nID: {entity.id}")
            return
        lines = [
            f"ENTITÀ: {entity.name}",
            f"Tipo CAD: {NOME_TIPO_IT.get(entity.etype, entity.etype)}",
            f"ID documento: {entity.id}",
            f"Visibilità CAD/OpenCascade: {entity.visibility_state}",
            "",
        ]
        ref = entity.meta.get("mesh_ref")
        if ref:
            lines += [
                f"Mesh: {ref[0]} · dim={ref[1]} · tag={ref[2]}",
                f"Elementi mesh: {len(self._mesh_element_ids(entity))}",
            ]
        assignments = [
            a for a in manager.element_assignments
            if int(a.entity_id) == int(entity.id)
        ]
        for a in assignments:
            mat = next((m for m in manager.materials
                        if int(m.tag) == int(a.material_tag)), None)
            cmd = a.effective_command()
            lines += [
                "",
                f"FEM: Gmsh {a.gmsh_type} → OpenSees {cmd}",
                f"  Elementi mesh: {len(a.element_ids)}",
                f"  Materiale: {a.material_tag} — "
                f"{mat.name if mat else 'NON DEFINITO'}"
                + (f" ({mat.model})" if mat else ""),
                f"  Area: {a.area:g}",
                f"  Thickness: {a.thickness:g}",
                f"  Plane: {a.plane_type}",
                f"  u-p: {'SI' if a.is_up else 'NO'}",
            ]
            if a.element_args:
                lines.append(f"  element_args: {a.element_args}")
            if a.section_tag is not None:
                lines.append(f"  Section tag: {a.section_tag}")
            if a.transf_tag is not None:
                lines.append(f"  geomTransf tag: {a.transf_tag}")
            if a.integration_tag is not None:
                lines.append(f"  beamIntegration tag: {a.integration_tag}")

        try:
            model = self.doc.mesh_models.get(ref[0]) if ref else None
            if model is not None and assignments:
                from gcs.core.opensees_flow import OpenSeesFlow
                tcl_all = OpenSeesFlow._render_elements(manager, model)
                selected_ids = {int(x) for a in assignments for x in a.element_ids}
                tcl_lines = [
                    line for line in tcl_all.splitlines()
                    if line.startswith("element ")
                    and any(f" {eid} " in line for eid in selected_ids)
                ]
                if tcl_lines:
                    lines += ["", "TCL ELEMENTI DELL'ENTITÀ:", *tcl_lines]
        except Exception as exc:
            lines += ["", f"Tcl preview non disponibile: {exc}"]

        groups = set(self._entity_groups(entity.id))
        constraints = []
        for c0 in manager.constraints:
            if entity.id in c0.entity_ids or groups.intersection(c0.group_names):
                constraints.append(
                    f"fix {c0.cid} · {c0.name} · DOF {c0.dof_flags(manager.ndf)}")
        for eq in manager.equaldofs:
            if (eq.master_entity_id == entity.id or eq.slave_entity_id == entity.id
                    or (eq.master_group and eq.master_group in groups)
                    or (eq.slave_group and eq.slave_group in groups)):
                constraints.append(
                    f"equalDOF {eq.eid} · {eq.name} · DOF {eq.dofs}")
        if constraints:
            lines += ["", "VINCOLI:", *constraints]

        loads = []
        for ld in manager.loads:
            if entity.id in ld.entity_ids or groups.intersection(ld.group_names):
                loads.append(
                    f"load {ld.lid} · {ld.name} · "
                    f"F=({ld.fx:g},{ld.fy:g},{ld.fz:g}) · pattern={ld.pattern_tag}")
        if loads:
            lines += ["", "LOAD:", *loads]

        try:
            from gcs.core.opensees_flow import OpenSeesFlow
            model = self.doc.mesh_models.get(ref[0]) if ref else None
            groups0 = set(self._entity_groups(entity.id))
            tcl_related = []

            # Elementi: estrazione delle righe Tcl esatte associate alla proprietà FEM.
            if model is not None and assignments:
                tcl_all = OpenSeesFlow._render_elements(manager, model)
                selected_ids = {int(x) for a in assignments for x in a.element_ids}
                tcl_related.extend(
                    line for line in tcl_all.splitlines()
                    if line.startswith("element ")
                    and any(f" {eid} " in line for eid in selected_ids)
                )

            # Vincoli/EqualDOF: usa gli stessi renderer del workflow.
            if model is not None:
                for c0 in manager.constraints:
                    if entity.id in c0.entity_ids or groups0.intersection(c0.group_names):
                        tcl_related.append(OpenSeesFlow._render_constraint(manager, c0, model))
                for eq in manager.equaldofs:
                    if (eq.master_entity_id == entity.id or eq.slave_entity_id == entity.id
                            or (eq.master_group and eq.master_group in groups0)
                            or (eq.slave_group and eq.slave_group in groups0)):
                        tcl_related.append(OpenSeesFlow._render_equal_dof(manager, eq, model))

            # Carichi nodali: documenta i nodi mesh coinvolti dall'entità.
            if model is not None:
                for ld in manager.loads:
                    if entity.id in ld.entity_ids or groups0.intersection(ld.group_names):
                        nodes = manager.resolve_load_nodes(ld, model)
                        if nodes:
                            vals = [ld.fx, ld.fy, ld.fz][:manager.ndf]
                            tcl_related.append(
                                f"# LOAD '{ld.name}' pattern {ld.pattern_tag} → nodi {nodes}")
                            tcl_related.extend(
                                f"load {nid} " + " ".join(f"{v/len(nodes):.10g}" for v in vals) + ";"
                                for nid in nodes
                            )

            if tcl_related:
                lines += ["", "TCL ASSOCIATO ALL'ENTITÀ:", *tcl_related]

            # Fasi realmente pertinenti all'entità: definizione FEM e condizioni/stage
            # legati al materiale o ai target dell'entità.
            flow = manager.flow
            flow.sync_from_manager(manager, model)
            material_tags = {int(a.material_tag) for a in assignments}
            related_phases = []
            for phase in flow.phases:
                relevant = phase.phase_id == 0 and bool(assignments or ref)
                relevant = relevant or any(
                    int(s.stage_id) == int(phase.phase_id)
                    and int(s.mat_tag) in material_tags
                    for s in manager.stages
                )
                relevant = relevant or (
                    phase.phase_id > 0 and (
                        any(entity.id in c0.entity_ids or groups0.intersection(c0.group_names)
                            for c0 in manager.constraints)
                        or any(entity.id in ld.entity_ids or groups0.intersection(ld.group_names)
                               for ld in manager.loads)
                    )
                )
                if relevant:
                    related_phases.append(
                        f"  Phase {phase.phase_id:02d} · {phase.name}")
            if related_phases:
                lines += ["", "FASI RILEVANTI:", *related_phases]

        except Exception as exc:
            lines += ["", f"Preview Tcl non disponibile: {exc}"]

        self.fem_details.setPlainText("\n".join(lines))

    def _mesh_element_ids(self, entity):
        ref = entity.meta.get("mesh_ref")
        if not ref:
            return []
        model = self.doc.mesh_models.get(ref[0])
        if model is None:
            return []
        block = model.blocks.get((int(ref[1]), int(ref[2])))
        return sorted(int(x) for x in (block.element_ids if block else []))

    # ---------------------------------------------------------------- eventi
    def _assignment_from_item(self, item):
        """Risolvi l'assegnazione FEM rappresentata da un nodo dell'albero."""
        if item.data(0, Qt.UserRole + 5) != "assignment":
            return None
        eid = item.data(0, Qt.UserRole)
        model_name = item.data(0, Qt.UserRole + 6)
        element_ids = {int(x) for x in (item.data(0, Qt.UserRole + 7) or [])}
        manager = getattr(self.doc, "opensees", None)
        if eid is None or manager is None:
            return None
        candidates = [
            a for a in manager.element_assignments
            if int(a.entity_id) == int(eid)
            and (not model_name or a.model_name == str(model_name))
        ]
        return next(
            (a for a in candidates if set(a.element_ids) == element_ids),
            candidates[0] if len(candidates) == 1 else None,
        )

    def _open_fem_assignment_editor(self, assignment):
        if assignment is None:
            return
        from .dialogs import OpenSeesFEMDialog
        dlg = OpenSeesFEMDialog(
            self.doc,
            parent=self,
            focus_entity_id=assignment.entity_id,
            focus_assignment=assignment,
        )
        if dlg.exec():
            self.doc.opensees.refresh_entity_metadata()
            self.doc.notify("opensees_condition_added",
                            {"type": "element_assignment_edited",
                             "entity_id": assignment.entity_id})
            self.refresh()
            self.viewer.redraw_all(fit=False)

    def _on_double(self, item, col):
        assignment = self._assignment_from_item(item)
        if assignment is not None:
            self._open_fem_assignment_editor(assignment)
            return

        eid = item.data(0, Qt.UserRole)
        if eid is not None:
            self.selection_manager.set_context("cad")
            self.selection_manager.set_selection([eid])
            assignment_ids = item.data(0, Qt.UserRole + 7) or []
            model_name = item.data(0, Qt.UserRole + 6)
            if assignment_ids and model_name:
                model = self.doc.mesh_models.get(str(model_name))
                if model is not None:
                    model.sel_elements = {int(x) for x in assignment_ids}
                    model.sel_nodes = model.nodes_of_elements(model.sel_elements)
                    model.sel_blocks = {
                        model.block_of_element(x)
                        for x in model.sel_elements
                        if model.block_of_element(x) is not None
                    }
            self.viewer.highlight_selection()
            return
        model_name = item.data(0, Qt.UserRole + 2)
        element_ids = item.data(0, Qt.UserRole + 3) or []
        node_ids = item.data(0, Qt.UserRole + 4) or []
        if not model_name:
            return
        model = self.doc.mesh_models.get(str(model_name))
        if model is None:
            return
        model.sel_elements = set(int(e) for e in element_ids)
        model.sel_nodes = set(int(n) for n in node_ids)
        if element_ids:
            model.sel_nodes.update(model.nodes_of_elements(model.sel_elements))
        block_keys = set()
        for elid in model.sel_elements:
            key = model.block_of_element(elid)
            if key:
                block_keys.add(key)
        model.sel_blocks = block_keys
        # Ricostruisce anche la selezione documentale dai blocchi mesh:
        # il viewer può così evidenziare il corrispondente blocco Gmsh.
        eids = set()
        for doc_eid, ent in self.doc.entities.items():
            ref = ent.meta.get("mesh_ref")
            if not ref or ref[0] != str(model_name):
                continue
            block = model.blocks.get((ref[1], ref[2]))
            if block and block_keys.intersection({(ref[1], ref[2])}):
                eids.add(doc_eid)
            elif block and set(block.element_ids).intersection(model.sel_elements):
                eids.add(doc_eid)
        if eids:
            self.selection_manager.set_context("mesh")
            self.selection_manager.set_selection(eids)
        self.viewer.highlight_selection()
        self.refresh()

    def _on_check(self, item, col):
        if self._updating or col != 0:
            return
        eid = item.data(0, Qt.UserRole)
        if eid is not None:
            visible = item.checkState(0) == Qt.Checked
            self.visibility_manager.set_entity_visible(eid, visible)
            return
        gname = item.data(0, Qt.UserRole + 1)
        if gname:
            group = self.doc.groups.groups.get(str(gname))
            if group:
                self._set_visibility_for_entities(group.member_ids, item.checkState(0) == Qt.Checked)

    def _set_visibility_for_entities(self, entity_ids, visible):
        return self.visibility_manager.set_entities_visible(entity_ids, visible)


    def _toggle_all_visibility(self, visible):
        changed = self._set_visibility_for_entities(self.doc.entities.keys(), visible)
        win = self.window()
        if hasattr(win, "_log"):
            win._log(f"Entità CAD: {'visibili' if visible else 'nascoste'} ({changed})")

    def _menu_contesto(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        win = self.window()

        if item is not None:
            assignment = self._assignment_from_item(item)
            if assignment is not None:
                menu.addAction(
                    "Modifica assegnazione FEM…",
                    lambda a=assignment: self._open_fem_assignment_editor(a))
                menu.addAction(
                    "Seleziona elementi FEM",
                    lambda a=assignment: self._select_fem_assignment(a))
                menu.addSeparator()

            eid = item.data(0, Qt.UserRole)
            if eid is not None:
                menu.addAction("Mostra entità", lambda eid=eid: self._set_visibility_for_entities([eid], True))
                menu.addAction("Nascondi entità", lambda eid=eid: self._set_visibility_for_entities([eid], False))
                menu.addSeparator()
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
        if item is None:
            menu.addAction("Mostra tutte le entità", lambda: self._toggle_all_visibility(True))
            menu.addAction("Nascondi tutte le entità", lambda: self._toggle_all_visibility(False))
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
        try:
            entity_ids, mesh_selection = self.doc.groups.resolve_mesh_selection(self.doc, gname)
        except Exception:
            return
        for model_name, data in mesh_selection.items():
            model = self.doc.mesh_models.get(model_name)
            if model is None:
                continue
            model.sel_elements = set(data.get("elements", set()))
            model.sel_nodes = set(data.get("nodes", set()))
            if model.sel_elements:
                model.sel_nodes.update(model.nodes_of_elements(model.sel_elements))
            model.sel_blocks = {
                model.block_of_element(eid) for eid in model.sel_elements
                if model.block_of_element(eid) is not None
            }
        self.doc.set_selection(entity_ids)
        self.viewer.highlight_selection()
        self.refresh()

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

    def _select_fem_assignment(self, assignment):
        entity_id = int(assignment.entity_id)
        self.selection_manager.set_context("mesh")
        self.selection_manager.set_selection([entity_id])
        model = self.doc.mesh_models.get(assignment.model_name)
        if model is not None:
            model.sel_elements = {int(x) for x in assignment.element_ids}
            model.sel_nodes = model.nodes_of_elements(model.sel_elements)
            model.sel_blocks = {
                model.block_of_element(x)
                for x in model.sel_elements
                if model.block_of_element(x) is not None
            }
        self.viewer.highlight_selection()
        self.refresh()

    def _select(self, eid):
        self.selection_manager.set_context("cad")
        self.selection_manager.set_selection([eid])
        self.viewer.highlight_selection()

    def _isolate(self, eid):
        self.visibility_manager.isolate_entities([eid])
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
            parent_id = e.meta.get("parent")
            if parent_id is not None:
                parent = self.doc.entities.get(int(parent_id))
                if parent is not None:
                    self._add_row(
                        "   parent",
                        f"{NOME_TIPO_IT.get(parent.etype, parent.etype)} "
                        f"{parent.name} (id {parent.id})")
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
            if hasattr(win, "tree_panel"):
                win.tree_panel.refresh()

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



class OpenSeesFlowPanel(QWidget):
    """Albero editabile del workflow OpenSees e dei comandi Tcl di fase."""

    def __init__(self, doc: CADDocument, model=None, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.model = model or (list(doc.mesh_models.values())[-1] if doc.mesh_models else None)
        self._building = False
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        title = QLabel("<b>Workflow OpenSees — fasi e comandi Tcl</b>")
        title.setToolTip(
            "Sposta i comandi tra le fasi; doppio click su una fase o comando per modificarlo.")
        lay.addWidget(title)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(("Fase / comando", "Tipo", "Stato"))
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.itemDoubleClicked.connect(self._edit_item)
        self.tree.currentItemChanged.connect(self._show_details)
        lay.addWidget(self.tree, 2)

        btns = QHBoxLayout()
        self.btn_add_phase = QPushButton("+ Fase")
        self.btn_add_cmd = QPushButton("+ Tcl")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        self.btn_toggle = QPushButton("Abilita/Disabilita")
        self.btn_move_phase = QPushButton("Sposta a fase…")
        self.btn_remove = QPushButton("Rimuovi")
        self.btn_add_phase.clicked.connect(self._add_phase)
        self.btn_add_cmd.clicked.connect(self._add_custom)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.btn_toggle.clicked.connect(self._toggle)
        self.btn_move_phase.clicked.connect(self._move_to_phase)
        self.btn_remove.clicked.connect(self._remove)
        for b in (self.btn_add_phase, self.btn_add_cmd, self.btn_up,
                  self.btn_down, self.btn_toggle, self.btn_move_phase, self.btn_remove):
            btns.addWidget(b)
        lay.addLayout(btns)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Seleziona un comando per vedere il Tcl che sarà esportato.")
        self.details.setFontFamily("Monospace")
        self.details.setMaximumHeight(180)
        lay.addWidget(self.details, 1)

        self.refresh()

    def refresh(self):
        if self._building or not hasattr(self.doc, "opensees"):
            return
        self._building = True
        try:
            flow = self.doc.opensees.flow
            flow.sync_from_manager(self.doc.opensees, self.model)
            self.tree.clear()
            for phase in flow.phases:
                pitem = QTreeWidgetItem([
                    f"{phase.phase_id:02d} · {phase.name}",
                    "FASE",
                    "ON" if phase.enabled else "OFF",
                ])
                pitem.setData(0, Qt.UserRole, int(phase.phase_id))
                pitem.setData(0, Qt.UserRole + 7, "phase")
                pitem.setCheckState(0, Qt.Checked if phase.enabled else Qt.Unchecked)
                if phase.phase_id == 0:
                    pitem.setForeground(0, QBrush(QColor("#88C0D0")))
                for index, command in enumerate(phase.commands):
                    state = "ON" if command.enabled else "OFF"
                    if command.overridden:
                        state += " · EDIT"
                    item = QTreeWidgetItem([
                        "  ↳ " + command.label,
                        command.kind,
                        state,
                    ])
                    item.setData(0, Qt.UserRole, int(phase.phase_id))
                    item.setData(0, Qt.UserRole + 1, int(index))
                    item.setData(0, Qt.UserRole + 2, command.uid)
                    item.setData(0, Qt.UserRole + 7, "command")
                    item.setCheckState(0, Qt.Checked if command.enabled else Qt.Unchecked)
                    item.setToolTip(0, command.tcl)
                    if not command.editable:
                        item.setForeground(0, QBrush(QColor("#8FBCBB")))
                    elif command.overridden:
                        item.setForeground(0, QBrush(QColor("#EBCB8B")))
                    pitem.addChild(item)
                self.tree.addTopLevelItem(pitem)
                pitem.setExpanded(phase.phase_id > 0)
        finally:
            self._building = False
        self._show_details(self.tree.currentItem(), None)

    def _selected_command(self):
        item = self.tree.currentItem()
        if item is None or item.data(0, Qt.UserRole + 7) != "command":
            return None
        phase = self.doc.opensees.flow.get_phase(item.data(0, Qt.UserRole))
        if phase is None:
            return None
        index = int(item.data(0, Qt.UserRole + 1))
        if not (0 <= index < len(phase.commands)):
            return None
        return phase, index, phase.commands[index]

    def _edit_item(self, item, column):
        kind = item.data(0, Qt.UserRole + 7)
        if kind == "phase":
            phase = self.doc.opensees.flow.get_phase(item.data(0, Qt.UserRole))
            if phase is None:
                return
            value, ok = QInputDialog.getText(
                self, "Modifica fase", "Nome fase:", text=phase.name)
            if ok and value.strip():
                phase.name = value.strip()
                phase.name_overridden = True
                stage = next((s for s in self.doc.opensees.stages
                               if int(s.stage_id) == int(phase.phase_id)), None)
                if stage is not None:
                    stage.name = phase.name
                self.doc.opensees.flow.current_phase_id = phase.phase_id
                self.doc.notify("opensees_flow_changed", {"phase": phase.phase_id})
                self.refresh()
            return

        selected = self._selected_command()
        if selected is None:
            return
        phase, _, command = selected
        if not command.editable:
            self.details.setPlainText(
                "# Comando generato dal modello; modifica da GUI dedicata.\n\n" + command.tcl)
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "Modifica comando Tcl",
            f"{command.label}\nModifica il Tcl che sarà scritto nella fase {phase.phase_id}:",
            command.tcl)
        if ok:
            command.tcl = text.strip()
            command.overridden = True
            self.doc.opensees.flow.current_phase_id = phase.phase_id
            self.doc.notify("opensees_flow_changed", {"command": command.uid})
            self.refresh()

    def _add_phase(self):
        name, ok = QInputDialog.getText(self, "Nuova fase", "Nome fase:",
                                        text="Nuova fase")
        if not ok:
            return
        phase_name = name.strip() or "Nuova fase"
        phase = self.doc.opensees.flow.add_phase(phase_name)
        from ..core.opensees_conditions import AnalysisStage, SolverSettings
        solver = SolverSettings.from_dict(self.doc.opensees.default_solver.to_dict())
        self.doc.opensees.stages.append(
            AnalysisStage(
                phase.phase_id, phase.name, stage_type="static",
                material_stage=1, mat_tag=1,
                update_stage_cmd=False, load_const=False,
                solver=solver, update_command="none"
            )
        )
        self.doc.opensees.flow.current_phase_id = phase.phase_id
        self.doc.notify("opensees_flow_changed", {"phase": phase.phase_id})
        self.refresh()

    def _add_custom(self):
        item = self.tree.currentItem()
        phase_id = self.doc.opensees.flow.current_phase_id
        if item is not None:
            phase_id = int(item.data(0, Qt.UserRole))
            if item.data(0, Qt.UserRole + 7) == "command":
                # Il comando selezionato determina la fase.
                pass
        label, ok = QInputDialog.getText(self, "Nuovo comando Tcl",
                                         "Descrizione:", text="Operazione Tcl")
        if not ok:
            return
        tcl, ok = QInputDialog.getMultiLineText(
            self, "Nuovo comando Tcl", "Comando Tcl:", "set parametro 1;")
        if not ok or not tcl.strip():
            return
        self.doc.opensees.flow.add_custom(phase_id, label, tcl)
        self.doc.notify("opensees_flow_changed", {})
        self.refresh()

    def _move(self, delta):
        selected = self._selected_command()
        if selected is None:
            return
        phase, index, _ = selected
        if self.doc.opensees.flow.move_command(phase.phase_id, index, delta):
            self.doc.notify("opensees_flow_changed", {})
            self.refresh()

    def _move_to_phase(self):
        selected = self._selected_command()
        if selected is None:
            return
        current_phase, index, command = selected
        phases = [p for p in self.doc.opensees.flow.phases if p.phase_id != current_phase.phase_id]
        if not phases:
            return
        labels = [f"{p.phase_id}: {p.name}" for p in phases]
        label, ok = QInputDialog.getItem(
            self, "Sposta comando", "Fase di destinazione:", labels, 0, False)
        if not ok:
            return
        target_id = phases[labels.index(label)].phase_id
        current_phase.commands.pop(index)
        self.doc.opensees.flow.get_phase(target_id).commands.append(command)
        self.doc.opensees.flow.current_phase_id = target_id
        self.doc.notify("opensees_flow_changed", {"command": command.uid, "phase": target_id})
        self.refresh()

    def _toggle(self):
        item = self.tree.currentItem()
        if item is None:
            return
        kind = item.data(0, Qt.UserRole + 7)
        phase_id = int(item.data(0, Qt.UserRole))
        if kind == "phase":
            phase = self.doc.opensees.flow.get_phase(phase_id)
            if phase:
                phase.enabled = not phase.enabled
        else:
            selected = self._selected_command()
            if selected:
                _, _, command = selected
                command.enabled = not command.enabled
        self.doc.notify("opensees_flow_changed", {})
        self.refresh()

    def _remove(self):
        item = self.tree.currentItem()
        if item is None:
            return
        phase_id = int(item.data(0, Qt.UserRole))
        kind = item.data(0, Qt.UserRole + 7)
        if kind == "phase":
            if phase_id == 0:
                QMessageBox.information(self, "Flow", "La fase 00 contiene le definizioni del modello.")
                return
            if self.doc.opensees.flow.remove_phase(phase_id):
                self.doc.opensees.stages = [
                    s for s in self.doc.opensees.stages
                    if int(s.stage_id) != phase_id
                ]
        else:
            phase = self.doc.opensees.flow.get_phase(phase_id)
            if phase:
                self.doc.opensees.flow.remove_command(
                    phase_id, int(item.data(0, Qt.UserRole + 1)))
        self.doc.notify("opensees_flow_changed", {})
        self.refresh()

    def _show_details(self, item, previous):
        if item is None:
            self.details.clear()
            return
        kind = item.data(0, Qt.UserRole + 7)
        if kind == "phase":
            phase = self.doc.opensees.flow.get_phase(item.data(0, Qt.UserRole))
            self.details.setPlainText(
                (phase.notes if phase and phase.notes else "(fase senza note)") +
                (f"\n\nComandi: {len(phase.commands)}" if phase else ""))
            return
        selected = self._selected_command()
        if selected:
            phase, _, command = selected
            header = f"# Fase {phase.phase_id}: {phase.name}\n# {command.kind} · {command.label}"
            self.details.setPlainText(header + "\n\n" + command.tcl)
