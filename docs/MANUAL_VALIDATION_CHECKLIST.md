# Manual CAD/CAE validation checklist

Run from a desktop environment with the project's gmshcad environment.

## Startup and layout

- Start `python main.py`.
- Verify the central OCC viewport is present.
- Verify CAD and Mesh workspace controls are visible.
- Verify tree, property, command and console panels can be resized and docked.
- Close and restart; verify the last workspace and dock layout are restored.

## CAD workflow

- Create a point, line, circle, rectangle and box.
- Select an entity in the viewport; verify the tree and properties follow.
- Select an entity in the tree; verify viewport highlighting follows.
- Use Ctrl/Shift multi-selection in the tree.
- Test Move/Rotate/Scale and Undo/Redo.
- Test a supported Boolean operation and inspect the resulting topology.
- Test grid, snap, standard views, fit-all and fit-selection.
- Hover over CAD geometry and verify status information/highlighting.

## Mesh workflow

- Import `samples/bracket_22.msh` and `samples/bracket_41.msh`.
- Switch between CAD and Mesh workspaces.
- Select mesh blocks/elements/nodes and verify the corresponding overlay.
- Toggle mesh visibility independently of CAD visibility.
- Toggle node/element labels.
- Create/edit a physical group and verify tree membership.
- Change CAD geometry after a mesh exists; verify the mesh is marked STALE.
- Regenerate/re-import the mesh and verify the STALE state clears.

## Command line

- Type `HELP`.
- Type `POINT 0 0 0`.
- Type `LINE 0 0 0 10 0 0`.
- Type `MOVE 1 2 3` with an entity selected.
- Type `SELECT TYPE FACE`.
- Type `WORKSPACE MESH`.
- Use Up/Down to navigate history.
- Use command completion.
- Press Escape to cancel/clear the active command line.

## OpenSees/FEM

- Open the existing OpenSees/FEM dialogs.
- Configure a supported material/element assignment.
- Verify the contextual tree/property information.
- Run model validation.
- Export the OpenSees bundle only with a current mesh.
- Confirm existing solver/phase/recorder workflows remain accessible.
