# CAD/CAE UX Redesign — Implementation Report

## Scope

This implementation applies the CAD/CAE interface redesign specification to the qwen repository while preserving the existing OpenCASCADE, Gmsh, OpenSees, document, mesh and macro backends.

## Implemented

### Application layout
- Menus reorganized around File, Edit, View, Geometry, Mesh, Physical Groups, Tools, Window, Settings and Help.
- Workspace toolbar with CAD/Mesh selector.
- CAD and Mesh workflow toolbars.
- Interaction toolbar for mouse editing, snap, grid and trihedron.
- Dockable model tree, properties, OpenSees workflow, Python console/log/macro panels, and CAD/CAE command line.

### Selection
- Central SelectionManager with CAD/Mesh/OpenSees contexts.
- Bidirectional viewport ↔ document ↔ tree synchronization.
- Extended tree multi-selection.
- Entity-type selection filter.
- Topological sub-entity resolution for faces, edges, vertices, wires, shells and solids.
- Persistent selection highlighting and contextual actions.
- Hover information for supported CAD geometry.

### Visibility
- Central VisibilityManager.
- Independent CAD layer visibility and mesh visibility.
- Per-entity visibility.
- Show/hide/invert CAD visibility.
- Mesh overlays/labels can be controlled separately.
- Stale meshes are hidden rather than displayed as current geometry.

### Command line
The command line invokes the same document/builder/editor/selection backends used by the GUI.

Implemented commands include:
HELP, CANCEL, UNDO, REDO, POINT, LINE, ARC, POLYLINE, CIRCLE, RECTANGLE,
BOX, CYLINDER, CONE, SPHERE, TORUS, EXTRUDE, REVOLVE, MOVE, ROTATE, SCALE,
DELETE, COPY, SELECT, WORKSPACE, VIEW, ZOOM, GRID, SNAP, WIRE, FIT, MESH,
GROUP, MACRO, SAVE and VALIDATE.

The widget provides command history, Up/Down navigation, autocomplete, aliases,
numeric input and Escape cancellation of command-line input.

### Shared model and mesh validity
- CADDocument now tracks a monotonic geometry revision.
- MeshModel records the geometry revision from which it was generated/imported.
- Geometry changes invalidate dependent meshes.
- The model tree and status bar show STALE status.
- OpenSees export is blocked for stale meshes.
- Undo/redo geometry operations update the geometry revision as well.

### Preferences
QSettings stores:
- window geometry;
- dock layout;
- active workspace;
- snap state;
- snap step;
- grid state;
- selection filter.

### Documentation
- Architecture audit and implementation plan.
- Manual graphical validation checklist.
- README documentation for the redesigned workflow and stale-mesh behavior.

## Existing functionality preserved

The redesign continues to use the existing backend components for:
- OCC B-Rep creation and editing;
- boolean operations;
- import/export;
- Gmsh meshing and MSH handling;
- physical groups;
- OpenSees/FEM configuration and export;
- macros;
- existing undo/redo mechanisms.

No unsupported CAD algorithm, meshing kernel, or solver was replaced with a placeholder implementation.

## Deliberate limitations

Some target interactions are not represented as new commands when the current backend does not provide a reliable implementation. In particular:
- Trim/Extend are not invented as fake commands.
- Full rectangular/window selection is left to the existing OCC interaction capabilities.
- Endpoint/midpoint/center/intersection/perpendicular snapping has not been fabricated where only grid/vertex snapping is currently implemented.
- Mesh algorithm/element-order controls remain exposed through the application's existing Gmsh workflows instead of introducing a parallel settings model.

## Validation

Automated validation includes:
- Python compilation of gcs and tests in GitHub Actions.
- Existing test suite plus new selection, visibility, stale-mesh, command-line and GUI integration tests.
- Qt headless runtime setup in CI.
- Linux EGL runtime dependency installation in CI.
- Application selfcheck in CI.

GUI/OCC-specific tests depend on the availability of pythonocc-core. The CI workflow is configured to install PySide6 and Qt runtime dependencies, but does not install pythonocc-core itself; those tests therefore remain conditional on the environment.

## Files added or modified

Key files:
- gcs/gui/command_line.py
- gcs/gui/main_window.py
- gcs/gui/viewer.py
- gcs/gui/panels.py
- gcs/core/selection_manager.py
- gcs/core/visibility_manager.py
- gcs/core/document.py
- gcs/core/mesh.py
- gcs/core/editors.py
- gcs/core/macro_engine.py
- tests/test_command_line.py
- tests/test_gui.py
- tests/test_groups_and_selection.py
- tests/test_macro_engine.py
- .github/workflows/python-core.yml
- README.md
- docs/ARCHITECTURE_AUDIT.md
- docs/MANUAL_VALIDATION_CHECKLIST.md

## Recommended manual validation

Use docs/MANUAL_VALIDATION_CHECKLIST.md on a desktop environment with
pythonocc-core, PySide6 and Gmsh available. The highest-value checks are:
startup/layout restoration, CAD selection synchronization, CAD transforms,
mesh import/generation, stale-mesh invalidation, physical groups, command-line
execution, and OpenSees export/validation.
