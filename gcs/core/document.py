"""Documento CAD: registro entità, modelli mesh, gruppi, selezione, undo/redo.

Il documento è il "modello" nell'architettura MVC: la GUI (``gcs.gui``) lo
osserva tramite ``notify``/listener e tutte le operazioni di core (builder,
editor, selettori, macro) operano su di esso.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Set

from .entities import Entity, normalize_type, NOME_TIPO_IT
from .groups import GroupManager
from .mesh import MeshModel


class DocumentError(Exception):
    pass


class CADDocument:
    """Stato completo dell'ambiente CAD aperto."""

    def __init__(self, name: str = "Documento"):
        self.name = name
        # entità geometriche / blocchi mesh esposti come entità
        self.entities: Dict[int, Entity] = {}
        self._next_id = 1
        # modelli mesh importati (nome -> MeshModel)
        self.mesh_models: Dict[str, MeshModel] = {}
        self.groups = GroupManager()
        from .opensees_conditions import OpenSeesManager
        self.opensees = OpenSeesManager(self)
        self.selection: Set[int] = set()
        self.mode: str = "geometria"          # "geometria" | "mesh"
        self.undo_stack: List[Callable] = []
        self.redo_stack: List[Callable] = []
        self.listeners: List[Callable[[str, dict], None]] = []
        self._sub_index = {}                  # {(TShape, Loc): id entità figlia}

    # ------------------------------------------------------------- notifiche
    def add_listener(self, fn: Callable[[str, dict], None]) -> None:
        self.listeners.append(fn)

    def notify(self, event: str, data=None) -> None:
        for fn in list(self.listeners):
            try:
                fn(event, data or {})
            except Exception:
                pass

    # ------------------------------------------------------------ gestione id
    def _allocate_id(self) -> int:
        while self._next_id in self.entities:
            self._next_id += 1
        return self._next_id

    def add_entity(self, ent: Entity, push_undo=True) -> Entity:
        """Registra una nuova entità nel documento (con undo)."""
        ent.id = self._allocate_id()
        self.entities[ent.id] = ent
        self._next_id += 1
        if push_undo:
            doc = self

            def undo():
                doc.entities.pop(ent.id, None)
                doc.selection.discard(ent.id)

            def redo():
                doc.entities[ent.id] = ent

            self._push(undo, redo)
        self.notify("entity_added", {"id": ent.id})
        return ent

    def remove_entities(self, ids, push_undo=True) -> int:
        """Rimuove entità per id (con undo: ripristina oggetti completi)."""
        ids = [int(i) for i in ids if int(i) in self.entities]
        if not ids:
            return 0
        rimossi = {i: self.entities.pop(i) for i in ids}
        for i in rimossi:
            self.selection.discard(i)
        if push_undo:
            doc = self

            def undo():
                for i, e in rimossi.items():
                    doc.entities[i] = e

            def redo():
                for i in rimossi:
                    doc.entities.pop(i, None)
                    doc.selection.discard(i)

            self._push(undo, redo)
        self.notify("entities_removed", {"ids": list(rimossi)})
        return len(rimossi)

    def get(self, eid: int) -> Optional[Entity]:
        return self.entities.get(int(eid))

    def by_name(self, name: str) -> Optional[Entity]:
        for e in self.entities.values():
            if e.name == name:
                return e
        return None

    def selected_entities(self) -> List[Entity]:
        return [self.entities[i] for i in sorted(self.selection) if i in self.entities]

    def counts_by_type(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self.entities.values():
            out[e.etype] = out.get(e.etype, 0) + 1
        return out

    # --------------------------------------------------------------- selezione
    def set_selection(self, ids, notify=True) -> Set[int]:
        self.selection = {int(i) for i in ids if int(i) in self.entities}
        if notify:
            self.notify("selection_changed", {"ids": list(self.selection)})
        return self.selection

    # --------------------------------------------------------------- undo/redo
    def _push(self, undo_fn, redo_fn) -> None:
        self.undo_stack.append((undo_fn, redo_fn))
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        undo_fn, _ = self.undo_stack.pop()
        undo_fn()
        self.redo_stack.append((undo_fn, _))
        self.notify("history_changed", {})
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        _, redo_fn = self.redo_stack.pop()
        redo_fn()
        self.undo_stack.append((_, redo_fn))
        self.notify("history_changed", {})
        return True

    # --------------------------------------------------- sotto-entità (explode)
    def find_or_create_sub_entity(self, parent: Entity, ttype: str, shape) -> Entity:
        """Trova (o crea) l'entità corrispondente a una sotto-shape del padre.

        Usato dai selettori topologici (select_faces_of, select_boundary...):
        le sotto-entità restano collegate al padre tramite meta['parent'].
        """
        from . import occ_utils as ou
        t = normalize_type(ttype)
        key = None
        try:
            key = (shape.TShape(), shape.Location())
        except Exception:
            key = None
        if key is not None and key in self._sub_index:
            eid = self._sub_index[key]
            if eid in self.entities:
                return self.entities[eid]
        figlio = Entity(t, shape=shape,
                        name=f"{NOME_TIPO_IT[t]} di {parent.name}")
        figlio.meta["parent"] = parent.id
        figlio.color = parent.color
        self.add_entity(figlio, push_undo=False)
        if key is not None:
            self._sub_index[key] = figlio.id
        return figlio

    # ---------------------------------------------------------------- query API
    def query(self) -> "selectors.Query":
        from . import selectors
        return selectors.Query(self)

    # ------------------------------------------------------------------ import
    def import_msh(self, path: str, nome: Optional[str] = None) -> MeshModel:
        """Importa un file .msh e crea le entità-blocco (punti/curve/superfici/volumi)."""
        from .msh_importer import parse_msh
        model = parse_msh(path)
        model.name = nome or os.path.splitext(os.path.basename(path))[0]
        self.mesh_models[model.name] = model
        self._create_mesh_entities(model, path)
        self.mode = "mesh"
        self.notify("mesh_imported", {"model": model.name})
        return model

    def _create_mesh_entities(self, model: MeshModel, path: str) -> None:
        from .mesh import ELEM_INFO
        etype_by_dim = {0: "point", 1: "curve", 2: "face", 3: "solid"}
        colori = {0: (1.0, 0.2, 0.2), 1: (0.9, 0.7, 0.1), 2: (0.2, 0.75, 0.95),
                  3: (0.55, 0.7, 0.35)}
        for (dim, tag), blk in sorted(model.blocks.items()):
            if not blk.element_ids:
                continue
            etype = etype_by_dim[dim]
            # nome: preferisci nome fisico
            nomi_phys = [model.physicals.get((dim, pt), f"phys{pt}")
                         for pt in blk.physical_tags]
            base = nomi_phys[0] if nomi_phys else blk.nome
            ent = Entity(etype, shape=None,
                         name=f"{base}" if len(nomi_phys) == 1 else f"{base} [{blk.nome}]",
                         marker=blk.physical_tags[0] if blk.physical_tags else 0)
            ent.color = colori[dim]
            ent.meta["mesh_ref"] = (model.name, dim, tag)
            ent.meta["path"] = path
            ent.meta["n_elementi"] = len(blk.element_ids)
            self.add_entity(ent, push_undo=False)

    def import_cad(self, path: str) -> List[Entity]:
        """Importa STEP/IGES/BREP creando entità per ogni solido/shape trovata."""
        from . import occ_utils as ou
        est = os.path.splitext(path)[1].lower()
        if est in (".step", ".stp"):
            shape = ou.read_step(path)
        elif est in (".iges", ".igs"):
            shape = ou.read_iges(path)
        elif est == ".brep":
            shape = ou.read_brep(path)
        else:
            raise DocumentError(f"Formato CAD non supportato: {est}")
        ents = []
        if shape.ShapeType() == ou.TopAbs_COMPOUND:
            subs = ou.unique_subshapes(shape, ou.TopAbs_SOLID) or [shape]
        else:
            subs = [shape]
        for s in subs:
            tname = ou.shape_type_name(s)
            e = Entity(normalize_type(tname), shape=s,
                       name=os.path.basename(path))
            self.add_entity(e)
            ents.append(e)
        return ents

    # ------------------------------------------------------------------ export
    def _shapes_for_export(self, ids=None) -> list:
        if ids is None:
            enti = self.selected_entities()
            if not enti:                    # nessuna selezione: esporta tutto
                enti = list(self.entities.values())
        else:
            enti = [self.entities[int(i)] for i in ids if int(i) in self.entities]
        return [e.shape for e in enti if e.shape is not None]

    def export_step(self, path: str, ids=None) -> None:
        from . import occ_utils as ou
        shapes = self._shapes_for_export(ids)
        if not shapes:
            raise DocumentError("Nessuna geometria da esportare")
        ou.export_step(shapes, path)

    def export_brep(self, path: str, ids=None) -> None:
        from . import occ_utils as ou
        shapes = self._shapes_for_export(ids)
        if not shapes:
            raise DocumentError("Nessuna geometria da esportare")
        ou.export_brep(shapes, path)

    # ----------------------------------------------------------------- utility
    def replace_entity_shape(self, ent: Entity, new_shape, push_undo=True) -> None:
        """Sostituisce lo shape di un'entità (usato da editor e macro, con undo)."""
        if push_undo:
            doc = self
            old = ent.shape

            def undo():
                ent.shape = old

            def redo():
                ent.shape = new_shape

            self._push(undo, redo)
        ent.shape = new_shape
        self.notify("entity_updated", {"id": ent.id})

    def help_selection(self) -> str:
        """Mini-guida dei comandi di selezione (usata da console e Aiuto)."""
        from . import selectors as sel
        funzioni = [n for n in dir(sel) if n.startswith("select_") or
                    n in ("grow_selection", "shrink_selection", "invert_selection",
                          "select_none")]
        return ("Comandi di selezione disponibili:\n  " + "\n  ".join(funzioni) +
                "\n\nEsempio fluente: doc.query().type('superficie').planar().select()")
