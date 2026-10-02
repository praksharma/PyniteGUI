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

- Choose Imperial or SI from the unit selector at the bottom-right, or use
  Edit > Units. All dimensional inputs, inspectors, coordinate readouts, load
  labels, property tables, results, and open diagrams use the selected system.
  Switching is undoable, preserves the physical model and valid results, and is
  saved with the project. New projects keep the currently selected system.
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
- Select a member and check Released (hinge) for its Start or End moment in
  the inspector, then press Apply. Hollow circles mark released member ends.
  These releases disconnect in-plane moment transfer at the member connection;
  they do not change node supports or disconnect axial/shear translations.
  Splitting and connecting preserve releases at original outer ends only;
  newly created internal connections stay rigid.
- Assign a node support using Support, or select a node/member and use Load (L).
- For an angled point force on a node or member, choose Global direction > Angle,
  then enter a nonnegative magnitude and an angle in degrees. Angles are global,
  counterclockwise from +X: 0 points right, 90 up, -90 down, and 180 left.
  The live FX/FY preview shows each component on its own line in the selected
  force units. One angled load is saved
  and edited as a single object; its components are resolved automatically for
  analysis. Negative combination factors reverse the force normally.
- Member loads can be Point or Distributed. Distributed loads use start/end
  intensities in kip/in or kN/m and start/end fractions along the member. Equal intensities
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
  another analysis. Deformed overlays the displaced members. Its toolbar offers
  Auto (maximum displayed displacement is 15% of the model extent), True Scale
  (1x), and Custom amplification. The current factor and actual maximum sampled
  displacement are shown separately; scaling never changes analysis results.
  The maximum is sampled at 41 positions per member, not an exact extremum search.
  Fit (F) includes the visible deformed shape. Diagrams opens whole-structure axial, shear, and bending moment
  diagrams with one common amplitude scale for every member. Member Detail
  provides axial force, local shear, bending moment, and transverse deflection
  plots for any member, sharing one distance axis.
  Diagram windows have their own combination selector and retain the analyzed
  snapshot even when the editor changes. The inspector always edits original
  case values, not the factored values displayed after analysis.
- Save/Open uses versioned `.pynite.json` project files. Ctrl+Z and Ctrl+Shift+Z
  undo and redo model edits. Delete removes the selected entity and its dependent
  members/loads. Unsaved changes are marked in the title and checked on exit.
- File > Simply Supported Example loads a 420-inch beam with a 10-kip downward
  midspan load. Each support should react with 5 kip. In SI the same physical
  example displays a 10.668 m span, 44.4822 kN load, and 22.2411 kN reactions.

## Units

| Quantity | Imperial | SI |
| --- | --- | --- |
| Coordinates, lengths, grid, displacements | in | m |
| Forces | kip | kN |
| Moments | kip-in | kN-m |
| Distributed intensity | kip/in | kN/m |
| E and G | kip/in2 | MPa |
| Weight density | kip/in3 | kN/m3 |
| Section area | in2 | mm2 |
| Iy, Iz, J | in4 | mm4 |
| Rotation | rad | rad |

Density is weight per volume, not mass density in kg/m3. Load fractions,
Poisson ratio, combination factors, and deformation amplification are
dimensionless and do not change with units. Switching preserves grid spacing;
enter a new value in Edit > Grid when a round metric spacing is wanted.
Section and material names are identifiers and are not renamed by conversion.

