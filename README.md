# PyniteGUI

A Python desktop editor for 2D frame analysis with PyNite.

## Run

Install Python 3.12+ and uv, then run from the repository:

```sh
uv sync
uv run pynitegui
```

The application uses PySide6 / Qt Widgets and PyNite for structural analysis.

## Workflow

- Choose Member (M), then click two points. Coordinates snap to the project grid
  or an existing node. Escape or right-click cancels an unfinished member.
- Choose Select (V) and click a node or member, or select it in the structure
  tree. Edit properties in the inspector and press Apply.
- Assign a node support using Support, or select a node/member and use Load (L).
- Use Pan (P) to drag the view, the mouse wheel to zoom, and Fit (F) to frame it.
- Analyze (F5) runs PyNite in a worker thread. Reactions and nodal displacements
  appear in Results. Deformed overlays the displaced members; Scale controls
  visual amplification. Diagrams opens whole-structure shear and bending moment
  diagrams with one common amplitude scale for every member. Member Detail
  provides local shear, bending moment, and deflection plots for any member.
- Save/Open uses versioned `.pynite.json` project files. Ctrl+Z and Ctrl+Shift+Z
  undo and redo model edits. Delete removes the selected entity and its dependent
  members/loads. Unsaved changes are marked in the title and checked on exit.
- File > Simply Supported Example loads a 420-inch beam with a 10-kip downward
  midspan load. Each support should react with 5 kip.

## Engineering Scope

Coordinates and sections use inches; forces use kips; moments use kip-in.
The editor models frames in the global XY plane. Out-of-plane translation and
rotations are restrained at every node. A pin restrains X/Y translation, a
roller restrains Y translation, and a fixed support also restrains Z rotation.
Loads support global FX, FY, and MZ, with one service combination at factor 1.
Member load positions are fractions measured from the start node.

All members currently share one material and section, editable through
Edit > Material and Section. Defaults are steel and W18x35 section properties.
No self-weight is applied automatically. Intersections do not automatically
split members: connect members at explicit shared endpoints. Distributed loads,
multiple material/section assignments, load cases/combinations, member releases,
and 3D editing are future extensions.

Results are invalidated after edits and belong to the analyzed project revision.
Result diagrams already open remain snapshots of that analysis.

Whole-structure diagrams use a consistent cut orientation from the endpoint with
the smaller (X, Y) coordinate to the larger endpoint. Positive shear and moment
offsets lie on the left normal of that direction. This makes diagram geometry
independent of member drawing order; negative sagging moments appear below a
horizontal beam. Member Detail retains PyNite local Fy/Mz signs. Point forces
and concentrated moments include both sides of each discontinuity.

## Architecture

- `src/pynitegui/qt/model.py`: validated, serializable project data.
- `src/pynitegui/qt/analysis.py`: project-to-PyNite adapter and analysis results.
- `src/pynitegui/qt/app.py`: Qt graphics editor, inspector, undo commands,
  background analysis, and a consistent light application theme.
- `src/pynitegui/qt/diagrams.py`: whole-frame SFD/BMD views, member detail plots,
  and sampling on both sides of force and moment discontinuities.
- `tests/`: project, solver, diagram, and Qt interaction regression tests.

## Development

Run the project, solver, diagram, and Qt interaction tests:

```sh
uv run python -m unittest discover -s tests
```

The Qt interaction tests run offscreen. The suite covers project persistence,
undo/redo, result invalidation, analytical beam checks, portal-frame diagrams,
inclined/reversed members, and point-force/moment jumps.

Keep workflow and engineering-scope changes documented here. Track remaining
features and known limitations in [TODO.md](TODO.md), updating it as work lands.
Commit completed, verified changes in coherent groups; keep implementation and
its regression tests together.
