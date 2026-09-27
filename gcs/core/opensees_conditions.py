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

from .geotech_catalog import GEOTECH_ELEMENTS, geotech_element_options, is_up_element
from .opensees_catalog import (
    UNIAXIAL_MATERIALS, ND_MATERIALS, ELEMENT_CATALOG, SECTION_CATALOG,
    GEOM_TRANSF, BEAM_INTEGRATION, TIME_SERIES_TYPES, PATTERN_TYPES,
    CONSTRAINT_HANDLERS, NUMBERERS, SYSTEMS, ALGORITHMS, INTEGRATORS, TESTS,
    ANALYSIS_TYPES, RECORDER_TYPES, RECORDER_OPTIONS, PARAMETER_TARGETS,
    UPDATE_COMMANDS, ELEMENT_LOAD_TYPES, GMSH_TO_OPENSEES,
    get_material_schema, is_uniaxial, is_ndmaterial,
)


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
        return flags[:ndf]

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
                 solver: Optional[SolverSettings] = None,
                 update_command: Optional[str] = None,
                 parameter_tag: int = 0, parameter_value: float = 0.0):
        self.stage_id = int(stage_id)
        self.name = name
        self.stage_type = stage_type  # "gravity", "elastoplastic", "static", "transient"
        self.material_stage = int(material_stage)  # 0 = elastico, 1 = plastico
        self.mat_tag = int(mat_tag)
        self.update_stage_cmd = bool(update_stage_cmd)
        self.load_const = bool(load_const)
        self.solver = solver if solver is not None else SolverSettings()
        self.update_command = update_command or (
            "updateMaterialStage" if self.update_stage_cmd else "none")
        if self.update_command not in ("none", "updateMaterialStage", "updateParameter"):
            raise ValueError(f"Comando update non supportato: {self.update_command}")
        self.parameter_tag = int(parameter_tag)
        self.parameter_value = float(parameter_value)

    def to_dict(self) -> dict:
        return {
            "stage_id": self.stage_id, "name": self.name,
            "stage_type": self.stage_type, "material_stage": self.material_stage,
            "mat_tag": self.mat_tag, "update_stage_cmd": self.update_stage_cmd,
            "load_const": self.load_const, "solver": self.solver.to_dict(),
            "update_command": self.update_command,
            "parameter_tag": self.parameter_tag,
            "parameter_value": self.parameter_value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AnalysisStage":
        sol_data = d.get("solver")
        sol = SolverSettings.from_dict(sol_data) if isinstance(sol_data, dict) else None
        d_copy = dict(d)
        d_copy["solver"] = sol
        return cls(**d_copy)


class MaterialDefinition:
    """Definizione materiale OpenSees con parametri numerici validati.

    Supporta tutto il catalogo in `opensees_catalog.UNIAXIAL_MATERIALS` e
    `opensees_catalog.ND_MATERIALS`. Il numero di parametri richiesti dipende
    dal modello specifico.
    """

    # Backward compatibility: vecchia lista di modelli con numero fisso di params.
    LEGACY_SCHEMAS = {
        "ElasticIsotropic": ("nDMaterial", 3),
        "PressureDependMultiYield": ("nDMaterial", 17),
        "Elastic": ("uniaxialMaterial", 1),
        "Steel01": ("uniaxialMaterial", 3),
        "Concrete01": ("uniaxialMaterial", 4),
    }

    def __init__(self, tag: int, name: str, model: str, parameters: List[float],
                 extra: Optional[Dict[str, Any]] = None):
        schema = get_material_schema(model)
        if schema is None:
            raise ValueError(f"Modello materiale OpenSees non supportato: {model}")
        self.command = ("uniaxialMaterial" if is_uniaxial(model)
                        else "nDMaterial" if is_ndmaterial(model)
                        else schema.get("command", "uniaxialMaterial"))
        self.tag = int(tag)
        self.name = name or f"{model}_{tag}"
        self.model = model
        self.parameters = [float(value) for value in parameters]
        self.extra = dict(extra or {})
        # Schema di riferimento (per introspezione GUI / docs).
        self.schema = schema

    def to_tcl(self) -> str:
        schema_params = self.schema.get("params", [])
        formatted = []
        for index, value in enumerate(self.parameters):
            ptype = schema_params[index][1] if index < len(schema_params) and len(schema_params[index]) > 1 else "float"
            if ptype == "int":
                formatted.append(str(int(round(value))))
            elif ptype == "bool":
                formatted.append("1" if bool(value) else "0")
            else:
                formatted.append(f"{value:.12g}")
        values = " ".join(formatted)
        # Materiali che richiedono argomenti speciali (es. -strain, -stress)
        if self.model == "ElasticMultiLinear":
            s = " ".join(f"{v:.12g}" for v in self.extra.get("strains", []))
            t = " ".join(f"{v:.12g}" for v in self.extra.get("stresses", []))
            return f"{self.command} {self.model} {self.tag} -strain {s} -stress {t};"
        suffix = str(self.extra.get("tcl_suffix", "")).strip()
        if suffix:
            return f"{self.command} {self.model} {self.tag} {values} {suffix};"
        if self.model in ("Parallel", "Series"):
            mat_tags = self.extra.get("mat_tags", "1 2")
            cmd = f"{self.command} {self.model} {self.tag} {mat_tags};"
            return cmd
        if self.model in ("InitStrainMaterial", "InitStressMaterial", "MinMaxMaterial",
                          "Fatigue", "PathIndependent"):
            inner = self.extra.get("material_tag", 1)
            extra_kv = ""
            if self.model == "InitStrainMaterial":
                extra_kv = f" -strain {self.extra.get('strain', 0.0):.12g}"
            elif self.model == "InitStressMaterial":
                extra_kv = f" -stress {self.extra.get('stress', 0.0):.12g}"
            elif self.model == "MinMaxMaterial":
                extra_kv = (f" -min {self.extra.get('min', -1e9):.12g}"
                            f" -max {self.extra.get('max', 1e9):.12g}")
            return f"{self.command} {self.model} {self.tag} -material {inner}{extra_kv};"
        return f"{self.command} {self.model} {self.tag} {values};"

    def to_dict(self) -> dict:
        return {"tag": self.tag, "name": self.name, "model": self.model,
                "parameters": self.parameters, "extra": self.extra}

    @classmethod
    def from_dict(cls, d: dict) -> "MaterialDefinition":
        return cls(d["tag"], d.get("name", ""), d["model"],
                   d.get("parameters", []), d.get("extra"))


class SectionDefinition:
    """Definizione sezione OpenSees (command `section`).

    Attualmente supporta i modelli in `opensees_catalog.SECTION_CATALOG`.
    Le sezioni Fiber possono contenere patch/layer/fiber (sub-objects).
    """

    def __init__(self, tag: int, name: str, model: str,
                 parameters: List[float], ndm: int = 2,
                 fibers: Optional[List[dict]] = None,
                 extra: Optional[Dict[str, Any]] = None):
        if model not in SECTION_CATALOG:
            raise ValueError(f"Tipo sezione OpenSees non supportato: {model}")
        self.tag = int(tag)
        self.name = name or f"Section_{model}_{tag}"
        self.model = model
        self.parameters = [float(value) for value in parameters]
        self.ndm = int(ndm)
        self.fibers = list(fibers or [])
        self.extra = dict(extra or {})
        self.schema = SECTION_CATALOG[model]

    def to_tcl(self) -> str:
        schema = SECTION_CATALOG.get(self.model, {})
        if self.model == "Fiber":
            lines = [f"section Fiber {self.tag} {'-GJ ' + f'{self.parameters[0]:.12g}' if self.parameters else ''}{{"]
            for fib in self.fibers:
                if fib.get("type") == "patch":
                    lines.append(f"  patch {fib.get('sub_type', 'rect')} {fib.get('mat_tag', 1)} "
                                 + " ".join(f"{v:.12g}" for v in fib.get("params", [])))
                elif fib.get("type") == "layer":
                    lines.append(f"  layer {fib.get('sub_type', 'straight')} {fib.get('mat_tag', 1)} "
                                 + f"{fib.get('n_bars', 1)} {fib.get('area', 1.0):.12g} "
                                 + " ".join(f"{v:.12g}" for v in fib.get("params", [])))
                elif fib.get("type") == "fiber":
                    lines.append(f"  fiber {fib.get('y', 0):.12g} {fib.get('z', 0):.12g} "
                                 f"{fib.get('area', 1.0):.12g} {fib.get('mat_tag', 1)}")
            lines.append("}")
            return "\n".join(lines)
        if self.model == "Aggregator":
            sec_tag = self.extra.get("sec_tag", 1)
            mat_tags = self.extra.get("mat_tags", "1")
            dirs = self.extra.get("dirs", "1")
            return f"section Aggregator {self.tag} {mat_tags} {dirs} -section {sec_tag};"
        if self.model == "PlateFiber":
            mat_tag = int(self.parameters[0]) if self.parameters else 1
            return f"section PlateFiber {self.tag} {mat_tag};"
        if self.model == "LayeredShell":
            n_layers = int(self.extra.get("n_layers", 1))
            mat_tags = self.extra.get("mat_tags", "1")
            ths = self.extra.get("thicknesses", "0.1")
            return f"section LayeredShell {self.tag} {n_layers} {mat_tags} {ths};"
        # Default per Elastic, Uniaxial, Bidirectional, ecc.
        values = " ".join(f"{value:.12g}" for value in self.parameters)
        return f"section {self.model} {self.tag} {values};"

    def to_dict(self) -> dict:
        return {"tag": self.tag, "name": self.name, "model": self.model,
                "parameters": self.parameters, "ndm": self.ndm,
                "fibers": self.fibers, "extra": self.extra}


class GeomTransfDefinition:
    """Trasformazione geometrica per elementi beam-column (command `geomTransf`).

    Tipi supportati: Linear, PDelta, Corotational.
    """

    def __init__(self, tag: int, name: str, transf_type: str,
                 ndm: int = 3,
                 vecxz: Tuple[float, float, float] = (0.0, 0.0, 1.0),
                 joint_offset: Optional[List[float]] = None):
        if transf_type not in GEOM_TRANSF:
            raise ValueError(f"Tipo geomTransf non supportato: {transf_type}")
        if ndm not in (2, 3):
            raise ValueError("ndm deve essere 2 o 3")
        if ndm not in GEOM_TRANSF[transf_type]["ndm"]:
            raise ValueError(f"geomTransf {transf_type} non disponibile per ndm={ndm}")
        self.tag = int(tag)
        self.name = name or f"{transf_type}_{tag}"
        self.transf_type = transf_type
        self.ndm = int(ndm)
        self.vecxz = tuple(float(v) for v in vecxz)
        self.joint_offset = list(joint_offset or [])

    def to_tcl(self) -> str:
        parts = ["geomTransf", self.transf_type, str(self.tag)]
        if self.ndm == 3:
            parts.extend(f"{v:.12g}" for v in self.vecxz)
        if self.joint_offset:
            if self.ndm == 2:
                if len(self.joint_offset) >= 4:
                    parts.extend(["-jntOffset"] + [f"{v:.12g}" for v in self.joint_offset[:4]])
            else:
                if len(self.joint_offset) >= 6:
                    parts.extend(["-jntOffset"] + [f"{v:.12g}" for v in self.joint_offset[:6]])
        return " ".join(parts) + ";"

    def to_dict(self) -> dict:
        return {"tag": self.tag, "name": self.name, "transf_type": self.transf_type,
                "ndm": self.ndm, "vecxz": list(self.vecxz),
                "joint_offset": self.joint_offset}


class BeamIntegrationDefinition:
    """Regola di integrazione per elementi forceBeamColumn / dispBeamColumn."""

    def __init__(self, tag: int, name: str, integration_type: str,
                 n_points: int = 3, sec_tag: int = 1,
                 locations: Optional[List[float]] = None,
                 weights: Optional[List[float]] = None,
                 lpI: Optional[float] = None, lpJ: Optional[float] = None):
        if integration_type not in BEAM_INTEGRATION:
            raise ValueError(f"Tipo beamIntegration non supportato: {integration_type}")
        self.tag = int(tag)
        self.name = name or f"{integration_type}_{tag}"
        self.integration_type = integration_type
        self.n_points = int(n_points)
        self.sec_tag = int(sec_tag)
        self.locations = list(locations or [])
        self.weights = list(weights or [])
        self.lpI = float(lpI) if lpI is not None else 0.0
        self.lpJ = float(lpJ) if lpJ is not None else 0.0

    def to_tcl(self) -> str:
        if self.integration_type in ("HingeRadau", "HingeMidpoint",
                                      "HingeRadauTwo"):
            return (f"beamIntegration {self.integration_type} {self.tag} "
                    f"{self.sec_tag} {self.lpI:.12g} {self.lpJ:.12g};")
        if self.integration_type in ("UserDefined", "FixedLocation"):
            pts = " ".join(f"{p:.12g}" for p in self.locations)
            if self.integration_type == "UserDefined":
                sec_tags = " ".join(str(self.sec_tag) for _ in self.locations)
                wts = " ".join(f"{w:.12g}" for w in self.weights)
                return (f"beamIntegration {self.integration_type} {self.tag} "
                        f"{len(self.locations)} {sec_tags} {wts};")
            return (f"beamIntegration {self.integration_type} {self.tag} "
                    f"{len(self.locations)} {pts} {self.sec_tag};")
        return (f"beamIntegration {self.integration_type} {self.tag} "
                f"{self.n_points} {self.sec_tag};")

    def to_dict(self) -> dict:
        return {"tag": self.tag, "name": self.name,
                "integration_type": self.integration_type,
                "n_points": self.n_points, "sec_tag": self.sec_tag,
                "locations": self.locations, "weights": self.weights,
                "lpI": self.lpI, "lpJ": self.lpJ}


class NodalMass:
    """Massa nodale (command `mass nodeTag m1 m2 ... mN`)."""

    def __init__(self, node_tag: int, mass_values: List[float]):
        if not mass_values:
            raise ValueError("Massa nodale richiede almeno un valore")
        self.node_tag = int(node_tag)
        self.mass_values = [float(m) for m in mass_values]

    def to_tcl(self) -> str:
        vals = " ".join(f"{m:.12g}" for m in self.mass_values)
        return f"mass {self.node_tag} {vals};"

    def to_dict(self) -> dict:
        return {"node_tag": self.node_tag, "mass_values": self.mass_values}


class RayleighDamping:
    """Smorzamento di Rayleigh globale (command `rayleigh alphaM betaK betaK0 betaKc`)."""

    def __init__(self, alpha_m: float = 0.0, beta_k: float = 0.0,
                 beta_k0: float = 0.0, beta_kc: float = 0.0):
        self.alpha_m = float(alpha_m)
        self.beta_k = float(beta_k)
        self.beta_k0 = float(beta_k0)
        self.beta_kc = float(beta_kc)

    def to_tcl(self) -> str:
        return (f"rayleigh {self.alpha_m:.12g} {self.beta_k:.12g} "
                f"{self.beta_k0:.12g} {self.beta_kc:.12g};")

    def to_dict(self) -> dict:
        return {"alpha_m": self.alpha_m, "beta_k": self.beta_k,
                "beta_k0": self.beta_k0, "beta_kc": self.beta_kc}


class Region:
    """Regione di elementi/nodi per applicare smorzamento o raggruppamento (command `region`)."""

    def __init__(self, tag: int, name: str = "",
                 element_ids: Optional[List[int]] = None,
                 node_ids: Optional[List[int]] = None,
                 rayleigh: Optional[RayleighDamping] = None):
        self.tag = int(tag)
        self.name = name or f"Region_{tag}"
        self.element_ids = [int(e) for e in (element_ids or [])]
        self.node_ids = [int(n) for n in (node_ids or [])]
        self.rayleigh = rayleigh

    def to_tcl(self) -> str:
        parts = ["region", str(self.tag)]
        if self.element_ids:
            parts.append("-ele")
            parts.extend(str(e) for e in self.element_ids)
        if self.node_ids:
            parts.append("-node")
            parts.extend(str(n) for n in self.node_ids)
        if self.rayleigh is not None:
            parts.extend(["-rayleigh", f"{self.rayleigh.alpha_m:.12g}",
                          f"{self.rayleigh.beta_k:.12g}",
                          f"{self.rayleigh.beta_k0:.12g}",
                          f"{self.rayleigh.beta_kc:.12g}"])
        return " ".join(parts) + ";"

    def to_dict(self) -> dict:
        return {"tag": self.tag, "name": self.name,
                "element_ids": self.element_ids, "node_ids": self.node_ids,
                "rayleigh": self.rayleigh.to_dict() if self.rayleigh else None}


class ElementLoad:
    """Carico su elemento (command `eleLoad -type T -ele ids ...`)."""

    def __init__(self, load_type: str, name: str = "",
                 element_ids: Optional[List[int]] = None,
                 element_range: Optional[Tuple[int, int]] = None,
                 region_tag: Optional[int] = None,
                 pattern_tag: int = 1,
                 values: Optional[List[float]] = None,
                 is_3d: bool = False):
        if load_type not in ELEMENT_LOAD_TYPES:
            raise ValueError(f"Tipo eleLoad non supportato: {load_type}")
        self.load_type = load_type
        self.name = name or f"EleLoad_{load_type}"
        self.element_ids = [int(e) for e in (element_ids or [])]
        self.element_range = tuple(element_range) if element_range else None
        self.region_tag = int(region_tag) if region_tag else None
        self.pattern_tag = int(pattern_tag)
        self.values = [float(v) for v in (values or [])]
        self.is_3d = bool(is_3d)

    def to_tcl(self) -> str:
        parts = ["eleLoad", "-type", self.load_type.lstrip("-")]
        if self.element_ids:
            parts.extend(["-ele"] + [str(e) for e in self.element_ids])
        elif self.element_range:
            parts.extend(["-eleRange", str(self.element_range[0]),
                          str(self.element_range[1])])
        elif self.region_tag:
            parts.extend(["-region", str(self.region_tag)])
        if self.pattern_tag:
            parts.extend(["-pattern", str(self.pattern_tag)])
        if self.values:
            parts.extend(f"{v:.12g}" for v in self.values)
        return " ".join(parts) + ";"

    def to_dict(self) -> dict:
        return {"load_type": self.load_type, "name": self.name,
                "element_ids": self.element_ids,
                "element_range": list(self.element_range) if self.element_range else None,
                "region_tag": self.region_tag,
                "pattern_tag": self.pattern_tag,
                "values": self.values, "is_3d": self.is_3d}


class ElementAssignment:
    """Associazione Gmsh -> elemento OpenSees e set di proprietà fisiche.

    element_command permette una formulazione esplicita, indispensabile per u-p.
    element_args contiene l'intero tail Tcl dopo la connettività; {matTag} viene
    sostituito automaticamente con il tag materiale dell'assegnazione.
    """

    COMMANDS = {
        1: "truss",
        2: "tri31",
        3: "quad",
        4: "FourNodeTetrahedron",
        5: "stdBrick",
        11: "TenNodeTetrahedron",
    }

    EXTRA_ELEMENTS = (
        "elasticBeamColumn", "elasticTimoshenkoBeam", "forceBeamColumn",
        "dispBeamColumn", "beamWithHinges", "nonlinearBeamColumn",
        "ShellMITC4", "ShellDKGQ", "ASDShellQ4",
        "bbarQuad", "enhancedQuad", "SSPquad",
        "bbarBrick", "SSPbrick", "20NodeBrick",
        "quadUP", "bbarQuadUP", "9_4_QuadUP", "SSPquadUP",
        "brickUP", "bbarBrickUP", "20_8_BrickUP", "SSPbrickUP",
        "zeroLength", "zeroLengthSection", "zeroLengthContact2D",
        "zeroLengthContact3D", "zeroLengthInterface2D", "TwoNodeLink",
        "SimpleContact2D", "SimpleContact3D", "BeamContact2D",
        "BeamContact3D", "BeamEndContact3D",
        "FlatSliderBearing", "ElastomericBearing", "FPBearingPTV",
        "Joint2D", "corotTruss", "TrussSection"
    )

    def __init__(self, entity_id: int, model_name: str, element_ids: List[int],
                 gmsh_type: int, material_tag: int, area: float = 1.0,
                 thickness: float = 1.0, plane_type: str = "PlaneStress",
                 section_tag: Optional[int] = None,
                 transf_tag: Optional[int] = None,
                 integration_tag: Optional[int] = None,
                 extra_args: Optional[str] = None,
                 element_command: Optional[str] = None,
                 element_args: Optional[str] = None):
        if gmsh_type not in self.COMMANDS and not element_command:
            raise ValueError(f"Tipo elemento Gmsh {gmsh_type} non supportato in OpenSees")
        if element_command and element_command not in self.EXTRA_ELEMENTS and element_command not in self.COMMANDS.values():
            raise ValueError(f"Elemento OpenSees non supportato: {element_command}")
        self.entity_id = int(entity_id)
        self.model_name = str(model_name)
        self.element_ids = sorted({int(eid) for eid in element_ids})
        self.gmsh_type = int(gmsh_type)
        self.material_tag = int(material_tag)
        self.area = float(area)
        self.thickness = float(thickness)
        self.plane_type = plane_type if plane_type in ("PlaneStress", "PlaneStrain") else "PlaneStress"
        self.section_tag = int(section_tag) if section_tag else None
        self.transf_tag = int(transf_tag) if transf_tag else None
        self.integration_tag = int(integration_tag) if integration_tag else None
        self.extra_args = str(extra_args) if extra_args else ""
        self.element_command = str(element_command) if element_command else None
        self.element_args = str(element_args) if element_args else ""

    def effective_command(self) -> str:
        return self.element_command or self.COMMANDS[self.gmsh_type]

    @property
    def is_up(self) -> bool:
        return is_up_element(self.effective_command())

    def to_dict(self) -> dict:
        d = {
            "entity_id": self.entity_id, "model_name": self.model_name,
            "element_ids": self.element_ids, "gmsh_type": self.gmsh_type,
            "material_tag": self.material_tag, "area": self.area,
            "thickness": self.thickness, "plane_type": self.plane_type,
        }
        if self.section_tag is not None:
            d["section_tag"] = self.section_tag
        if self.transf_tag is not None:
            d["transf_tag"] = self.transf_tag
        if self.integration_tag is not None:
            d["integration_tag"] = self.integration_tag
        if self.extra_args:
            d["extra_args"] = self.extra_args
        if self.element_command:
            d["element_command"] = self.element_command
        if self.element_args:
            d["element_args"] = self.element_args
        return d


class PrescribedDisplacement:
    """Spostamento imposto con il comando OpenSees sp."""

    def __init__(self, name: str, entity_ids: List[int], dof: int,
                 value: float, time_series_tag: int = 1, pattern_tag: int = 1):
        if int(dof) not in range(1, 7):
            raise ValueError("Il DOF deve essere compreso tra 1 e 6")
        self.name = name or "Spostamento imposto"
        self.entity_ids = [int(value) for value in entity_ids]
        self.dof = int(dof)
        self.value = float(value)
        self.time_series_tag = int(time_series_tag)
        self.pattern_tag = int(pattern_tag)

    def to_dict(self) -> dict:
        return {"name": self.name, "entity_ids": self.entity_ids,
                "dof": self.dof, "value": self.value,
                "time_series_tag": self.time_series_tag,
                "pattern_tag": self.pattern_tag}


class RecorderDefinition:
    """Recorder nodale o di elemento collegato a entità geometriche/mesh."""

    NODE_RESPONSES = {"disp", "vel", "accel", "incrDisp", "reaction"}
    ELEMENT_RESPONSES = {"force", "deformation", "stress", "strain",
                         "stresses", "strains"}

    def __init__(self, kind: str, entity_ids: List[int], file_path: str,
                 response: str, dofs: Optional[List[int]] = None):
        allowed = self.NODE_RESPONSES if kind == "Node" else self.ELEMENT_RESPONSES
        if kind not in ("Node", "Element") or response not in allowed:
            raise ValueError("Tipo o risposta recorder OpenSees non supportati")
        self.kind = kind
        self.entity_ids = [int(value) for value in entity_ids]
        self.file_path = str(file_path)
        self.response = response
        self.dofs = sorted({int(value) for value in (dofs or []) if 1 <= int(value) <= 6})

    def to_dict(self) -> dict:
        return {"kind": self.kind, "entity_ids": self.entity_ids,
                "file_path": self.file_path, "response": self.response,
                "dofs": self.dofs}


class ParameterBinding:
    """Collega un ID `parameter` Tcl a un target (elemento/nodo/materiale/pattern).

    Esteso per supportare tutti i tipi di parameter di OpenSees:
      - element: parameter tag element eleTag path
      - node: parameter tag node nodeTag disp dof
      - pattern: parameter tag pattern patternTag lambda
      - loadPattern: parameter tag loadPattern loadTag path
      - blank: parameter tag value (valore costante)
    """

    TARGETS = ("element", "node", "pattern", "loadPattern", "blank")

    def __init__(self, tag: int, target_type: str = "element",
                 target_id: int = 0, path: str = "",
                 dof: int = 1, value: float = 0.0,
                 extra_args: Optional[str] = None):
        if target_type not in self.TARGETS:
            raise ValueError(f"Tipo target parameter non supportato: {target_type}")
        self.tag = int(tag)
        self.target_type = target_type
        self.target_id = int(target_id)
        # Path può contenere più parole Tcl semplici (es. "E", "rho", "rho0 rho")
        tokens = str(path).split() if path else []
        if tokens and any(not token.replace("_", "").replace("-", "").isalnum()
                          for token in tokens):
            raise ValueError("Il percorso parametro deve contenere solo parole Tcl semplici")
        self.path = " ".join(tokens)
        self.dof = int(dof) if 1 <= int(dof) <= 6 else 1
        self.value = float(value)
        self.extra_args = str(extra_args) if extra_args else ""

    def to_tcl(self) -> str:
        if self.target_type == "blank":
            return f"parameter {self.tag} {self.value:.12g};"
        if self.target_type == "element":
            return f"parameter {self.tag} element {self.target_id} {self.path};"
        if self.target_type == "node":
            return (f"parameter {self.tag} node {self.target_id} disp {self.dof};")
        if self.target_type == "pattern":
            return f"parameter {self.tag} pattern {self.target_id} lambda;"
        if self.target_type == "loadPattern":
            return f"parameter {self.tag} loadPattern {self.target_id} {self.path};"
        return f"parameter {self.tag};"

    def to_dict(self) -> dict:
        return {"tag": self.tag, "target_type": self.target_type,
                "target_id": self.target_id, "path": self.path,
                "dof": self.dof, "value": self.value,
                "extra_args": self.extra_args}

    # --- Backward compatibility ---
    @property
    def element_id(self) -> int:
        return self.target_id if self.target_type == "element" else 0


class SetParameterCommand:
    """Comando `setParameter -val value -ele tag1 tag2 ... paramName`.

    Permette di applicare un parametro a un range di elementi in una sola
    operazione.
    """

    def __init__(self, value: float, parameter_name: str,
                 element_ids: Optional[List[int]] = None,
                 element_range: Optional[Tuple[int, int]] = None):
        if not element_ids and not element_range:
            raise ValueError("Necessario specificare element_ids o element_range")
        self.value = float(value)
        self.parameter_name = str(parameter_name)
        self.element_ids = [int(e) for e in (element_ids or [])]
        self.element_range = (tuple(element_range) if element_range
                              else None)

    def to_tcl(self) -> str:
        parts = ["setParameter", "-val", f"{self.value:.12g}"]
        if self.element_ids:
            parts.extend(["-ele"] + [str(e) for e in self.element_ids])
        elif self.element_range:
            parts.extend(["-eleRange", str(self.element_range[0]),
                          str(self.element_range[1])])
        parts.append(self.parameter_name)
        return " ".join(parts) + ";"

    def to_dict(self) -> dict:
        return {"value": self.value, "parameter_name": self.parameter_name,
                "element_ids": self.element_ids,
                "element_range": list(self.element_range) if self.element_range else None}


class UpdateMaterialsCommand:
    """Comando `updateMaterials -material matTag paramName value`.

    Usato per materiali soil (PressureDependMultiYield, ecc.) per cambiare
    lo stato (es. soilState 0=elastic, 1=plastic, 2=liquefied).
    """

    def __init__(self, material_tag: int, parameter_name: str, value: float):
        self.material_tag = int(material_tag)
        self.parameter_name = str(parameter_name)
        self.value = float(value)

    def to_tcl(self) -> str:
        return (f"updateMaterials -material {self.material_tag} "
                f"{self.parameter_name} {self.value:.12g};")

    def to_dict(self) -> dict:
        return {"material_tag": self.material_tag,
                "parameter_name": self.parameter_name,
                "value": self.value}


class InterfaceDefinition:
    """Interfaccia 2D tra due curve meshate, suddivisa in segmenti a 4 nodi."""

    def __init__(self, secondary_entity_id: int, primary_entity_id: int,
                 secondary_nodes: List[int], primary_nodes: List[int],
                 secondary_dof: int, primary_dof: int,
                 kn: float, kt: float, friction_angle: float,
                 model_name: str = ""):
        if len(secondary_nodes) < 2 or len(secondary_nodes) != len(primary_nodes):
            raise ValueError("Le due interfacce devono avere lo stesso numero di nodi, almeno 2")
        if int(secondary_dof) not in range(1, 7) or int(primary_dof) not in range(1, 7):
            raise ValueError("I DOF d'interfaccia devono essere compresi tra 1 e 6")
        if float(kn) <= 0 or float(kt) <= 0 or not 0 <= float(friction_angle) < 90:
            raise ValueError("Kn/Kt devono essere positivi e l'angolo d'attrito tra 0 e 90 gradi")
        self.secondary_entity_id = int(secondary_entity_id)
        self.primary_entity_id = int(primary_entity_id)
        self.secondary_nodes = [int(node) for node in secondary_nodes]
        self.primary_nodes = [int(node) for node in primary_nodes]
        self.secondary_dof = int(secondary_dof)
        self.primary_dof = int(primary_dof)
        self.kn = float(kn)
        self.kt = float(kt)
        self.friction_angle = float(friction_angle)
        self.model_name = str(model_name)

    def to_dict(self) -> dict:
        return {"secondary_entity_id": self.secondary_entity_id,
                "primary_entity_id": self.primary_entity_id,
                "secondary_nodes": self.secondary_nodes,
                "primary_nodes": self.primary_nodes,
                "secondary_dof": self.secondary_dof,
                "primary_dof": self.primary_dof, "kn": self.kn, "kt": self.kt,
                "friction_angle": self.friction_angle, "model_name": self.model_name}


class OpenSeesManager:
    """Registro e coordinatore di tutte le condizioni OpenSees di un CADDocument."""

    MATERIAL_COLORS = (
        (0.20, 0.62, 0.92), (0.95, 0.58, 0.18), (0.24, 0.74, 0.48),
        (0.78, 0.42, 0.82), (0.88, 0.78, 0.24), (0.18, 0.76, 0.78),
    )

    def __init__(self, doc):
        self.doc = doc
        self.time_series: Dict[int, TimeSeries] = {}
        self.constraints: List[StaticConstraint] = []
        self.equaldofs: List[EqualDOFConstraint] = []
        self.loads: List[EntityLoad] = []
        self.materials: List[MaterialDefinition] = []
        self.element_assignments: List[ElementAssignment] = []
        self.prescribed_displacements: List[PrescribedDisplacement] = []
        self.recorders: List[RecorderDefinition] = []
        self.parameter_bindings: List[ParameterBinding] = []
        self.interfaces: List[InterfaceDefinition] = []
        self.manual_nodes: Dict[int, Tuple[float, float, float]] = {}
        self.ndm = 3
        self.ndf = 3

        # --- Estensioni (catalogo allargato) ---
        self.sections: List[SectionDefinition] = []
        self.geom_transfs: List[GeomTransfDefinition] = []
        self.beam_integrations: List[BeamIntegrationDefinition] = []
        self.nodal_masses: List[NodalMass] = []
        self.rayleigh: Optional[RayleighDamping] = None
        self.regions: List[Region] = []
        self.element_loads: List[ElementLoad] = []
        self.set_parameters: List[SetParameterCommand] = []
        self.update_materials_cmds: List[UpdateMaterialsCommand] = []
        # Mapping parametri globali (es. parametri di fase) -> valore
        self.global_parameters: Dict[str, float] = {}
        from .opensees_flow import OpenSeesFlow
        self.flow = OpenSeesFlow()

        self._next_cid = 1
        self._next_eid = 1
        self._next_lid = 1
        self._next_sec_tag = 1
        self._next_transf_tag = 1
        self._next_integration_tag = 1
        self._next_region_tag = 1
        self._next_param_tag = 1

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

    def _entity_ids_for_targets(self, entity_ids=None, group_names=None) -> Set[int]:
        result = {int(eid) for eid in (entity_ids or [])
                  if eid is not None and int(eid) in self.doc.entities}
        names = {str(name) for name in (group_names or []) if name}
        if not names:
            return result
        for name in names:
            group = self.doc.groups.groups.get(name)
            if group:
                result.update(group.member_ids)
        for entity in self.doc.entities.values():
            ref = entity.meta.get("mesh_ref")
            if not ref:
                continue
            model_name, dim, block_tag = ref
            model = self.doc.mesh_models.get(model_name)
            block = model.blocks.get((dim, block_tag)) if model else None
            if block and any(model.physicals.get((dim, tag), "") in names or str(tag) in names
                             for tag in block.physical_tags):
                result.add(entity.id)
        return result

    def refresh_entity_metadata(self) -> None:
        """Ricalcola marcatori e colore FEM dalle associazioni OpenSees correnti."""
        marks: Dict[int, Set[str]] = {}
        colors: Dict[int, Tuple[float, float, float]] = {}

        def add_mark(entity_ids, group_names, label, color=None):
            for entity_id in self._entity_ids_for_targets(entity_ids, group_names):
                marks.setdefault(entity_id, set()).add(label)
                if color is not None:
                    colors[entity_id] = color

        for assignment in self.element_assignments:
            material = next((item for item in self.materials
                             if item.tag == assignment.material_tag), None)
            material_name = material.name if material else str(assignment.material_tag)
            color = self.MATERIAL_COLORS[(assignment.material_tag - 1) % len(self.MATERIAL_COLORS)]
            element_name = assignment.effective_command()
            add_mark([assignment.entity_id], [],
                     f"MAT {assignment.material_tag} {element_name} "
                     f"({len(assignment.element_ids)} elem., {material_name})", color)
        for item in self.constraints:
            add_mark(item.entity_ids, item.group_names, f"FIX {item.name}",
                     (0.90, 0.28, 0.22))
        for item in self.loads:
            add_mark(item.entity_ids, item.group_names, f"LOAD {item.name}",
                     (0.96, 0.56, 0.16))
        for item in self.equaldofs:
            add_mark([item.master_entity_id, item.slave_entity_id],
                     [item.master_group, item.slave_group], f"EQUALDOF {item.name}",
                     (0.12, 0.72, 0.73))
        for item in self.prescribed_displacements:
            add_mark(item.entity_ids, [], f"SP DOF {item.dof}", (0.72, 0.34, 0.78))
        for item in self.recorders:
            add_mark(item.entity_ids, [], f"REC {item.kind} {item.response}")
        for binding in self.parameter_bindings:
            assignment = next((item for item in self.element_assignments
                               if binding.element_id in item.element_ids), None)
            if assignment:
                add_mark([assignment.entity_id], [],
                         f"PARAM {binding.tag} {binding.path}", (0.30, 0.78, 0.82))
        for interface in self.interfaces:
            add_mark([interface.secondary_entity_id, interface.primary_entity_id], [],
                     f"INTERFACE {len(interface.secondary_nodes) - 1} segmenti",
                     (0.88, 0.30, 0.72))

        for entity in self.doc.entities.values():
            entity.meta.pop("fem_marks", None)
            entity.meta.pop("fem_color", None)
            if entity.id in marks:
                entity.meta["fem_marks"] = sorted(marks[entity.id])
                entity.meta["fem_color"] = colors.get(entity.id, (0.86, 0.88, 0.90))

    def add_material(self, name: str, model: str,
                     parameters: List[float], tag: Optional[int] = None,
                     extra: Optional[Dict[str, Any]] = None) -> MaterialDefinition:
        used = {material.tag for material in self.materials}
        if tag is None:
            tag = 1
            while tag in used:
                tag += 1
        if int(tag) in used:
            raise ValueError(f"Il tag materiale {tag} è già in uso")
        material = MaterialDefinition(tag, name, model, parameters, extra)
        self.materials.append(material)
        return material

    def resolve_entity_elements(self, entity_id: int, model=None) -> List[int]:
        """Restituisce gli elementi del blocco mesh associato all'entità CAD."""
        entity = self.doc.entities.get(int(entity_id))
        if entity is None:
            return []
        mesh_ref = entity.meta.get("mesh_ref")
        if not mesh_ref:
            return []
        model_name, dim, tag = mesh_ref
        mesh_model = self.doc.mesh_models.get(model_name, model)
        if mesh_model is None:
            return []
        block = mesh_model.blocks.get((dim, tag))
        return sorted(block.element_ids) if block else []

    def assign_entity_elements(self, entity_id: int, material_tag: int,
                               model=None, area: float = 1.0,
                               thickness: float = 1.0,
                               plane_type: str = "PlaneStress",
                               element_ids: Optional[List[int]] = None,
                               element_command: Optional[str] = None,
                               element_args: Optional[str] = None) -> ElementAssignment:
        entity = self.doc.entities.get(int(entity_id))
        if entity is None or not entity.meta.get("mesh_ref"):
            raise ValueError("Selezionare un'entità meshata (blocco Gmsh)")
        model_name, dim, tag = entity.meta["mesh_ref"]
        mesh_model = self.doc.mesh_models.get(model_name, model)
        if mesh_model is None:
            raise ValueError(f"Modello mesh non disponibile: {model_name}")
        block = mesh_model.blocks.get((dim, tag))
        if not block or not block.element_ids:
            raise ValueError("L'entità selezionata non contiene elementi mesh")
        element_types = {mesh_model.elements[eid][0] for eid in block.element_ids
                         if eid in mesh_model.elements}
        if len(element_types) != 1:
            raise ValueError("Il blocco contiene tipi di elemento Gmsh misti")
        gmsh_type = element_types.pop()
        effective_command = element_command or ElementAssignment.COMMANDS.get(gmsh_type)
        if effective_command is None:
            raise ValueError(
                f"Il tipo Gmsh {gmsh_type} non ha un mapping OpenSees diretto"
            )
        if effective_command in GEOTECH_ELEMENTS:
            info = GEOTECH_ELEMENTS[effective_command]
            if gmsh_type not in info.get("mesh_types", ()):
                raise ValueError(
                    f"{effective_command} non è compatibile direttamente con Gmsh {gmsh_type}"
                )
            required_ndm = info.get("ndm")
            if isinstance(required_ndm, int) and self.ndm != required_ndm:
                raise ValueError(f"{effective_command} richiede ndm={required_ndm}")
            if self.ndf != info.get("ndf", self.ndf):
                raise ValueError(f"{effective_command} richiede ndf={info.get('ndf')}")
            if not element_args or not str(element_args).strip():
                raise ValueError(f"{effective_command} richiede gli argomenti u-p dell'elemento")
        if gmsh_type in (2, 3, 10):
            block_nodes = {node for eid in block.element_ids
                           for node in mesh_model.elements[eid][1]}
            heights = [mesh_model.nodes[node][2] for node in block_nodes]
            if heights and max(heights) - min(heights) > 1.0e-8:
                raise ValueError("La mesh piana deve giacere nel piano XY; trasformazioni locali non configurate")
        if gmsh_type in (4, 5, 11) and self.ndm != 3:
            raise ValueError("Tetraedri e brick richiedono ndm=3")
        block_element_ids = set(block.element_ids)
        selected_ids = set(element_ids) if element_ids else block_element_ids
        if not selected_ids or not selected_ids.issubset(block_element_ids):
            raise ValueError("Gli ID elemento devono appartenere al blocco mesh selezionato")
        if any(mesh_model.elements[eid][0] != gmsh_type for eid in selected_ids):
            raise ValueError("Gli elementi selezionati devono avere tutti lo stesso tipo Gmsh")
        if self.materials:
            material = next((item for item in self.materials
                             if item.tag == int(material_tag)), None)
            if material is None:
                raise ValueError(f"Il materiale OpenSees {material_tag} non esiste")
            expected = "uniaxialMaterial" if gmsh_type == 1 else "nDMaterial"
            if material.command != expected:
                raise ValueError("Truss richiede materiale uniaxial; elementi continui richiedono materiale nD")
        assignment = ElementAssignment(
            entity_id, model_name, sorted(selected_ids), gmsh_type, material_tag,
            area, thickness, plane_type,
            element_command=element_command, element_args=element_args
        )
        retained = []
        for old in self.element_assignments:
            old_ids = set(old.element_ids)
            if old.model_name != model_name or not old_ids.intersection(selected_ids):
                retained.append(old)
                continue
            remaining = old_ids - selected_ids
            if remaining:
                retained.append(ElementAssignment(
                    old.entity_id, old.model_name, sorted(remaining), old.gmsh_type,
                    old.material_tag, old.area, old.thickness, old.plane_type,
                    old.section_tag, old.transf_tag, old.integration_tag, old.extra_args,
                    old.element_command, old.element_args))
        self.element_assignments = retained
        self.element_assignments.append(assignment)
        self.refresh_entity_metadata()
        return assignment

    def validate_element_assignments(self, model=None) -> Dict[str, Any]:
        """Controlla ID, appartenenza al blocco, tipo e materiale prima dell'export."""
        if model is None and self.doc.mesh_models:
            model = list(self.doc.mesh_models.values())[-1]
        if model is None:
            return {"valid": False, "errors": ["Nessun modello mesh disponibile"],
                    "assigned_elements": []}

        errors = []
        owners = {}
        material_by_tag = {material.tag: material for material in self.materials}
        for assignment in self.element_assignments:
            if assignment.model_name != model.name:
                continue
            entity = self.doc.entities.get(assignment.entity_id)
            if entity is None or not entity.meta.get("mesh_ref"):
                errors.append(f"Entità {assignment.entity_id} non esiste o non è meshata")
                continue
            ref_model, dim, block_tag = entity.meta["mesh_ref"]
            block = model.blocks.get((dim, block_tag)) if ref_model == model.name else None
            block_ids = set(block.element_ids) if block else set()
            for element_id in assignment.element_ids:
                if element_id not in model.elements or element_id not in block_ids:
                    errors.append(f"Elemento {element_id} non appartiene al blocco dell'entità {entity.name}")
                    continue
                gmsh_type = model.elements[element_id][0]
                if gmsh_type != assignment.gmsh_type:
                    errors.append(f"Elemento {element_id}: tipo Gmsh diverso dall'assegnazione")
                if element_id in owners:
                    errors.append(f"Elemento {element_id} assegnato più di una volta")
                owners[element_id] = assignment
                if gmsh_type in (2, 3) and (self.ndm != 2 or self.ndf < 2):
                    errors.append(f"Elemento piano {element_id} richiede ndm=2 e ndf>=2")
                if gmsh_type in (4, 5, 11) and self.ndm != 3:
                    errors.append(f"Elemento solido {element_id} richiede ndm=3")
                material = material_by_tag.get(assignment.material_tag)
                if material is None:
                    errors.append(f"Elemento {element_id}: materiale {assignment.material_tag} non definito")
                else:
                    expected = "uniaxialMaterial" if gmsh_type == 1 else "nDMaterial"
                    if material.command != expected:
                        errors.append(f"Elemento {element_id}: classe materiale incompatibile")

        return {"valid": not errors, "errors": errors,
                "assigned_elements": sorted(owners)}

    def validate_model(self, model=None) -> Dict[str, Any]:
        """Validazione pre-export dell'intero modello FEM/OpenSees.

        Restituisce errori bloccanti e warning separati. La validazione richiede
        che gli elementi analizzabili siano completamente assegnati, che i
        riferimenti a materiali/sezioni/trasformazioni esistano e che le
        condizioni abbiano almeno un target risolvibile.
        """
        if model is None and self.doc.mesh_models:
            model = list(self.doc.mesh_models.values())[-1]
        if model is None:
            return {"valid": False, "errors": ["Nessun modello mesh disponibile"],
                    "warnings": [], "stats": {}}

        errors: List[str] = []
        warnings: List[str] = []
        stats: Dict[str, Any] = {}

        from .opensees_export import verify_mesh_coherence
        coherence = verify_mesh_coherence(model)
        if not coherence["valid"]:
            errors.extend(
                [f"Mesh: {msg}" for msg in (
                    [f"nodi mancanti: {coherence['missing_nodes'][:10]}"]
                    if coherence["missing_nodes"] else []
                )]
            )
            if coherence["mismatched_elements_count"]:
                errors.append(
                    f"Mesh: {coherence['mismatched_elements_count']} elementi con numero nodi errato"
                )

        assignments = [a for a in self.element_assignments
                       if a.model_name == model.name]
        owners: Dict[int, ElementAssignment] = {}
        supported = set(ElementAssignment.COMMANDS)

        # In una mesh Gmsh 3D possono essere presenti anche facce/linee di bordo.
        # Non sono automaticamente elementi del modello OpenSees volumetrico.
        # Consideriamo analizzabili gli elementi 1D e quelli con dimensione
        # topologica coerente con ndm.
        from .mesh import ELEM_INFO
        analyzable_types = set()
        for etype in supported:
            info = ELEM_INFO.get(etype)
            if info is None:
                continue
            name = info[0].lower()
            dim = 1 if name.startswith(("linea", "line")) else (
                2 if name.startswith(("triangolo", "quadrilatero")) else (
                    3 if name.startswith(("tetraedro", "esaedro")) else 0
                )
            )
            if dim == self.ndm or dim == 1:
                analyzable_types.add(etype)
        supported_model_elements = {
            eid for eid, (etype, _) in model.elements.items()
            if etype in analyzable_types
        }

        # Gli elementi presenti nella mesh ma non trattabili dal mapper restano
        # un warning diagnostico e non vengono falsamente considerati assegnati.
        unsupported = sorted(
            eid for eid, (etype, _) in model.elements.items()
            if etype not in supported and (
                ELEM_INFO.get(etype, ("", 0, 0))[1] is not None
            )
        )
        if unsupported:
            warnings.append(
                f"{len(unsupported)} elementi Gmsh non mappati direttamente da OpenSees "
                f"(primi: {unsupported[:12]})"
            )

        for assignment in assignments:
            entity = self.doc.entities.get(assignment.entity_id)
            if entity is None:
                errors.append(f"Assegnazione: entità {assignment.entity_id} inesistente")
                continue
            for eid in assignment.element_ids:
                if eid not in model.elements:
                    errors.append(
                        f"Assegnazione {entity.name}: elemento {eid} non presente nella mesh"
                    )
                    continue
                if eid in owners:
                    errors.append(f"Elemento {eid}: assegnato a più proprietà fisiche")
                else:
                    owners[eid] = assignment

                etype = model.elements[eid][0]
                if assignment.gmsh_type != etype:
                    errors.append(
                        f"Elemento {eid}: tipo Gmsh {etype} diverso dal tipo assegnato "
                        f"{assignment.gmsh_type}"
                    )
                if assignment.element_command:
                    command = assignment.element_command
                    info = ELEMENT_CATALOG.get(command) or GEOTECH_ELEMENTS.get(command, {})
                    if not info:
                        errors.append(f"Elemento {eid}: comando OpenSees {command} non catalogato")
                    elif command in GEOTECH_ELEMENTS:
                        allowed_types = tuple(info.get("mesh_types", ()))
                        if etype not in allowed_types:
                            errors.append(f"Elemento {eid}: {command} incompatibile con Gmsh {etype}")
                        req_ndm = info.get("ndm")
                        if isinstance(req_ndm, int) and self.ndm != req_ndm:
                            errors.append(f"Elemento {eid}: {command} richiede ndm={req_ndm}")
                        req_ndf = info.get("ndf")
                        if req_ndf and self.ndf != req_ndf:
                            errors.append(f"Elemento {eid}: {command} richiede ndf={req_ndf}")
                        if assignment.is_up and not assignment.element_args.strip():
                            errors.append(f"Elemento {eid}: {command} richiede element_args u-p")
                if etype in (2, 3, 10) and self.ndm != 2:
                    errors.append(f"Elemento {eid}: elemento piano incompatibile con ndm={self.ndm}")
                if etype in (4, 5, 11) and self.ndm != 3:
                    errors.append(f"Elemento {eid}: elemento solido incompatibile con ndm={self.ndm}")
                if assignment.gmsh_type in (1,) and assignment.area <= 0:
                    errors.append(f"Elemento {eid}: area deve essere > 0")
                if assignment.gmsh_type in (2, 3) and assignment.thickness <= 0:
                    errors.append(f"Elemento {eid}: thickness deve essere > 0")

        unassigned = sorted(supported_model_elements - set(owners))
        if unassigned:
            errors.append(
                f"{len(unassigned)} elementi OpenSees senza proprietà assegnata "
                f"(primi: {unassigned[:12]})"
            )

        materials = {m.tag: m for m in self.materials}
        if len(materials) != len(self.materials):
            errors.append("Tag materiale duplicati")
        sections = {s.tag: s for s in self.sections}
        if len(sections) != len(self.sections):
            errors.append("Tag sezione duplicati")
        transformations = {t.tag: t for t in self.geom_transfs}
        if len(transformations) != len(self.geom_transfs):
            errors.append("Tag geomTransf duplicati")
        integrations = {b.tag: b for b in self.beam_integrations}
        if len(integrations) != len(self.beam_integrations):
            errors.append("Tag beamIntegration duplicati")

        for eid, assignment in owners.items():
            if assignment.material_tag not in materials:
                errors.append(
                    f"Elemento {eid}: materiale {assignment.material_tag} non definito"
                )
            if assignment.section_tag is not None and assignment.section_tag not in sections:
                errors.append(
                    f"Elemento {eid}: sezione {assignment.section_tag} non definita"
                )
            if assignment.transf_tag is not None and assignment.transf_tag not in transformations:
                errors.append(
                    f"Elemento {eid}: geomTransf {assignment.transf_tag} non definita"
                )
            if assignment.integration_tag is not None and assignment.integration_tag not in integrations:
                errors.append(
                    f"Elemento {eid}: beamIntegration {assignment.integration_tag} non definita"
                )
            if assignment.gmsh_type == 1 and materials.get(assignment.material_tag) and \
                    materials[assignment.material_tag].command != "uniaxialMaterial":
                errors.append(
                    f"Elemento {eid}: truss richiede uniaxialMaterial"
                )
            if assignment.gmsh_type in (2, 3, 4, 5, 10, 11) and materials.get(assignment.material_tag) and \
                    materials[assignment.material_tag].command != "nDMaterial":
                errors.append(
                    f"Elemento {eid}: elemento continuo richiede nDMaterial"
                )
            if assignment.is_up and assignment.material_tag in materials and                     materials[assignment.material_tag].command != "nDMaterial":
                errors.append(f"Elemento {eid}: elemento u-p richiede nDMaterial")

        for constraint in self.constraints:
            nodes = self.resolve_constraint_nodes(constraint, model)
            if not nodes:
                errors.append(f"Vincolo '{constraint.name}': nessun nodo risolvibile")
            elif max(constraint.dof_flags(), default=0) > self.ndf:
                errors.append(
                    f"Vincolo '{constraint.name}': DOF incompatibile con ndf={self.ndf}"
                )
        for eq in self.equaldofs:
            pairs = self.resolve_equaldof_pairs(eq, model)
            if not pairs:
                errors.append(f"EqualDOF '{eq.name}': nessuna coppia master/slave risolvibile")
            if any(m == s for m, s in pairs):
                errors.append(f"EqualDOF '{eq.name}': master e slave contengono lo stesso nodo")

        for recorder in self.recorders:
            if not self.resolve_recorder_targets(recorder, model):
                warnings.append(f"Recorder '{recorder.kind} {recorder.response}': nessun target risolvibile")

        for binding in self.parameter_bindings:
            if binding.target_type == "element":
                if binding.target_id not in model.elements:
                    errors.append(
                        f"Parameter {binding.tag}: elemento {binding.target_id} non presente"
                    )
                if not binding.path.strip():
                    errors.append(f"Parameter {binding.tag}: path vuoto")
            elif binding.target_type == "node" and binding.target_id not in model.nodes and                     binding.target_id not in self.manual_nodes:
                errors.append(
                    f"Parameter {binding.tag}: nodo {binding.target_id} non presente"
                )

        for interface in self.interfaces:
            if interface.model_name and interface.model_name != model.name:
                continue
            if len(interface.secondary_nodes) != len(interface.primary_nodes):
                errors.append("Interfaccia: discretizzazione secondaria/primaria non compatibile")
            if len(interface.secondary_nodes) < 2:
                errors.append("Interfaccia: servono almeno due nodi per lato")
            if interface.kn <= 0 or interface.kt < 0:
                errors.append("Interfaccia: rigidezze kn/kt non valide")

        if self.multi_stage:
            seen_stage_tags = set()
            for stage in self.stages:
                if stage.stage_id in seen_stage_tags:
                    errors.append(f"Fase {stage.stage_id}: tag duplicato")
                seen_stage_tags.add(stage.stage_id)
                if stage.solver is None:
                    errors.append(f"Fase {stage.stage_id}: solver non definito")
                if stage.update_command == "updateParameter":
                    if stage.parameter_tag not in {p.tag for p in self.parameter_bindings}:
                        errors.append(
                            f"Fase {stage.stage_id}: parameter {stage.parameter_tag} non definito"
                        )

        stats.update({
            "mesh_nodes": len(model.nodes),
            "mesh_elements": len(model.elements),
            "assigned_elements": len(owners),
            "unassigned_elements": len(unassigned),
            "materials": len(self.materials),
            "sections": len(self.sections),
            "constraints": len(self.constraints),
            "equal_dof": len(self.equaldofs),
            "interfaces": len(self.interfaces),
            "parameters": len(self.parameter_bindings),
            "phases": len(self.stages),
        })
        return {"valid": not errors, "errors": errors, "warnings": warnings,
                "stats": stats}

    def remove_interface(self, index: int) -> bool:
        """Rimuove un'interfaccia per indice di elenco."""
        if 0 <= int(index) < len(self.interfaces):
            self.interfaces.pop(int(index))
            self.refresh_entity_metadata()
            return True
        return False

    def add_manual_node(self, x: float, y: float, z: float,
                        tag: Optional[int] = None) -> int:
        used = set(self.manual_nodes)
        for mesh_model in self.doc.mesh_models.values():
            used.update(mesh_model.nodes)
        if tag is None:
            tag = max(used, default=0) + 1
            while tag in used:
                tag += 1
        if int(tag) in used:
            raise ValueError(f"Il tag nodo {tag} è già in uso")
        self.manual_nodes[int(tag)] = (float(x), float(y), float(z))
        return int(tag)

    def add_prescribed_displacement(self, name: str, entity_ids: List[int],
                                    dof: int, value: float,
                                    time_series_tag: int = 1,
                                    pattern_tag: int = 1) -> PrescribedDisplacement:
        item = PrescribedDisplacement(name, entity_ids, dof, value,
                                      time_series_tag, pattern_tag)
        self.prescribed_displacements.append(item)
        return item

    def add_recorder(self, kind: str, entity_ids: List[int], file_path: str,
                     response: str, dofs: Optional[List[int]] = None) -> RecorderDefinition:
        recorder = RecorderDefinition(kind, entity_ids, file_path, response, dofs)
        self.recorders.append(recorder)
        return recorder

    def add_parameter_binding(self, element_id: int, path: str,
                              tag: Optional[int] = None) -> ParameterBinding:
        """Aggiunge un binding parameter -> elemento (backward-compatible).

        Per usare gli altri target_type (node, pattern, ecc.), creare direttamente
        l'oggetto ParameterBinding e chiamare `self.parameter_bindings.append(...)`.
        """
        existing_ids = {item.tag for item in self.parameter_bindings}
        if tag is None:
            tag = max(existing_ids, default=0) + 1
        if int(tag) in existing_ids:
            raise ValueError(f"Il tag parameter {tag} è già in uso")
        if not any(int(element_id) in model.elements
                   for model in self.doc.mesh_models.values()):
            raise ValueError(f"Elemento OpenSees {element_id} non trovato nelle mesh")
        binding = ParameterBinding(tag=tag, target_type="element",
                                    target_id=int(element_id), path=path)
        self.parameter_bindings.append(binding)
        self._next_param_tag = max(self._next_param_tag, int(tag) + 1)
        self.refresh_entity_metadata()
        return binding

    def add_parameter(self, target_type: str = "element",
                      target_id: int = 0, path: str = "",
                      dof: int = 1, value: float = 0.0,
                      tag: Optional[int] = None) -> ParameterBinding:
        """API generica per parameter con qualsiasi target_type."""
        existing_ids = {item.tag for item in self.parameter_bindings}
        if tag is None:
            tag = max(existing_ids, default=0) + 1
        if int(tag) in existing_ids:
            raise ValueError(f"Il tag parameter {tag} è già in uso")
        binding = ParameterBinding(tag=tag, target_type=target_type,
                                    target_id=target_id, path=path,
                                    dof=dof, value=value)
        self.parameter_bindings.append(binding)
        self._next_param_tag = max(self._next_param_tag, int(tag) + 1)
        self.refresh_entity_metadata()
        return binding

    def update_parameter(self, parameter_tag: int, value: float) -> str:
        """Genera il comando `updateParameter tag value;` come stringa Tcl."""
        if not any(b.tag == int(parameter_tag) for b in self.parameter_bindings):
            raise ValueError(f"Parametro {parameter_tag} non definito")
        return f"updateParameter {int(parameter_tag)} {float(value):.12g};"

    def add_set_parameter(self, value: float, parameter_name: str,
                          element_ids: Optional[List[int]] = None,
                          element_range: Optional[Tuple[int, int]] = None) -> SetParameterCommand:
        cmd = SetParameterCommand(value, parameter_name, element_ids, element_range)
        self.set_parameters.append(cmd)
        return cmd

    def add_update_materials(self, material_tag: int, parameter_name: str,
                              value: float) -> UpdateMaterialsCommand:
        cmd = UpdateMaterialsCommand(material_tag, parameter_name, value)
        self.update_materials_cmds.append(cmd)
        return cmd

    def set_rayleigh(self, alpha_m: float = 0.0, beta_k: float = 0.0,
                     beta_k0: float = 0.0, beta_kc: float = 0.0) -> RayleighDamping:
        self.rayleigh = RayleighDamping(alpha_m, beta_k, beta_k0, beta_kc)
        return self.rayleigh

    def add_nodal_mass(self, node_tag: int, mass_values: List[float]) -> NodalMass:
        mass = NodalMass(node_tag, mass_values)
        self.nodal_masses.append(mass)
        return mass

    def add_section(self, name: str, model: str, parameters: List[float],
                    ndm: int = 2, fibers: Optional[List[dict]] = None,
                    extra: Optional[Dict[str, Any]] = None,
                    tag: Optional[int] = None) -> SectionDefinition:
        used = {item.tag for item in self.sections}
        if tag is None:
            tag = max(used, default=0) + 1
        if int(tag) in used:
            raise ValueError(f"Il tag sezione {tag} è già in uso")
        section = SectionDefinition(tag, name, model, parameters, ndm, fibers, extra)
        self.sections.append(section)
        return section

    def add_geom_transf(self, name: str, transf_type: str,
                        ndm: int = 3,
                        vecxz: Tuple[float, float, float] = (0.0, 0.0, 1.0),
                        joint_offset: Optional[List[float]] = None,
                        tag: Optional[int] = None) -> GeomTransfDefinition:
        used = {item.tag for item in self.geom_transfs}
        if tag is None:
            tag = max(used, default=0) + 1
        if int(tag) in used:
            raise ValueError(f"Il tag geomTransf {tag} è già in uso")
        transf = GeomTransfDefinition(tag, name, transf_type, ndm, vecxz, joint_offset)
        self.geom_transfs.append(transf)
        return transf

    def add_beam_integration(self, name: str, integration_type: str,
                              n_points: int = 3, sec_tag: int = 1,
                              tag: Optional[int] = None,
                              **kwargs) -> BeamIntegrationDefinition:
        used = {item.tag for item in self.beam_integrations}
        if tag is None:
            tag = max(used, default=0) + 1
        if int(tag) in used:
            raise ValueError(f"Il tag beamIntegration {tag} è già in uso")
        bi = BeamIntegrationDefinition(tag, name, integration_type, n_points, sec_tag,
                                        **kwargs)
        self.beam_integrations.append(bi)
        return bi

    def add_region(self, name: str = "",
                    element_ids: Optional[List[int]] = None,
                    node_ids: Optional[List[int]] = None,
                    rayleigh: Optional[RayleighDamping] = None,
                    tag: Optional[int] = None) -> Region:
        used = {item.tag for item in self.regions}
        if tag is None:
            tag = max(used, default=0) + 1
        if int(tag) in used:
            raise ValueError(f"Il tag region {tag} è già in uso")
        region = Region(tag, name, element_ids, node_ids, rayleigh)
        self.regions.append(region)
        return region

    def add_element_load(self, load_type: str, name: str = "",
                         element_ids: Optional[List[int]] = None,
                         element_range: Optional[Tuple[int, int]] = None,
                         region_tag: Optional[int] = None,
                         pattern_tag: int = 1,
                         values: Optional[List[float]] = None,
                         is_3d: bool = False) -> ElementLoad:
        load = ElementLoad(load_type, name, element_ids, element_range,
                           region_tag, pattern_tag, values, is_3d)
        self.element_loads.append(load)
        return load

    def set_global_parameter(self, name: str, value: float) -> None:
        """Memorizza un parametro globale (es. E0, fy)."""
        self.global_parameters[str(name)] = float(value)

    def update_global_parameters(self, params: Dict[str, float]) -> None:
        """Aggiorna in batch i parametri globali (`update parameters`)."""
        for name, value in params.items():
            self.global_parameters[str(name)] = float(value)

    def add_interface2d(self, secondary_entity_id: int, primary_entity_id: int,
                        model=None, secondary_dof: int = 2, primary_dof: int = 2,
                        kn: float = 1.0e6, kt: float = 1.0e4,
                        friction_angle: float = 30.0) -> InterfaceDefinition:
        secondary = self.doc.entities.get(int(secondary_entity_id))
        primary = self.doc.entities.get(int(primary_entity_id))
        if not secondary or not primary or secondary.id == primary.id:
            raise ValueError("Selezionare due curve meshate distinte")
        secondary_ref = secondary.meta.get("mesh_ref")
        primary_ref = primary.meta.get("mesh_ref")
        if not secondary_ref or not primary_ref or secondary_ref[0] != primary_ref[0]:
            raise ValueError("Le due curve devono appartenere allo stesso modello mesh")
        if secondary_ref[1] != 1 or primary_ref[1] != 1:
            raise ValueError("zeroLengthInterface2D richiede due entità curva")
        model_name = secondary_ref[0]
        mesh_model = self.doc.mesh_models.get(model_name, model)
        if mesh_model is None:
            raise ValueError(f"Modello mesh non disponibile: {model_name}")
        for entity, ref in ((secondary, secondary_ref), (primary, primary_ref)):
            block = mesh_model.blocks.get((ref[1], ref[2]))
            if not block or any(mesh_model.elements[eid][0] != 1
                                for eid in block.element_ids if eid in mesh_model.elements):
                raise ValueError(f"{entity.name} non contiene elementi lineari Gmsh")
        if any(item.model_name == model_name and item.gmsh_type in (4, 5, 11)
               for item in self.element_assignments):
            raise ValueError("zeroLengthInterface2D non può convivere con assegnazioni solide 3D nello stesso modello")

        secondary_nodes = self.resolve_entity_nodes(secondary.id, mesh_model)
        primary_nodes = self.resolve_entity_nodes(primary.id, mesh_model)
        if len(secondary_nodes) != len(primary_nodes) or len(secondary_nodes) < 2:
            raise ValueError("Le curve d'interfaccia devono avere lo stesso numero di nodi (almeno 2)")

        def order_along_curve(node_ids):
            points = np.array([mesh_model.nodes[node_id] for node_id in node_ids], dtype=float)
            centered = points - points.mean(axis=0)
            _, singular, vectors = np.linalg.svd(centered, full_matrices=False)
            if not len(singular) or singular[0] <= 1.0e-12:
                raise ValueError("La curva d'interfaccia non ha una direzione distinguibile")
            projection = centered @ vectors[0]
            return [node_ids[index] for index in np.argsort(projection)]

        secondary_nodes = order_along_curve(secondary_nodes)
        primary_nodes = order_along_curve(primary_nodes)
        direct = sum(np.linalg.norm(np.subtract(mesh_model.nodes[s], mesh_model.nodes[p]))
                     for s, p in zip((secondary_nodes[0], secondary_nodes[-1]),
                                     (primary_nodes[0], primary_nodes[-1])))
        reversed_cost = sum(np.linalg.norm(np.subtract(mesh_model.nodes[s], mesh_model.nodes[p]))
                            for s, p in zip((secondary_nodes[0], secondary_nodes[-1]),
                                            (primary_nodes[-1], primary_nodes[0])))
        if reversed_cost < direct:
            primary_nodes.reverse()
        interface = InterfaceDefinition(
            secondary.id, primary.id, secondary_nodes, primary_nodes,
            secondary_dof, primary_dof, kn, kt, friction_angle, model_name)
        self.interfaces.append(interface)
        self.ndm, self.ndf = 2, 2
        self.refresh_entity_metadata()
        return interface

    # ------------------------------------------------------ Risoluzione Nodi
    def resolve_entity_nodes(self, entity_id: int, model=None, tol: float = 1e-2) -> List[int]:
        """Risolve tutti i nodi della mesh associati a un'entità geometrica o blocco mesh."""
        ent = self.doc.entities.get(entity_id)
        if ent is None:
            return []
        manual_tag = ent.meta.get("opensees_node_tag")
        if manual_tag is not None:
            return [int(manual_tag)]
        if model is None and getattr(self.doc, "mesh_models", None):
            model = list(self.doc.mesh_models.values())[-1]
        if model is None:
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

    def resolve_recorder_targets(self, recorder: RecorderDefinition,
                                 model=None) -> List[int]:
        targets: Set[int] = set()
        for entity_id in recorder.entity_ids:
            if recorder.kind == "Node":
                targets.update(self.resolve_entity_nodes(entity_id, model))
            else:
                targets.update(self.resolve_entity_elements(entity_id, model))
        return sorted(targets)

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
    def generate_tcl_script(self, model=None, ndf: Optional[int] = None,
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

        ndf = int(ndf if ndf is not None else self.ndf)
        ndm = int(self.ndm)
        from .opensees_export import reorder_element_nodes_for_opensees

        lines = [
            "#" + "=" * 78,
            "# Script OpenSees TCL Completo — Generato da GmshCAD Studio",
            f"# Modello: {model.name if model else 'CAD'}",
            f"# Gradi di Libertà per nodo (ndf): {ndf}",
            "#" + "=" * 78,
            "wipe;",
            f"model BasicBuilder -ndm {ndm} -ndf {ndf};",
            "",
            "#" + "-" * 78,
            "# 1. DEFINIZIONE NODI",
            "#" + "-" * 78,
        ]

        if model:
            for nid in sorted(model.nodes.keys()):
                c = model.nodes[nid]
                coords = " ".join(f"{value:.10g}" for value in c[:ndm])
                lines.append(f"node {nid} {coords};")
        for nid, coord in sorted(self.manual_nodes.items()):
            coords = " ".join(f"{value:.10g}" for value in coord[:ndm])
            lines.append(f"node {nid} {coords};")

        # --- Masse nodali ---
        if self.nodal_masses:
            lines += ["", "# Masse nodali (mass nodeTag m1 m2 ...)"]
            for mass in self.nodal_masses:
                lines.append(mass.to_tcl())

        lines += [
            "",
            "#" + "-" * 78,
            "# 2. DEFINIZIONE MATERIALI ED ELEMENTI (Connettività OpenSees verificata)",
            "#" + "-" * 78,
        ]
        if self.materials:
            for material in self.materials:
                lines.append(material.to_tcl())
            default_material_tag = self.materials[0].tag
        else:
            default_material_tag = 1
            lines.append("nDMaterial ElasticIsotropic 1 30000.0 0.2 0.0;")
            lines.append("# Materiale di default: definire materiali da GUI per sostituirlo.")
        lines.append("")

        # --- Sezioni ---
        if self.sections:
            lines += ["", "# Sezioni (section)"]
            for sec in self.sections:
                lines.append(sec.to_tcl())
            lines.append("")

        # --- GeomTransf ---
        if self.geom_transfs:
            lines += ["", "# Trasformazioni geometriche (geomTransf)"]
            for gt in self.geom_transfs:
                lines.append(gt.to_tcl())
            lines.append("")

        # --- BeamIntegration ---
        if self.beam_integrations:
            lines += ["", "# Regole di integrazione (beamIntegration)"]
            for bi in self.beam_integrations:
                lines.append(bi.to_tcl())
            lines.append("")

        if model:
            assignments_by_element = {
                eid: assignment
                for assignment in self.element_assignments
                if assignment.model_name == model.name
                for eid in assignment.element_ids
            }
            element_ids = (sorted(assignments_by_element)
                           if self.element_assignments or self.materials
                           else sorted(model.elements))
            material_tags = {material.tag for material in self.materials}
            for eid in element_ids:
                if eid not in model.elements:
                    continue
                etype, raw_nodes = model.elements[eid]
                assignment = assignments_by_element.get(eid)
                if assignment and assignment.gmsh_type != etype:
                    continue
                ordered, _ = reorder_element_nodes_for_opensees(etype, raw_nodes, model.nodes)
                mat_tag = assignment.material_tag if assignment else default_material_tag
                if self.materials and mat_tag not in material_tags:
                    raise ValueError(f"Elemento {eid}: materiale OpenSees {mat_tag} inesistente")
                if assignment:
                    command = assignment.effective_command()
                    if assignment.element_args.strip():
                        args = assignment.element_args.replace(
                            "{matTag}", str(assignment.material_tag)).strip()
                        lines.append(
                            f"element {command} {eid} {' '.join(map(str, ordered))} {args};"
                        )
                        continue
                    if etype == 1:
                        lines.append(f"element truss {eid} {ordered[0]} {ordered[1]} {assignment.area:g} {mat_tag};")
                    elif etype == 2:
                        if ndm != 2 or ndf < 2:
                            raise ValueError("Gli elementi tri31 richiedono ndm=2 e almeno ndf=2")
                        lines.append(f"element {command} {eid} {ordered[0]} {ordered[1]} {ordered[2]} {assignment.thickness:g} {assignment.plane_type} {mat_tag};")
                    elif etype == 3:
                        if ndm != 2 or ndf < 2:
                            raise ValueError("Gli elementi quad richiedono ndm=2 e almeno ndf=2")
                        lines.append(f"element {command} {eid} {ordered[0]} {ordered[1]} {ordered[2]} {ordered[3]} {assignment.thickness:g} {assignment.plane_type} {mat_tag};")
                    elif etype == 4:
                        lines.append(f"element {command} {eid} {' '.join(map(str, ordered[:4]))} {mat_tag};")
                    elif etype == 5:
                        lines.append(f"element {command} {eid} {' '.join(map(str, ordered[:8]))} {mat_tag};")
                    elif etype == 10:
                        raise ValueError(
                            "L'elemento Gmsh 10 (quad9) richiede element_args per 9_4_QuadUP"
                        )
                    elif etype == 11:
                        lines.append(f"element {command} {eid} {' '.join(map(str, ordered[:10]))} {mat_tag};")
                    continue
                if etype == 4:
                    lines.append(f"element FourNodeTetrahedron {eid} {ordered[0]} {ordered[1]} {ordered[2]} {ordered[3]} {mat_tag};")
                elif etype == 5:
                    n_str = " ".join(str(n) for n in ordered[:8])
                    lines.append(f"element stdBrick {eid} {n_str} {mat_tag};")
                elif etype == 11:
                    lines.append(f"element TenNodeTetrahedron {eid} {' '.join(map(str, ordered[:10]))} {mat_tag};")
                elif etype == 2:
                    lines.append(f"element tri31 {eid} {ordered[0]} {ordered[1]} {ordered[2]} 1.0 \"PlaneStress\" {mat_tag};")
                elif etype == 3:
                    lines.append(f"element quad {eid} {ordered[0]} {ordered[1]} {ordered[2]} {ordered[3]} 1.0 \"PlaneStress\" {mat_tag};")

        if model and self.interfaces:
            lines += ["", "# Interfacce zeroLengthInterface2D"]
            next_interface_tag = max(model.elements, default=0) + 1
            for interface in self.interfaces:
                if interface.model_name and interface.model_name != model.name:
                    continue
                if ndm != 2:
                    raise ValueError("zeroLengthInterface2D richiede ndm=2")
                for index in range(len(interface.secondary_nodes) - 1):
                    nodes = (interface.secondary_nodes[index],
                             interface.secondary_nodes[index + 1],
                             interface.primary_nodes[index],
                             interface.primary_nodes[index + 1])
                    node_text = " ".join(str(node) for node in nodes)
                    lines.append(
                        f"element zeroLengthInterface2D {next_interface_tag} "
                        f"-sNdNum 2 -pNdNum 2 -dof {interface.secondary_dof} "
                        f"{interface.primary_dof} -Nodes {{ {node_text} }} "
                        f"{interface.kn:.12g} {interface.kt:.12g} "
                        f"{interface.friction_angle:.12g};")
                    next_interface_tag += 1

        lines += [
            "",
            "# Binding dei parametri modificabili (parameter id element tag percorso)",
        ]
        for binding in self.parameter_bindings:
            if model and binding.element_id not in model.elements:
                raise ValueError(f"Parametro {binding.tag}: elemento {binding.element_id} non nel modello attivo")
            lines.append(binding.to_tcl())

        lines += [
            "",
            "#" + "-" * 78,
            "# 3. WORKFLOW DELLE FASI — COMANDI EDITABILI",
            "#" + "-" * 78,
        ]

        # Il flow è la sorgente d'ordine per tutte le operazioni che modificano
        # il dominio durante il calcolo. Le definizioni di modello (nodi,
        # materiali, elementi, interfacce e timeSeries) restano nelle sezioni
        # precedenti per preservare le dipendenze OpenSees.
        self.flow.sync_from_manager(self, model)
        for phase, commands in self.flow.phase_commands(self, model):
            if phase.phase_id == 0:
                continue
            lines += [
                "",
                "#" + "=" * 78,
                f"# FASE {phase.phase_id}: {phase.name.upper()}",
                "#" + "=" * 78,
            ]
            if phase.notes:
                lines.append(f"# {phase.notes}")
            if not commands:
                lines.append("# (nessun comando di fase)")
                continue
            for command in commands:
                if command.notes:
                    lines.append(f"# {command.notes}")
                if command.tcl.strip():
                    lines.extend(command.tcl.rstrip().splitlines())

        lines.append("")
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "time_series": {tag: ts.to_dict() for tag, ts in self.time_series.items()},
            "constraints": [sc.to_dict() for sc in self.constraints],
            "equaldofs": [eq.to_dict() for eq in self.equaldofs],
            "loads": [ld.to_dict() for ld in self.loads],
            "materials": [item.to_dict() for item in self.materials],
            "element_assignments": [item.to_dict() for item in self.element_assignments],
            "prescribed_displacements": [item.to_dict() for item in self.prescribed_displacements],
            "recorders": [item.to_dict() for item in self.recorders],
            "parameter_bindings": [item.to_dict() for item in self.parameter_bindings],
            "interfaces": [item.to_dict() for item in self.interfaces],
            "manual_nodes": {tag: list(coords) for tag, coords in self.manual_nodes.items()},
            "ndm": self.ndm,
            "ndf": self.ndf,
            "default_solver": self.default_solver.to_dict(),
            "multi_stage": self.multi_stage,
            "stages": [stg.to_dict() for stg in self.stages],
            # --- Estensioni ---
            "sections": [s.to_dict() for s in self.sections],
            "geom_transfs": [g.to_dict() for g in self.geom_transfs],
            "beam_integrations": [b.to_dict() for b in self.beam_integrations],
            "nodal_masses": [m.to_dict() for m in self.nodal_masses],
            "rayleigh": self.rayleigh.to_dict() if self.rayleigh else None,
            "regions": [r.to_dict() for r in self.regions],
            "element_loads": [el.to_dict() for el in self.element_loads],
            "set_parameters": [sp.to_dict() for sp in self.set_parameters],
            "update_materials_cmds": [um.to_dict() for um in self.update_materials_cmds],
            "global_parameters": dict(self.global_parameters),
            "flow": self.flow.to_dict(),
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
        mgr.materials = [MaterialDefinition(**item) for item in d.get("materials", [])]
        # Backward-compat per ElementAssignment: gestisce vecchi dict senza i nuovi campi
        mgr.element_assignments = []
        for item in d.get("element_assignments", []):
            item = dict(item)
            # I nuovi campi opzionali sono ignorati se non presenti
            mgr.element_assignments.append(ElementAssignment(**item))
        mgr.prescribed_displacements = [PrescribedDisplacement(**item)
                        for item in d.get("prescribed_displacements", [])]
        mgr.recorders = [RecorderDefinition(**item) for item in d.get("recorders", [])]
        # Backward-compat per ParameterBinding:
        # Vecchio formato: {tag, element_id, path}
        # Nuovo formato: {tag, target_type, target_id, path, dof, value, extra_args}
        mgr.parameter_bindings = []
        for item in d.get("parameter_bindings", []):
            item = dict(item)
            if "target_type" not in item:
                # Vecchio formato
                item["target_type"] = "element"
                item["target_id"] = item.pop("element_id", 0)
                item.setdefault("dof", 1)
                item.setdefault("value", 0.0)
                item.setdefault("extra_args", "")
            else:
                # Nuovo formato - potrebbe avere element_id legacy, ignorare
                item.pop("element_id", None)
            mgr.parameter_bindings.append(ParameterBinding(**item))
        mgr.interfaces = [InterfaceDefinition(**item)
                  for item in d.get("interfaces", [])]
        mgr.manual_nodes = {int(tag): tuple(coords)
                    for tag, coords in d.get("manual_nodes", {}).items()}
        mgr.ndm = int(d.get("ndm", 3))
        mgr.ndf = int(d.get("ndf", 3))
        if "default_solver" in d:
            mgr.default_solver = SolverSettings.from_dict(d["default_solver"])
        mgr.multi_stage = d.get("multi_stage", True)
        if "stages" in d:
            mgr.stages = [AnalysisStage.from_dict(sd) for sd in d["stages"]]
        # --- Nuovi campi (estensioni) ---
        mgr.sections = [SectionDefinition(**item) for item in d.get("sections", [])]
        mgr.geom_transfs = [GeomTransfDefinition(**item) for item in d.get("geom_transfs", [])]
        mgr.beam_integrations = [BeamIntegrationDefinition(**item)
                                  for item in d.get("beam_integrations", [])]
        mgr.nodal_masses = [NodalMass(**item) for item in d.get("nodal_masses", [])]
        rayleigh_data = d.get("rayleigh")
        if rayleigh_data:
            mgr.rayleigh = RayleighDamping(**rayleigh_data)
        mgr.regions = []
        for item in d.get("regions", []):
            item = dict(item)
            r_data = item.pop("rayleigh", None)
            r = RayleighDamping(**r_data) if r_data else None
            mgr.regions.append(Region(rayleigh=r, **item))
        mgr.element_loads = [ElementLoad(**item) for item in d.get("element_loads", [])]
        mgr.set_parameters = []
        for item in d.get("set_parameters", []):
            item = dict(item)
            er = item.pop("element_range", None)
            if er and isinstance(er, list):
                item["element_range"] = tuple(er)
            mgr.set_parameters.append(SetParameterCommand(**item))
        mgr.update_materials_cmds = [UpdateMaterialsCommand(**item)
                                      for item in d.get("update_materials_cmds", [])]
        mgr.global_parameters = dict(d.get("global_parameters", {}))
        from .opensees_flow import OpenSeesFlow
        flow_data = d.get("flow")
        if isinstance(flow_data, dict):
            mgr.flow = OpenSeesFlow.from_dict(flow_data)
        return mgr
