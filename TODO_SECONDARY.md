# Secondary Roadmap: Stabileo-Inspired Ideas

Reviewed 2026-10-03. Inspiration: [Stabileo](https://github.com/lambdaclass/stabileo)
and its [Basic](https://stabileo.com/app/basic) and
[PRO](https://stabileo.com/app/pro) editors. This is a wishlist,
not a commitment to copy its interface or replace Qt/PyNite.

[TODO.md](TODO.md) remains the primary implementation roadmap. When an item
below overlaps it, the primary item owns completion; promote new work there
when selected. Existing loads, materials, units, themes, examples, and result
inspection are not new tasks just because Stabileo also has them.

## Compatibility Gate

Checked against the installed **PyniteFEA 3.0.0** source, not only the latest
online documentation. Our application now exposes linear static 2D frames/trusses
and 3D spatial frames/axial-only trusses; solver capability does not mean a feature is already usable
here. See the primary [capability audit](TODO.md#pynite-capability-coverage) for
current engine-feature coverage, partial support and future solver milestones.

- **UI**: application-side editing or presentation of an existing PyNite model
  or result. No new structural solver is needed.
- **Adapter**: verified PyNite capability, but requires model/schema, adapter,
  validation, units, and benchmark work before exposure.
- **Deferred adapter**: supported engine capability with a substantially larger
  workflow change. Keep behind the mature 2D static workflow.

## First: Interface and Result Reading

Observed in the live editor: grouped tools, a resizable contextual results panel,
diagram/colour-map modes, a comparison selector, and separate result-table tabs.
These are the strongest ideas to adapt to a desktop engineering workflow.

- [ ] **Grouped compact toolbar (UI).** Organize view, draw, properties, loads,
  analysis, and results tools into clear groups. Use recognizable icons,
  tooltips, visible active modes, and disabled result controls until solved.
  Keep engineering controls usable at smaller window sizes.
- [ ] **In-canvas result workspace (UI).** Switch between model, deformation,
  axial, shear, and moment views without opening a window each time. Keep a
  resizable results dock with combination, scale, and inspection controls.
  Preserve Member Detail windows and their snapshot identity.
- [ ] **Combination comparison (UI).** Overlay two solved combinations with
  distinct styles, a shared scale, and governing values at the probe station.
  Never combine results from different model revisions or analysis methods.
- [ ] **Signed result colour maps (UI).** Offer a colour-map alternative to
  offset diagrams, using PyNite span samples. Include a numerical legend,
  zero/sign distinction, explicit units, and a shared scale for comparisons.
  Colour alone must not communicate the sign.
- [x] **Linked result tables (UI).** Promoted to TODO.md and implemented in the
  native results dock: combined node overview plus separate displacement,
  reaction and member-force tabs; numeric sorting, two-way geometry/tree links,
  multi-selection, correct units and snapshot-preserving combination changes.
  Member rows load on demand and double-click opens that member's detail.
- [ ] **Diagram readability controls (UI).** Toggle IDs, loads, supports, values,
  and extrema independently. Avoid label collisions and make local-axis/sign
  conventions inspectable. Primary owner: dense labels, sign preferences, and
  consistent result annotations in TODO.md.
- [ ] **Combination envelopes (UI).** Add max/min curves and governing
  combination identification, including both sides of load discontinuities.
  PyNite member extrema accept combination tags; sampled curves can use the
  existing span-result API. Primary owner: result envelopes in TODO.md.

## Next: Faster Modelling and Exploration

Stabileo's Project panel groups examples and exports; its Explore panel offers
temporary parameter multipliers and reset. Adapt these workflows without
silently changing saved engineering definitions.

- [ ] **Numerical tables and bulk assignment (UI).** Edit coordinates and load
  values in tables; assign material, section, or case to a selection in one
  undoable operation. Validate the whole transaction before applying it.
  Primary owner: editable tables and multiple selection in TODO.md.
- [ ] **Section chooser with previews (UI).** Browse named sections and show a
  dimensional sketch alongside A, Iy, Iz, and J. Feed validated properties to
  PyNite; do not imply a shape sketch provides stress recovery or code design.
  Primary owner: section library in TODO.md.
- [ ] **Opt-in live linear recalculation (UI).** Debounce completed edits, solve
  a cloned model in the background, and display pending/failed/current state.
  Reject stale replies, avoid solving unfinished numeric input, and allow
  manual mode for larger models. Retain explicit Analyze as the default.
- [ ] **Temporary what-if workspace (UI).** Explore load, E, and section-property
  multipliers against a baseline using cloned projects and PyNite solves.
  Provide reset and explicit apply-as-one-edit. Shared definitions must not
  accidentally change unselected members. Invalid variants stay visibly failed.
- [ ] **Deformation animation (UI).** Animate the scale of the existing static
  displacement field with pause/reset and a fixed reference outline. Label it
  as static deformation animation, not a dynamic response calculation.
- [ ] **Example browser (UI).** Group beams, frames, and future trusses with a
  preview, loading summary, and expected check values. Add Gerber/internal-hinge
  and three-hinged polygonal-arch examples; keep tests and unsaved-change prompts.
- [ ] **Model/result exchange and graphics (UI).** Add a validated spreadsheet
  template and richer model-plus-result reports, plus PNG/SVG diagram export.
  Import into a preview before replacing the project; show units and snapshot
  metadata in exports. Primary owner: richer printable reports in TODO.md.

## PRO: Larger-Model Workflows

Follow-up review on 2026-10-03 covered PRO's Model, Analyze, and Design tabs,
including Transform, Generators, Groups, Edit, Project, and a solved 20-node,
28-member planar-frame example. These are observed interface workflows, not
an audit of Stabileo's engineering calculations. PRO is labelled beta.

### Priority: Repeated Geometry and Model Organization

- [ ] **Model/Results workspaces (UI).** Adapt PRO's command tabs to our scope:
  modelling tools in one workspace, results and exports in another, with the
  command strip collapsible. Preserve selection, view framing, and unsaved
  input when switching. Extend the grouped-toolbar/in-canvas-result tasks
  above; do not add an empty Design tab or imply code verification.
- [ ] **Named groups and levels (UI).** Save node/member selection sets for a
  frame, storey, or zone; reselect and isolate them quickly. Define explicit
  elevation levels in our XY plane, with optional snapping. Groups are editing
  metadata, not rigid diaphragms or solver constraints. Update references after
  splitting/deleting entities and coordinate with primary multiple selection.
- [ ] **Repeat, mirror, rotate, and move with preview (UI).** Transform selected
  geometry about a specified point, or repeat it at explicit bay/storey offsets.
  Show a ghost before applying; offer separate load/support-copy options and
  optional connecting members. Preserve global versus local force semantics,
  load positions, end releases, and identifiers. Resolve node collisions and
  support conflicts explicitly; one undo transaction per operation. PyNite
  receives ordinary validated nodes, members, and loads.
- [ ] **Parametric planar generators and reusable pieces (UI).** Generate
  continuous beams and multi-bay/multi-storey frames from spacing lists, with
  separate beam/column sections, material, base supports, and insertion point.
  Preview counts, dimensions, and assumptions before placement. Save selected
  geometry as a reusable local template. Truss generators wait for the explicit
  truss workflow; no automatic sizing or structural design is implied.
- [ ] **Reviewable topology cleanup and construction aids (UI).** Turn existing
  validation findings into select/zoom actions and previewed fixes. Finding
  selection and equal frame subdivision are completed in the primary roadmap;
  finding-focused zoom, previewed fixes, perpendicular connections and
  midpoint-to-midpoint members remain pending.
  Offer controlled node merging, orientation reversal, and renumbering; rewrite
  every reference and preserve loads, releases, and group membership. Merge
  collinear members only when the intermediate node has no engineering role
  and properties agree. Never silently remove a support/load/hinge or connect
  a crossing; build on existing split/connect operations in TODO.md.

### Priority: Navigable Engineering Results

- [ ] **Scoped result queries (UI).** Filter by all members, selection, group,
  or ID, then max, min, absolute extreme, and a unit-aware threshold. Clicking
  the governing row locates its member and station. Reuse PyNite extrema/span
  results, include interior extrema and discontinuities rather than only ends,
  and export the filtered query with snapshot/combination metadata. Extend the
  linked tables and envelope tasks above instead of duplicating them.
- [x] **Visible equilibrium and analysis status (UI).** Promoted and completed in
  the primary roadmap: planar/spatial global totals, residuals, tolerances and
  units, including combination factors, manual/self-weight loads and distributed
  resultants. Analysis lifecycle states identify retained snapshots explicitly.
  Balance is not design approval. Navigation from recognized failure diagnostics
  to affected geometry is also completed in the primary roadmap; extend the
  free-body inspector below.
- [ ] **Plain storey displacement/drift table (UI).** For explicitly paired
  nodes at successive levels, calculate horizontal displacement difference and
  drift ratio from PyNite nodal results. Report pairs, height, combination, and
  governing value; allow multiple columns without assuming a rigid floor.
  This is static result post-processing, not automatic seismic load generation,
  code-amplified seismic drift, or a code pass/fail check. PRO's drift tab was
  inspected but required code-generator settings; borrow the workflow, not its
  code-dependent calculation.
- [ ] **Fast deformation preview for large frames (UI).** Offer sampled member
  curves versus displaced-node straight lines, clearly identifying the latter
  as an approximate display. Both use the same solved snapshot; switching must
  not change numerical probes, extrema, exported result tables, or the solver.
  Coordinate with existing deformation scale/animation controls.

### Later: Approximate Geometry, Not a New Element Formulation

- [ ] **Tapered-member segmentation helper (UI, deferred).** Generate a sequence
  of prismatic members with explicitly assigned section properties to approximate
  a changing section. PyNite supports that assembled model; this is not native
  exact tapered-element support. Preserve integrated loads and self-weight,
  define section/torsion assumptions, and require mesh-convergence benchmarks
  before exposing the helper. Do not reuse PRO's advertised error bound.

## Later: Verified Solver Extensions

- [ ] **Elastic supports and settlement (Adapter).** Expose global DX/DY/RZ
  support stiffness via `def_support_spring` and imposed displacement/rotation
  via `def_node_disp`. Start with bilateral springs. Spring units, reaction
  signs, and mechanism checks need dedicated tests. Imposed displacements are
  model-level in this API, not automatically case-specific loads. Primary owner
  for springs: elastic support springs in TODO.md; inclined supports are separate.
  Bilateral springs are now implemented and benchmarked in the primary roadmap;
  imposed settlements/rotations remain future work.
- [ ] **Explicit truss/member behaviour (Adapter).** Add a clear pin-ended truss
  workflow using supported end releases, then optional tension/compression-only
  behaviour via member flags and iterative `analyze`, not `analyze_linear`.
  Verify unloaded joint rotations and do not silently apply transverse member
  loads to an axial-only idealization. Primary owner: truss elements in TODO.md.
- [ ] **First-order versus P-Delta (Adapter).** Expose `analyze_PDelta` as a
  separate method with convergence feedback, method-labelled snapshots, and
  benchmark comparisons. Evaluate each factored combination as its own solve;
  do not superpose nonlinear results. This is not an eigenvalue buckling tool.
- [ ] **Free-body and stiffness inspection (Adapter).** Show solved member-end
  forces, applied loads, reactions, and equilibrium residuals. An optional
  educational inspector can read PyNite's `Ke`, `FER`, `P`, `D`, and member
  transformations; label DOFs, releases, and physical-member segmentation.
  Do not introduce a second solver or replace stability diagnostics with a
  simple degree-of-indeterminacy formula.
- [ ] **Modal frequencies and mode shapes (Deferred adapter).** The installed
  engine exposes `analyze_modal`. Require an explicit mass-source combination,
  consistent gravity conversion, mode filtering, a separate result type, and
  independent benchmarks. Static weight density must not be treated directly
  as mass density. Do not promise time-history or response-spectrum analysis.
- [x] **3D frame viewport (Adapter).** Implemented as a separate spatial project
  with XYZ geometry, six DOFs, work-plane drawing, rolled local axes, spatial
  member results, force/moment overlays and deformation. Planar mode remains
  first-class. Remaining scope is owned by 3D Follow-Ups in TODO.md.

## Intentionally Not Tasks

Stabileo advertises a wider engine and several in-development modules. This
review does **not** add thermal member loads, eigenvalue buckling, general
plastic collapse, time-history/response-spectrum/harmonic response, staged
construction, arbitrary section stress/shear-flow analysis, concrete/code-design
checks, or AI model generation. No verified equivalent end-to-end workflow was
established in our installed adapter for these features. PyNite has specialized
capabilities beyond the current app; that is not a basis to promise parity.

Moving loads/influence lines would need a separately validated orchestration
layer, rather than a native capability verified here. Plates/shells are supported
by PyNite, but are outside this frame-focused shortlist. Web accounts, hosted
sharing, and web-only delivery are not desktop UI requirements.

The PRO review does not promote its Design tab, reinforcement detailing,
connection checks, automatic wind/seismic code loads, rigid diaphragms, member
offsets, IFC inference, or automatic architectural-DXF-to-structure proposals.
Those require independently verified solver/engineering workflows beyond this
shortlist. A tab or advertised feature is not evidence of PyNite compatibility.
Shell meshing remains a separate scope decision, not a new near-term task.

## Evidence and Recheck Points

- [Stabileo repository and feature/status overview](https://github.com/lambdaclass/stabileo).
- [Live Basic editor](https://stabileo.com/app/basic): reviewed Project, portal-frame
  results, Advanced, and Explore panels; observations are not implementation guarantees.
- [Live PRO editor](https://stabileo.com/app/pro): reviewed Model tools and Project
  examples/exports, solved the planar static-force example, inspected Analyze
  outputs/query controls and Design prerequisites. Design checks, imports,
  transforms, and generator placement were not independently validated.
- [PyNite model API overview](https://pynite.readthedocs.io/en/latest/FEModel3D.html).
- [PyNite member conventions and result APIs](https://pynite.readthedocs.io/en/latest/member.html).
- Local check: installed `Pynite/FEModel3D.py` and `Pynite/Member3D.py` in `.venv`,
  version 3.0.0. Online documentation currently describes 3.2.0; recheck the
  installed/pinned version when promoting any solver extension.

Recommended starting batch: grouped toolbar, in-canvas result workspace, linked
tables, then comparison/envelopes. These improve daily use without widening the
engineering assumptions.
Follow with PRO-inspired selection groups, previewed repeat/mirror tools, and
planar generators; these become much more useful once bulk selection is in place.
