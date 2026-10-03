# PyniteGUI Guide

A Python desktop editor for 2D frame and truss analysis with PyNite.

## Run

Install Python 3.12+ and uv, then run from the repository:

```sh
uv sync
uv run pynitegui
```

The application uses PySide6 / Qt Widgets and PyNite for structural analysis.

## Workflow

- The unit selector also offers SI (mm, N) and Imperial (ft, kip). The mm/N
  preset uses N-mm moments, N/mm line loads, MPa stresses, and mm2/mm4 sections.
  The ft/kip preset uses kip-ft moments and kip/ft line loads, while keeping
  section properties in in2/in4 and material stiffness in kip/in2. Weight
  density follows the geometry volume units (N/mm3 or kip/ft3).
- File > Examples opens fresh, editable models: a simply supported beam,
  distributed-load portal frame, cantilever with partial distributed/angled/tip
  loads and a moment, partially loaded continuous beam, pitched frame with local
  roof loads, and a two-storey gravity/wind frame with separate combinations.
  A seventh example demonstrates a beam loaded only by automatic self-weight.
  A triangular truss example demonstrates axial-only members and joint loads.
  Examples retain the current unit system and prompt before replacing unsaved
  work. They start as unsaved projects, not as files to overwrite.
- View > Appearance selects Light or Dark. The preference is saved between app
  sessions, separately from project files. It updates all open editor/diagram
  windows, including the grid, engineering symbols, labels, tables, and plots,
  without changing units, undo history, results, inspection positions, or plot
  zoom/navigation history. Printed reports remain light for paper/PDF output.
  Properties scroll when the dock is too short for all fields.
- Choose Imperial or SI from the unit selector at the bottom-right, or use
  Edit > Units. All dimensional inputs, inspectors, coordinate readouts, load
  labels, property tables, results, and open diagrams use the selected system.
  Switching is undoable, preserves the physical model and valid results, and is
  saved with the project. New projects keep the currently selected system.
- Choose Member (M), then click two points. Coordinates snap to the project grid
  or an existing node. Escape or right-click cancels an unfinished member.
- Choose Select (V) and click a node or member, or select it in the structure
  tree. Edit properties in the inspector and press Apply.
- In Select mode, Ctrl/Shift-click toggles nodes/members on the canvas. Drag an
  empty area to box-select nodes and any members that cross the rectangle;
  Ctrl/Shift adds that box to the current selection. Escape/right-click cancels
  the box without changing the selection. A plain empty click clears it. The
  tree supports Ctrl-click toggles and Shift-click ranges, including manual
  loads. Edit > Select All (Ctrl+A) selects all geometry and visible manual loads;
  generated self-weight remains read-only. Selected geometry and load arrows
  are highlighted, and selections stay synchronized with the tree.
  Multiple items show a bulk inspector: assign member materials/sections and
  end hinges, node supports/custom restraints, or load cases and a signed
  magnitude multiplier. The multiplier scales both distributed-load intensities,
  preserving fractions, angles, and directions. Keep existing and partially
  checked boxes leave properties unchanged; checked sets on and unchecked sets
  off. Choose custom before editing restraint boxes; unmodified restraints retain
  each node's effective previous support. Apply validates all selected edits in
  one transaction; Delete Selection removes selected items and their dependents
  in one undo step. Selection alone never invalidates results; actual bulk edits
  do. Single-node dragging and single-entity commands still require one target.
  Hiding a load case removes its loads from the selection without clearing
  selected geometry. Opening another project clears the selection.
