"""Fasi di modello (updateModel), proprietà per elemento e pacchetti solutori.

Ispirato alla logica FEM-preprocessing di OpenSeesSTAAD/STKO: il modello CAD
può essere suddiviso in **fasi** (es. "Scavo 1", "Getto pilastri", ...); ogni
fase ha un *update model* che elenca cosa aggiungere/rimuovere rispetto alla
fase precedente, un **pacchetto solutore** associato e l'**associazione delle
proprietà** (materiali, sezioni, vincoli) per tipo di elemento fisico.

Il modulo è puro Python (nessuna dipendenza da OCC/Qt): testabile headless.

Integrazione con OpenSeesManager
-------------------------------
Permette di avere un'unica sorgente di verità per l'export Tcl:
- `PhaseManager` è usato dalla GUI per gestire le fasi in modo intuitivo.
- `Phase.to_analysis_stage()` converte la fase in un `AnalysisStage` che
  `OpenSeesManager.generate_tcl_script()` sa già esportare.
- `Phase.to_solver_settings()` restituisce un `SolverSettings` che usa i
  comandi Tcl **reali** di OpenSees (system, test, algorithm, integrator, ...).
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Any, Set


# ---------------------------------------------------------------------------
# Tipi di elemento "fisico" supportati dall'associazione proprietà
# ---------------------------------------------------------------------------

TIPI_ELEMENTO_FISICO = {
    "truss":      {"nome_it": "Asta (truss)",            "n_nodi": 2},
    "beam":       {"nome_it": "Trave (beam-column)",     "n_nodi": 2},
    "shell":      {"nome_it": "Guscio (shell)",          "n_nodi": 4},
    "solid":      {"nome_it": "Solido (brick/tet)",      "n_nodi": 8},
    "spring":     {"nome_it": "Molla (zero-length)",     "n_nodi": 2},
    "constraint": {"nome_it": "Vincolo multi-punto",     "n_nodi": 0},
}

#: famiglie di vincoli associate alle entità del documento
VINCOLI = ["fix", "pin", "roller", "equalDOF", "rigidDiaphragm"]


class ElementProperty:
    """Proprietà fisica associata a una classe di elementi."""

    def __init__(self, kind: str, nome: str, mat_id: int = 0,
                 sezione_id: int = 0, geom: Optional[dict] = None):
        if kind not in TIPI_ELEMENTO_FISICO:
            raise ValueError(
                f"tipo elemento sconosciuto '{kind}'; validi: "
                + ", ".join(sorted(TIPI_ELEMENTO_FISICO)))
        self.kind = kind
        self.nome = nome
        self.mat_id = int(mat_id)          # id materiale OpenSees-style
        self.sezione_id = int(sezione_id)  # id sezione
        self.geom = dict(geom or {})

    def to_dict(self) -> dict:
        return {"kind": self.kind, "nome": self.nome, "mat_id": self.mat_id,
                "sezione_id": self.sezione_id, "geom": self.geom}

    @classmethod
    def from_dict(cls, d: dict) -> "ElementProperty":
        return cls(d["kind"], d.get("nome", d["kind"]), d.get("mat_id", 0),
                   d.get("sezione_id", 0), d.get("geom"))

    def __repr__(self):  # pragma: no cover
        return (f"ElementProperty({self.kind}, {self.nome!r}, "
                f"mat={self.mat_id}, sez={self.sezione_id})")


class SolverPack:
    """Pacchetto solutore: wrapping di SolverSettings con metadati.

    Genera comandi Tcl **reali** di OpenSees (system, test, algorithm,
    integrator, analysis) tramite `to_solver_settings()`. Il vecchio
    `comandi_opensees()` (che produceva Tcl non valido) è deprecato.
    """

    # Mapping dai nomi italiani del vecchio SolverPack ai nomi OpenSees reali
    _ANALYSIS_MAP = {"Static": "Static", "Transient": "Transient",
                     "Modal": "Static", "Variabile": "VariableTransient"}
    _SYSTEM_MAP = {"SparseSymmetric": "SparseSYM", "Umfpack": "Umfpack",
                   "SparseGeneral": "SparseGeneral", "BandSPD": "BandSPD",
                   "BandGeneral": "BandGeneral", "ProfileSPD": "ProfileSPD",
                   "FullGeneral": "FullGeneral", "Mumps": "Mumps"}
    _NUMBERER_MAP = {"BandGeneral": "RCM", "ProfileSPD": "RCM",
                     "RCM": "RCM", "AMD": "AMD", "Plain": "Plain"}

    def __init__(self, nome: str, analisatore: str = "Static",
                 soluzione: str = "Umfpack", numero: str = "RCM",
                 sistema: str = "SparseSYM", params: Optional[dict] = None):
        self.nome = nome
        self.analisatore = analisatore
        self.soluzione = soluzione          # legacy: alias per `sistema`
        self.numero = numero
        self.sistema = sistema
        self.params = dict(params or {})

    def to_solver_settings(self):
        """Restituisce un `SolverSettings` equivalente (import pigro per evitare ciclo)."""
        from .opensees_conditions import SolverSettings
        analysis_type = self._ANALYSIS_MAP.get(self.analisatore, "Static")
        system_name = self._SYSTEM_MAP.get(self.sistema, self.sistema)
        if system_name == self.sistema and self.sistema == "SparseSymmetric":
            system_name = "SparseSYM"
        numberer_name = self._NUMBERER_MAP.get(self.numero, "RCM")
        return SolverSettings(
            constraints=self.params.get("constraints", "Transformation"),
            numberer=numberer_name,
            system=system_name,
            test_type=self.params.get("test", "NormDispIncr"),
            test_tol=float(self.params.get("tol", 1e-8)),
            test_iter=int(self.params.get("maxIter", 25)),
            test_pflag=int(self.params.get("pFlag", 0)),
            algorithm=self.params.get("algoritmo", "Newton"),
            integrator_type=self.params.get("integrator",
                                             "LoadControl" if analysis_type == "Static"
                                             else "Newmark"),
            integrator_step=float(self.params.get("integrator_step", 0.1)),
            analysis_type=analysis_type,
            n_steps=int(self.params.get("n_steps", 10)),
            dt=float(self.params.get("dt", 0.01)),
        )

    def comandi_opensees(self) -> List[str]:
        """Genera comandi Tcl **validi** di OpenSees (versione corretta).

        Deprecato in favore di `to_solver_settings().to_tcl()`.
        """
        solver = self.to_solver_settings()
        return solver.to_tcl()

    def to_dict(self) -> dict:
        return {"nome": self.nome, "analisatore": self.analisatore,
                "soluzione": self.soluzione, "numero": self.numero,
                "sistema": self.sistema, "params": self.params}

    @classmethod
    def from_dict(cls, d: dict) -> "SolverPack":
        return cls(d["nome"], d.get("analisatore", "Static"),
                   d.get("soluzione", "Umfpack"), d.get("numero", "RCM"),
                   d.get("sistema", "SparseSYM"), d.get("params"))


class Phase:
    """Una fase del modello con update model e pacchetto solutore.

    Estensioni:
    - `to_analysis_stage()` converte la fase in un `AnalysisStage` per
      l'integrazione con `OpenSeesManager.generate_tcl_script()`.
    - `to_solver_settings()` restituisce un `SolverSettings` valido.
    - `properties` e `constraints` sono associabili per-entità.
    """

    def __init__(self, tag: int, nome: str,
                 update_model: Optional[dict] = None,
                 solver_pack: Optional[SolverPack] = None):
        self.tag = int(tag)
        self.nome = nome
        #: {"add_elements": [...], "remove_elements": [...],
        #:  "add_constraints": [...], "remove_constraints": [...]}
        self.update_model: Dict[str, List[int]] = {
            "add_elements": [], "remove_elements": [],
            "add_constraints": [], "remove_constraints": [],
            **(update_model or {})}
        self.solver_pack: Optional[SolverPack] = solver_pack
        #: {entita_id: ElementProperty} — associazione proprietà per elemento
        self.properties: Dict[int, ElementProperty] = {}
        #: {entita_id: tipo_vincolo} — vincoli assegnati
        self.constraints: Dict[int, str] = {}
        # Comando di update per la fase (updateMaterialStage / updateParameter / none)
        self.update_command: str = "none"
        # Per updateParameter: tag del parameter target e nuovo valore
        self.parameter_tag: int = 0
        self.parameter_value: float = 0.0
        # Per updateMaterialStage: tag materiale e stage (0=elastic, 1=plastic)
        self.material_tag: int = 0
        self.material_stage: int = 0
        self.enabled = True

    # ------------------------------------------------------------ proprietà
    def set_property(self, entita_id: int, prop: ElementProperty) -> None:
        self.properties[int(entita_id)] = prop

    def assign_constraint(self, entita_id: int, vincolo: str) -> None:
        if vincolo not in VINCOLI:
            raise ValueError(f"vincolo '{vincolo}' non valido; validi: {VINCOLI}")
        self.constraints[int(entita_id)] = vincolo

    # ------------------------------------------------------- update model
    def apply_update_model(self, attivi: set) -> set:
        """Restituisce l'insieme di entità attive dopo questa fase.

        ``attivi`` è l'insieme delle entità già presenti dalla fase precedente.
        """
        out = set(attivi)
        out |= set(self.update_model.get("add_elements", []))
        out -= set(self.update_model.get("remove_elements", []))
        return out

    def add_elements(self, *entity_ids: int) -> None:
        """Aggiunge entità all'update_model della fase (stile STKO)."""
        for eid in entity_ids:
            eid = int(eid)
            if eid not in self.update_model["add_elements"]:
                self.update_model["add_elements"].append(eid)
            if eid in self.update_model["remove_elements"]:
                self.update_model["remove_elements"].remove(eid)

    def remove_elements(self, *entity_ids: int) -> None:
        """Rimuove entità dall'update_model della fase."""
        for eid in entity_ids:
            eid = int(eid)
            if eid not in self.update_model["remove_elements"]:
                self.update_model["remove_elements"].append(eid)
            if eid in self.update_model["add_elements"]:
                self.update_model["add_elements"].remove(eid)

    def add_constraints(self, *constraint_ids: int) -> None:
        for cid in constraint_ids:
            cid = int(cid)
            if cid not in self.update_model["add_constraints"]:
                self.update_model["add_constraints"].append(cid)
            if cid in self.update_model["remove_constraints"]:
                self.update_model["remove_constraints"].remove(cid)

    def remove_constraints(self, *constraint_ids: int) -> None:
        for cid in constraint_ids:
            cid = int(cid)
            if cid not in self.update_model["remove_constraints"]:
                self.update_model["remove_constraints"].append(cid)
            if cid in self.update_model["add_constraints"]:
                self.update_model["add_constraints"].remove(cid)

    def set_update_command(self, command: str, **kwargs) -> None:
        """Imposta il comando di update per la fase.

        Args:
            command: "none", "updateMaterialStage", "updateParameter",
                     "updateMaterials", "setParameter"
            kwargs: dipendenti dal comando:
                - updateMaterialStage: material_tag, material_stage
                - updateParameter: parameter_tag, parameter_value
                - updateMaterials: material_tag, parameter_name, value
                - setParameter: parameter_name, value, element_range
        """
        valid = ("none", "updateMaterialStage", "updateParameter",
                 "updateMaterials", "setParameter")
        if command not in valid:
            raise ValueError(f"update_command non valido: {command}; validi: {valid}")
        self.update_command = command
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_solver_settings(self):
        """Converte il SolverPack della fase in un `SolverSettings` valido.

        Se la fase non ha un solver_pack, ritorna None.
        """
        if self.solver_pack is None:
            return None
        return self.solver_pack.to_solver_settings()

    def to_analysis_stage(self):
        """Converte la fase in un `AnalysisStage` per il pipeline Tcl.

        Permette di usare PhaseManager come sorgente unica di fasi, esportando
        via OpenSeesManager.generate_tcl_script().
        """
        from .opensees_conditions import AnalysisStage
        solver = self.to_solver_settings()
        if solver is None:
            from .opensees_conditions import SolverSettings
            solver = SolverSettings()
        stage_type = "static"
        if self.solver_pack and "Transient" in self.solver_pack.analisatore:
            stage_type = "transient"
        elif self.tag == 1 and self.update_command == "updateMaterialStage":
            stage_type = "gravity"
        return AnalysisStage(
            stage_id=self.tag,
            name=self.nome,
            stage_type=stage_type,
            material_stage=self.material_stage,
            mat_tag=self.material_tag or 1,
            update_stage_cmd=self.update_command != "none",
            load_const=(stage_type == "gravity"),
            solver=solver,
            update_command=self.update_command,
            parameter_tag=self.parameter_tag,
            parameter_value=self.parameter_value,
        )

    def summary(self) -> str:
        pk = self.solver_pack.nome if self.solver_pack else "—"
        return (f"Fase {self.tag} «{self.nome}»: +{len(self.update_model['add_elements'])} "
                f"-{len(self.update_model['remove_elements'])} elementi, "
                f"{len(self.properties)} proprietà, "
                f"{len(self.constraints)} vincoli, solutore: {pk}")

    def to_dict(self) -> dict:
        return {"tag": self.tag, "nome": self.nome,
                "update_model": self.update_model,
                "solver_pack": self.solver_pack.to_dict() if self.solver_pack else None,
                "properties": {str(k): v.to_dict() for k, v in self.properties.items()},
                "constraints": {str(k): v for k, v in self.constraints.items()},
                "update_command": self.update_command,
                "parameter_tag": self.parameter_tag,
                "parameter_value": self.parameter_value,
                "material_tag": self.material_tag,
                "material_stage": self.material_stage,
                "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: dict) -> "Phase":
        ph = cls(d["tag"], d["nome"], d.get("update_model"),
                 SolverPack.from_dict(d["solver_pack"]) if d.get("solver_pack") else None)
        ph.properties = {int(k): ElementProperty.from_dict(v)
                         for k, v in d.get("properties", {}).items()}
        ph.constraints = {int(k): v for k, v in d.get("constraints", {}).items()}
        ph.update_command = d.get("update_command", "none")
        ph.parameter_tag = int(d.get("parameter_tag", 0))
        ph.parameter_value = float(d.get("parameter_value", 0.0))
        ph.material_tag = int(d.get("material_tag", 0))
        ph.material_stage = int(d.get("material_stage", 0))
        ph.enabled = d.get("enabled", True)
        return ph


class PhaseManager:
    """Registro delle fasi del documento (modello a fasi stile STKO).

    Estensioni:
    - `bridge_to_stages()` sincronizza le fasi con `OpenSeesManager.stages`.
    - `to_analysis_stages()` restituisce la lista di `AnalysisStage` per export.
    """

    def __init__(self):
        self.phases: List[Phase] = []
        self.current_tag: int = 1

    # ------------------------------------------------------------- gestione
    def add_phase(self, nome: str, update_model: Optional[dict] = None,
                  solver_pack: Optional[SolverPack] = None) -> Phase:
        tag = max((p.tag for p in self.phases), default=0) + 1
        ph = Phase(tag, nome, update_model, solver_pack)
        self.phases.append(ph)
        return ph

    def remove_phase(self, tag: int) -> bool:
        before = len(self.phases)
        self.phases = [p for p in self.phases if p.tag != tag]
        return len(self.phases) < before

    def get(self, tag: int) -> Optional[Phase]:
        return next((p for p in self.phases if p.tag == tag), None)

    def set_current(self, tag: int) -> bool:
        if self.get(tag) is not None:
            self.current_tag = tag
            return True
        return False

    # -------------------------------------------------------- derivazioni
    def active_entities(self, fino_a: Optional[int] = None) -> set:
        """Entità attive cumulativamente fino alla fase ``fino_a`` (default corrente)."""
        up_to = self.current_tag if fino_a is None else fino_a
        attivi: set = set()
        for ph in sorted(self.phases, key=lambda p: p.tag):
            if ph.enabled and ph.tag <= up_to:
                attivi = ph.apply_update_model(attivi)
        return attivi

    def merged_properties(self, fino_a: Optional[int] = None) -> Dict[int, ElementProperty]:
        up_to = self.current_tag if fino_a is None else fino_a
        props: Dict[int, ElementProperty] = {}
        for ph in sorted(self.phases, key=lambda p: p.tag):
            if ph.enabled and ph.tag <= up_to:
                props.update(ph.properties)
        return props

    def merged_constraints(self, fino_a: Optional[int] = None) -> Dict[int, str]:
        up_to = self.current_tag if fino_a is None else fino_a
        cons: Dict[int, str] = {}
        for ph in sorted(self.phases, key=lambda p: p.tag):
            if ph.enabled and ph.tag <= up_to:
                cons.update(ph.constraints)
        return cons

    def solver_packs(self) -> Dict[int, Optional[str]]:
        return {p.tag: (p.solver_pack.nome if p.solver_pack else None)
                for p in self.phases}

    def summary(self) -> str:
        return "\n".join(p.summary() for p in sorted(self.phases, key=lambda x: x.tag)) \
            or "(nessuna fase)"

    # -------------------------------------------------------- integrazione
    def to_analysis_stages(self) -> List:
        """Restituisce la lista di `AnalysisStage` per l'export OpenSees.

        Se non ci sono fasi definite, ritorna una lista vuota (e l'exporter
        usa i defaults di OpenSeesManager.stages).
        """
        if not self.phases:
            return []
        return [p.to_analysis_stage() for p in sorted(self.phases, key=lambda x: x.tag)]

    def bridge_to_stages(self, opensees_manager) -> None:
        """Sincronizza le fasi di PhaseManager con gli stages di OpenSeesManager.

        Dopo la chiamata, `opensees_manager.stages` contiene una `AnalysisStage`
        per ciascuna fase definita in PhaseManager. Se non ci sono fasi,
        lascia invariati gli stages di default di OpenSeesManager.
        """
        if not self.phases:
            return
        opensees_manager.stages = self.to_analysis_stages()
        opensees_manager.multi_stage = True

    # ------------------------------------------------------------ persistenza
    def to_dict(self) -> dict:
        return {"current": self.current_tag,
                "phases": [p.to_dict() for p in sorted(self.phases, key=lambda x: x.tag)]}

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "PhaseManager":
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        pm = cls()
        pm.phases = [Phase.from_dict(x) for x in d.get("phases", [])]
        pm.current_tag = d.get("current", 1)
        return pm
