"""Gestione delle condizioni al contorno, vincoli, carichi, leggi temporali,
risolutori e fasi di calcolo per OpenSees.

Fornisce:
  1. StaticConstraint: vincoli statici (fix) sui gradi di libertà traslazionali (X, Y, Z)
     e rotazionali su entità geometriche o gruppi di entità.
  2. EqualDOFConstraint: multi-point constraint (equalDOF) tra coppie di entità o gruppi.
  3. TimeSeries: definizione delle leggi di carico nel tempo (Linear, Constant, Sine, Path).
  4. EntityLoad: carichi nodali e distribuiti associati a entità o gruppi e time series.
  5. SolverSettings: configurazione completa del blocco di risoluzione OpenSees
     (constraints, numberer, system, test, algorithm, integrator, analysis).
  6. AnalysisStage: fasi di calcolo sequenziali con supporto a Gravity Loading
     e transizione elastoplastica tramite 'updateMaterialStage' (wiki OpenSees).
  7. OpenSeesManager: gestore centrale integrato con CADDocument.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set, Tuple, Any
import numpy as np


class TimeSeries:
    """Legge di carico nel tempo per OpenSees (timeSeries)."""

    def __init__(self, tag: int, name: str, stype: str = "Linear",
                 factor: float = 1.0, t_start: float = 0.0, t_end: float = 10.0,
                 period: float = 1.0, shift: float = 0.0,
                 time_points: Optional[List[float]] = None,
                 value_points: Optional[List[float]] = None,
                 file_path: Optional[str] = None):
        self.tag = int(tag)
        self.name = name or f"TimeSeries_{self.tag}"
        self.stype = stype  # "Linear", "Constant", "Sine", "Path"
        self.factor = float(factor)
        self.t_start = float(t_start)
        self.t_end = float(t_end)
        self.period = float(period)
        self.shift = float(shift)
        self.time_points = list(time_points or [])
        self.value_points = list(value_points or [])
        self.file_path = file_path

    def to_tcl(self) -> str:
        """Genera il comando OpenSees TCL corrispondente."""
        t = self.stype.strip().capitalize()
        if t == "Linear":
            return f"timeSeries Linear {self.tag} -factor {self.factor:g};"
        elif t == "Constant":
            return f"timeSeries Constant {self.tag} -factor {self.factor:g};"
        elif t in ("Sine", "Trig"):
            return (f"timeSeries Sine {self.tag} {self.t_start:g} {self.t_end:g} "
                    f"{self.period:g} -shift {self.shift:g} -factor {self.factor:g};")
        elif t == "Path":
            if self.file_path and os.path.isfile(self.file_path):
                return f"timeSeries Path {self.tag} -filePath \"{self.file_path}\" -factor {self.factor:g};"
            elif self.time_points and self.value_points:
                t_str = " ".join(f"{x:g}" for x in self.time_points)
                v_str = " ".join(f"{v:g}" for v in self.value_points)
                return f"timeSeries Path {self.tag} -time {{ {t_str} }} -values {{ {v_str} }} -factor {self.factor:g};"
            else:
                return f"timeSeries Linear {self.tag} -factor {self.factor:g};"
        return f"timeSeries Linear {self.tag} -factor {self.factor:g};"

    def to_dict(self) -> dict:
        return {
            "tag": self.tag, "name": self.name, "stype": self.stype,
            "factor": self.factor, "t_start": self.t_start, "t_end": self.t_end,
            "period": self.period, "shift": self.shift,
            "time_points": self.time_points, "value_points": self.value_points,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TimeSeries":
        return cls(**d)


class StaticConstraint:
    """Vincolo statico applicato a una o più entità geometriche o gruppi (fix $nodeTag x y z)."""

    def __init__(self, cid: int, name: str,
                 entity_ids: Optional[List[int]] = None,
                 fix_x: bool = True, fix_y: bool = True, fix_z: bool = True,
                 fix_rx: bool = False, fix_ry: bool = False, fix_rz: bool = False,
                 group_names: Optional[List[str]] = None):
        self.cid = int(cid)
        self.name = name or f"Vincolo_{self.cid}"
        self.entity_ids = [int(i) for i in (entity_ids or [])]
        self.group_names = [str(g) for g in (group_names or [])]
        self.fix_x = bool(fix_x)
        self.fix_y = bool(fix_y)
        self.fix_z = bool(fix_z)
        self.fix_rx = bool(fix_rx)
        self.fix_ry = bool(fix_ry)
        self.fix_rz = bool(fix_rz)

    def dof_flags(self, ndf: int = 3) -> List[int]:
        flags = [1 if self.fix_x else 0,
                 1 if self.fix_y else 0,
                 1 if self.fix_z else 0]
        if ndf >= 6:
            flags += [1 if self.fix_rx else 0,
                      1 if self.fix_ry else 0,
                      1 if self.fix_rz else 0]
        return flags

    def to_dict(self) -> dict:
        return {
            "cid": self.cid, "name": self.name,
            "entity_ids": self.entity_ids,
            "group_names": self.group_names,
            "fix_x": self.fix_x, "fix_y": self.fix_y, "fix_z": self.fix_z,
            "fix_rx": self.fix_rx, "fix_ry": self.fix_ry, "fix_rz": self.fix_rz,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StaticConstraint":
        return cls(
            cid=d.get("cid", 1),
            name=d.get("name", ""),
            entity_ids=d.get("entity_ids", []),
            fix_x=d.get("fix_x", True),
            fix_y=d.get("fix_y", True),
            fix_z=d.get("fix_z", True),
            fix_rx=d.get("fix_rx", False),
            fix_ry=d.get("fix_ry", False),
            fix_rz=d.get("fix_rz", False),
            group_names=d.get("group_names", []),
        )


class EqualDOFConstraint:
    """Multi-point constraint equalDOF tra due entità geometriche o gruppi (Master e Slave)."""

    def __init__(self, eid: int, name: str,
                 master_entity_id: Optional[int] = None,
                 slave_entity_id: Optional[int] = None,
                 dofs: Optional[List[int]] = None,
                 pairing_mode: str = "spatial_match",
                 master_group: Optional[str] = None,
                 slave_group: Optional[str] = None):
        self.eid = int(eid)
        self.name = name or f"EqualDOF_{self.eid}"
        self.master_entity_id = int(master_entity_id) if master_entity_id is not None else None
        self.slave_entity_id = int(slave_entity_id) if slave_entity_id is not None else None
        self.master_group = str(master_group) if master_group else None
        self.slave_group = str(slave_group) if slave_group else None
        self.dofs = list(dofs or [1, 2, 3])  # 1=Ux, 2=Uy, 3=Uz, 4=Rx, 5=Ry, 6=Rz
        self.pairing_mode = pairing_mode     # "spatial_match" o "master_to_all"

    def to_dict(self) -> dict:
        return {
            "eid": self.eid, "name": self.name,
            "master_entity_id": self.master_entity_id,
            "slave_entity_id": self.slave_entity_id,
            "master_group": self.master_group,
            "slave_group": self.slave_group,
            "dofs": self.dofs, "pairing_mode": self.pairing_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EqualDOFConstraint":
        return cls(
            eid=d.get("eid", 1),
            name=d.get("name", ""),
            master_entity_id=d.get("master_entity_id"),
            slave_entity_id=d.get("slave_entity_id"),
            dofs=d.get("dofs"),
            pairing_mode=d.get("pairing_mode", "spatial_match"),
            master_group=d.get("master_group"),
            slave_group=d.get("slave_group"),
        )


class EntityLoad:
    """Carico applicato a entità geometriche o gruppi con associazione a una TimeSeries."""

    def __init__(self, lid: int, name: str,
                 entity_ids: Optional[List[int]] = None,
                 fx: float = 0.0, fy: float = 0.0, fz: float = 0.0,
                 mx: float = 0.0, my: float = 0.0, mz: float = 0.0,
                 load_type: str = "total", time_series_tag: int = 1,
                 pattern_tag: int = 1,
                 group_names: Optional[List[str]] = None):
        self.lid = int(lid)
        self.name = name or f"Carico_{self.lid}"
        self.entity_ids = [int(i) for i in (entity_ids or [])]
        self.group_names = [str(g) for g in (group_names or [])]
        self.fx = float(fx)
        self.fy = float(fy)
        self.fz = float(fz)
        self.mx = float(mx)
        self.my = float(my)
        self.mz = float(mz)
        self.load_type = load_type  # "total" (ripartito) o "per_node"
        self.time_series_tag = int(time_series_tag)
        self.pattern_tag = int(pattern_tag)

    def to_dict(self) -> dict:
        return {
            "lid": self.lid, "name": self.name,
            "entity_ids": self.entity_ids,
            "group_names": self.group_names,
            "fx": self.fx, "fy": self.fy, "fz": self.fz,
            "mx": self.mx, "my": self.my, "mz": self.mz,
            "load_type": self.load_type, "time_series_tag": self.time_series_tag,
            "pattern_tag": self.pattern_tag,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EntityLoad":
        return cls(
            lid=d.get("lid", 1),
            name=d.get("name", ""),
            entity_ids=d.get("entity_ids", []),
            fx=d.get("fx", 0.0),
            fy=d.get("fy", 0.0),
            fz=d.get("fz", 0.0),
            mx=d.get("mx", 0.0),
            my=d.get("my", 0.0),
            mz=d.get("mz", 0.0),
            load_type=d.get("load_type", "total"),
            time_series_tag=d.get("time_series_tag", 1),
            pattern_tag=d.get("pattern_tag", 1),
            group_names=d.get("group_names", []),
        )


class SolverSettings:
    """Configurazione completa dei comandi di risoluzione del modello OpenSees."""

    def __init__(self,
                 constraints: str = "Transformation",
                 numberer: str = "RCM",
                 system: str = "BandGeneral",
                 test_type: str = "NormDispIncr",
                 test_tol: float = 1e-6,
                 test_iter: int = 25,
                 test_pflag: int = 0,
                 algorithm: str = "Newton",
                 integrator_type: str = "LoadControl",
                 integrator_step: float = 0.1,
                 analysis_type: str = "Static",
                 n_steps: int = 10,
                 dt: float = 0.01):
        self.constraints = constraints
        self.numberer = numberer
        self.system = system
        self.test_type = test_type
        self.test_tol = float(test_tol)
        self.test_iter = int(test_iter)
        self.test_pflag = int(test_pflag)
        self.algorithm = algorithm
        self.integrator_type = integrator_type
        self.integrator_step = float(integrator_step)
        self.analysis_type = analysis_type
        self.n_steps = int(n_steps)
        self.dt = float(dt)

    def to_tcl(self, res_var: str = "ok") -> List[str]:
        """Restituisce le righe TCL per definire il blocco del solutore ed eseguire l'analisi."""
        lines = [
            f"constraints {self.constraints};",
            f"numberer {self.numberer};",
            f"system {self.system};",
            f"test {self.test_type} {self.test_tol:g} {self.test_iter} {self.test_pflag};",
            f"algorithm {self.algorithm};",
        ]
        if self.analysis_type.lower() == "transient":
            lines.append("integrator Newmark 0.5 0.25;")
            lines.append("analysis Transient;")
            lines.append(f"set {res_var} [analyze {self.n_steps} {self.dt:g}];")
        else:
            step = self.integrator_step if self.integrator_step > 0 else (1.0 / max(1, self.n_steps))
            lines.append(f"integrator {self.integrator_type} {step:g};")
            lines.append("analysis Static;")
            lines.append(f"set {res_var} [analyze {self.n_steps}];")
        return lines

    def to_dict(self) -> dict:
        return {
            "constraints": self.constraints, "numberer": self.numberer,
            "system": self.system, "test_type": self.test_type,
            "test_tol": self.test_tol, "test_iter": self.test_iter,
            "test_pflag": self.test_pflag, "algorithm": self.algorithm,
            "integrator_type": self.integrator_type,
            "integrator_step": self.integrator_step,
            "analysis_type": self.analysis_type,
            "n_steps": self.n_steps, "dt": self.dt,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SolverSettings":
        return cls(**d)


class AnalysisStage:
    """Fase di calcolo OpenSees con supporto a Gravity Loading e stato Elastoplastico (updateMaterialStage)."""

    def __init__(self, stage_id: int, name: str, stage_type: str = "gravity",
                 material_stage: int = 0, mat_tag: int = 1,
                 update_stage_cmd: bool = True, load_const: bool = True,
                 solver: Optional[SolverSettings] = None):
        self.stage_id = int(stage_id)
        self.name = name
        self.stage_type = stage_type  # "gravity", "elastoplastic", "static", "transient"
        self.material_stage = int(material_stage)  # 0 = elastico, 1 = plastico
        self.mat_tag = int(mat_tag)
        self.update_stage_cmd = bool(update_stage_cmd)
        self.load_const = bool(load_const)
        self.solver = solver if solver is not None else SolverSettings()

    def to_dict(self) -> dict:
        return {
            "stage_id": self.stage_id, "name": self.name,
            "stage_type": self.stage_type, "material_stage": self.material_stage,
            "mat_tag": self.mat_tag, "update_stage_cmd": self.update_stage_cmd,
            "load_const": self.load_const, "solver": self.solver.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AnalysisStage":
        sol_data = d.get("solver")
        sol = SolverSettings.from_dict(sol_data) if isinstance(sol_data, dict) else None
        d_copy = dict(d)
        d_copy["solver"] = sol
        return cls(**d_copy)


class OpenSeesManager:
    """Registro e coordinatore di tutte le condizioni OpenSees di un CADDocument."""

    def __init__(self, doc):
        self.doc = doc
        self.time_series: Dict[int, TimeSeries] = {}
        self.constraints: List[StaticConstraint] = []
        self.equaldofs: List[EqualDOFConstraint] = []
        self.loads: List[EntityLoad] = []

        self._next_cid = 1
        self._next_eid = 1
        self._next_lid = 1

        # Solutore predefinito
        self.default_solver = SolverSettings()

        # Fasi di calcolo sequenziali (Gravity -> Elastoplastica con updateMaterialStage)
        self.multi_stage: bool = True
        self.stages: List[AnalysisStage] = [
            AnalysisStage(
                stage_id=1,
                name="Gravity Loading (Stato Elastico)",
                stage_type="gravity",
                material_stage=0,
                mat_tag=1,
                update_stage_cmd=True,
                load_const=True,
                solver=SolverSettings(
                    constraints="Transformation",
                    numberer="RCM",
                    system="BandGeneral",
                    test_type="NormDispIncr",
                    test_tol=1e-6,
                    test_iter=25,
                    algorithm="Newton",
                    integrator_type="LoadControl",
                    integrator_step=0.1,
                    analysis_type="Static",
                    n_steps=10
                )
            ),
            AnalysisStage(
                stage_id=2,
                name="Fase Elastoplastica (Plastic Stage)",
                stage_type="elastoplastic",
                material_stage=1,
                mat_tag=1,
                update_stage_cmd=True,
                load_const=False,
                solver=SolverSettings(
                    constraints="Transformation",
                    numberer="RCM",
                    system="BandGeneral",
                    test_type="NormDispIncr",
                    test_tol=1e-6,
                    test_iter=35,
                    algorithm="Newton",
                    integrator_type="LoadControl",
                    integrator_step=0.05,
                    analysis_type="Static",
                    n_steps=20
                )
            )
        ]

        # Legge di carico lineare di default (tag 1)
        self.add_time_series(stype="Linear", name="Legge_Lineare_Default", tag=1)

    # ------------------------------------------------------------- TimeSeries
    def add_time_series(self, stype: str = "Linear", name: str = "",
                        tag: Optional[int] = None, **kwargs) -> TimeSeries:
        if tag is None:
            tag = 1
            while tag in self.time_series:
                tag += 1
        ts = TimeSeries(tag=tag, name=name or f"Legge_{tag}_{stype}", stype=stype, **kwargs)
        self.time_series[tag] = ts
        return ts

    def remove_time_series(self, tag: int) -> bool:
        if tag in self.time_series:
            del self.time_series[tag]
            return True
        return False

    # --------------------------------------------------- Vincoli Statici (fix)
    def add_constraint(self, name: str,
                       entity_ids: Optional[List[int]] = None,
                       fix_x: bool = True, fix_y: bool = True, fix_z: bool = True,
                       fix_rx: bool = False, fix_ry: bool = False, fix_rz: bool = False,
                       group_names: Optional[List[str]] = None) -> StaticConstraint:
        cid = self._next_cid
        self._next_cid += 1
        sc = StaticConstraint(cid, name, entity_ids, fix_x, fix_y, fix_z, fix_rx, fix_ry, fix_rz, group_names)
        self.constraints.append(sc)
        return sc

    def remove_constraint(self, cid: int) -> bool:
        for i, c in enumerate(self.constraints):
            if c.cid == cid:
                self.constraints.pop(i)
                return True
        return False

    # -------------------------------------------------------------- EqualDOF
    def add_equaldof(self, name: str,
                     master_entity_id: Optional[int] = None,
                     slave_entity_id: Optional[int] = None,
                     dofs: Optional[List[int]] = None,
                     pairing_mode: str = "spatial_match",
                     master_group: Optional[str] = None,
                     slave_group: Optional[str] = None) -> EqualDOFConstraint:
        eid = self._next_eid
        self._next_eid += 1
        eq = EqualDOFConstraint(eid, name, master_entity_id, slave_entity_id, dofs, pairing_mode,
                                master_group, slave_group)
        self.equaldofs.append(eq)
        return eq

    def remove_equaldof(self, eid: int) -> bool:
        for i, eq in enumerate(self.equaldofs):
            if eq.eid == eid:
                self.equaldofs.pop(i)
                return True
        return False

    # ----------------------------------------------------------------- Carichi
    def add_load(self, name: str,
                 entity_ids: Optional[List[int]] = None,
                 fx: float = 0.0, fy: float = 0.0, fz: float = 0.0,
                 mx: float = 0.0, my: float = 0.0, mz: float = 0.0,
                 load_type: str = "total", time_series_tag: int = 1,
                 pattern_tag: int = 1,
                 group_names: Optional[List[str]] = None) -> EntityLoad:
        lid = self._next_lid
        self._next_lid += 1
        ld = EntityLoad(lid, name, entity_ids, fx, fy, fz, mx, my, mz,
                        load_type, time_series_tag, pattern_tag, group_names)
        self.loads.append(ld)
        return ld

    def remove_load(self, lid: int) -> bool:
        for i, ld in enumerate(self.loads):
            if ld.lid == lid:
                self.loads.pop(i)
                return True
        return False

    # ------------------------------------------------------ Risoluzione Nodi
    def resolve_entity_nodes(self, entity_id: int, model=None, tol: float = 1e-2) -> List[int]:
        """Risolve tutti i nodi della mesh associati a un'entità geometrica o blocco mesh."""
        if model is None and getattr(self.doc, "mesh_models", None):
            model = list(self.doc.mesh_models.values())[-1]
        if model is None:
            return []

        ent = self.doc.entities.get(entity_id)
        if ent is None:
            return []

        # 1. Entità derivata da MeshBlock
        if "mesh_ref" in ent.meta:
            mname, dim, tag = ent.meta["mesh_ref"]
            m = self.doc.mesh_models.get(mname, model)
            blk = m.blocks.get((dim, tag))
            if blk:
                nodes: Set[int] = set()
                for eid in blk.element_ids:
                    el = m.elements.get(eid)
                    if el:
                        nodes.update(el[1])
                return sorted(list(nodes))

        # 2. Entità marcata con Physical Tag Gmsh
        if getattr(ent, "marker", 0) > 0:
            pt = ent.marker
            nodes: Set[int] = set()
            for (dim, tag), blk in model.blocks.items():
                if pt in blk.physical_tags:
                    for eid in blk.element_ids:
                        el = model.elements.get(eid)
                        if el:
                            nodes.update(el[1])
            if nodes:
                return sorted(list(nodes))

        # 3. Entità CAD con TopoDS_Shape: test spaziale sui nodi
        if getattr(ent, "shape", None) is not None:
            from . import occ_utils as ou
            try:
                xmin, ymin, zmin, xmax, ymax, zmax = ou.bbox_of(ent.shape)
            except Exception:
                return []

            matched_nodes: List[int] = []
            cand_nodes = []
            for nid, (x, y, z) in model.nodes.items():
                if (xmin - tol <= x <= xmax + tol and
                    ymin - tol <= y <= ymax + tol and
                    zmin - tol <= z <= zmax + tol):
                    cand_nodes.append((nid, x, y, z))

            for nid, x, y, z in cand_nodes:
                try:
                    v = ou.make_vertex((x, y, z))
                    d = ou.distance(v, ent.shape)
                    if d <= tol:
                        matched_nodes.append(nid)
                except Exception:
                    matched_nodes.append(nid)
            return sorted(matched_nodes)

        return []

    def resolve_group_nodes(self, group_name: str, model=None) -> List[int]:
        """Risolve tutti i nodi appartenenti a un gruppo (entità associate, elementi mesh, nodi diretti)."""
        if model is None and getattr(self.doc, "mesh_models", None):
            model = list(self.doc.mesh_models.values())[-1]
        if model is None:
            return []

        # 1. Utilizza l'estrattore consolidato di opensees_export
        try:
            from .opensees_export import extract_defined_groups_nodes
            groups_data = extract_defined_groups_nodes(self.doc, model)
            if group_name in groups_data:
                return sorted(list(groups_data[group_name]["node_ids"]))
        except Exception:
            pass

        nodes: Set[int] = set()

        # 2. Fallback su doc.groups
        if hasattr(self.doc, "groups"):
            grp = self.doc.groups.get(group_name)
            if grp:
                for mname, nids in grp.mesh_nodes.items():
                    nodes.update(nids)
                for mname, eids in grp.mesh_elements.items():
                    m = self.doc.mesh_models.get(mname, model)
                    if m:
                        for eid in eids:
                            el = m.elements.get(eid)
                            if el:
                                nodes.update(el[1])
                for eid in grp.member_ids:
                    nodes.update(self.resolve_entity_nodes(eid, model))

        # 3. Fallback su model.physicals
        phys_map = getattr(model, "physicals", {})
        for (dim, tag), blk in model.blocks.items():
            for pt in blk.physical_tags:
                pname = phys_map.get((dim, pt), "")
                if pname == group_name or str(pt) == group_name:
                    for eid in blk.element_ids:
                        el = model.elements.get(eid)
                        if el:
                            nodes.update(el[1])

        return sorted(list(nodes))

    def resolve_constraint_nodes(self, sc: StaticConstraint, model=None) -> List[int]:
        """Risolve tutti i nodi coperti da un vincolo statico (sia da entity_ids che da group_names)."""
        nodes: Set[int] = set()
        for eid in sc.entity_ids:
            nodes.update(self.resolve_entity_nodes(eid, model))
        for gname in sc.group_names:
            nodes.update(self.resolve_group_nodes(gname, model))
        return sorted(list(nodes))

    def resolve_load_nodes(self, ld: EntityLoad, model=None) -> List[int]:
        """Risolve tutti i nodi coperti da un carico (sia da entity_ids che da group_names)."""
        nodes: Set[int] = set()
        for eid in ld.entity_ids:
            nodes.update(self.resolve_entity_nodes(eid, model))
        for gname in ld.group_names:
            nodes.update(self.resolve_group_nodes(gname, model))
        return sorted(list(nodes))

    def resolve_equaldof_pairs(self, eq: EqualDOFConstraint, model=None) -> List[Tuple[int, int]]:
        """Risolve le coppie (master, slave) per un vincolo equalDOF tra entità o gruppi."""
        m_nodes: Set[int] = set()
        if eq.master_entity_id is not None:
            m_nodes.update(self.resolve_entity_nodes(eq.master_entity_id, model))
        if eq.master_group:
            m_nodes.update(self.resolve_group_nodes(eq.master_group, model))

        s_nodes: Set[int] = set()
        if eq.slave_entity_id is not None:
            s_nodes.update(self.resolve_entity_nodes(eq.slave_entity_id, model))
        if eq.slave_group:
            s_nodes.update(self.resolve_group_nodes(eq.slave_group, model))

        return self.match_equaldof_nodes(sorted(list(m_nodes)), sorted(list(s_nodes)),
                                         model.nodes if model else {}, eq.pairing_mode)

    def match_equaldof_nodes(self, master_nodes: List[int], slave_nodes: List[int],
                             coords: Dict[int, Tuple[float, float, float]],
                             pairing_mode: str = "spatial_match") -> List[Tuple[int, int]]:
        """Calcola le coppie di nodi (master, slave) per il comando equalDOF."""
        if not master_nodes or not slave_nodes:
            return []

        if pairing_mode == "master_to_all" or len(master_nodes) == 1:
            m0 = master_nodes[0]
            return [(m0, s) for s in slave_nodes]

        # spatial_match
        m_pts = np.array([coords.get(m, (0.0, 0.0, 0.0)) for m in master_nodes])
        s_pts = np.array([coords.get(s, (0.0, 0.0, 0.0)) for s in slave_nodes])
        m_center = np.mean(m_pts, axis=0)
        s_center = np.mean(s_pts, axis=0)
        offset = m_center - s_center

        pairs = []
        available_master = list(master_nodes)
        for s in slave_nodes:
            sp = np.array(coords.get(s, (0.0, 0.0, 0.0))) + offset
            dists = [np.linalg.norm(np.array(coords.get(m, (0.0, 0.0, 0.0))) - sp) for m in available_master]
            idx = int(np.argmin(dists))
            best_m = available_master[idx]
            pairs.append((best_m, s))
            if len(master_nodes) == len(slave_nodes) and len(available_master) > 1:
                available_master.pop(idx)
        return pairs

    # ---------------------------------------------------- Generazione TCL Completa
    def generate_tcl_script(self, model=None, ndf: int = 3,
                            analysis_type: Optional[str] = None,
                            n_steps: Optional[int] = None) -> str:
        """Genera lo script completo OpenSees TCL:

        - Nodi ed elementi con connettività coerente (2D CCW / 3D V>0)
        - Vincoli statici (fix) su entità e gruppi di entità
        - EqualDOF tra coppie di entità o gruppi
        - Leggi di carico nel tempo (timeSeries)
        - Pattern di carico (Plain) con carichi su entità o gruppi
        - Fasi di calcolo sequenziali con Gravity Loading (updateMaterialStage 0)
          e transizione Elastoplastica (updateMaterialStage 1)
        """
        if model is None and getattr(self.doc, "mesh_models", None):
            model = list(self.doc.mesh_models.values())[-1]

        from .opensees_export import reorder_element_nodes_for_opensees

        lines = [
            "#" + "=" * 78,
            "# Script OpenSees TCL Completo — Generato da GmshCAD Studio",
            f"# Modello: {model.name if model else 'CAD'}",
            f"# Gradi di Libertà per nodo (ndf): {ndf}",
            "#" + "=" * 78,
            "wipe;",
            f"model BasicBuilder -ndm 3 -ndf {ndf};",
            "",
            "#" + "-" * 78,
            "# 1. DEFINIZIONE NODI",
            "#" + "-" * 78,
        ]

        if model:
            for nid in sorted(model.nodes.keys()):
                c = model.nodes[nid]
                lines.append(f"node {nid} {c[0]:.10g} {c[1]:.10g} {c[2]:.10g};")

        lines += [
            "",
            "#" + "-" * 78,
            "# 2. DEFINIZIONE MATERIALI ED ELEMENTI (Connettività OpenSees verificata)",
            "#" + "-" * 78,
            "set matTag 1;",
            "# Definizione materiale elastico/elastoplastico:",
            "# (Supporta il comando wiki OpenSees: updateMaterialStage -material $matTag -stage $stageNum)",
            "nDMaterial ElasticIsotropic $matTag 30000.0 0.2;",
            "# Per terreni/modelli non-lineari UCSD: nDMaterial PressureDependMultiYield $matTag ...",
            "",
        ]

        if model:
            for eid in sorted(model.elements.keys()):
                etype, raw_nodes = model.elements[eid]
                ordered, _ = reorder_element_nodes_for_opensees(etype, raw_nodes, model.nodes)
                if etype == 4:
                    lines.append(f"element FourNodeTetrahedron {eid} {ordered[0]} {ordered[1]} {ordered[2]} {ordered[3]} $matTag;")
                elif etype == 5:
                    n_str = " ".join(str(n) for n in ordered[:8])
                    lines.append(f"element stdBrick {eid} {n_str} $matTag;")
                elif etype == 2:
                    lines.append(f"element tri31 {eid} {ordered[0]} {ordered[1]} {ordered[2]} 1.0 \"PlaneStress\" $matTag;")
                elif etype == 3:
                    lines.append(f"element quad {eid} {ordered[0]} {ordered[1]} {ordered[2]} {ordered[3]} 1.0 \"PlaneStress\" $matTag;")

        lines += [
            "",
            "#" + "-" * 78,
            "# 3. VINCOLI STATICI (Boundary Conditions — fix)",
            "#" + "-" * 78,
        ]

        if not self.constraints:
            lines.append("# (Nessun vincolo statico esplicito definito)")
        else:
            for sc in self.constraints:
                all_nodes = self.resolve_constraint_nodes(sc, model)
                if all_nodes:
                    flags_str = " ".join(str(f) for f in sc.dof_flags(ndf))
                    targets = []
                    if sc.group_names:
                        targets.append(f"gruppi: {', '.join(sc.group_names)}")
                    if sc.entity_ids:
                        targets.append(f"entità: {sc.entity_ids}")
                    desc = " | ".join(targets) or "generale"
                    lines.append(f"# Vincolo '{sc.name}' su {desc} ({len(all_nodes)} nodi):")
                    nodes_list_str = " ".join(str(n) for n in all_nodes)
                    lines.append(f"foreach node {{ {nodes_list_str} }} {{")
                    lines.append(f"    fix $node {flags_str};")
                    lines.append("}")

        lines += [
            "",
            "#" + "-" * 78,
            "# 4. EQUAL DOF (Multi-Point Constraints)",
            "#" + "-" * 78,
        ]

        if not self.equaldofs:
            lines.append("# (Nessun vincolo equalDOF definito)")
        else:
            for eq in self.equaldofs:
                pairs = self.resolve_equaldof_pairs(eq, model)
                dof_str = " ".join(str(d) for d in eq.dofs)
                m_desc = f"Gruppo '{eq.master_group}'" if eq.master_group else f"Entità {eq.master_entity_id}"
                s_desc = f"Gruppo '{eq.slave_group}'" if eq.slave_group else f"Entità {eq.slave_entity_id}"
                lines.append(f"# EqualDOF '{eq.name}' tra Master ({m_desc}) e Slave ({s_desc}): {len(pairs)} coppie")
                for m_id, s_id in pairs:
                    lines.append(f"equalDOF {m_id} {s_id} {dof_str};")

        lines += [
            "",
            "#" + "-" * 78,
            "# 5. LEGGI DI CARICO NEL TEMPO (Time Series)",
            "#" + "-" * 78,
        ]

        for tag in sorted(self.time_series.keys()):
            ts = self.time_series[tag]
            lines.append(f"# {ts.name}:")
            lines.append(ts.to_tcl())

        lines += [
            "",
            "#" + "-" * 78,
            "# 6. PATTERN DI CARICO (Load Patterns — load)",
            "#" + "-" * 78,
        ]

        # Raggruppa i carichi per pattern_tag
        loads_by_pattern: Dict[int, List[EntityLoad]] = {}
        for ld in self.loads:
            loads_by_pattern.setdefault(ld.pattern_tag, []).append(ld)

        if not loads_by_pattern:
            lines.append("# (Nessun carico esplicito definito)")
        else:
            for pat_tag, lds in sorted(loads_by_pattern.items()):
                ts_tag = lds[0].time_series_tag
                lines.append(f"pattern Plain {pat_tag} {ts_tag} {{")
                for ld in lds:
                    ld_nodes = self.resolve_load_nodes(ld, model)
                    if not ld_nodes:
                        continue
                    n_cnt = len(ld_nodes)
                    if ld.load_type == "total":
                        fx_i = ld.fx / n_cnt
                        fy_i = ld.fy / n_cnt
                        fz_i = ld.fz / n_cnt
                        mx_i = ld.mx / n_cnt
                        my_i = ld.my / n_cnt
                        mz_i = ld.mz / n_cnt
                    else:
                        fx_i, fy_i, fz_i = ld.fx, ld.fy, ld.fz
                        mx_i, my_i, mz_i = ld.mx, ld.my, ld.mz

                    load_vals = [f"{fx_i:.10g}", f"{fy_i:.10g}", f"{fz_i:.10g}"]
                    if ndf >= 6:
                        load_vals += [f"{mx_i:.10g}", f"{my_i:.10g}", f"{mz_i:.10g}"]
                    l_str = " ".join(load_vals)

                    targets = []
                    if ld.group_names:
                        targets.append(f"gruppi: {', '.join(ld.group_names)}")
                    if ld.entity_ids:
                        targets.append(f"entità: {ld.entity_ids}")
                    desc = " | ".join(targets) or "generale"
                    lines.append(f"    # Carico '{ld.name}' ({ld.load_type}) su {desc}:")
                    for nid in ld_nodes:
                        lines.append(f"    load {nid} {l_str};")
                lines.append("}")

        lines += [
            "",
            "#" + "-" * 78,
            "# 7. IMPOSTAZIONE ANALISI E RISOLUTORE (FASI DI CALCOLO)",
            "#" + "-" * 78,
        ]

        # Se sono definite fasi di calcolo (es. Gravity -> Elastoplastica)
        if self.multi_stage and self.stages and (analysis_type is None and n_steps is None):
            for stg in self.stages:
                lines += [
                    "",
                    "#" + "=" * 78,
                    f"# FASE {stg.stage_id}: {stg.name.upper()} (Tipo: {stg.stage_type})",
                    "#" + "=" * 78,
                ]
                if stg.update_stage_cmd:
                    lines.append(f"# Aggiornamento stage materiale a {stg.material_stage} (wiki OpenSees: updateMaterialStage)")
                    lines.append(f"updateMaterialStage -material {stg.mat_tag} -stage {stg.material_stage};")
                    lines.append("")

                res_var = f"ok_stage{stg.stage_id}"
                sol_lines = stg.solver.to_tcl(res_var=res_var)
                lines.extend(sol_lines)

                lines += [
                    f"if {{$ {res_var} == 0}} {{",
                    f'    puts "FASE {stg.stage_id} ({stg.name}) COMPLETATA CON SUCCESSO!";',
                    "} else {",
                    f'    puts "ATTENZIONE: Fase {stg.stage_id} non convergente (codice di uscita: ${res_var})";',
                    "}",
                ]

                if stg.stage_type == "gravity" and stg.load_const:
                    lines += [
                        "",
                        "# Mantiene costante il carico gravitazionale per le fasi successive e azzera il tempo:",
                        "loadConst -time 0.0;",
                    ]
        else:
            # Singola fase / risolutore personalizzato
            solver = self.default_solver
            if analysis_type:
                solver.analysis_type = analysis_type
            if n_steps:
                solver.n_steps = n_steps
            sol_lines = solver.to_tcl(res_var="ok")
            lines.extend(sol_lines)
            lines += [
                "if {$ok == 0} {",
                '    puts "ANALISI OPENSEES COMPLETATA CON SUCCESSO!";',
                "} else {",
                '    puts "ATTENZIONE: Analisi non convergente (codice di uscita: $ok)";',
                "}",
            ]

        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "time_series": {tag: ts.to_dict() for tag, ts in self.time_series.items()},
            "constraints": [sc.to_dict() for sc in self.constraints],
            "equaldofs": [eq.to_dict() for eq in self.equaldofs],
            "loads": [ld.to_dict() for ld in self.loads],
            "default_solver": self.default_solver.to_dict(),
            "multi_stage": self.multi_stage,
            "stages": [stg.to_dict() for stg in self.stages],
        }

    @classmethod
    def from_dict(cls, doc, d: dict) -> "OpenSeesManager":
        mgr = cls(doc)
        mgr.time_series.clear()
        for ts_data in d.get("time_series", {}).values():
            ts = TimeSeries.from_dict(ts_data)
            mgr.time_series[ts.tag] = ts
        mgr.constraints = [StaticConstraint.from_dict(cd) for cd in d.get("constraints", [])]
        mgr.equaldofs = [EqualDOFConstraint.from_dict(ed) for ed in d.get("equaldofs", [])]
        mgr.loads = [EntityLoad.from_dict(ld) for ld in d.get("loads", [])]
        if "default_solver" in d:
            mgr.default_solver = SolverSettings.from_dict(d["default_solver"])
        mgr.multi_stage = d.get("multi_stage", True)
        if "stages" in d:
            mgr.stages = [AnalysisStage.from_dict(sd) for sd in d["stages"]]
        return mgr
