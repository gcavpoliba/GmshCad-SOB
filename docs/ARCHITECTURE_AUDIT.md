# Architecture audit and UX implementation plan

## Existing architecture

`qwen` is a PySide6 desktop application using a Qt QMainWindow, a pythonocc/OpenCASCADE AIS viewer, Gmsh-backed .msh import/embedded meshing, a document model, geometry builder/editor, selection/query services, groups, OpenSees/FEM managers, macro execution, and pytest coverage.

The document is already the shared model for geometry, mesh blocks, groups, selection, history, OpenSees data, phases, and parameters. The redesign therefore keeps the CAD/mesh kernels intact and moves UX improvements into the GUI and state-management layers.

## Reusable components

- gcs/core/document.py: shared document, selection and undo/redo.
- gcs/core/builder.py: real OCC geometry creation.
- gcs/core/editors.py: real OCC transforms/booleans/modification.
- gcs/core/occ_utils.py: OCC geometry and topology utilities.
- gcs/core/gmsh_bridge.py and msh_importer.py: existing Gmsh workflows.
- gcs/core/mesh.py: mesh data model and mesh selection.
- gcs/core/groups.py / selectors.py: groups and selection queries.
- gcs/core/opensees_*: existing OpenSees/FEM workflow and export.
- gcs/gui/viewer.py: existing AIS viewer and mouse interaction.
- gcs/gui/dialogs.py: existing parameter/form workflows.
- gcs/gui/panels.py: existing tree, properties, console, macros and phases.

## Main UX problems found

1. Commands were technically available but spread across top-level menus whose organization did not follow the user's engineering workflow.
2. The only command prompt was a Python console, so ordinary CAD commands did not have an AutoCAD-like command entry/history/autocomplete surface.
3. CAD and Mesh workspaces were represented as a mode plus two toolbars, but their active state and contextual controls were not exposed as one coherent workspace surface.
4. Selection had multiple paths and needed stronger synchronization between OCC picks, the document, and the Qt tree.
5. Visibility needed contextual control so CAD entities, mesh overlays and OpenSees symbols could be managed independently.
6. A generated/imported mesh had no explicit document-level stale indicator after CAD topology/geometry changes.
7. Window layout and interaction preferences were not persistently restored.

## Implementation plan

1. Keep the document, OCC and Gmsh engines.
2. Centralize selection and visibility state.
3. Add a real command line whose commands invoke the existing application backends and actions.
4. Reorganize menus and toolbars around CAD, Mesh, Physical Groups, Tools, Window, Settings and Help.
5. Expose workspace selection/filtering and status information.
6. Add mesh revision/staleness tracking and block operations that require a current mesh when appropriate.
7. Persist window layout and relevant UI preferences with QSettings.
8. Add tests and document a manual GUI validation checklist.

## Deliberate non-goals

The redesign does not implement unsupported OCC algorithms, replace Gmsh, replace OpenSees, or fake unimplemented AutoCAD commands. Selection windows, advanced dynamic constraints, and any operation not supported by the current backend remain documented as future/manual-only items.