- Edit > Model Tables opens draft Nodes, Members, and Loads tables. Enter signed
  coordinates and load values directly (scientific notation is accepted), choose
  endpoints/materials/sections/cases, and set custom restraints or end hinges.
  Add rows or remove selected rows to build/edit the model numerically. IDs are
  generated and read-only; references to newly added rows are available immediately.
  OK validates all three tables and applies one undoable edit; Cancel discards
  the draft. Removing a referenced row requires explicitly removing or reassigning
  its dependent members/loads before OK. Invalid input never partially changes
  the active model. Untouched numbers preserve their full stored precision.
  Coordinates use the selected length unit; each load row shows its magnitude
  units, and the end-intensity header identifies distributed-load units. Changing
  load type/direction reinterprets the entered magnitude in those units. Positions
  are member fractions, angles are degrees, and end intensity/fraction apply to
  distributed loads only. Preset restraint checkboxes show the effective supports
  but are editable only for custom supports. Generated self-weight is not listed
  as a manual load; configure it separately in Edit > Self-Weight.
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
- The desktop app keeps a separate autosave snapshot of unsaved changes every
  30 seconds in Qt's per-user application-data recovery directory. These files
  never overwrite your project. After an interrupted session, startup offers
  Recover/Discard; File > Recover Autosave reopens that list. Snapshots owned by
  another running process are excluded. Saving or intentionally closing clears
  this window's snapshot; a cancelled close retains it. Unsaved recovered work
  stays marked dirty. File > Recent Projects remembers the latest ten files.
- Choose custom in the node Support inspector for independent global horizontal
  (DX), vertical (DY), and rotational (RZ) restraint checkboxes. Checked means
  restrained. Existing free/pin/roller/fixed presets remain available. Custom
  support symbols show horizontal/vertical restraint lines and a square for
  rotational restraint; hovering identifies the restrained degrees of freedom.
- In Select mode, drag a node to move it with snapping. Dashed connected members
  preview the move; releasing creates one undoable edit. Escape/right-click
  cancels. Coincident nodes and collapsed members are rejected without changing
  the model. Moving geometry invalidates analysis results.
- The selector above the structure tree shows all load cases, one case, or hides
  loads. It filters load arrows and tree entries only; analysis still includes
  all loads according to the selected combination.
- For an angled point force on a node or member, choose Direction > Angle,
  then enter a signed magnitude and an angle in degrees. Angles are global,
  counterclockwise from +X: 0 points right, 90 up, -90 down, and 180 left for
  positive magnitudes. A negative magnitude reverses the chosen direction.
  The live FX/FY preview shows each component on its own line in the selected
  force units. One angled load is saved
  and edited as a single object; its components are resolved automatically for
  analysis. Negative combination factors reverse the force normally.
- Member loads can be Point or Distributed. Distributed loads use start/end
  intensities in kip/in or kN/m and start/end fractions along the member. Equal intensities
  give a uniform load; different intensities give a linear ramp, including
  triangular or sign-changing loads. Choose FX/FY for global axis loading or
  Angle for a global angled distribution; one angle applies to both endpoint
  intensities. Negative intensities reverse that direction. Intensities remain
  force per unit member length, not projected length. Select a load in the tree
  to edit it in the inspector.
  Splitting clips each loaded region and interpolates its endpoint intensities,
  preserving the original distribution without creating artificial nodal forces.
- Member forces also offer Local x, Local y, and Local angle for both point and
  distributed loads. +local x runs from the member start node to its end node;
  +local y is 90 degrees counterclockwise from that direction in the XY plane.
  Local angle is counterclockwise from +local x. These definitions are resolved
  to global FX/FY at the solver boundary, independently of PyNite's internal
  3D axis orientation. The preview always shows global components. Local loads
  rotate with member geometry, including when its endpoints are reversed.
  Split segments retain the local reference. A point force at a split becomes
  a global angled nodal load with the same vector, since a node has no unique
  member-local axes. Reassigning a local point load to a node in the inspector
  also preserves its current global vector.
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
  Library provides five reference presets: US/EU typical steel, generic aluminum,
  and C30/37 concrete with plain or reinforced-concrete weight. Search, preview
  E/Poisson ratio/G/weight density, and Add to Project. Imports do not reassign
  members or change the default. Source distinguishes Library from Custom;
  renaming retains the preset, while numerical edits make it custom.
