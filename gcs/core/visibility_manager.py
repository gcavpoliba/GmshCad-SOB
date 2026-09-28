"""Gestore centralizzato della visibilità dei layer della scena."""

from __future__ import annotations

CAD_LAYER_TYPES = {
    "vertices": "point",
    "edges": "curve",
    "surfaces": "face",
    "solids": "solid",
    "compounds": "compound",
}


class VisibilityManager:
    """Separa visibilità per-entità, layer CAD e layer mesh."""

    def __init__(self, doc, viewer=None):
        self.doc = doc
        self.viewer = viewer
        self._cad_layers = {
            etype: True for etype in CAD_LAYER_TYPES.values()
        }
        self._mesh_visible = True

    def attach_viewer(self, viewer):
        self.viewer = viewer

    def _redraw(self):
        if self.viewer is not None and hasattr(self.viewer, "redraw_all"):
            self.viewer.redraw_all(fit=False)

    def _notify(self, reason: str, **extra):
        data = {"reason": reason}
        data.update(extra)
        self.doc.notify("visibility_changed", data)

    def is_entity_visible(self, entity) -> bool:
        if entity is None:
            return False
        if entity.is_mesh_block:
            ref = entity.meta.get("mesh_ref")
            if ref:
                model = self.doc.mesh_models.get(str(ref[0]))
                if model is not None and model.stale:
                    return False
            return bool(entity.visible and self._mesh_visible)
        return bool(
            entity.visible
            and self._cad_layers.get(str(entity.etype), True)
        )

    def is_cad_type_visible(self, etype: str) -> bool:
        return bool(self._cad_layers.get(str(etype), True))

    def set_entity_visible(self, entity_id: int, visible: bool):
        entity = self.doc.entities.get(int(entity_id))
        if entity is None:
            return False
        value = bool(visible)
        if entity.visible == value:
            return False
        entity.set_visible(value)
        self._notify("entity", entity_id=int(entity_id), visible=value)
        self._redraw()
        return True

    def set_entities_visible(self, entity_ids, visible: bool):
        value = bool(visible)
        changed = []
        for eid in entity_ids:
            entity = self.doc.entities.get(int(eid))
            if entity is not None and entity.visible != value:
                entity.set_visible(value)
                changed.append(int(eid))
        if changed:
            self._notify("entities", ids=changed, visible=value)
            self._redraw()
        return len(changed)

    def set_cad_type_visible(self, etype: str, visible: bool):
        etype = str(etype)
        value = bool(visible)
        changed = self._cad_layers.get(etype, True) != value
        self._cad_layers[etype] = value
        for entity in self.doc.entities.values():
            if (not entity.is_mesh_block
                    and entity.etype == etype
                    and entity.visible != value):
                entity.set_visible(value)
                changed = True
        if changed:
            self._notify("cad_layer", etype=etype, visible=value)
            self._redraw()
        return changed

    def set_all_cad_visible(self, visible: bool):
        value = bool(visible)
        changed = []
        layers_changed = any(state != value for state in self._cad_layers.values())
        for etype in self._cad_layers:
            self._cad_layers[etype] = value
        for entity in self.doc.entities.values():
            if entity.is_mesh_block:
                continue
            if entity.etype in self._cad_layers and entity.visible != value:
                entity.set_visible(value)
                changed.append(entity.id)
        if changed or layers_changed:
            self._notify("cad_all", ids=changed, visible=value)
            self._redraw()
        return len(changed)

    def invert_cad_visibility(self):
        changed = []
        for entity in self.doc.entities.values():
            if entity.is_mesh_block or entity.etype not in self._cad_layers:
                continue
            effective = self.is_entity_visible(entity)
            entity.set_visible(not effective)
            changed.append(entity.id)
        for etype in self._cad_layers:
            self._cad_layers[etype] = True
        if changed:
            self._notify("cad_invert", ids=changed)
            self._redraw()
        return len(changed)

    def isolate_entities(self, entity_ids):
        """Mostra solo le entità CAD indicate e aggiorna lo stato condiviso."""
        selected = {int(eid) for eid in entity_ids}
        changed = []
        for entity in self.doc.entities.values():
            if entity.is_mesh_block:
                continue
            if entity.etype not in self._cad_layers:
                continue
            value = entity.id in selected
            if entity.visible != value:
                entity.set_visible(value)
                changed.append(entity.id)
        if changed:
            self._notify("isolate", ids=sorted(selected))
            self._redraw()
        return len(changed)

    def set_mesh_visible(self, visible: bool):
        value = bool(visible)
        if self._mesh_visible == value:
            return False
        self._mesh_visible = value
        self._notify("mesh_layer", visible=value)
        self._redraw()
        return True

    def is_mesh_visible(self) -> bool:
        return self._mesh_visible
