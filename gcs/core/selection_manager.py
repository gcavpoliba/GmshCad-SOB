"""Gestore unico della selezione logica CAD/Mesh/OpenSees.

Il documento resta la sorgente di verità dello stato; la GUI usa questa
facade come unico punto di ingresso per sincronizzare viewer e tree.
"""

from __future__ import annotations

from contextlib import contextmanager


class SelectionManager:
    """Facade unificata sopra CADDocument.selection."""

    CONTEXTS = ("cad", "mesh", "opensees")

    def __init__(self, doc):
        self.doc = doc
        self.context = "cad"
        self._sync_depth = 0

    @property
    def sync_in_progress(self) -> bool:
        return self._sync_depth > 0

    @contextmanager
    def syncing(self):
        self._sync_depth += 1
        try:
            yield
        finally:
            self._sync_depth = max(0, self._sync_depth - 1)

    def set_context(self, context: str) -> str:
        value = str(context or "").strip().lower()
        if value not in self.CONTEXTS:
            raise ValueError(
                f"Contesto selezione non valido: {context!r}. "
                f"Valori ammessi: {', '.join(self.CONTEXTS)}"
            )
        self.context = value
        return value

    def set_selection(self, entity_ids, context: str | None = None):
        if context is not None:
            self.set_context(context)
        with self.syncing():
            return self.doc.set_selection(entity_ids)

    def select(self, entity_id: int, additive: bool = False,
               toggle: bool = False, context: str | None = None):
        if context is not None:
            self.set_context(context)
        eid = int(entity_id)
        current = set(self.doc.selection)
        if toggle:
            if eid in current:
                current.remove(eid)
            else:
                current.add(eid)
        elif additive:
            current.add(eid)
        else:
            current = {eid}
        return self.set_selection(current)

    def select_many(self, entity_ids, additive: bool = False,
                    toggle: bool = False, context: str | None = None):
        if context is not None:
            self.set_context(context)
        incoming = {int(i) for i in entity_ids}
        current = set(self.doc.selection) if (additive or toggle) else set()
        if toggle:
            for eid in incoming:
                if eid in current:
                    current.remove(eid)
                else:
                    current.add(eid)
        else:
            current.update(incoming)
        return self.set_selection(current)

    def add_to_selection(self, entity_ids):
        return self.select_many(entity_ids, additive=True)

    def remove_from_selection(self, entity_ids):
        current = set(self.doc.selection)
        current.difference_update(int(i) for i in entity_ids)
        return self.set_selection(current)

    def clear_selection(self, context: str | None = None):
        return self.set_selection(set(), context=context)

    def selected_entities(self):
        return self.doc.selected_entities()

    def selected_entity_ids(self):
        return set(self.doc.selection)
