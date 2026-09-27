"""Workflow editabile delle fasi OpenSees per GmshCAD-SOB.

Il flow rende esplicite le operazioni che entrano nel Tcl: vincoli, EqualDOF,
pattern, recorder, region, eleLoad, parametri, updateMaterialStage,
updateParameter, solver/analyze e comandi Tcl custom. Le definizioni strutturali
del modello restano generate dalle strutture FEM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import uuid4


@dataclass
class FlowCommand:
    uid: str
    label: str
    kind: str
    tcl: str
    source_id: str = ""
    enabled: bool = True
    editable: bool = True
    overridden: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "uid": self.uid, "label": self.label, "kind": self.kind,
            "tcl": self.tcl, "source_id": self.source_id,
            "enabled": self.enabled, "editable": self.editable,
            "overridden": self.overridden, "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FlowCommand":
        return cls(
            d.get("uid", str(uuid4())), d.get("label", "Comando"),
            d.get("kind", "custom"), d.get("tcl", ""),
            d.get("source_id", ""), d.get("enabled", True),
            d.get("editable", True), d.get("overridden", False),
            d.get("notes", ""),
        )


@dataclass
class FlowPhase:
    phase_id: int
    name: str
    enabled: bool = True
    commands: List[FlowCommand] = field(default_factory=list)
    notes: str = ""
    name_overridden: bool = False

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id, "name": self.name,
            "enabled": self.enabled,
            "commands": [c.to_dict() for c in self.commands],
            "notes": self.notes,
            "name_overridden": self.name_overridden,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FlowPhase":
        return cls(
            int(d.get("phase_id", 1)), d.get("name", "Fase"),
            d.get("enabled", True),
            [FlowCommand.from_dict(c) for c in d.get("commands", [])],
            d.get("notes", ""),
            d.get("name_overridden", False),
        )


class OpenSeesFlow:
    """Registro e sincronizzazione del workflow OpenSees."""

    def __init__(self):
        self.phases: List[FlowPhase] = [
            FlowPhase(0, "00 · Definizione modello",
                      notes="wipe/model, nodi, materiali, elementi, interfacce, parameter, timeSeries"),
            FlowPhase(1, "Gravity Loading (Stato Elastico)"),
            FlowPhase(2, "Fase Elastoplastica (Plastic Stage)"),
        ]
        self.current_phase_id = 1

    # ---------------------------------------------------------------- utility
    def get_phase(self, phase_id: int) -> Optional[FlowPhase]:
        return next((p for p in self.phases if p.phase_id == int(phase_id)), None)

    def ensure_phase(self, phase_id: int, name: str = "") -> FlowPhase:
        phase = self.get_phase(phase_id)
        if phase is not None:
            return phase
        phase = FlowPhase(int(phase_id), name or f"{int(phase_id):02d} · Fase")
        self.phases.append(phase)
        self.phases.sort(key=lambda p: p.phase_id)
        return phase

    def add_phase(self, name: str = "") -> FlowPhase:
        new_id = max((p.phase_id for p in self.phases), default=0) + 1
        phase = FlowPhase(new_id, name or f"{new_id:02d} · Nuova fase")
        self.phases.append(phase)
        self.current_phase_id = new_id
        return phase

    def remove_phase(self, phase_id: int) -> bool:
        phase_id = int(phase_id)
        if phase_id == 0:
            return False
        old = len(self.phases)
        self.phases = [p for p in self.phases if p.phase_id != phase_id]
        if len(self.phases) == old:
            return False
        if self.current_phase_id == phase_id:
            self.current_phase_id = min((p.phase_id for p in self.phases), default=0)
        return True

    def add_custom(self, phase_id: int, label: str, tcl: str) -> FlowCommand:
        phase = self.ensure_phase(phase_id)
        cmd = FlowCommand(
            uid=f"custom:{uuid4().hex}",
            label=label.strip() or "Tcl custom",
            kind="custom", tcl=tcl.strip(), overridden=True,
        )
        phase.commands.append(cmd)
        return cmd

    def move_command(self, phase_id: int, index: int, delta: int) -> bool:
        phase = self.get_phase(phase_id)
        if phase is None or not (0 <= index < len(phase.commands)):
            return False
        target = index + int(delta)
        if not 0 <= target < len(phase.commands):
            return False
        phase.commands[index], phase.commands[target] = (
            phase.commands[target], phase.commands[index])
        return True

    def remove_command(self, phase_id: int, index: int) -> bool:
        phase = self.get_phase(phase_id)
        if phase is None or not (0 <= index < len(phase.commands)):
            return False
        phase.commands.pop(index)
        return True

    # -------------------------------------------------------------- sync
    def sync_from_manager(self, manager, model=None) -> None:
        if model is None and manager.doc.mesh_models:
            model = list(manager.doc.mesh_models.values())[-1]

        self.ensure_phase(0, "00 · Definizione modello")
        for stage in manager.stages:
            phase = self.get_phase(stage.stage_id)
            if phase is None:
                self.ensure_phase(stage.stage_id, stage.name)
            elif not phase.name_overridden:
                phase.name = stage.name

        specs = self._build_specs(manager, model)
        generated = {s["uid"] for s in specs}
        existing: Dict[str, FlowCommand] = {}
        for phase in self.phases:
            for cmd in phase.commands:
                existing[cmd.uid] = cmd

        for spec in specs:
            cmd = existing.get(spec["uid"])
            if cmd is None:
                cmd = FlowCommand(
                    uid=spec["uid"], label=spec["label"], kind=spec["kind"],
                    tcl=spec["tcl"], source_id=spec.get("source_id", ""),
                    enabled=spec.get("enabled", True),
                    editable=spec.get("editable", True),
                    notes=spec.get("notes", ""),
                )
                self.ensure_phase(spec["phase_id"]).commands.append(cmd)
                continue
            cmd.label = spec["label"]
            cmd.kind = spec["kind"]
            cmd.source_id = spec.get("source_id", cmd.source_id)
            cmd.editable = spec.get("editable", cmd.editable)
            cmd.notes = spec.get("notes", cmd.notes)
            if not cmd.overridden:
                cmd.tcl = spec["tcl"]
                cmd.enabled = spec.get("enabled", True)

        # Oggetti eliminati dal manager non devono più essere esportati, ma
        # restano nell'albero per rendere visibile la modifica.
        for phase in self.phases:
            for cmd in phase.commands:
                if cmd.kind != "custom" and cmd.uid not in generated:
                    cmd.enabled = False
                    if not cmd.label.startswith("[rimosso]"):
                        cmd.label = "[rimosso] " + cmd.label

        self.phases.sort(key=lambda p: p.phase_id)
        if self.current_phase_id not in {p.phase_id for p in self.phases}:
            self.current_phase_id = 1 if self.get_phase(1) else 0

    def _join(self, values) -> str:
        return "\n".join(str(v) for v in values if str(v).strip())

    def _build_specs(self, manager, model) -> List[dict]:
        specs: List[dict] = []
        ndm, ndf = manager.ndm, manager.ndf

        specs.append({
            "uid": "model:builder", "phase_id": 0, "kind": "model",
            "label": "model BasicBuilder", "source_id": "model",
            "tcl": f"wipe;\nmodel BasicBuilder -ndm {ndm} -ndf {ndf};",
            "editable": False,
        })

        if model:
            node_lines = [
                f"node {nid} " + " ".join(f"{v:.10g}" for v in c[:ndm]) + ";"
                for nid, c in sorted(model.nodes.items())
            ]
            node_lines += [
                f"node {nid} " + " ".join(f"{v:.10g}" for v in c[:ndm]) + ";"
                for nid, c in sorted(manager.manual_nodes.items())
            ]
            if node_lines:
                specs.append({
                    "uid": "model:nodes", "phase_id": 0, "kind": "nodes",
                    "label": f"Nodi ({len(node_lines)})", "source_id": "nodes",
                    "tcl": self._join(node_lines), "editable": False,
                })

        if manager.materials:
            specs.append({
                "uid": "model:materials", "phase_id": 0, "kind": "materials",
                "label": f"Materiali ({len(manager.materials)})", "source_id": "materials",
                "tcl": self._join(m.to_tcl() for m in manager.materials),
                "editable": False,
            })

        for attr, kind, label in (
            ("sections", "sections", "Sezioni"),
            ("geom_transfs", "geomTransf", "Trasformazioni"),
            ("beam_integrations", "beamIntegration", "Integrazioni"),
        ):
            objs = getattr(manager, attr, [])
            if objs:
                specs.append({
                    "uid": f"model:{kind}", "phase_id": 0, "kind": kind,
                    "label": f"{label} ({len(objs)})", "source_id": kind,
                    "tcl": self._join(o.to_tcl() for o in objs), "editable": False,
                })

        if manager.nodal_masses:
            specs.append({
                "uid": "model:masses", "phase_id": 0, "kind": "mass",
                "label": f"Masse nodali ({len(manager.nodal_masses)})", "source_id": "masses",
                "tcl": self._join(m.to_tcl() for m in manager.nodal_masses),
                "editable": False,
            })

        if model:
            element_tcl = self._render_elements(manager, model)
            if element_tcl:
                specs.append({
                    "uid": "model:elements", "phase_id": 0, "kind": "elements",
                    "label": "Elementi OpenSees", "source_id": "elements",
                    "tcl": element_tcl, "editable": False,
                })

        if manager.interfaces:
            specs.append({
                "uid": "model:interfaces", "phase_id": 0, "kind": "interfaces",
                "label": f"Interfacce ({len(manager.interfaces)})",
                "source_id": "interfaces",
                "tcl": self._render_interfaces(manager, model), "editable": False,
            })

        if manager.parameter_bindings:
            specs.append({
                "uid": "model:parameters", "phase_id": 0, "kind": "parameter",
                "label": f"Parameter ({len(manager.parameter_bindings)})",
                "source_id": "parameters",
                "tcl": self._join(b.to_tcl() for b in manager.parameter_bindings),
                "editable": False,
            })

        if manager.time_series:
            specs.append({
                "uid": "model:timeSeries", "phase_id": 0, "kind": "timeSeries",
                "label": f"TimeSeries ({len(manager.time_series)})",
                "source_id": "timeSeries",
                "tcl": self._join(manager.time_series[tag].to_tcl()
                                   for tag in sorted(manager.time_series)),
                "editable": False,
            })

        first_stage = min((int(s.stage_id) for s in manager.stages), default=1)

        for cons in manager.constraints:
            specs.append({
                "uid": f"constraint:{cons.cid}", "phase_id": first_stage,
                "kind": "constraint", "label": f"fix · {cons.name}",
                "source_id": str(cons.cid),
                "tcl": self._render_constraint(manager, cons, model),
            })
        for eq in manager.equaldofs:
            specs.append({
                "uid": f"equaldof:{eq.eid}", "phase_id": first_stage,
                "kind": "equalDOF", "label": f"equalDOF · {eq.name}",
                "source_id": str(eq.eid),
                "tcl": self._render_equal_dof(manager, eq, model),
            })

        pattern_tags = sorted(
            {getattr(l, "pattern_tag", 1) for l in manager.loads} |
            {getattr(d, "pattern_tag", 1) for d in manager.prescribed_displacements}
        )
        for tag in pattern_tags:
            tcl = self._render_pattern(manager, model, tag)
            if tcl:
                specs.append({
                    "uid": f"pattern:{tag}", "phase_id": first_stage,
                    "kind": "pattern", "label": f"pattern Plain {tag}",
                    "source_id": str(tag), "tcl": tcl,
                })

        for idx, recorder in enumerate(manager.recorders):
            specs.append({
                "uid": f"recorder:{idx}", "phase_id": first_stage,
                "kind": "recorder",
                "label": f"recorder {recorder.kind} · {recorder.response}",
                "source_id": str(idx),
                "tcl": self._render_recorder(manager, recorder, model),
            })
        for idx, region in enumerate(manager.regions):
            specs.append({
                "uid": f"region:{idx}", "phase_id": first_stage,
                "kind": "region", "label": f"region {region.tag}",
                "source_id": str(idx), "tcl": region.to_tcl(),
            })
        for idx, cmd in enumerate(manager.element_loads):
            specs.append({
                "uid": f"element_load:{idx}", "phase_id": first_stage,
                "kind": "eleLoad", "label": f"eleLoad · {cmd.name}",
                "source_id": str(idx), "tcl": cmd.to_tcl(),
            })
        if manager.rayleigh is not None:
            specs.append({
                "uid": "rayleigh:global", "phase_id": first_stage, "kind": "rayleigh",
                "label": "rayleigh globale", "source_id": "global",
                "tcl": manager.rayleigh.to_tcl(),
            })
        if manager.global_parameters:
            specs.append({
                "uid": "parameters:global", "phase_id": first_stage,
                "kind": "globalParameter", "label": "Parametri globali",
                "source_id": "global",
                "tcl": self._join(
                    f"set {name} {value:.12g};"
                    for name, value in manager.global_parameters.items()),
            })
        for idx, cmd in enumerate(manager.set_parameters):
            specs.append({
                "uid": f"setParameter:{idx}", "phase_id": first_stage,
                "kind": "setParameter", "label": f"setParameter · {cmd.parameter_name}",
                "source_id": str(idx), "tcl": cmd.to_tcl(),
            })
        for idx, cmd in enumerate(manager.update_materials_cmds):
            specs.append({
                "uid": f"updateMaterials:{idx}", "phase_id": first_stage,
                "kind": "updateMaterials", "label": f"updateMaterials · {cmd.parameter_name}",
                "source_id": str(idx), "tcl": cmd.to_tcl(),
            })

        for stage in manager.stages:
            if stage.update_command == "updateMaterialStage":
                tcl = (f"updateMaterialStage -material {stage.mat_tag} "
                       f"-stage {stage.material_stage};")
                specs.append({
                    "uid": f"stage-update:{stage.stage_id}",
                    "phase_id": int(stage.stage_id), "kind": "stageUpdate",
                    "label": f"Update stage · {stage.stage_id}",
                    "source_id": str(stage.stage_id), "tcl": tcl,
                })
            elif stage.update_command == "updateParameter":
                tcl = (f"updateParameter {stage.parameter_tag} "
                       f"{stage.parameter_value:.12g};")
                specs.append({
                    "uid": f"stage-update:{stage.stage_id}",
                    "phase_id": int(stage.stage_id), "kind": "stageUpdate",
                    "label": f"Update parameter · {stage.parameter_tag}",
                    "source_id": str(stage.stage_id), "tcl": tcl,
                })

            solver_lines = list(stage.solver.to_tcl(
                res_var=f"ok_stage{stage.stage_id}")) if stage.solver else []
            solver_lines += [
                f"if {{$ok_stage{stage.stage_id} == 0}} {{",
                f'    puts "FASE {stage.stage_id} ({stage.name}) COMPLETATA CON SUCCESSO!";',
                "} else {",
                f'    puts "ATTENZIONE: Fase {stage.stage_id} non convergente (codice di uscita: $ok_stage{stage.stage_id})";',
                "}",
            ]
            if stage.stage_type == "gravity" and stage.load_const:
                solver_lines.append("loadConst -time 0.0;")
            specs.append({
                "uid": f"stage-solver:{stage.stage_id}",
                "phase_id": int(stage.stage_id), "kind": "solver",
                "label": f"Solutore / analyze · fase {stage.stage_id}",
                "source_id": str(stage.stage_id),
                "tcl": self._join(solver_lines),
            })
        return specs

    # -------------------------------------------------------------- renderer Tcl
    @staticmethod
    def _render_constraint(manager, constraint, model):
        nodes = manager.resolve_constraint_nodes(constraint, model)
        flags = " ".join(str(f) for f in constraint.dof_flags(manager.ndf))
        if constraint.group_names:
            target = "gruppi: " + ", ".join(constraint.group_names)
        elif constraint.entity_ids:
            target = "entità: " + str(constraint.entity_ids)
        else:
            target = "generale"
        return (f"# Vincolo '{constraint.name}' su {target} ({len(nodes)} nodi):\n"
                f"foreach node {{ {' '.join(str(n) for n in nodes)} }} {{\n"
                f"    fix $node {flags};\n}}")

    @staticmethod
    def _render_equal_dof(manager, eq, model):
        pairs = manager.resolve_equaldof_pairs(eq, model)
        dofs = " ".join(str(d) for d in eq.dofs)
        master = f"Gruppo '{eq.master_group}'" if eq.master_group else f"Entità {eq.master_entity_id}"
        slave = f"Gruppo '{eq.slave_group}'" if eq.slave_group else f"Entità {eq.slave_entity_id}"
        header = (
            f"# EqualDOF '{eq.name}' tra Master ({master}) e Slave ({slave}): "
            f"{len(pairs)} coppie equalDOF"
        )
        return header + "\n" + "\n".join(
            f"equalDOF {m} {s} {dofs};" for m, s in pairs
        )

    def _render_pattern(self, manager, model, tag):
        loads = [ld for ld in manager.loads if ld.pattern_tag == int(tag)]
        disps = [d for d in manager.prescribed_displacements if d.pattern_tag == int(tag)]
        if not loads and not disps:
            return ""
        ts_tags = {item.time_series_tag for item in (*loads, *disps)}
        if len(ts_tags) > 1:
            raise ValueError(f"Il pattern {tag} usa più di una timeSeries")
        ts = next(iter(ts_tags), 1)
        lines = [f"pattern Plain {int(tag)} {ts} {{"]
        for ld in loads:
            nodes = manager.resolve_load_nodes(ld, model)
            if not nodes:
                continue
            n = len(nodes)
            vals = [ld.fx/n, ld.fy/n, ld.fz/n][:manager.ndf]
            if manager.ndf >= 6:
                vals += [ld.mx/n, ld.my/n, ld.mz/n]
            values = " ".join(f"{v:.10g}" for v in vals)
            if ld.group_names:
                target = "gruppi: " + ", ".join(ld.group_names)
            elif ld.entity_ids:
                target = "entità: " + str(ld.entity_ids)
            else:
                target = "target"
            lines.append(
                f"    # Carico '{ld.name}' ({ld.load_type}) su {target}:"
            )
            for nid in nodes:
                lines.append(f"    load {nid} {values};")
        for disp in disps:
            node_ids = set()
            for eid in disp.entity_ids:
                node_ids.update(manager.resolve_entity_nodes(eid, model))
            for nid in sorted(node_ids):
                lines.append(f"    sp {nid} {disp.dof} {disp.value:.12g};")
        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def _render_recorder(manager, recorder, model):
        targets = manager.resolve_recorder_targets(recorder, model)
        if not targets:
            return f"# Recorder omesso: nessun target per {recorder.file_path}"
        target_flag = "-node" if recorder.kind == "Node" else "-ele"
        output = recorder.file_path.replace("\\", "/")
        parts = ["recorder", recorder.kind, "-file", f'"{output}"', "-time",
                 target_flag, "{ " + " ".join(str(x) for x in targets) + " }"]
        if recorder.kind == "Node" and recorder.dofs:
            parts += ["-dof", " ".join(str(d) for d in recorder.dofs)]
        parts.append(recorder.response)
        return " ".join(parts) + ";"

    @staticmethod
    def _render_elements(manager, model):
        from .opensees_export import reorder_element_nodes_for_opensees
        assignments = {
            eid: a for a in manager.element_assignments
            if a.model_name == model.name for eid in a.element_ids
        }
        lines = []
        for eid in sorted(assignments):
            if eid not in model.elements:
                continue
            etype, raw_nodes = model.elements[eid]
            assignment = assignments[eid]
            ordered, _ = reorder_element_nodes_for_opensees(etype, raw_nodes, model.nodes)
            command = assignment.effective_command()
            if assignment.element_args.strip():
                args = assignment.element_args.replace(
                    "{matTag}", str(assignment.material_tag)).strip()
                lines.append(
                    f"element {command} {eid} {' '.join(map(str, ordered))} {args};")
                continue
            mat = assignment.material_tag
            if etype == 1:
                lines.append(f"element truss {eid} {ordered[0]} {ordered[1]} {assignment.area:g} {mat};")
            elif etype == 2:
                lines.append(f"element tri31 {eid} {' '.join(map(str, ordered[:3]))} {assignment.thickness:g} {assignment.plane_type} {mat};")
            elif etype == 3:
                lines.append(f"element quad {eid} {' '.join(map(str, ordered[:4]))} {assignment.thickness:g} {assignment.plane_type} {mat};")
            elif etype == 4:
                lines.append(f"element FourNodeTetrahedron {eid} {' '.join(map(str, ordered[:4]))} {mat};")
            elif etype == 5:
                lines.append(f"element stdBrick {eid} {' '.join(map(str, ordered[:8]))} {mat};")
            elif etype == 10:
                raise ValueError("L'elemento Gmsh 10 (quad9) richiede element_args espliciti per 9_4_QuadUP")
            elif etype == 17:
                if command == "20NodeBrick":
                    lines.append(f"element 20NodeBrick {eid} {' '.join(map(str, ordered[:20]))} {mat};")
                else:
                    raise ValueError("L'elemento Gmsh 17 richiede element_args per 20_8_BrickUP")
            elif etype == 11:
                lines.append(f"element TenNodeTetrahedron {eid} {' '.join(map(str, ordered[:10]))} {mat};")
        return "\n".join(lines)

    @staticmethod
    def _render_interfaces(manager, model):
        if model is None:
            return ""
        tag = max(model.elements, default=0) + 1
        lines = []
        for interface in manager.interfaces:
            if interface.model_name and interface.model_name != model.name:
                continue
            for i in range(len(interface.secondary_nodes) - 1):
                nodes = (
                    interface.secondary_nodes[i], interface.secondary_nodes[i + 1],
                    interface.primary_nodes[i], interface.primary_nodes[i + 1],
                )
                lines.append(
                    f"element zeroLengthInterface2D {tag} -sNdNum 2 -pNdNum 2 "
                    f"-dof {interface.secondary_dof} {interface.primary_dof} "
                    f"-Nodes {{ {' '.join(map(str, nodes))} }} "
                    f"{interface.kn:.12g} {interface.kt:.12g} "
                    f"{interface.friction_angle:.12g};")
                tag += 1
        return "\n".join(lines)

    def phase_commands(self, manager, model=None):
        self.sync_from_manager(manager, model)
        return [
            (phase, [cmd for cmd in phase.commands if cmd.enabled])
            for phase in self.phases if phase.enabled
        ]

    def to_dict(self) -> dict:
        return {
            "current_phase_id": self.current_phase_id,
            "phases": [p.to_dict() for p in self.phases],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OpenSeesFlow":
        obj = cls()
        obj.current_phase_id = int(d.get("current_phase_id", 1))
        obj.phases = [FlowPhase.from_dict(x) for x in d.get("phases", [])]
        if not obj.phases:
            obj.phases = [
                FlowPhase(0, "00 · Definizione modello"),
                FlowPhase(1, "Gravity Loading (Stato Elastico)"),
                FlowPhase(2, "Fase Elastoplastica (Plastic Stage)"),
            ]
        obj.phases.sort(key=lambda p: p.phase_id)
        return obj