- Edit > Sections manages reusable area, Iy, Iz, and J definitions. Choose
  Section in a selected member inspector and press Apply. Section defaults,
  renaming, deletion protection, and undo work like material definitions.
  Library opens a searchable, family-filtered AISC starter catalog. Choose the
  in-plane strong or weak bending axis and Add to Project, then assign the
  definition to members or Set Default. Imports never replace existing sections;
  duplicate names receive a suggested suffix. The Source column distinguishes
  catalog definitions from custom properties. Renaming preserves provenance;
  changing any numerical property makes the definition custom.
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
  diagrams with one common amplitude scale for every member.
  Whole Structure also offers Default/Opposite side and Reverse display signs.
  Side changes placement only; sign reversal changes plotted values and labels
  the convention in the title (+ tension for reversed axial diagrams).
  These per-window controls survive unit/combination/theme changes but do not
  change Member Detail, numerical tables, CSV, analysis results, or saved models.
  New diagram windows start with the standard convention. Member Detail
  provides axial force, local shear, bending moment, and transverse deflection
  plots for any member, sharing one distance axis.
  In Member Detail, enter a distance or click a plot to inspect N, Fy, Mz, and dy.
  Left/Right side selects one-sided values at point-load jumps. Dashed cursors
  align all four plots. Member Results lists start/end values and solver minimum/
  maximum values for each member in local axes and current units; each extrema
  column is independent, not a set of forces at one common station.
  Diagram windows have their own combination selector and retain the analyzed
  snapshot even when the editor changes. The inspector always edits original
  case values, not the factored values displayed after analysis.
- Diagrams > Envelopes compares checked combinations from that analyzed
  snapshot without another solve. The main combination selector does not change
  the envelope selection. Nodes lists displacement/reaction bounds; Members
  lists exact solver extrema for N, Fy, Mz, and dy over entire members. Each
  minimum and maximum identifies its governing combination. Ties use the first
  checked combination in list order; undefined truss-joint rotations remain n/a.
  These are independent bounds, not a simultaneous force/displacement state.
  Member Curves shows sampled min/max envelopes in local axes, including both
  sides of load jumps. Curve peaks are sampled, not exact extrema searches; use
  Members for solver extrema. Enter a distance or click a curve to inspect exact
  one-sided station bounds and their governing combinations. Left/Right side
  chooses the side at point-load jumps. Axial N remains positive compression;
  Whole Structure placement/sign controls do not change envelopes.
  The envelope export icon saves both summary tables as CSV with units, source,
  snapshot identity, selected combinations/factors, and self-weight metadata.
  Unit/theme changes retain the selection. Envelopes are window-local and are
  not included in the single-combination print report or saved project.
- File > Export Results saves node reactions/displacements or member end/extrema
  values as CSV in the selected units and combination. Files include source,
  analysis ID, UTC timestamp, model signature, and unit system. Undefined joint
  rotations export as n/a; CSV/report metadata also identifies the self-weight
  case and multiplier when enabled. Extrema have no common station, so x is blank.
  Text identifiers that could be interpreted as spreadsheet formulas are
  prefixed with an apostrophe; numeric loads/results retain their signs.
  Print Results first opens content choices for model definitions, node/member
  results, and selected axial/SFD/BMD diagrams, then opens native print preview.
  Model definitions include nodes/effective supports, frame/truss assignments
  and hinges, materials/section properties and provenance, manual and generated
  unfactored loads, defaults, and load combinations. Diagrams use the selected
  analyzed combination, snapshot ID, units, and explicitly labelled display
  side/sign/amplitude. Printing from a diagram window starts with its current
  diagram settings. Charts use a light print palette even in dark mode and have
  their own pages. Reports can be printed or saved to PDF through the print
  dialog. Cancelling content selection does not open preview or change the model.
