"""Motore macro: comandi personalizzati caricabili da cartella ``.py``.

Una macro dichiara, tramite decorator, a quali bersagli si applica e i
propri parametri::

    from gcs.core.macro_engine import macro, P

    @macro(
        nome="Offset ogni superficie",
        applies_to=("superficie",),           # punto/curva/superficie/solido/
                                              # nodo_mesh/elemento_mesh/entita
        params=[P("offset", "float", default=1.0, min=-50, max=50,
                  help="Spostamento lungo la normale [mm]")],
        create_new=True,                       # crea entità nuove dal risultato
    )
    def run(ctx, target, params):
        \"\"\"Applicata a OGNI superficie delle entità selezionate.\"\"\"
        ...
        return nuovo_shape            # oppure None (solo effetti collaterali)

Il motore:
  1. espande la selezione corrente nei **bersagli** richiesti (es. ogni
     superficie di ogni solido selezionato);
  2. invoca ``run(ctx, target, params)`` per ciascun bersaglio con gestione
     errori per-elemento, callback di progresso e statistiche;
  3. raccoglie i risultati: shape di ritorno -> sostituzione o nuova entità
     (opzione ``create_new``), gruppi collessivi, log dettagliato.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .entities import Entity, normalize_type, NOME_TIPO_IT


# ---------------------------------------------------------------------------
# schema parametri
# ---------------------------------------------------------------------------

@dataclass
class Param:
    """Descrizione di un parametro macro (usata per il dialog GUI auto-generato)."""
    name: str
    ptype: str = "float"          # float | int | str | bool | choice | vec3
    default: object = 0.0
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[Tuple] = None
    help: str = ""

    def coerce(self, value):
        """Converte e valida un valore fornito dall'utente."""
        try:
            if self.ptype == "float":
                v = float(value)
                if self.min is not None and v < self.min:
                    v = self.min
                if self.max is not None and v > self.max:
                    v = self.max
                return v
            if self.ptype == "int":
                v = int(round(float(value)))
                if self.min is not None and v < int(self.min):
                    v = int(self.min)
                if self.max is not None and v > int(self.max):
                    v = int(self.max)
                return v
            if self.ptype == "bool":
                return bool(value)
            if self.ptype == "choice":
                s = str(value)
                if self.choices is not None and s not in self.choices:
                    raise ValueError(
                        f"'{s}' non tra le scelte ammesse {tuple(self.choices)}")
                return s
            if self.ptype == "vec3":
                if isinstance(value, (list, tuple)):
                    return tuple(float(x) for x in value[:3])
                return tuple(float(x) for x in str(value).replace(",", " ").split()[:3])
            return str(value)
        except Exception as exc:
            raise ValueError(f"Parametro '{self.name}': valore '{value}' non valido "
                             f"({self.ptype})") from exc


def P(name, ptype="float", default=0.0, min=None, max=None, choices=None,
      help="") -> Param:
    """Scorciatoia per dichiarare un parametro."""
    return Param(name, ptype, default, min, max, choices, help)


#: bersagli ammessi (canonici + alias italiani)
TARGET_ALIASES = {
    "point": "point", "punto": "point", "punti": "point",
    "curve": "curve", "curva": "curve", "edge": "curve", "linea": "curve",
    "face": "face", "superficie": "face", "superfici": "face",
    "solid": "solid", "solido": "solid", "solidi": "solid", "volume": "solid",
    "mesh_node": "mesh_node", "nodo_mesh": "mesh_node", "nodi_mesh": "mesh_node",
    "mesh_element": "mesh_element", "elemento_mesh": "mesh_element",
    "entity": "entity", "entita": "entity", "entità": "entity",
}


def normalize_target(t: str) -> str:
    tt = TARGET_ALIASES.get((t or "").strip().lower())
    if not tt:
        raise ValueError(f"Bersaglio macro '{t}' non valido. Ammessi: "
                         "punto, curva, superficie, solido, nodo_mesh, "
                         "elemento_mesh, entita")
    return tt


# ---------------------------------------------------------------------------
# specifica macro e contesto
# ---------------------------------------------------------------------------

