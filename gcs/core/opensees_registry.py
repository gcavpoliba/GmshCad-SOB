"""Registro professionale dei comandi OpenSees.

Il registro unifica:
- comandi core del ModelBuilder/Domain/Analysis;
- schemi gia presenti in opensees_catalog.py;
- provenienza nel tree ufficiale OpenSees/SRC;
- collegamento alla documentazione ufficiale.

Il registro e separato dalla GUI: puo essere usato per browser,
validazione, generazione di form, import/export e diagnostica di copertura.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import opensees_catalog as catalog


OFFICIAL_REPO = "https://github.com/OpenSees/OpenSees"
OFFICIAL_MANUAL = (
    "https://openseesdocumentation.readthedocs.io/en/latest/user/userManual.html"
)


@dataclass(frozen=True)
class OpenSeesCommandSpec:
    """Descrizione normalizzata di un comando OpenSees."""

    name: str
    kind: str
    family: str
    source: str
    documentation: str = OFFICIAL_MANUAL
    syntax: str = ""
    notes: str = ""
    implemented: bool = False
    schema: Optional[dict] = None

    @property
    def source_url(self) -> str:
        return f"{OFFICIAL_REPO}/tree/master/{self.source}"

    @property
    def search_text(self) -> str:
        return " ".join(
            str(x or "")
            for x in (
                self.name,
                self.kind,
                self.family,
                self.source,
                self.syntax,
                self.notes,
            )
        ).lower()


_CORE = (
    ("model", "model", "builder", "SRC/modelbuilder/tcl/", "model ndm ndf"),
    ("node", "model", "node", "SRC/modelbuilder/tcl/", "node tag x y ?z?"),
    ("mass", "model", "mass", "SRC/modelbuilder/tcl/", "mass nodeTag mx ?my mz ...?"),
    ("fix", "constraint", "sp", "SRC/handler/", "fix nodeTag dof..."),
    ("sp", "constraint", "sp", "SRC/handler/", "sp nodeTag dof value ?-pattern patternTag?"),
    ("equalDOF", "constraint", "mpc", "SRC/handler/", "equalDOF masterNode slaveNode dof..."),
    ("rigidLink", "constraint", "mpc", "SRC/handler/", "rigidLink type masterNode slaveNode"),
    ("rigidDiaphragm", "constraint", "mpc", "SRC/handler/", "rigidDiaphragm perpDir masterNode slaveNodes..."),
    ("uniaxialMaterial", "material", "uniaxial", "SRC/material/uniaxial/", "uniaxialMaterial type matTag args..."),
    ("nDMaterial", "material", "nD", "SRC/material/nD/", "nDMaterial type matTag args..."),
    ("section", "section", "section", "SRC/material/section/", "section type secTag args..."),
    ("geomTransf", "transformation", "coordTransformation", "SRC/coordTransformation/", "geomTransf type tag args..."),
    ("beamIntegration", "integration", "beam", "SRC/element/", "beamIntegration type tag args..."),
    ("element", "element", "element", "SRC/element/", "element type eleTag nodes... args..."),
    ("timeSeries", "domain", "timeSeries", "SRC/domain/pattern/", "timeSeries type tag args..."),
    ("pattern", "domain", "pattern", "SRC/domain/pattern/", "pattern type tag args..."),
    ("load", "domain", "load", "SRC/domain/pattern/", "load nodeTag values..."),
    ("eleLoad", "domain", "elementLoad", "SRC/domain/pattern/", "eleLoad -ele eleTags... type args..."),
    ("loadConst", "domain", "load", "SRC/domain/pattern/", "loadConst -time time"),
    ("region", "domain", "region", "SRC/domain/region/", "region regionTag -ele eleTags... ?options?"),
    ("rayleigh", "domain", "damping", "SRC/damping/", "rayleigh alphaM betaK betaKInit betaKcomm"),
    ("constraints", "analysis", "constraints", "SRC/handler/", "constraints type args..."),
    ("numberer", "analysis", "numberer", "SRC/analysis/", "numberer type"),
    ("system", "analysis", "system", "SRC/system_of_eqn/", "system type args..."),
    ("test", "analysis", "convergenceTest", "SRC/convergenceTest/", "test type args..."),
    ("algorithm", "analysis", "algorithm", "SRC/analysis/", "algorithm type args..."),
    ("integrator", "analysis", "integrator", "SRC/analysis/", "integrator type args..."),
    ("analysis", "analysis", "analysis", "SRC/analysis/", "analysis type"),
    ("analyze", "analysis", "analysis", "SRC/analysis/", "analyze numIter ?dt?"),
    ("eigen", "analysis", "eigen", "SRC/analysis/", "eigen numEigenvalues"),
    ("modalProperties", "analysis", "modal", "SRC/analysis/", "modalProperties -file file"),
    ("responseSpectrumAnalysis", "analysis", "spectrum", "SRC/analysis/", "responseSpectrumAnalysis args..."),
    ("recorder", "recorder", "recorder", "SRC/recorder/", "recorder type args..."),
    ("parameter", "parameter", "parameter", "SRC/domain/component/", "parameter tag target..."),
    ("addToParameter", "parameter", "parameter", "SRC/domain/component/", "addToParameter parameterTag target..."),
    ("updateParameter", "parameter", "parameter", "SRC/domain/component/", "updateParameter parameterTag value"),
    ("updateMaterials", "parameter", "material-update", "SRC/domain/component/", "updateMaterials -material matTag parameter value"),
    ("updateMaterialStage", "parameter", "material-stage", "SRC/material/nD/soil/", "updateMaterialStage -material matTag -stage stage"),
    ("setParameter", "parameter", "parameter", "SRC/domain/component/", "setParameter -val value target..."),
    ("print", "domain", "diagnostics", "SRC/modelbuilder/tcl/", "print ?options?"),
    ("wipe", "domain", "lifecycle", "SRC/modelbuilder/tcl/", "wipe"),
    ("wipeAnalysis", "analysis", "lifecycle", "SRC/analysis/", "wipeAnalysis"),
    ("frictionModel", "material", "friction", "SRC/element/frictionBearing/", "frictionModel type tag args..."),
)


_OFFICIAL_MODELING = (
    ("build", "model", "builder", "SRC/runtime/commands/modeling/model.cpp", "build"),
    ("getNDM", "model", "query", "SRC/runtime/commands/modeling/nodes.cpp", "getNDM"),
    ("getNDF", "model", "query", "SRC/runtime/commands/modeling/nodes.cpp", "getNDF"),
    ("node", "model", "node", "SRC/runtime/commands/modeling/nodes.cpp", "node tag x y ?z?"),
    ("mass", "model", "mass", "SRC/runtime/commands/modeling/nodes.cpp", "mass nodeTag mx ?my mz ...?"),
    ("element", "element", "element", "SRC/runtime/commands/modeling/element.cpp", "element type eleTag nodes... args..."),
    ("print", "domain", "diagnostics", "SRC/runtime/commands/modeling/printing.cpp", "print ?options?"),
    ("classType", "domain", "diagnostics", "SRC/runtime/commands/modeling/printing.cpp", "classType type tag"),
    ("printModel", "domain", "diagnostics", "SRC/runtime/commands/modeling/printing.cpp", "printModel"),
    ("fix", "constraint", "sp", "SRC/runtime/commands/modeling/constraint.cpp", "fix nodeTag dof..."),
    ("fixX", "constraint", "sp", "SRC/runtime/commands/modeling/constraint.cpp", "fixX nodeTag"),
    ("fixY", "constraint", "sp", "SRC/runtime/commands/modeling/constraint.cpp", "fixY nodeTag"),
    ("fixZ", "constraint", "sp", "SRC/runtime/commands/modeling/constraint.cpp", "fixZ nodeTag"),
    ("sp", "constraint", "sp", "SRC/runtime/commands/modeling/constraint.cpp", "sp nodeTag dof value"),
    ("equalDOF", "constraint", "mpc", "SRC/runtime/commands/modeling/constraint.cpp", "equalDOF masterNode slaveNode dof..."),
    ("rigidLink", "constraint", "mpc", "SRC/runtime/commands/domain/rigid_links.cpp", "rigidLink type masterNode slaveNode"),
    ("rigidDiaphragm", "constraint", "mpc", "SRC/runtime/commands/domain/rigid_links.cpp", "rigidDiaphragm normalDir retained constrained..."),
    ("groundMotion", "constraint", "motion", "SRC/runtime/commands/modeling/constraint.cpp", "groundMotion tag type args..."),
    ("imposedMotion", "constraint", "motion", "SRC/runtime/commands/modeling/constraint.cpp", "imposedMotion nodeTag dof motionTag"),
    ("imposedSupportMotion", "constraint", "motion", "SRC/runtime/commands/modeling/constraint.cpp", "imposedSupportMotion nodeTag dof motionTag"),
    ("uniaxialMaterial", "material", "uniaxial", "SRC/runtime/commands/modeling/uniaxialMaterial.cpp", "uniaxialMaterial type matTag args..."),
    ("nDMaterial", "material", "nD", "SRC/runtime/commands/modeling/material/nDMaterial.cpp", "nDMaterial type matTag args..."),
    ("material", "material", "generic", "SRC/runtime/commands/modeling/material/material.cpp", "material type tag args..."),
    ("patch", "section", "fiber", "SRC/runtime/commands/modeling/section.cpp", "patch type ..."),
    ("fiber", "section", "fiber", "SRC/runtime/commands/modeling/section.cpp", "fiber ..."),
    ("layer", "section", "fiber", "SRC/runtime/commands/modeling/section.cpp", "layer ..."),
    ("Hfiber", "section", "fiber", "SRC/runtime/commands/modeling/section.cpp", "Hfiber ..."),
    ("geomTransf", "transformation", "coordTransformation", "SRC/runtime/commands/modeling/geomTransf.cpp", "geomTransf type tag args..."),
    ("transform", "transformation", "coordTransformation", "SRC/runtime/commands/modeling/geomTransf.cpp", "transform type tag args..."),
    ("timeSeries", "domain", "timeSeries", "SRC/runtime/commands/modeling/nodes.cpp", "timeSeries type tag args..."),
    ("pattern", "domain", "pattern", "SRC/runtime/commands/modeling/nodes.cpp", "pattern type tag args..."),
    ("nodalLoad", "domain", "load", "SRC/runtime/commands/modeling/nodes.cpp", "nodalLoad nodeTag values..."),
    ("eleLoad", "domain", "elementLoad", "SRC/runtime/commands/modeling/element.cpp", "eleLoad ..."),
    ("block2D", "mesh", "block", "SRC/runtime/commands/modeling/utilities/blockND.cpp", "block2D ..."),
    ("block3D", "mesh", "block", "SRC/runtime/commands/modeling/utilities/blockND.cpp", "block3D ..."),
    ("beamIntegration", "integration", "beam", "SRC/runtime/commands/modeling/element.cpp", "beamIntegration type tag args..."),
    ("frictionModel", "material", "friction", "SRC/runtime/commands/modeling/element.cpp", "frictionModel type tag args..."),
    ("cyclicModel", "material", "cyclic", "SRC/runtime/commands/modeling/commands.h", "cyclicModel type tag args..."),
    ("damageModel", "material", "damage", "SRC/runtime/commands/modeling/commands.h", "damageModel type tag args..."),
    ("hystereticBackbone", "material", "backbone", "SRC/runtime/commands/modeling/commands.h", "hystereticBackbone ..."),
    ("backbone", "material", "backbone", "SRC/runtime/commands/modeling/commands.h", "backbone ..."),
    ("ysEvolutionModel", "material", "yieldSurface", "SRC/runtime/commands/modeling/commands.h", "ysEvolutionModel ..."),
    ("yieldSurface_BC", "material", "yieldSurface", "SRC/runtime/commands/modeling/commands.h", "yieldSurface_BC ..."),
    ("plasticMaterial", "material", "yieldSurface", "SRC/runtime/commands/modeling/commands.h", "plasticMaterial ..."),
    ("updateMaterialStage", "parameter", "material-stage", "SRC/runtime/commands/modeling/commands.h", "updateMaterialStage -material tag -stage stage"),
    ("updateMaterials", "parameter", "material-update", "SRC/domain/component/TclUpdateMaterialCommand.cpp", "updateMaterials -material tag parameter value"),
    ("updateParameter", "parameter", "parameter", "SRC/modelbuilder/tcl/TclModelBuilder.cpp", "updateParameter parameterTag value"),
    ("generateInterfacePoints", "interface", "interface", "SRC/element/UWelements/Tcl_generateInterfacePoints.cpp", "generateInterfacePoints ..."),
    ("addElementRayleigh", "damping", "element-rayleigh", "SRC/element/", "addElementRayleigh ..."),
)
 
_CATALOGS: Tuple[Tuple[str, str, str], ...] = (
    ("UNIAXIAL_MATERIALS", "uniaxialMaterial", "material/uniaxial"),
    ("ND_MATERIALS", "nDMaterial", "material/nD"),
    ("ELEMENT_CATALOG", "element", "element"),
    ("SECTION_CATALOG", "section", "material/section"),
    ("GEOM_TRANSF", "geomTransf", "coordTransformation"),
    ("BEAM_INTEGRATION", "beamIntegration", "element"),
    ("TIME_SERIES_TYPES", "timeSeries", "domain/pattern"),
    ("PATTERN_TYPES", "pattern", "domain/pattern"),
    ("RECORDER_TYPES", "recorder", "recorder"),
    ("ELEMENT_LOAD_TYPES", "eleLoad", "domain/pattern"),
)


class OpenSeesCommandRegistry:
    """Registro interrogabile dei comandi OpenSees supportati dal progetto."""

    def __init__(self) -> None:
        self._commands: Dict[Tuple[str, str], OpenSeesCommandSpec] = {}
        self._build()

    def _add(self, spec: OpenSeesCommandSpec) -> None:
        self._commands[(spec.kind, spec.name)] = spec

    def _build(self) -> None:
        implemented_core = {
            "node", "mass", "fix", "sp", "equalDOF", "uniaxialMaterial",
            "nDMaterial", "section", "geomTransf", "beamIntegration", "element",
            "timeSeries", "pattern", "load", "eleLoad", "region", "rayleigh",
            "constraints", "numberer", "system", "test", "algorithm",
            "integrator", "analysis", "analyze", "recorder", "parameter",
            "updateParameter", "updateMaterials", "updateMaterialStage",
            "setParameter",
        }
        for name, kind, family, source, syntax in _CORE:
            self._add(
                OpenSeesCommandSpec(
                    name=name,
                    kind=kind,
                    family=family,
                    source=source,
                    syntax=syntax,
                    implemented=name in implemented_core,
                )
            )

        for table_name, kind, source_area in _CATALOGS:
            table = getattr(catalog, table_name, {}) or {}
            if not isinstance(table, dict):
                continue
            for name, raw in table.items():
                if not isinstance(raw, dict):
                    continue
                source = f"SRC/{source_area}/"
                syntax = ""
                notes = str(raw.get("notes", "") or "")
                if kind == "element":
                    syntax = f"element {name} eleTag <nodes...> {raw.get('args', '')}".strip()
                elif kind in {"uniaxialMaterial", "nDMaterial", "section"}:
                    params = [
                        str(p[0])
                        for p in raw.get("params", [])
                        if isinstance(p, (tuple, list)) and p
                    ]
                    syntax = f"{kind} {name} tag " + " ".join(params)
                elif kind == "geomTransf":
                    syntax = f"geomTransf {name} tag ..."
                elif kind == "beamIntegration":
                    syntax = f"beamIntegration {name} tag ..."
                elif kind in {"timeSeries", "pattern"}:
                    syntax = f"{kind} {name} tag ..."
                elif kind == "recorder":
                    syntax = f"recorder {name} ..."
                elif kind == "eleLoad":
                    syntax = f"eleLoad {name} ..."
                self._add(
                    OpenSeesCommandSpec(
                        name=name,
                        kind=kind,
                        family=str(raw.get("family", table_name.lower())),
                        source=source,
                        syntax=syntax,
                        notes=notes,
                        implemented=True,
                        schema=raw,
                    )
                )

        # Comandi presenti direttamente nel runtime OpenSees/SRC.
        official_implemented = {"node", "mass", "element", "fix", "fixX", "fixY", "fixZ",
                                "sp", "equalDOF", "rigidLink", "rigidDiaphragm",
                                "groundMotion", "imposedMotion", "imposedSupportMotion",
                                "uniaxialMaterial", "nDMaterial", "material", "patch", "fiber",
                                "layer", "Hfiber", "geomTransf", "transform", "timeSeries",
                                "pattern", "nodalLoad", "eleLoad", "block2D", "block3D",
                                "beamIntegration", "frictionModel", "cyclicModel", "damageModel",
                                "hystereticBackbone", "backbone", "ysEvolutionModel",
                                "yieldSurface_BC", "plasticMaterial", "updateMaterialStage",
                                "updateMaterials", "updateParameter", "generateInterfacePoints",
                                "addElementRayleigh"}
        for name, kind, family, source, syntax in _OFFICIAL_MODELING:
            self._add(
                OpenSeesCommandSpec(
                    name=name, kind=kind, family=family, source=source, syntax=syntax,
                    implemented=name in official_implemented,
                )
            )

        for table_name, kind, source_area in (
            ("CONSTRAINT_HANDLERS", "constraints", "handler"),
            ("NUMBERERS", "numberer", "graph"),
            ("SYSTEMS", "system", "system_of_eqn"),
            ("ALGORITHMS", "algorithm", "analysis"),
            ("INTEGRATORS", "integrator", "analysis"),
            ("TESTS", "test", "convergenceTest"),
        ):
            table = getattr(catalog, table_name, {}) or {}
            if not isinstance(table, dict):
                continue
            for name, raw in table.items():
                if not isinstance(raw, dict):
                    continue
                self._add(
                    OpenSeesCommandSpec(
                        name=name,
                        kind=kind,
                        family=table_name.lower(),
                        source=f"SRC/{source_area}/",
                        syntax=f"{kind} {name} ...",
                        notes=str(raw.get("notes", "") or ""),
                        implemented=True,
                        schema=raw,
                    )
                )

        for name, raw in (getattr(catalog, "UPDATE_COMMANDS", {}) or {}).items():
            if not isinstance(raw, dict):
                continue
            self._add(
                OpenSeesCommandSpec(
                    name=name,
                    kind="parameter",
                    family="update",
                    source="SRC/domain/component/",
                    syntax=str(raw.get("syntax", "") or name),
                    notes=str(raw.get("notes", "") or ""),
                    implemented=True,
                    schema=raw,
                )
            )

    def all(self) -> List[OpenSeesCommandSpec]:
        return sorted(self._commands.values(), key=lambda x: (x.kind.lower(), x.name.lower()))

    def find(
        self,
        query: str = "",
        kind: Optional[str] = None,
        implemented_only: bool = False,
    ) -> List[OpenSeesCommandSpec]:
        q = str(query or "").strip().lower()
        rows: Iterable[OpenSeesCommandSpec] = self._commands.values()
        if kind and kind != "Tutti":
            rows = (r for r in rows if r.kind == kind)
        if implemented_only:
            rows = (r for r in rows if r.implemented)
        if q:
            rows = (r for r in rows if q in r.search_text)
        return sorted(rows, key=lambda x: (x.kind.lower(), x.name.lower()))

    def kinds(self) -> List[str]:
        return sorted({x.kind for x in self._commands.values()}, key=str.lower)

    def coverage(self) -> Dict[str, Any]:
        rows = self.all()
        by_kind: Dict[str, int] = {}
        implemented = 0
        for row in rows:
            by_kind[row.kind] = by_kind.get(row.kind, 0) + 1
            implemented += int(row.implemented)
        return {
            "total": len(rows),
            "implemented": implemented,
            "catalog_only": len(rows) - implemented,
            "by_kind": dict(sorted(by_kind.items(), key=lambda kv: kv[0].lower())),
            "official_repo": OFFICIAL_REPO,
            "official_manual": OFFICIAL_MANUAL,
        }

    def get(self, name: str, kind: Optional[str] = None) -> Optional[OpenSeesCommandSpec]:
        if kind:
            return self._commands.get((kind, name))
        for spec in self._commands.values():
            if spec.name == name:
                return spec
        return None
