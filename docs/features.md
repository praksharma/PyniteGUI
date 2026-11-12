# Feature Index

This index describes GUI workflows in the current source checkout, not everything
the PyNite engine can do. Use the [capability audit](project/roadmap.md#pynite-capability-coverage)
for Done/Partial/Pending status, and the [version scope](reference/version-scope.md)
when comparing with the published RC4 wheel.

## Modeling

| Features | Workflow and reference |
| --- | --- |
| 2D drawing, grid/node snapping, select/pan/fit, multiple and box selection | [Drawing and selection](modeling/drawing.md) |
| Dragging nodes, previews, cancel and undo | [Moving nodes](modeling/moving.md), [3D dragging](modeling/3d.md) |
| Atomic bulk edits and node/member/load tables | [Selection](modeling/drawing.md), [model tables](modeling/tables.md) |
| Named node/member groups, isolation, saved global-Y levels and optional drawing/drag snapping (development after RC2) | [Groups and levels](modeling/drawing.md) |
| Split, equal subdivision, explicit intersections and connectivity findings | [Topology and model checks](modeling/topology.md) |
| Previewed move/repeat/rotate/mirror, planar beam/frame generators and controlled two-node merging (development after RC2) | [Modelling tools](modeling/tools.md) |
| Perpendicular and midpoint construction connections | [Construction connections](modeling/construction.md) |
| Per-member materials with optional independent frame/truss G, and sections, searchable libraries with dimensioned section sketches, defaults and provenance | [Assignments](modeling/properties.md), [materials](reference/materials.md), [sections](reference/sections.md) |
| Free/pin/roller/fixed/custom supports, 2D/3D inclined rollers, imposed support motion and bilateral support springs | [2D supports](modeling/supports.md), [six-DOF spatial supports](modeling/3d.md) |
| Massless bilateral/tension-only/compression-only axial links between existing joints, staged editing, spring-only networks, results/CSV/MCP | [Joint springs](modeling/joint-springs.md) |
| Planar axial/shear/moment end releases | [Release editing](modeling/releases.md), [formulation and limits](reference/releases.md) |
| Spatial local DX/DY/DZ/RX/RY/RZ end releases, recovered member-side motion and released 2D conversion | [3D editing and scope](modeling/3d.md), [release formulation](reference/releases.md) |
| Bilateral axial-only trusses and mixed frame/truss models | [Trusses](modeling/trusses.md), [3D models](modeling/3d.md) |
| 3D work planes, XYZ entry, member roll, gizmo, orbit, picking and visibility | [Spatial workflow](modeling/3d.md) |
| Independent 2D-to-3D conversion and explicit support mapping | [Spatial conversion](modeling/3d.md) |

## Loads and Analysis

| Features | Workflow and reference |
| --- | --- |
| Nodal/member forces and moments; global/member-local angled forces | [Loads](analysis/loads.md), [3D loading](modeling/3d.md) |
| Uniform, triangular, varying and partial-span distributed member forces | [Distributed loads](analysis/loads.md) |
| Named load cases, default cases and signed/zero combination factors | [Cases and combinations](analysis/combinations.md) |
| Opt-in self-weight from member material density and area | [Self-weight](analysis/self-weight.md) |
| Linear elastic and frame-only P-Delta analysis, saved method, progress phases, cancellation and stale-result rejection | [Solve workflow](analysis/solve.md), [snapshots](results/snapshots.md) |
| Opt-in debounced live recalculation | [Live recalculation](analysis/live.md) |
| Rigid-body/mechanism/stiffness checks and affected-node findings | [Diagnostics](analysis/stability.md), [topology](modeling/topology.md) |

Reinforced-concrete plasticity remains pending. See the
[audited roadmap](project/roadmap.md), not the upstream feature list alone.
Development adds [inclined rollers](modeling/supports.md) for 2D/3D linear frames,
trusses and supported releases, plus inclined supports in the existing frame
P-Delta workflow. Staged native controls, conversion, normal symbols, reports and
MCP reactions share the same conventions and independent mechanics checks.

[Imposed support movements](modeling/supports.md) use length units/radians and
apply unchanged across every combination, including zero applied loads. Native
controls, tables/bulk edits, reports and MCP expose the prescribed quantities.
Supported frame-only P-Delta also accepts these motions, solves each combination
independently and checks geometric-stiffness convergence. Spring rest positions remain zero.

Iterative elastic adds tension/compression-only axial bars and one-way global
support springs, activation/reactivation, load stepping, independent combinations,
neutral stability checks and snapshot active-state/iteration tables, CSV and MCP.
Surfaces and spatial frame releases remain excluded. Three official unilateral
examples are available under Iterative elastic.

P-Delta keeps materials elastic and excludes slabs/trusses/released translations
and spatial rotational releases.
See [method limits and plasticity boundaries](analysis/solve.md).

Frame [Vibration Modes](analysis/modal.md) provide explicit physical mass sources,
frequencies/periods and normalized 2D/3D shapes in a separate native workspace, with
CSV/PNG/SVG/JSON and revision-aware MCP jobs. Scope: unreleased bilateral frames;
no surfaces, trusses, geometric preload, imposed motion or earthquake response.

Development also adds [Steel Pushover](analysis/pushover.md): explicit steel
I-section strengths, elastic preload, checked first-order capacity/end-yield
histories and separate native/MCP exports. Combined P-Delta/plastic response and
RC/surface plasticity remain outside this workflow.

## Results

| Features | Workflow and reference |
| --- | --- |
| Unit-aware displacements/reactions, member end values/extrema and linked selections | [Linked results](results/linked.md) |
| Equilibrium summary and independent reaction/load balance | [Equilibrium](results/linked.md) |
| Main-canvas 2D/3D result selector, exact click/station probes and signed member colour maps with shared combination scales | [Canvas results](analysis/solve.md) |
| Static deformation animation for retained 2D/3D member/surface fields, pause/reset and still-frame export | [Animation](analysis/solve.md) |
| Auto/true/custom deformation scaling, sampled curves and optional approximate straight preview | [Deformation](analysis/solve.md), [3D deformation](modeling/3d.md) |
| Whole-structure axial/shear/bending diagrams; spatial biaxial bending and torsion | [Diagrams](analysis/solve.md), [3D results](modeling/3d.md) |
| Member Detail, station inspection and one-sided values at jumps | [Inspection](analysis/solve.md) |
| Sign/side/amplitude controls and annotation collision handling | [Diagrams](analysis/solve.md), [conventions](results/conventions.md) |
| Independent diagram IDs, end values and sampled extrema in 2D, 3D overlays and printed projections; separate support/load visibility | [2D readability](analysis/solve.md), [3D visibility](modeling/3d.md), [report options](results/reports.md) |
| Two-combination member overlays with shared axes and exact signed governing probes; summary and sampled-curve envelopes | [Envelopes](results/envelopes.md), [spatial envelopes](modeling/3d.md) |
| Envelope-summary scopes (member ID, selection at open, saved group, all), component/unit-aware thresholds and filtered snapshot CSV | [Summary filters](results/envelopes.md) |
| Static storey drift from explicit node pairs, signed ratios, governing combinations and snapshot CSV | [Drift and envelopes](results/envelopes.md) |
| CSV, snapshot metadata, printable model/results/diagrams/envelopes and PDF through print | [Exports and reports](results/reports.md) |
| PNG/SVG native plot export with visible snapshot stamp and embedded context | [Plot image export](results/reports.md) |
| Global signed/absolute governing-station queries with member, combination and one-sided locations (development after RC2) | [Envelopes and station queries](results/envelopes.md) |
| Retained result windows and revision-aware snapshots | [Snapshots](results/snapshots.md) |

## Surfaces, Files and Automation

| Features | Status and documentation |
| --- | --- |
| Seven PyNite generators, Quad/Rect where supported, sizing, origins, modifiers and numbering | [Experimental mesh catalog](surfaces/meshing.md) |
| Rectangle control lines/openings, recipe files, undo and connectivity export | [Mesh options](surfaces/meshing.md) |
| Main-model surfaces, face and enclosed/crossing box selection, edit/delete, saved recipes and frame placement | [Surface geometry](surfaces/main-model.md) |
| Opt-in rectangular Quad/frame coupling, pressure cases, self-weight, deformed mesh and geometry-owned global edge supports | [Experimental coupled slabs](surfaces/main-model.md) |
| Snapshot-bound local moment/membrane-stress contours, natural-coordinate probes, CSV and MCP; Quad shear withheld pending validation | [Slab results](surfaces/main-model.md) |
| Affine/nonuniform applied-traction membrane convergence and strain energy, coincident beam/slab strip refinement and quantified rejected drilling cases; corrected non-square YZ edge/probe axes | [Bounded coupled verification](surfaces/main-model.md) |
| Rectangle fitting to selected corners/perimeters or complete frame levels | [Slab placement](surfaces/main-model.md) |
| Separate Quad/Rect plate bending, multiple uniform cases/combinations, horizontal self-weight, edge supports, cached combination contours and provenance CSV | [Experimental plate-only analysis](surfaces/plates.md) |
| Separate-plate element picking, local bending probes, linked marker, centre table and unit/snapshot-labelled centre/probe CSV; corrected Rect shear and guarded recovered Quad centre shear | [Local plate inspection](surfaces/plates.md) |
| Independent centred-opening/Rect recovery benchmarks; corrected Rect resultants in post-RC4 development, with explicit limits | [Plate verification and RC4 limitation](surfaces/plates.md) |
| Guarded standalone thin-Quad recovered centre shear, explicit corner/stencil masks, centre-only probes, provenance CSV and two custom examples; raw/coupled shear unavailable | [Quad shear feasibility](surfaces/plates.md) |
| Four display-unit presets and canonical inch/kip storage | [Units](reference/units.md) |
| Versioned save/open, migrations, undo/redo, recent-file cleanup and autosave/recovery | [History](reference/saving.md), [formats](reference/formats.md), [recovery](reference/recovery.md) |
| Native macOS/Windows/Linux development packages, locked wheel/source builds and relocated frozen checks; public installers/signing pending | [Installation/build workflow](start/install.md), [validation record](project/releases.md) |
| Selection/finding-focused camera navigation in 2D/3D; Shift+F and full-model Fit | [Help and workspace](start/help.md), [model findings](modeling/topology.md) |
| Optional Model/Results workspaces and collapsible command toolbars, preserving draft inputs and view framing | [Workspaces](start/help.md) |
| Help menu, website/F1, searchable shortcuts, About/version details and default-layout recovery | [Help and workspace](start/help.md) |
| Searchable native example browser with geometry/loading/check previews; categorized menus, Gerber/three-hinged arch, fourteen official examples, coupled slabs and P-Delta | [Examples and preferences](start/examples.md), [hinge walkthrough](start/first-model.md#try-an-internal-hinge-or-three-hinged-arch) |
| Official clamped Quad plate and hydrostatic wall in the separate workspace; fourteen of twenty upstream examples adapted | [Examples and limits](start/examples.md), [plate workspace](surfaces/plates.md) |
| Light/dark themes and scrollable properties | [Examples and preferences](start/examples.md) |
| Software-rendering recovery, observed renderer diagnostics, NVIDIA/Wayland profiles | [Graphics](start/graphics.md), [Linux NVIDIA](start/nvidia.md) |
| Optional localhost MCP server, frame/surface/pressure batch edits, coupling opt-in, permission groups and background solve lifecycle | [MCP server](automation/mcp.md) |

General curved-shell analysis, combined shell face stresses, arbitrary CAD meshing,
shear-wall/mat workflows remain pending. A touching
surface is not connected unless coupled analysis is enabled and the mesh passes
the shared-node/interface checks.

For contributors, [focused test groups](development/testing.md) separate native
UI checks from engineering, surface and MCP suites. Combine affected groups;
full-suite and release verification remain available.

Development [Steel Pushover](analysis/pushover.md) adds explicit steel profiles,
elastic preload plus nodal push increments, checked histories/capacity curves,
unit-labelled tables, CSV/PNG/SVG/JSON and MCP jobs. Partial results are labelled;
no P-Delta/plastic combination, nonlinear slabs or RC plasticity is claimed.
Three editable examples have independent hand references and refinement checks.
A [combined P-Delta/plastic prerequisite study](analysis/pushover.md) isolates
pre-yield axial-force and changing-load equilibrium defects in PyNite 3.2.1.
Its illustrated 62-record report retains rejection; both official combined
pushover examples remain pending. The application keeps its checked first-order path.
A subsequent test-only total-state corrector resolves the bounded elastic
preload/ramp defects, with independent fields, derivatives, stability and unit
checks plus 36 reproducible records. Plastic yielding and production integration
remain unvalidated; the original negative measurements are preserved.
A subsequent local section prototype adds backward-Euler yielding, unloading,
reverse yield and consistent material tangents, checked against scalar cycles and
independent mixed-return optimization. Its 33-record report also demonstrates
and excludes a nonconvex interaction region. These remain local research checks;
member/hinge compatibility and combined frame-plastic qualification are pending.

The separate plate workspace supports geometry-owned linear pressure along local
width/height, centroid-load previews and pressure probes. The official hydrostatic
tank wall is available with pinned bending/nodal parity and independent load and
refinement checks. See [Plate loading](surfaces/plates.md). That thick clamped wall remains outside recovered-shear scope.

The [Quad-shear validation study](surfaces/plates.md) now covers outer boundaries,
graded meshes and material/thickness interfaces with explicit missing stencils.
Independent Kirchhoff energy references now resolve selected opening-area means
and sampled fields away from corners. A compatible, pressure-equilibrated research
method meets the bounded free-rim target while preserving polynomial and
interface checks. Its guarded standalone integration provides separately labelled
Recovered Qx/Qy centre contours, missing-value masks and provenance exports.
Finite edge-beam checks reject coupled recovery; main-model CSV/MCP reports null
shear with explicit eligibility/status metadata. General source/interface and
corner-peak validation remain pending.

A subsequent constant-resultant segment study checks explicit plastic-zone length,
section-to-extension/rotation compatibility, energy and plastic-work partition.
Axial/pure-couple cycles and mixed tangents pass bounded references; general
member geometry and combined frame plasticity remain pending. See [Steel
Pushover](analysis/pushover.md).

A planar bending-gradient compatibility study additionally checks located
prescribed-curvature zones, chord-relative rotations, elastic beam stiffness and
virtual work against closed-form references. It supplies no generated plastic
flow or combined frame solver. See [Steel Pushover](analysis/pushover.md).

A subsequent pure-bending material-element study generates plastic curvature from
imposed nodal motion and integrates moving fronts, forces, tangent and energy.
Independent section-return/cycle references pass; global equilibrium, mesh
refinement and combined nonlinear frame analysis remain pending. See [Steel
Pushover](analysis/pushover.md).

A global propped-beam research assembly now closes equilibrium and checks unloading,
committed history and an independent overload mechanism bound. Its 32-segment
solution still fails the 1% displacement/moment gates; numerical convergence does
not qualify the member or enable combined frame analysis. See [Steel Pushover](analysis/pushover.md).

A separate explicit base point-hinge research formulation now passes the ideal
propped-beam displacement/moment gates across tested meshes and increments,
including unloading, reversal and energy checks. This changes the localization
model; distributed-curvature failures remain preserved. General frame and
P-Delta integration remain pending. See [Steel Pushover](analysis/pushover.md).

A research extension accepts up to four configured scalar hinge interfaces and
nodal forces/couples, with signed active-set equilibrium and a detected two-hinge
mechanism rather than a hardcoded load bound. Only configured interfaces yield;
remaining spans are elastic. General frames and P-Delta remain pending. See
[Steel Pushover](analysis/pushover.md).

A separate connected planar-frame research assembly now verifies two stable active
base hinges and the four-hinge portal collapse against independent slope-deflection
and virtual work. Joint equilibrium, subdivision, cycles, energy, tangent and
coordinate/unit invariance are checked. This remains first-order scalar configured
hinges, with elastic spans and no axial–moment/P-Delta or GUI integration. See
[Steel Pushover](analysis/pushover.md).

A bounded corotational scalar-hinge research frame now checks geometric/material
energy derivatives, independent compressed/tensioned-column references and a
gravity-loaded yielding portal with unload/reverse work balance. Column refinement
is required: the one-element compression result misses the continuum reference by
4%. This distinct energy law does not qualify PyNite combined-source parity,
interaction or production use. See [Steel Pushover](analysis/pushover.md).
