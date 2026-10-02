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
- Select a member and choose Split in its inspector, or Edit > Split Selected
  Member, to divide it at a fraction measured from its start node. The first
  segment keeps the original member ID. Point loads and moments retain their
  physical locations; a load at the split becomes a nodal load at the new joint.
- Edit > Connect Intersections splits crossing members and T-junctions into
  explicit segments sharing one node. Existing interior nodes are also connected.
  Splitting and connecting are each a single undoable edit.
- Edit > Check Model reports overlapping members, interior-node connections that
  need splitting, and disconnected groups. Analysis also runs these checks.
- Assign a node support using Support, or select a node/member and use Load (L).
- Edit > Materials opens reusable material definitions. Add or edit a name, E,
  Poisson ratio, and density; G is calculated for an isotropic material. Select
  a member, choose Material in its inspector, and press Apply to assign it.
  Set Default controls newly drawn members without changing existing assignments.
  Renaming a definition updates its references; assigned/default materials cannot
  be deleted until members are reassigned and a different default is chosen.
- Edit > Sections manages reusable area, Iy, Iz, and J definitions. Choose
  Section in a selected member inspector and press Apply. Section defaults,
  renaming, deletion protection, and undo work like material definitions.
  Edit > Grid changes the drawing grid spacing.
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

Each member references a reusable material definition. Editing that definition
updates every member assigned to it and invalidates results. Split member
segments inherit the original material. The default definition is Steel_A992;
material units are E/G in kip/in2 and density in kip/in3. Materials are isotropic
and linear elastic; yield strength and nonlinear constitutive models are not
currently represented.

Each member also references a reusable section definition. Area uses in2;
Iy, Iz, and J use in4 in the member local axes. Iz governs in-plane bending
for the current XY frame model. Section properties are entered directly;
definition names do not perform a section-catalog lookup. The initial default
uses W18x35 properties. Split segments inherit their original section.

Version 1 files migrate their shared material to a named Project material.
Version 1 and 2 files migrate their shared section to a named Project section.
New saves use version 3 and retain all material/section definitions and member
assignments. Editing a definition updates all members assigned to it and
invalidates analysis results.
No self-weight is applied automatically. Drawing an intersection alone does not
connect it: use Edit > Connect Intersections to create explicit shared endpoints.
Analysis requires one connected structure and rejects overlapping members or
nodes inside unsplit members, avoiding implicit solver connections. Geometry
connections use an absolute tolerance of 1e-8 inches. Distributed loads,
load cases/combinations, member releases,
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
- `src/pynitegui/qt/materials.py`: material definition manager and property editor.
- `src/pynitegui/qt/sections.py`: section definition manager and property editor.
- `tests/`: project, solver, diagram, and Qt interaction regression tests.

## Development

Run the project, solver, diagram, and Qt interaction tests:

```sh
uv run python -m unittest discover -s tests
```

The Qt interaction tests run offscreen. The suite covers project persistence,
undo/redo, result invalidation, analytical beam checks, portal-frame diagrams,
inclined/reversed members, point-force/moment jumps, explicit member connections,
load preservation during splitting, rejection of invalid model topology,
mixed-material/section stiffness, legacy-file migration, and material/section
assignment with undo.

Keep workflow and engineering-scope changes documented here. Track remaining
features and known limitations in [TODO.md](TODO.md), updating it as work lands.
Commit completed, verified changes in coherent groups; keep implementation and
its regression tests together.