- Diagram windows show their analysis ID, analysis time, original editor revision,
  and whether their model matches the current editor. A new analysis of the same
  model is distinguished from the earlier snapshot. The export icon in a diagram
  window exports/prints that snapshot, even after editor results are invalidated.
  Unit and combination changes retain the snapshot ID; engineering changes
  require a new analysis before exporting from the main editor.
- Save/Open uses versioned `.pynite.json` project files. Ctrl+Z and Ctrl+Shift+Z
  undo and redo model edits. Delete removes the selected entity and its dependent
  members/loads. Unsaved changes are marked in the title and checked on exit.
- File > Examples > Simply Supported Beam loads a 420-inch beam with a 10-kip downward
  midspan load. Each support should react with 5 kip. In SI the same physical
  example displays a 10.668 m span, 44.4822 kN load, and 22.2411 kN reactions.

## Units

| Quantity | Imperial (in, kip) | SI (m, kN) | SI (mm, N) | Imperial (ft, kip) |
| --- | --- | --- | --- | --- |
| Coordinates, lengths, grid, displacements | in | m | mm | ft |
| Forces | kip | kN | N | kip |
| Moments | kip-in | kN-m | N-mm | kip-ft |
| Distributed intensity | kip/in | kN/m | N/mm | kip/ft |
| E and G | kip/in2 | MPa | MPa | kip/in2 |
| Weight density | kip/in3 | kN/m3 | N/mm3 | kip/ft3 |
| Section area | in2 | mm2 | mm2 | in2 |
| Iy, Iz, J | in4 | mm4 | mm4 | in4 |
| Rotation | rad | rad | rad | rad |

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
Custom supports independently restrain global DX, DY, and RZ; inclined supports
and elastic springs are not implemented yet. Point loads support global FX, FY,
MZ, and signed angled forces. Member point/distributed forces additionally
support local x/y and member-relative angles. Nodal forces use global axes only;
distributed moments are not implemented.
Loads belong to named cases. User-defined combinations superpose those cases
with finite factors using linear elastic analysis. The initial project has
Case 1 and a Service combination at factor 1. No design-code factors or
envelopes are generated automatically.
Edit > Self-Weight opts into automatic gravity loading in a chosen load case,
with a positive multiplier and total unfactored weight in the current force
units. Frame members receive global downward FY uniform loads using their
own weight density times section area. Truss weight is lumped equally to the
two end nodes; it never creates transverse member bending. Zero-density members contribute no
weight. The case must appear in a combination to affect that combination;
combination factors apply normally. Existing manual loads are additional, so
do not also enter the same member self-weight manually. Generated loads appear
as read-only entries in the structure tree and respect case visibility filters.
They are recalculated after material/section changes and member splitting,
not duplicated as editable project loads. Disabling or changing self-weight is
undoable and invalidates results; case renaming follows the reference, and a
referenced case cannot be deleted. Density is weight per volume, not kg/m3;
do not multiply it by gravity again.
Member load positions are fractions measured from the start node.

Member moment releases act about local Z, normal to the XY frame. End releases
are independent: one member may hinge at a shared node while other members
retain a rigid connection. Releasing both ends supports pin-jointed frames with
nodal loads, but the member remains a beam and can still bend under transverse
member loads; it is not a separate axial-only truss element. Axial/shear,
out-of-plane, and partial-stiffness releases are not exposed in this editor.