@dataclass
class MacroSpec:
    """Metadati + funzione di una macro personalizzata."""
    name: str
    func: Callable
    applies_to: Tuple[str, ...] = ("entity",)
    params: List[Param] = field(default_factory=list)
    description: str = ""
    category: str = "Generale"
    create_new: bool = False     # shape ritornate -> nuove entità in un gruppo
    replace: bool = True         # shape ritornate -> sostituisce l'entità bersaglio
    source_file: str = ""

    def targets_label(self) -> str:
        return ", ".join(self.applies_to)


class MacroTarget:
    """Un bersaglio singolo su cui la macro viene invocata."""

    def __init__(self, kind: str, entity: Optional[Entity] = None,
                 shape=None, model=None, node_id: Optional[int] = None,
                 element_id: Optional[int] = None):
        self.kind = kind            # point/curve/face/solid/entity/mesh_node/mesh_element
        self.entity = entity        # entità proprietaria (None per nodi mesh)
        self.shape = shape          # TopoDS_Shape (geometria) o None (mesh)
        self.model = model          # MeshModel (per bersagli mesh)
        self.node_id = node_id
        self.element_id = element_id

    @property
    def label(self) -> str:
        if self.kind == "mesh_node":
            return f"nodo {self.node_id} [{self.model.name if self.model else '-'}]"
        if self.kind == "mesh_element":
            return f"elemento {self.element_id} [{self.model.name if self.model else '-'}]"
        return f"{NOME_TIPO_IT.get(self.kind, self.kind)}: {self.entity.name}"


class MacroContext:
    """Contesto passato a ogni macro: documento, parametri, log, statistiche."""

    def __init__(self, doc, params: dict, log=print, progress=None):
        self.doc = doc
        self.params = params
        self._log = log
        self._progress = progress
        self.ok = 0
        self.errors: List[Tuple[str, str]] = []
        self.new_shapes: List[Tuple[MacroTarget, object]] = []
        self.t0 = time.time()

    def log(self, msg: str) -> None:
        self._log(f"[macro] {msg}")

    def progress(self, i: int, n: int) -> None:
        if self._progress:
            self._progress(i, n)

    def report(self) -> str:
        dt = time.time() - self.t0
        righe = [f"Completata in {dt:.2f}s — {self.ok} bersagli OK, "
                 f"{len(self.errors)} errori"]
        for label, err in self.errors[:8]:
            righe.append(f"  ✗ {label}: {err}")
        if len(self.errors) > 8:
            righe.append(f"  ... e altri {len(self.errors) - 8} errori")
        return "\n".join(righe)


# ---------------------------------------------------------------------------
# decorator di registrazione
# ---------------------------------------------------------------------------

def macro(nome=None, applies_to=("entita",), params=None, description="",
          category="Generale", create_new=False, replace=True):
    """Decorator che trasforma una funzione in macro registrabile.

    La funzione deve avere firma ``run(ctx, target, params)``.
    """
    def _decor(fn: Callable):
        targets = tuple(normalize_target(t) for t in
                        (applies_to if isinstance(applies_to, (list, tuple))
                         else [applies_to]))
        spec = MacroSpec(
            name=nome or fn.__name__.replace("_", " ").title(),
            func=fn,
            applies_to=targets,
            params=list(params or []),
            description=description or inspect.getdoc(fn) or "",
            category=category,
            create_new=create_new,
            replace=replace,
        )
        fn.__macro_spec__ = spec
        return fn
    return _decor


# ---------------------------------------------------------------------------
# motore
# ---------------------------------------------------------------------------

