"""Gestione dei gruppi di entità.

I gruppi possono contenere:
  * entità geometriche (member_ids: insieme di id Entity);
  * elementi/nodi di mesh (per ogni MeshModel: insiemi di id).

Un gruppo ha un nome univoco, un colore opzionale e può essere esportato
come lista testuale o mappato su gruppi fisici Gmsh.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict, Iterable, Optional, Set, Tuple

from .entities import Entity, normalize_type


class EntityGroup:
    """Gruppo di entità (geometria e/o mesh)."""

    def __init__(self, name: str, color=None):
        self.name = name
        self.color = color                    # (r,g,b) o None
        self.member_ids: Set[int] = set()     # entità geometriche
        # mesh: {nome_modello: {id_elemento}}, {nome_modello: {id_nodo}}
        self.mesh_elements: Dict[str, Set[int]] = {}
        self.mesh_nodes: Dict[str, Set[int]] = {}

    def empty(self) -> bool:
        return not self.member_ids and not self.mesh_elements and not self.mesh_nodes

    def count_geo(self) -> int:
        return len(self.member_ids)

    def count_mesh(self) -> Tuple[int, int]:
        nel = sum(len(v) for v in self.mesh_elements.values())
        nno = sum(len(v) for v in self.mesh_nodes.values())
        return nel, nno

    def __repr__(self):  # pragma: no cover
        return (f"EntityGroup('{self.name}', geo={self.count_geo()}, "
                f"mesh_el={self.count_mesh()[0]}, mesh_nodi={self.count_mesh()[1]})")


class GroupError(Exception):
    pass


class GroupManager:
    """Registro dei gruppi del documento (nome -> EntityGroup)."""

    def __init__(self):
        self.groups: "OrderedDict[str, EntityGroup]" = OrderedDict()

    # ----------------------------------------------------------------- CRUD
    def create(self, name: str, color=None) -> EntityGroup:
        if not name or not name.strip():
            raise GroupError("Nome gruppo vuoto")
        if name in self.groups:
            raise GroupError(f"Esiste già un gruppo chiamato '{name}'")
        g = EntityGroup(name, color)
        self.groups[name] = g
        return g

    def get_or_create(self, name: str, color=None) -> EntityGroup:
        return self.groups.get(name) or self.create(name, color)

    def get(self, name: str) -> Optional[EntityGroup]:
        return self.groups.get(name)

    def delete(self, name: str) -> None:
        self.groups.pop(name, None)

    def rename(self, old: str, new: str) -> None:
        g = self.groups.get(old)
        if not g:
            raise GroupError(f"Gruppo '{old}' inesistente")
        if new in self.groups and new != old:
            raise GroupError(f"Esiste già un gruppo chiamato '{new}'")
        self.groups.pop(old)
        g.name = new
        self.groups[new] = g

    def list_names(self) -> list:
        return list(self.groups.keys())

    def clear(self) -> None:
        self.groups.clear()

    # -------------------------------------------------------------- membri geo
    def add_geo(self, name: str, entity_ids: Iterable[int]) -> EntityGroup:
        g = self.get_or_create(name)
        g.member_ids.update(int(i) for i in entity_ids)
        return g

    def remove_geo(self, name: str, entity_ids: Iterable[int]) -> EntityGroup:
        g = self._require(name)
        g.member_ids.difference_update(int(i) for i in entity_ids)
        return g

    def _require(self, name: str) -> EntityGroup:
        g = self.groups.get(name)
        if not g:
            raise GroupError(f"Gruppo '{name}' inesistente")
        return g

    # ------------------------------------------------------------- membri mesh
    def add_mesh_elements(self, name: str, model_name: str,
                          elem_ids: Iterable[int]) -> EntityGroup:
        g = self.get_or_create(name)
        g.mesh_elements.setdefault(model_name, set()).update(int(i) for i in elem_ids)
        return g

    def add_mesh_nodes(self, name: str, model_name: str,
                       node_ids: Iterable[int]) -> EntityGroup:
        g = self.get_or_create(name)
        g.mesh_nodes.setdefault(model_name, set()).update(int(i) for i in node_ids)
        return g

    # ------------------------------------------------------------- risoluzione
    def resolve_geo(self, doc, name: str) -> list:
        """Entità del documento membri del gruppo (espande anche gruppi annidati
        che contengono id di altri gruppi tramite meta['group_ref'])."""
        g = self._require(name)
        out = []
        seen = set(g.member_ids)
        for eid in list(g.member_ids):
            ent = doc.entities.get(eid)
            if ent is not None and ent.etype == "group":
                for sub in self.resolve_geo(doc, ent.name):
                    out.append(sub)
            elif ent is not None:
                out.append(ent)
        _ = seen
        return out

    def group_from_selection(self, doc, name: str, color=None) -> EntityGroup:
        """Crea (o aggiorna) un gruppo a partire dalla selezione corrente."""
        g = self.get_or_create(name, color)
        g.member_ids.update(doc.selection)
        for model_name, model in doc.mesh_models.items():
            if model.sel_elements:
                g.mesh_elements.setdefault(model_name, set()).update(model.sel_elements)
            if model.sel_nodes:
                g.mesh_nodes.setdefault(model_name, set()).update(model.sel_nodes)
        return g

    # ------------------------------------------------------------------ export
    def export_text(self, doc) -> str:
        """Rappresentazione testuale di tutti i gruppi (lista id + conteggi)."""
        righe = ["# Gruppi documento", ""]
        for name, g in self.groups.items():
            righe.append(f"[{name}]")
            if g.member_ids:
                enti = []
                for eid in sorted(g.member_ids):
                    ent = doc.entities.get(eid)
                    enti.append(f"{eid}({normalize_type(ent.etype) if ent else '?'})")
                righe.append("  entità: " + ", ".join(enti))
            for mod, els in g.mesh_elements.items():
                righe.append(f"  mesh[{mod}] elementi ({len(els)}): "
                             + ", ".join(str(i) for i in sorted(els)))
            for mod, nodi in g.mesh_nodes.items():
                righe.append(f"  mesh[{mod}] nodi ({len(nodi)}): "
                             + ", ".join(str(i) for i in sorted(nodi)))
            righe.append("")
        return "\n".join(righe)