Choose Type = truss in the member inspector, bulk inspector, or Model Tables
for an explicitly axial-only member. Truss ends are implicitly pinned; saved
frame hinge settings are retained but ignored until switched back to frame.
Dashed member lines and end circles distinguish trusses on the editing canvas.
Materials and section area determine EA stiffness; Iy/Iz/J remain stored for
switching back to a frame but do not affect the planar truss response.
The adapter uses [PyNite rotational end releases](https://pynite.readthedocs.io/en/latest/member.html)
with strict joint-only loading to enforce this behavior in the XY model.
Member point/distributed forces and moments are rejected on trusses, including
when changing a loaded frame to truss. Move loads to nodes explicitly; there is
no silent conversion. Splitting a straight truss bar creates a new joint that
must be properly restrained or braced: an unbraced intermediate joint generally
introduces a transverse mechanism. Mixed frame/truss structures are supported;
a rigid frame connection at a shared joint retains its rotational DOF.

When every connected member end at a node without an RZ restraint is hinged, the shared
rotation has no stiffness. Analysis removes that unused rotation from the
unknowns without restraining translations or transferring connection moments.
Results show RZ as n/a for those joints, not a physical zero rotation. Individual
member end rotations and deformations remain governed by the released beam.
A net nodal MZ on such a joint is rejected for each analyzed combination unless
a moment-resisting connection or rotational support restraint is provided. Real translational
mechanisms are not hidden by adding translational restraints.

Analysis checks whether the actual supports prevent planar rigid-body motion
and lists affected global DX/DY/RZ directions when they do not. Solver
instability errors are translated into joint-level messages where possible.
For models with at most 600 free planar degrees of freedom, a diagonally scaled
stiffness check also rejects singular/numerically ill-conditioned results even
when the solver returns finite values. Candidate mechanism directions are
diagnostic hints, not a unique identification of the defective member. Very
large stiffness contrasts can cause poor conditioning without a physical
mechanism. For larger models, solver checks and rejection of nonfinite results
remain active, but detailed spectral checks/localization are skipped to avoid
an expensive dense calculation. These are linear-model checks, not buckling
or nonlinear stability verification.

Each member references a reusable material definition. Editing that definition
updates every member assigned to it and invalidates results. Split member
segments inherit the original material. The default definition is Steel_A992;
E/G and weight density use the selected units. Materials are isotropic
and linear elastic; yield strength and nonlinear constitutive models are not
currently represented.

Material-library presets are reference starting points, not certified grades.
US steel uses the [PyNite Quickstart](https://pynite.readthedocs.io/en/latest/quickstart.html)
elastic constants and weight density. EU steel and C30/37 concrete use
[JRC Handbook 3](https://eurocodes.jrc.ec.europa.eu/sites/default/files/2021-12/handbook3.pdf)
(steel Annex Table 2; concrete Chapter VI and Annex Table 9). Aluminum uses
the [MIT material database](https://www.mit.edu/~6.777/matprops/aluminum.htm).
Mass densities for EU steel/aluminum are converted with standard gravity
9.80665 m/s2; the UI and PyNite receive weight density, not mass density.
Concrete presets assume uncracked, short-term stiffness. The RC-weight variant
changes density only, not reinforcement stiffness. No preset adds cracking,
creep, plasticity, yield strength, buckling, or a design-code check. Verify
properties for the actual grade, alloy, aggregate, and conditions of use.

Each member also references a reusable section definition. Area uses in2 or mm2;
Iy, Iz, and J use in4 or mm4 in the member local axes. Iz governs in-plane bending
for the current XY frame model. Custom properties are entered directly;
definition names alone do not perform a section-catalog lookup. The initial
default uses W18x35 properties but is classified as custom, like older saved
definitions. Split segments inherit their original section.

The offline library contains 15 doubly symmetric wide-flange, square,
rectangular, and round HSS sections, not a complete catalog. Its numerical
properties come from the August 2023 [AISC Shapes Database v16.0](https://www.aisc.org/aisc/publications/steel-construction-manual/aisc-shapes-database-v160/),
consistent with the 16th Edition Manual, first printing. The source workbook was
retrieved from this [public mirror](https://github.com/OpenCivil-Project/Open-Structures/blob/main/app/resources/aisc-shapes-database-v16.0.xlsx)
because the official download returned HTTP 403. Its SHA-256 is
`82d0ceb96a0d938ae1a6bd9637cb10a1e269225b5d668dce5b0bdc8d86013496`.
Only designation and A/Iy/Ix/J numerical facts are bundled, not the workbook.
Values use U.S. customary columns C, F, AQ, AM, AX; metric previews convert
these values rather than using the workbook's separately rounded metric columns.
Strong-axis bending maps catalog Ix to PyNite Iz and catalog Iy to PyNite Iy.
Weak-axis bending swaps those inertias; A and torsional J stay unchanged.
HSS design properties are taken directly from the database, not recalculated
from nominal wall thickness. Imported catalog properties and orientation are
validated on reopen; modified values must be classified as custom. Materials
remain a separate assignment, and imports do not change them. This is a stiffness
library, not a strength, buckling, or code-compliance check. Verify suitability
and section properties independently for engineering use.

Version 1 files migrate their shared material to a named Project material.
Version 1 and 2 files migrate their shared section to a named Project section.
Versions 1 through 4 migrate existing loads into Case 1 with the original
Service combination. Version 3 point loads and version 4 distributed loads
remain supported. Versions 1 through 5 migrate to rigid member ends.
Versions 1 through 6 open in Imperial, preserving their original inch-kip values.
New saves use version 14 and retain material/section definitions, member
assignments, load cases, combination factors, the default load case, and each
member end moment release, plus the selected unit system, point-load angle,
and custom support restraints. Version 10 adds local force directions and
angled distributed loading; version 9 and older files retain their saved global
force directions and physical magnitudes.
Version 11 adds the optional self-weight case and factor. Versions 1 through 10
open with automatic self-weight off so existing reactions do not change.
Version 12 adds section catalog provenance and strong/weak-axis orientation.
Older files retain their exact numerical properties as custom definitions.
Version 13 adds material-library provenance; older materials remain custom.
Version 14 adds the frame/truss member type. Earlier files keep frame behavior,
including any existing end moment releases, without changing their response.
Older project loads retain their original directions and magnitudes. The JSON units field
remains in-kip to identify the canonical storage units; unit_system controls
presentation and input conversion.
Malformed files are rejected before replacing the active project. Missing fields,
incorrect collection/entity shapes, unknown entity fields, invalid references,
boolean/string/nonfinite numerical values, and duplicate JSON keys produce
readable errors. JSON syntax errors include their line and column. Supported
versions 1 through 14 are migrated without modifying the input; unknown/future
versions are rejected rather than guessed. Node and member identifiers must be
distinct so load targets are unambiguous.
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
- `src/pynitegui/qt/envelopes.py`: combination bounds, governing combinations,
  envelope tables/curves, exact station inspection, and atomic CSV export.
- `src/pynitegui/qt/materials.py`: material definition manager and property editor.
- `src/pynitegui/qt/sections.py`: section definition manager and property editor.
- `src/pynitegui/qt/section_library.py`: offline catalog facts and axis mapping.
- `src/pynitegui/qt/material_library.py`: reference elastic and weight-density presets.
- `src/pynitegui/qt/load_cases.py`: load-case manager and combination factor editor.
- `src/pynitegui/qt/recovery.py`: per-window atomic recovery snapshots and validation.
- `src/pynitegui/qt/reports.py`: unit-aware CSV exports and native printable reports.
- `src/pynitegui/qt/examples.py`: fresh, canonical-unit example beam/frame models.
- `src/pynitegui/qt/theme.py`: shared light/dark widget, canvas, and plot styling.
- `src/pynitegui/qt/self_weight.py`: opt-in case/factor editor and weight preview.
- `src/pynitegui/qt/model_tables.py`: atomic numerical geometry/load editing.
- `src/pynitegui/qt/bulk_edit.py`: explicit multi-entity property assignments.
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
Additional-preset checks cover known mm/N and ft/kip conversion factors and
preservation of model data, analysis identity, result exports, and persistence.
Editing checks cover drag preview/commit/cancel, snapping, collision rejection,
and non-destructive load visibility. Custom support checks cover preset
equivalence, independent restraints, hinged joints, persistence, and undo.
Member-result checks cover extrema, exact-distance queries, one-sided jumps,
click inspection, combination switching, and SI conversion. Recovery checks
cover atomic write failures, untouched project files, multiple windows,
malformed snapshots, recovery dirtiness, cancelled closing, and recent projects.
Local-loading checks cover inclined/vertical/reversed axes, angled triangular
resultants, manual component equivalence, sign-changing ramps, split/node
conversion, SI input, persistence, and unedited angle/intensity precision.
Export checks cover SI/imperial values, combination identity, undefined rotations,
CSV quoting/formula safety, atomic failures, cancellation, stale-model rejection,
retained snapshot exports, report escaping, and native PDF rendering.
File-validation checks cover malformed shapes and values, duplicate keys,
versions 1 through 14, future-version rejection, non-mutating migrations, and
preservation of the active project and source file after a failed open.
Stability checks cover inadequate pins/rollers, custom restraints, translated
coordinates, zero-stiffness and internal sway mechanisms, valid released beams,
uniformly soft materials, nonfinite results in any combination, unrelated solver
errors, and the dense-localization size limit.
Larger-model benchmarks compare a twenty-segment mixed-material/section column
against independently integrated bending/axial formulas. Four-storey, two-bay
frames check global force/moment equilibrium, combination superposition,
triangular beam loads, lateral floor loads and nodal moments, fixed/pinned/mixed
supports, partial end releases, and endpoint reversal. These are numerical
regression benchmarks, not wall-clock performance targets or design certification.
Example checks solve every supplied model/combination, verify a cantilever's
analytical reactions, and cover fresh copies, SI equivalence, menu loading,
unsaved-state handling, and cancellation. Theme checks cover preference restore,
live recoloring, multi-window synchronization, contrast, toolbar icons, compact
inspector scrolling, pending input, and preservation of results/plot inspection.
Self-weight checks cover analytical beam deflection/reactions, per-member
materials/sections, inclined/reversed axes, case omission/factors/renaming,
zero density, splitting, old-file migration, validation, preview precision,
manual-load superposition, repeated analysis without duplication, undo/filtering,
snapshot invalidation, and export metadata.
Model-table checks cover all unit presets, unchanged-value precision, force/moment/
intensity interpretation, custom restraints, assignments/releases, new references,
dependent deletion, invalid drafts, the active numeric editor, cancellation,
self-weight separation, and one-step undo/redo.
Bulk-edit checks cover tree/canvas modifier selection, rectangle intersections,
cancellation, selection synchronization, mixed entity types, preserved properties,
all load quantities, atomic failure, cascading deletion, filtering, history,
selected-load highlighting, and result preservation/invalidation.
Section-library checks cover all entries, strong/weak-axis stiffness, all unit
presets, source metadata validation, legacy custom definitions, save/reopen,
search/family filters, duplicate-name protection, cancellation, one-step import
undo/redo, rename provenance, and custom classification after property edits.
Material-library checks cover reference conversions, mass/weight distinction,
all unit presets, source validation, old-file preservation, safe imports,
search, cancellation, conflicts, undo/redo, and property-edit classification.
Truss checks cover triangle joint equilibrium and virtual-work displacement,
zero shear/moment, inertia independence, reversed endpoints, mixed joints,
joint moments, lumped/mixed self-weight and combinations, split mechanisms,
migration, type validation, inspector/bulk/table edits, generated force units,
load rejection, and undo.
Presentation/report checks cover placement and sign independence, unchanged
solver probes, unit/combination updates, model definition conversions and HTML
escaping, selected sections, embedded light-palette images, inherited diagram
settings, invalid/empty choices, snapshot validation, and cancellation.

Keep workflow and engineering-scope changes documented here. Track remaining
features and known limitations in [TODO.md](TODO.md), updating it as work lands.
Commit completed, verified changes in coherent groups; keep implementation and
its regression tests together.