class MacroEngine:
    """Carica macro da cartelle .py e le esegue sulla selezione corrente."""

    def __init__(self, doc, log=print, progress=None):
        self.doc = doc
        self.log = log
        self.progress = progress
        self.macros: Dict[str, MacroSpec] = {}
        self.load_errors: List[str] = []

    # ---------------------------------------------------------------- loading
    def load_folder(self, folder: str) -> int:
        """Importa tutti i .py della cartella; ogni funzione con attributo
        ``__macro_spec__`` viene registrata. Ritorna il numero di macro."""
        self.load_errors.clear()
        if not os.path.isdir(folder):
            self.log(f"[macro] Cartella macro non trovata: {folder}")
            return 0
        prima = len(self.macros)
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            path = os.path.join(folder, fn)
            self._load_file(path)
        self.log(f"[macro] Caricate {len(self.macros) - prima} macro da {folder}")
        return len(self.macros) - prima

    def _load_file(self, path: str) -> None:
        modname = f"gcs_user_macro_{os.path.splitext(os.path.basename(path))[0]}"
        try:
            spec = importlib.util.spec_from_file_location(modname, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[modname] = mod
            spec.loader.exec_module(mod)
            trovate = 0
            for attr in vars(mod).values():
                spec_obj = getattr(attr, "__macro_spec__", None)
                if spec_obj is not None:
                    spec_obj.source_file = path
                    self.register(spec_obj)
                    trovate += 1
            if trovate == 0:
                self.load_errors.append(
                    f"{os.path.basename(path)}: nessuna @macro trovata")
        except Exception as exc:
            tb = traceback.format_exc(limit=2)
            self.load_errors.append(f"{os.path.basename(path)}: {exc}\n{tb}")
            self.log(f"[macro] ERRORE caricando {path}: {exc}")

    def register(self, spec: MacroSpec) -> None:
        self.macros[spec.name] = spec

    def list_names(self) -> List[str]:
        return list(self.macros.keys())

    def by_name(self, name: str) -> Optional[MacroSpec]:
        return self.macros.get(name)

    # ------------------------------------------------------- risoluzione bersagli
    def _expand_targets(self, spec: MacroSpec) -> List[MacroTarget]:
        """Espande la selezione corrente nei bersagli richiesti dalla macro."""
        from . import occ_utils as ou
        bersagli: List[MacroTarget] = []
        visti = set()

        def add_geo(kind: str, entity: Entity, shape):
            key = id(shape)
            if key in visti:
                return
            visti.add(key)
            bersagli.append(MacroTarget(kind, entity=entity, shape=shape))

        for t in spec.applies_to:
            if t in ("mesh_node", "mesh_element"):
                for model in self.doc.mesh_models.values():
                    if t == "mesh_node":
                        nodi = model.sel_nodes or set()
                        for n in nodi:
                            bersagli.append(MacroTarget(t, model=model, node_id=n))
                    else:
                        eles = model.sel_elements or set()
                        for eid in eles:
                            bersagli.append(MacroTarget(t, model=model,
                                                        element_id=eid))
                continue

            for eid in sorted(self.doc.selection):
                e = self.doc.entities.get(eid)
                if e is None:
                    continue
                if t == "entity":
                    shape = e.shape
                    if shape is None:
                        shape = self._mesh_block_shape(e)
                    add_geo(e.etype, e, shape if shape is not None else e)
                    continue
                # espande in sotto-shape del tipo richiesto
                shape = e.shape
                if shape is None:
                    shape = self._mesh_block_shape(e)
                if shape is None:
                    continue
                kind = {"point": ou.TopAbs_VERTEX, "curve": ou.TopAbs_EDGE,
                        "face": ou.TopAbs_FACE, "solid": ou.TopAbs_SOLID}[t]
                if e.etype == t:
                    add_geo(t, e, shape)
                    continue
                try:
                    for s in ou.unique_subshapes(shape, kind):
                        add_geo(t, e, s)
                except Exception:
                    continue
        return bersagli

    def _mesh_block_shape(self, e: Entity):
        """Shape di display on-the-fly per un blocco mesh (per macro uniformi)."""
        from . import occ_utils as ou
        ref = e.meta.get("mesh_ref")
        if not ref:
            return None
        model = self.doc.mesh_models.get(ref[0])
        if model is None:
            return None
        try:
            return ou.mesh_block_shape(model, ref[1], ref[2])
        except Exception:
            return None

    # ---------------------------------------------------------------- esecuzione
    def run(self, spec: MacroSpec, params: Optional[dict] = None) -> MacroContext:
        """Esegue la macro su tutti i bersagli della selezione corrente."""
        # valida/coerce parametri
        pfin = {}
        for p in spec.params:
            pfin[p.name] = p.coerce((params or {}).get(p.name, p.default))
        extra = {k: v for k, v in (params or {}).items() if k not in pfin}
        pfin.update(extra)

        ctx = MacroContext(self.doc, pfin, log=self.log, progress=self.progress)
        bersagli = self._expand_targets(spec)
        if not bersagli:
            self.log(f"[macro] '{spec.name}': nessun bersaglio nella selezione "
                     f"(richiesti: {spec.targets_label()})")
            return ctx

        self.log(f"[macro] '{spec.name}' su {len(bersagli)} bersaglio/i "
                 f"({spec.targets_label()})")
        n = len(bersagli)
        for i, target in enumerate(bersagli):
            ctx.progress(i, n)
            try:
                res = spec.func(ctx, target, pfin)
                if res is not None and hasattr(res, "ShapeType"):
                    ctx.new_shapes.append((target, res))
                ctx.ok += 1
            except Exception as exc:
                ctx.errors.append((target.label, str(exc)))
        ctx.progress(n, n)

        # materializza i risultati
        if ctx.new_shapes:
            if spec.create_new:
                g = self.doc.groups.get_or_create(f"Risultati — {spec.name}",
                                                  (0.85, 0.5, 0.15))
                from .entities import Entity as _E
                for target, shape in ctx.new_shapes:
                    ent = _E(spec.applies_to[0], shape=shape,
                             name=f"{spec.name} {len(g.member_ids) + 1}")
                    self.doc.add_entity(ent)
                    g.member_ids.add(ent.id)
                self.log(f"[macro] create {len(ctx.new_shapes)} nuove entità "
                         f"nel gruppo 'Risultati — {spec.name}'")
            elif spec.replace:
                for target, shape in ctx.new_shapes:
                    if target.entity is not None and target.entity.shape is not None:
                        # sostituisce solo se il bersaglio è l'intera entità
                        try:
                            if target.entity.shape.IsSame(shape):
                                continue
                        except Exception:
                            pass
                        if target.kind in ("point", "curve", "face", "solid") and \
                                target.entity.etype == target.kind:
                            self.doc.replace_entity_shape(target.entity, shape)

        self.log("[macro] " + ctx.report().replace("\n", "\n[macro] "))
        self.doc.notify("macro_completed", {"name": spec.name,
                                            "ok": ctx.ok,
                                            "errors": len(ctx.errors)})
        return ctx


def write_macro_template(path: str, name="La mia macro") -> None:
    """Genera un file macro di partenza personalizzabile."""
    modello = '''"""Macro generata automaticamente: personalizzala liberamente."""

from gcs.core.macro_engine import macro, P


@macro(
    nome="{nome}",
    applies_to=("superficie",),        # punto | curva | superficie | solido |
                                       # nodo_mesh | elemento_mesh | entita
    params=[
        P("fattore", "float", default=1.0, min=0.0, max=100.0,
          help="Parametro di esempio"),
        P("opzione", "choice", default="A", choices=("A", "B", "C"),
          help="Scelta di esempio"),
    ],
    category="Personalizzate",
    create_new=False,                  # True: lo shape ritornato diventa nuova entità
    replace=False,                     # True: sostituisce la geometria del bersaglio
)
def run(ctx, target, params):
    """Invocata su OGNI bersaglio della selezione corrente."""
    ctx.log(f"Bersaglio: {{target.label}}, fattore={{params['fattore']}}")
    # Esempi:
    #   target.shape      -> TopoDS_Shape del bersaglio (geometria)
    #   target.entity     -> Entity proprietaria (nome, colore, meta...)
    #   target.model.nodes[target.node_id] -> (x, y, z) per nodo_mesh
    #   per spostare un nodo: target.model.nodes[target.node_id] = (nx, ny, nz)
    # return nuovo_shape  (opzionale: vedi create_new / replace)
'''
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(modello.format(nome=name))
