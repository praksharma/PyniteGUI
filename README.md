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
- Member loads can be Point or Distributed. Distributed loads use start/end
  intensities in kip/in and start/end fractions along the member. Equal intensities
  give a uniform load; different intensities give a linear ramp, including
  triangular or sign-changing loads. Global FX/FY directions apply independently
  of member orientation. Select a load in the tree to edit it in the inspector.
  Splitting clips each loaded region and interpolates its endpoint intensities,
  preserving the original distribution without creating artificial nodal forces.
- Edit > Load Cases and Combinations manages named load cases and linear
  combinations. Assign each load a Case in its creation dialog or inspector.
  Set Default chooses the case for new loads without reassigning existing loads.
  Renaming a case updates all references; a case used by loads, combinations,
  or the default cannot be deleted until those references are removed.
  Add or edit a combination by checking its included cases and entering factors.
  At least one combination is required; zero and negative factors are supported.
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
  appear in Results. Choose a combination above the result table to update
  reactions, displacements, deformation, and factored load annotations without
  another analysis. Deformed overlays the displaced members; Scale controls
  visual amplification. Diagrams opens whole-structure shear and bending moment
  diagrams with one common amplitude scale for every member. Member Detail
  provides local shear, bending moment, and deflection plots for any member.
  Diagram windows have their own combination selector and retain the analyzed
  snapshot even when the editor changes. The inspector always edits original
  case values, not the factored values displayed after analysis.
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
Point loads support global FX, FY, and MZ; distributed forces support FX/FY.
Loads belong to named cases. User-defined combinations superpose those cases
with finite factors using linear elastic analysis. The initial project has
Case 1 and a Service combination at factor 1. No design-code factors or
envelopes are generated automatically.
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
Versions 1 through 4 migrate existing loads into Case 1 with the original
Service combination. Version 3 point loads and version 4 distributed loads
remain supported. New saves use version 5 and retain material/section definitions,
member assignments, load cases, combination factors, and the default load case.
Editing a definition updates all members assigned to it and
invalidates analysis results.
No self-weight is applied automatically. Drawing an intersection alone does not
connect it: use Edit > Connect Intersections to create explicit shared endpoints.
Analysis requires one connected structure and rejects overlapping members or
nodes inside unsplit members, avoiding implicit solver connections. Geometry
connections use an absolute tolerance of 1e-8 inches. Distributed intensity is
force per unit member length, not projected length. Member releases,
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
- `src/pynitegui/qt/load_cases.py`: load-case manager and combination factor editor.
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
Distributed-load checks cover analytical uniform/triangular beam responses,
partial-span resultants, inclined global loading, orientation-independent
diagrams, interpolated split loads, persistence, and editor creation/undo.
Load-case checks cover independent results, linear superposition, negative/zero
factors, reference-safe renaming/deletion, persistence/migration, default case
assignment, result/diagram switching, deformation, and analyzed snapshots.

Keep workflow and engineering-scope changes documented here. Track remaining
features and known limitations in [TODO.md](TODO.md), updating it as work lands.
Commit completed, verified changes in coherent groups; keep implementation and
its regression tests together.
