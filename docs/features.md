# Feature Index

This index describes GUI workflows in the current source checkout, not everything
the PyNite engine can do. Use the [capability audit](project/roadmap.md#pynite-capability-coverage)
for Done/Partial/Pending status, and the [version scope](reference/version-scope.md)
when comparing with the published rc1 wheel.

## Modeling

| Features | Workflow and reference |
| --- | --- |
| 2D drawing, grid/node snapping, select/pan/fit, multiple and box selection | [Drawing and selection](modeling/drawing.md) |
| Dragging nodes, previews, cancel and undo | [Moving nodes](modeling/moving.md), [3D dragging](modeling/3d.md) |
| Atomic bulk edits and node/member/load tables | [Selection](modeling/drawing.md), [model tables](modeling/tables.md) |
| Split, equal subdivision, explicit intersections and connectivity findings | [Topology and model checks](modeling/topology.md) |
| Perpendicular and midpoint construction connections | [Construction connections](modeling/construction.md) |
| Per-member materials and sections, searchable starter libraries, defaults and provenance | [Assignments](modeling/properties.md), [materials](reference/materials.md), [sections](reference/sections.md) |
| Free/pin/roller/fixed/custom supports and bilateral support springs | [2D supports](modeling/supports.md), [six-DOF spatial supports](modeling/3d.md) |
| Planar axial/shear/moment end releases | [Release editing](modeling/releases.md), [formulation and limits](reference/releases.md) |
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

Modal analysis, steel pushover, reinforced-concrete plasticity, unilateral
members/springs, node-to-node spring elements and inclined supports are **not implemented GUI workflows**. See the
[audited roadmap](project/roadmap.md), not the upstream feature list alone.

P-Delta keeps materials elastic and excludes slabs/trusses/released translations.
See [method limits and plasticity boundaries](analysis/solve.md).

## Results

| Features | Workflow and reference |
| --- | --- |
| Unit-aware displacements/reactions, member end values/extrema and linked selections | [Linked results](results/linked.md) |
| Equilibrium summary and independent reaction/load balance | [Equilibrium](results/linked.md) |
| Auto/true/custom deformed shape amplification and sampled peak displacement | [Deformation](analysis/solve.md), [3D deformation](modeling/3d.md) |
| Whole-structure axial/shear/bending diagrams; spatial biaxial bending and torsion | [Diagrams](analysis/solve.md), [3D results](modeling/3d.md) |
| Member Detail, station inspection and one-sided values at jumps | [Inspection](analysis/solve.md) |
| Sign/side/amplitude controls and annotation collision handling | [Diagrams](analysis/solve.md), [conventions](results/conventions.md) |
| Independent 2D diagram IDs, end values, sampled extrema and support/load visibility | [Diagram readability](analysis/solve.md) |
| Exact summary and sampled-curve combination envelopes, governing combinations | [Envelopes](results/envelopes.md), [spatial envelopes](modeling/3d.md) |
| CSV, snapshot metadata, printable model/results/diagrams/envelopes and PDF through print | [Exports and reports](results/reports.md) |
| PNG/SVG native plot export with visible snapshot stamp and embedded context | [Plot image export](results/reports.md) |
| Retained result windows and revision-aware snapshots | [Snapshots](results/snapshots.md) |

## Surfaces, Files and Automation

| Features | Status and documentation |
| --- | --- |
| Seven PyNite generators, Quad/Rect where supported, sizing, origins, modifiers and numbering | [Experimental mesh catalog](surfaces/meshing.md) |
| Rectangle control lines/openings, recipe files, undo and connectivity export | [Mesh options](surfaces/meshing.md) |
| Main-model surfaces, face and enclosed/crossing box selection, edit/delete, saved recipes and frame placement | [Surface geometry](surfaces/main-model.md) |
| Opt-in rectangular Quad/frame coupling, normal pressure cases, self-weight and deformed mesh | [Experimental coupled slabs](surfaces/main-model.md) |
| Rectangle fitting to selected corners/perimeters or complete frame levels | [Slab placement](surfaces/main-model.md) |
| Separate rectangular Quad/Rect bending tool, pressure/edge supports, contours and nodal CSV | [Experimental plate-only analysis](surfaces/plates.md) |
| Four display-unit presets and canonical inch/kip storage | [Units](reference/units.md) |
| Versioned save/open, migrations, undo/redo, recent-file cleanup and autosave/recovery | [History](reference/saving.md), [formats](reference/formats.md), [recovery](reference/recovery.md) |
| Selection/finding-focused camera navigation in 2D/3D; Shift+F and full-model Fit | [Help and workspace](start/help.md), [model findings](modeling/topology.md) |
| Help menu, website/F1, searchable shortcuts, About/version details and default-layout recovery | [Help and workspace](start/help.md) |
| Searchable native example browser with geometry/loading/check previews; categorized menus, Gerber/three-hinged arch, six official examples, coupled slabs and P-Delta | [Examples and preferences](start/examples.md), [hinge walkthrough](start/first-model.md#try-an-internal-hinge-or-three-hinged-arch) |
| Light/dark themes and scrollable properties | [Examples and preferences](start/examples.md) |
| Software-rendering recovery, observed renderer diagnostics, NVIDIA/Wayland profiles | [Graphics](start/graphics.md), [Linux NVIDIA](start/nvidia.md) |
| Optional localhost MCP server, frame/surface/pressure batch edits, coupling opt-in, permission groups and background solve lifecycle | [MCP server](automation/mcp.md) |

General curved-shell analysis, slab stress contours, arbitrary CAD meshing,
shear-wall/mat workflows remain pending. A touching
surface is not connected unless coupled analysis is enabled and the mesh passes
the shared-node/interface checks.

For contributors, [focused test groups](development/testing.md) separate native
UI checks from engineering, surface and MCP suites. Combine affected groups;
full-suite and release verification remain available.