The model, saved engineering numbers, and solver use canonical inch-kip units.
Only input/output boundaries convert. This avoids repeated conversion drift and
keeps old projects physically unchanged. Unedited property fields retain their
full internal precision even when displayed with fewer decimals. Open diagram
windows retain their analyzed geometry and loading, but follow the active unit
selection. Unit changes alone do not require another analysis.
Conversions use exact inch and pound-force definitions from
[NIST SP 811](https://pml.nist.gov/cuu/pdf/sp811.pdf), with other factors derived
by their physical dimensions.

## Engineering Scope

Dimensional inputs and results use the selected system listed above.
The editor models frames in the global XY plane. Out-of-plane translation and
rotations are restrained at every node. A pin restrains X/Y translation, a
roller restrains Y translation, and a fixed support also restrains Z rotation.
Point loads support global FX, FY, and MZ; distributed forces support FX/FY.
Loads belong to named cases. User-defined combinations superpose those cases
with finite factors using linear elastic analysis. The initial project has
Case 1 and a Service combination at factor 1. No design-code factors or
envelopes are generated automatically.
Member load positions are fractions measured from the start node.

Member moment releases act about local Z, normal to the XY frame. End releases
are independent: one member may hinge at a shared node while other members
retain a rigid connection. Releasing both ends supports pin-jointed frames with
nodal loads, but the member remains a beam and can still bend under transverse
member loads; it is not a separate axial-only truss element. Axial/shear,
out-of-plane, and partial-stiffness releases are not exposed in this editor.

When every connected member end at a non-fixed node is hinged, the shared
rotation has no stiffness. Analysis removes that unused rotation from the
unknowns without restraining translations or transferring connection moments.
Results show RZ as n/a for those joints, not a physical zero rotation. Individual
member end rotations and deformations remain governed by the released beam.
A net nodal MZ on such a joint is rejected for each analyzed combination unless
a moment-resisting connection or fixed support is provided. Real translational
mechanisms still fail the solver stability checks.

Each member references a reusable material definition. Editing that definition
updates every member assigned to it and invalidates results. Split member
segments inherit the original material. The default definition is Steel_A992;
E/G and weight density use the selected units. Materials are isotropic
and linear elastic; yield strength and nonlinear constitutive models are not
currently represented.

Each member also references a reusable section definition. Area uses in2 or mm2;
Iy, Iz, and J use in4 or mm4 in the member local axes. Iz governs in-plane bending
for the current XY frame model. Section properties are entered directly;
definition names do not perform a section-catalog lookup. The initial default
uses W18x35 properties. Split segments inherit their original section.

Version 1 files migrate their shared material to a named Project material.
Version 1 and 2 files migrate their shared section to a named Project section.
Versions 1 through 4 migrate existing loads into Case 1 with the original
Service combination. Version 3 point loads and version 4 distributed loads
remain supported. Versions 1 through 5 migrate to rigid member ends.
Versions 1 through 6 open in Imperial, preserving their original inch-kip values.
New saves use version 8 and retain material/section definitions, member
assignments, load cases, combination factors, the default load case, and each
member end moment release, plus the selected unit system and point-load angle.
Older project loads retain their original directions and magnitudes. The JSON units field
remains in-kip to identify the canonical storage units; unit_system controls
presentation and input conversion.
Editing a definition updates all members assigned to it and
invalidates analysis results.
No self-weight is applied automatically. Drawing an intersection alone does not
connect it: use Edit > Connect Intersections to create explicit shared endpoints.
Analysis requires one connected structure and rejects overlapping members or
nodes inside unsplit members, avoiding implicit solver connections. Geometry
connections use an absolute tolerance of 1e-8 inches. Distributed intensity is
force per unit member length, not projected length. Additional release types
and 3D editing are future extensions.

Results are invalidated after engineering edits and belong to the analyzed project revision.
Unit selection changes presentation only and retains valid analysis results.
Result diagrams already open remain snapshots of that analysis.

Whole-structure diagrams use a consistent cut orientation from the endpoint with
the smaller (X, Y) coordinate to the larger endpoint. Positive shear and moment
offsets lie on the left normal of that direction. This makes diagram geometry
independent of member drawing order; negative sagging moments appear below a
horizontal beam. Axial force N uses the PyNite convention: positive compression
and negative tension. Axial force is independent of member drawing direction;
compression offsets lie on the same canonical left normal, and tension offsets
lie on the opposite side. Each whole-structure quantity has a common amplitude
scale across all members. Member Detail retains PyNite local Fy/Mz signs. Point forces
and concentrated moments include both sides of each discontinuity.

## Architecture

- `src/pynitegui/qt/model.py`: validated, serializable project data.
- `src/pynitegui/qt/units.py`: canonical-to-display conversion factors and presets.
- `src/pynitegui/qt/analysis.py`: project-to-PyNite adapter and analysis results.
- `src/pynitegui/qt/app.py`: Qt graphics editor, inspector, undo commands,
  background analysis, and a consistent light application theme.
- `src/pynitegui/qt/diagrams.py`: whole-frame axial/SFD/BMD views, member detail plots,
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
Hinge checks cover analytical released beams, pin-jointed frames, mixed rigid
and hinged connections, real mechanisms, unsupported nodal moments, inactive
rotation reporting, split/intersection preservation, persistence, and undo.
Axial-force checks cover tension/compression signs, inclined and reversed members,
point-force jumps, distributed axial loading, pin-jointed frames, common scaling,
combination switching, snapshot preservation, and compact plot-label layout.
Unit checks cover known conversion factors, SI analytical beam responses,
precision-preserving input, grid snapping, all dimensional editors/result columns,
live diagram switching, persistence/migration, undo, and repeated unit changes.

Keep workflow and engineering-scope changes documented here. Track remaining
features and known limitations in [TODO.md](TODO.md), updating it as work lands.
Commit completed, verified changes in coherent groups; keep implementation and
its regression tests together.
