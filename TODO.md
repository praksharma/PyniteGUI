# Brecon Roadmap

- [x] Rename the app/distribution/command to Brecon, with a place-inspired
  wordmark, current docs/citation/MCP identity, legacy command/import compatibility
  and unchanged project, preferences and recovery identifiers. Preserve existing
  release tags/assets and repository URLs. Brecon publishing needs its own PyPI
  project/publisher setup; the previous-name distribution is not renamed in place.
- [x] Owner: configure Brecon's pending PyPI publisher before its first release
  (`brecon`, `praksharma/PyniteGUI`, `publish.yml`, environment `pypi`). Preserve
  the existing PyniteGUI publisher; owner confirmed setup on 2026-10-28. This
  does not publish a renamed package.
- [x] Restrict the publishing workflow to Brecon metadata and reject pre-rename
  RC2/RC3 tags before downloading/uploading distributions. Exercise the real
  metadata gate against accepted Brecon and rejected old/mismatched tags.
- [x] Prepare the first Brecon release, 1.0.0rc4: full locked/installed suites,
  final base/MCP and uv-tool installs, viewport/docs checks, audited artifacts
  and release notes. Retain old PyniteGUI releases and the stable-platform gates.
- [x] Publish Brecon 1.0.0rc4 on GitHub and PyPI through Trusted Publishing after
  the owner's environment approval. Verify registry artifact hashes and a fresh
  public-PyPI installation; preserve existing PyniteGUI releases (2026-10-28).

Current scope: a 2D/3D frame and bilateral axial-only truss editor with SI/imperial input and display, per-member materials and
sections, custom global support restraints, global/member-local angled forces, distributed loads,
and named load cases/combinations. This list tracks remaining work;
items are not promises of a particular release date.

See the [focused UI/modelling backlog](TODO_SECONDARY.md) for eight completed
canvas, organization, result-query and previewed modelling improvements. This file owns engineering work, completed records and
release gates. Scope was pruned 2026-10-27: duplicate umbrella/release/solver ticks
and unrequested speculative extras were removed, without dropping validation
requirements or the official-example dependency audit.

## PyNite Capability Coverage

Audited 2026-10-16 against our application adapters, schemas and documented
workflows, plus the locked **PyniteFEA 3.0.0** source. The
[upstream capability list](https://github.com/JWock82/Pynite#current-capabilities)
describes the engine, not features automatically available in this GUI.
**Done** means usable in the stated application workflow; **Partial** identifies
the exact missing part. Summary: **9 done, 4 partial, 5 pending**. P-Delta coverage rechecked 2026-10-26.

| Engine capability | GUI status | Coverage or remaining task |
| --- | --- | --- |
| Elastic 3D statics | Done | Linear spatial-frame and axial-only truss analysis, six DOFs, rolled frame members, materials/sections and validated results. |
| Frame P-Delta | Done | Saved linear/P-Delta choice for 2D/3D frame-only models; independent combination solves, actual phase feedback, effective-stiffness rejection, method-labelled snapshots/reports/MCP and analytical compression/tension/refinement benchmarks. No coupled slabs, trusses or released translations. |
| Frame modal analysis | Pending | Add an explicit mass source, gravity/unit conversion, frequencies, mode shapes and a separate modal result workflow. |
| Steel-frame pushover | Pending | Confirmed locked-engine steel I-section interaction model: needs fy, Zy/Zz, section/material binding, elastic preload, push increments, displacement stop, accepted-step histories and capacity curves. First-order only; no P-Delta integration or nonlinear shells. Benchmark before GUI exposure. |
| Member point/distributed and nodal loading | Done | Nodal/member forces and moments, uniform/linear-varying distributed forces and partial spans in 2D/3D. Distributed member moments are excluded. |
| Cases and factored combinations | Done | Named cases, combination editing, selected-combination results and visible factored loads in 2D/3D. |
| Member shear, moment and deflection output | Done | Member detail curves in 2D/3D; spatial biaxial shear/bending, torsion and deformation; whole-frame force/moment overlays. |
| Physical-member internal joints | Partial | Explicit split/connect workflows in 2D/3D; experimental coupled slabs add solver-only subdivision at conforming shell nodes. General implicit user-frame intersections remain excluded. |
| Unilateral member behaviour | Pending | Add tension-only/compression-only flags, iterative active-set analysis and activation/mechanism benchmarks; ordinary 2D/3D trusses are not unilateral members. |
| Node-to-node spring elements | Pending | Add separate spring entities, axial stiffness units and bilateral/tension-only/compression-only behaviour; support springs are not spring elements. |
| Bilateral/unilateral support springs | Partial | Bilateral global DX/DY/RZ springs in 2D and all six DOFs in 3D are implemented. One-way support springs and iterative activation remain pending. |
| DKMQ quadrilaterals | Partial | Plate-only bending tool plus opt-in rectangular Quad/frame coupling with pressure cases, self-weight, shared joints, conformity checks, nodal results/deformation and equilibrium. General shell result inspection, stress contours and curved-shell benchmarks remain pending. |
| Polynomial rectangles | Partial | Quad/Rect choice for rectangular plate bending (including openings) with centre-coordinate recovery, deflection comparison and equilibrium regressions. General membrane/shell workflows and additional formulation-specific benchmarks remain pending. |
| Shape/opening meshing | Done | All seven concrete PyNite generators with shape-specific/common options, bounded checks, control lines/openings, offline 3D geometry preview, recipes/undo and connectivity export. Curved-shell analysis and frame assembly remain distinct pending capabilities. |
| Support reactions | Done | Unit-aware reaction tables, CSV and printable output; all six components for spatial frames, including bilateral support springs. |
| Geometry/load/deformation rendering | Done | Frame/truss loads, supports and deformed shapes; plate-only contours, seven mesh previews, plus experimental coupled rectangular slab pressures and deformed meshes. |
| Shear walls and mats | Pending | Add dedicated wall/foundation definitions, meshing, openings, soil/support input and specialized results; verify the locked engine before exposing workflows. |
| Model/result PDF output | Done | Native printable model definitions/results with save-to-PDF; 2D diagrams and numerical envelopes; 3D six-component diagrams with selectable orthographic views and numerical envelopes. |

### Analysis Method Checklist

Implementation status checked 2026-10-26. Tick a method only when its stated GUI
workflow has validated inputs, usable results and regression coverage; an API
existing in PyNite alone does not count. Keep this checklist and the capability
table above in sync as methods are implemented.

**Current priority:** software quality and UI polish. New solver implementation
is on hold at the user’s request; existing analysis methods remain available.

- [x] **Linear elastic** (`analyze_linear`): 2D/3D frames, bilateral axial-only
  trusses and opt-in rectangular Quad slab/frame coupling; reactions,
  displacements, member results, combinations and exports.
- [x] **P-Delta elastic** (`analyze_PDelta`): saved, undoable method selection
  across manual/live/MCP frame analysis; independent combination solves, actual
  progress phases, effective-stiffness checks and method-labelled snapshots/
  exports. Analytical compression/tension, refinement and instability regressions
  plus a public example. Frame-only; no slabs, trusses or released translations.
- [ ] **General iterative elastic** (`analyze`): tension-only/compression-only
  members and one-way support springs, activation/deactivation and optional
  load stepping. Add persisted behaviour flags, iteration/tolerance controls,
  convergence/active-state results, independent combination solves and activation/
  mechanism benchmarks. Materials remain elastic; this is not plastic yielding.
- [ ] **Steel plastic pushover** (`analyze_pushover`) — planned after the solver hold:
  validated yield strength and plastic section moduli (`fy`, `Zy`, `Zz`), section/
  material binding, elastic preload and push patterns, load increments,
  displacement stop conditions, accepted-step histories and base-shear/roof-
  displacement capacity curves. Benchmark the steel I-section interaction model.
  The public engine method is first-order; no P-Delta integration or nonlinear slabs.
- [ ] **Modal analysis** (`analyze_modal`): explicit mass-source combination,
  load-to-mass direction and consistent gravity conversion, mode count, natural
  frequencies/periods and mode shapes with their own results/visualization and
  independent benchmarks. Modal analysis alone is not an earthquake-response solver.

Separate solver/formulation work:

- [ ] **Reinforced-concrete nonlinear frames/slabs:** evaluate a separate validated
  formulation/solver for cracking, reinforcement and plasticity. The locked
  PyNite steel pushover and elastic concrete presets do not supply RC plasticity.

### Implementation Gates

- Keep the existing linear-static workflow intact. P-Delta, unilateral and
  pushover results need their own analysis identity and per-combination solves;
  do not use linear superposition for nonlinear results.
- Modal mass must be defined explicitly, not inferred by treating weight density
  as mass density. Do not imply dynamic time-history or response-spectrum support.
- Physical-member handling must preserve user member IDs, load stations,
  assignments and releases while exposing actual solver segmentation. A crossing
  must not silently become a joint; coordinate with the split/connect tasks below.
- Plates, meshes, shear walls and mats are separate validated milestones, not
  extensions of the line-member renderer alone. Nonlinear steel modelling needs
  verified material/section assumptions, not a generic plastic-design claim.

This section owns engine-capability coverage. Existing 3D editing/report tasks
below and the secondary interface wishlist retain their more specific scope.

## Official PyNite Example Adaptations

Requested 2026-10-26. Track the 20 scripts currently listed in the
[official PyNite Examples directory](https://github.com/JWock82/Pynite/tree/main/Examples).
Unchecked items are pending adaptations, including cases where a similar GUI example
already exists. Audit each script against the locked engine and current GUI
before implementation; an upstream example does not establish GUI support.

For each completed adaptation: provide an editable **File > Examples** entry in
the appropriate category, record the upstream source commit/link and applicable
license notices, preserve units/loading/analysis assumptions, document expected
results, and add focused numerical and save/reopen checks. Reuse or update an
existing matching example rather than adding duplicates. Record any deliberate
differences from upstream. New solver work remains on hold; this checklist does
not change the analysis-method priorities above.

**Frames and existing analysis methods — first adaptation candidates:**

- [x] [Simple Beam - Point Load.py](https://github.com/JWock82/Pynite/blob/main/Examples/Simple%20Beam%20-%20Point%20Load.py)
- [x] [Simple Beam - Uniform Load.py](https://github.com/JWock82/Pynite/blob/main/Examples/Simple%20Beam%20-%20Uniform%20Load.py)
- [x] [Simple Beam - Factored Envelope.py](https://github.com/JWock82/Pynite/blob/main/Examples/Simple%20Beam%20-%20Factored%20Envelope.py)

  First batch completed 2026-10-27 from upstream revision
  `e3a0bbd912b6cf13140f01ca0ed3a2ee55069f45`: three editable 2D Frames menu
  entries, original span/properties/cases/factors/load signs, planar adaptation
  notes and MIT notice. Closed-form beam responses, governing envelopes, fresh
  instances, all-unit persistence and native menu loading are covered. See
  [Examples and Appearance](GUIDE.md#examples-and-appearance) for expected values.

- [x] [Moment Frame - Lateral Load.py](https://github.com/JWock82/Pynite/blob/main/Examples/Moment%20Frame%20-%20Lateral%20Load.py)
- [x] [Space Frame - Nodal Loads 1.py](https://github.com/JWock82/Pynite/blob/main/Examples/Space%20Frame%20-%20Nodal%20Loads%201.py)
- [x] [Space Frame - Nodal Loads 2.py](https://github.com/JWock82/Pynite/blob/main/Examples/Space%20Frame%20-%20Nodal%20Loads%202.py)
- [x] [Space Truss - Nodal Load.py](https://github.com/JWock82/Pynite/blob/main/Examples/Space%20Truss%20-%20Nodal%20Load.py)
- [x] [P-Delta Analysis.py](https://github.com/JWock82/Pynite/blob/main/Examples/P-Delta%20Analysis.py)

  Second batch completed 2026-10-27 at the same pinned revision: preserve the
  moment frame's P-Delta method, original IDs/cases/local weights and uplift;
  convert the official column from ft/kip with five explicit segments; convert
  the space truss from m/kN to bilateral axial bars with original EA and IDs.
  Document planar/G, physical-member and released-frame differences. Verify
  pinned upstream frame parity/load resultants, analytical column response and
  refinement, independent truss joint equilibrium, persistence and menu loading.

- [x] Add optional independent shear-modulus material input and the two official
  Space Frame examples. Preserve E = 30000 ksi, G = 10000 ksi and nu = 0.3,
  original IDs/geometry/sections/supports/loads and Combo 1. Default materials
  still derive G; explicit positive finite values are custom frame/truss inputs.
  Include native editing, units/reports/MCP, legacy migration, formats 25/26,
  pinned-source result fixtures, independent 3D stiffness benchmarks, torsion
  sensitivity, save/reopen and categorized native opening. Surface/plate recipe
  materials reject independent G because their formulations derive it internally.

**Springs and unilateral members — audit dependencies; defer missing behaviour:**

- [ ] [Beam on Elastic Foundation.py](https://github.com/JWock82/Pynite/blob/main/Examples/Beam%20on%20Elastic%20Foundation.py)
- [ ] [Braced Frame - Spring Supported.py](https://github.com/JWock82/Pynite/blob/main/Examples/Braced%20Frame%20-%20Spring%20Supported.py)
- [ ] [Braced Frame - Tension Only.py](https://github.com/JWock82/Pynite/blob/main/Examples/Braced%20Frame%20-%20Tension%20Only.py)

**Plates, shells, walls and foundations — gate on validated surface workflows:**

- [x] [Rectangular Plate Bending - Qauds.py](https://github.com/JWock82/Pynite/blob/main/Examples/Rectangular%20Plate%20Bending%20-%20Qauds.py) (upstream filename spelling)
- [ ] [Rectangular Wall - Linear Varying Load.py](https://github.com/JWock82/Pynite/blob/main/Examples/Rectangular%20Wall%20-%20Linear%20Varying%20Load.py)
- [ ] [Shear Wall - Basic.py](https://github.com/JWock82/Pynite/blob/main/Examples/Shear%20Wall%20-%20Basic.py)
- [ ] [Shear Wall - Advanced.py](https://github.com/JWock82/Pynite/blob/main/Examples/Shear%20Wall%20-%20Advanced.py)
- [ ] [Mat Foundation.py](https://github.com/JWock82/Pynite/blob/main/Examples/Mat%20Foundation.py)
- [ ] [Circular Bin with Conical Hopper.py](https://github.com/JWock82/Pynite/blob/main/Examples/Circular%20Bin%20with%20Conical%20Hopper.py)

**Current-capability audit (2026-10-27, all 20 pinned scripts reviewed):**

Nine official adaptations are now available. The rectangular Quad plate opens
through **File > Examples > Plates (Experimental)** or Browse Examples in the
separate editable plate workspace: original 10 × 20 ft dimensions, 1 ft thickness,
1 ft Quad mesh, clamped edges, W pressure +250 psf and factor 1.0. Canonical unit
conversion, 200-element/231-node topology, upstream transverse nodal/reaction/
centre-moment parity, classical reference, persistence and native opening checks
are covered. Existing MIT notice and pinned source revision apply. No solver
features were added. See GUIDE for the plate-only constraint/combination-name
adaptation and the complete dependency table.

Remaining 11 scripts are intentionally unchecked:

- Beam on Elastic Foundation: 24 **compression-only** DY springs; bilateral
  support springs would change lift-off behaviour. Physical-member subdivision
  alone is not the blocker.
- Braced Frame - Spring Supported: tension-only and compression-only axial
  spring elements, including documented gravity-only instability. Bilateral
  nodal springs are not equivalent.
- Braced Frame - Tension Only: tension-only braces/active-set analysis.
- Rectangular Wall - Linear Varying Load: geometry-owned depth-varying pressure
  and shell edge supports; the plate pilot accepts one uniform pressure only.
- Shear Wall - Basic/Advanced: validated in-plane membrane/drilling workflow,
  shell support/load assignment, wall result recovery; Advanced additionally
  needs shear-wall/story/pier/coupling-beam APIs and its stiffness modifiers.
- Mat Foundation: mat API, compression-only soil springs and point load/moment
  assignment to the foundation mesh with openings.
- Circular Bin with Conical Hopper: curved shell assembly/merged interfaces,
  spatially varying pressure and shell supports/results. Its geometry generators
  being available does not establish analysis support.
- Modal Analysis: mass/modal solver and mode results.
- Moment Frame - Pushover / Pushover Analysis: plastic section definitions,
  incremental pushover controls, hinge states and results.

**Additional solver workflows — on hold with the corresponding solver tasks:**

- [ ] [Modal Analysis.py](https://github.com/JWock82/Pynite/blob/main/Examples/Modal%20Analysis.py)
- [ ] [Moment Frame - Pushover.py](https://github.com/JWock82/Pynite/blob/main/Examples/Moment%20Frame%20-%20Pushover.py)
- [ ] [Pushover Analysis.py](https://github.com/JWock82/Pynite/blob/main/Examples/Pushover%20Analysis.py)

## Surface Geometry and Meshing

- [x] Experimental separate rectangular DKMQ plate workspace with geometry-owned
  pressure/boundary assignments, mesh preview/refinement, four unit presets,
  persistence/undo, isolated cancellable solve, contours and nodal CSV; validate
  against Navier deflection, equilibrium, support and plane/sign tests.
- [x] First integration stage: version 19 spatial projects own uncoupled surface
  recipes; all generators render beside frames with face picking, tree/inspector
  edit/delete, visibility, fitting, undo/redo and save/autosave/recovery. Preserve
  recipes through frame-table/MCP edits; expose read-only MCP discovery and block
  manual/live/MCP/direct analysis rather than silently ignoring surfaces.
- [x] Place rectangular surfaces from selected corner nodes/perimeter members or
  detected complete frame levels. Default new slabs to the selected boundary or
  highest valid level, preview with the reference frame, preserve recipe options
  and provide one-step fitting undo without implying structural node coupling.
- [x] Define rectangular Quad shared frame/surface solver-node ownership, merging tolerance,
  compatible member segmentation, adjacent-mesh conformity and remesh/delete
  behaviour; reject incompatible/overlapping interfaces rather than silently join.
- [x] Opt-in rectangular Quad/frame assembly with geometry-owned pressure cases,
  combinations, surface self-weight, existing shared-joint supports, unchanged
  upstream membrane/drilling formulation, nodal results, equilibrium and deformed
  meshes. Add classical plate and symmetric slab/column benchmarks; keep legacy
  geometry-only projects disabled on migration to version 20.
- [x] Refuse all coupled result publication if any combination fails independent
  global force/moment equilibrium; regression-test lateral moment imbalance from
  the locked engine's weak drilling approximation without relaxing tolerances.
- [ ] Add coupled-slab local stress/moment/shear inspection, contours and surface
  edge-support editors; extend independent membrane, drilling, interface and
  mesh-convergence benchmarks before broadening the experimental scope.
- [ ] Add eccentric slab/beam offsets or explicit connectors with tested load
  transfer; current connections require coincident centreline/mid-surface nodes.
- [x] Add surface-aware MCP edit schemas and atomic topology/assignment validation;
  add surface box selection after the geometry ownership rules are established.
  Cover deferred recipe/pressure/case references, one-step undo, invalid-interface
  rollback and a real client building/analyzing two-storey slabs. Box selection
  includes enclosed/crossing faces, holes, additive selection and cancellation.
- [x] Add rectangular openings/control lines with geometry-owned assignments,
  Quad/Rect analysis, origin/options transfer, version 1 plate-file migration,
  basic mesh-quality checks and net-area pressure/reaction regressions.
- [x] Expose all seven concrete PyNite mesh generators and applicable parameters,
  including ring/transition helpers, families, origins, numbering and modifiers;
  add 3D geometry previews, recipes/undo/export and all-axis/option/browser tests.
- [ ] Independently benchmark opening deflection/moment recovery and refinement;
  extend formulation-specific Rect bending/shear benchmarks.
- [ ] Extend the plate pilot to general membrane behaviour, multiple surface load
  cases/combinations, surface self-weight and detailed local result inspection;
  independently benchmark moment/shear recovery before engineering claims.
- [ ] Add annular/curved-shell boundary/load definitions, membrane behaviour,
  normal-pressure orientation, reaction/result inspection and independent shell
  benchmarks before enabling analysis for nonrectangular catalog meshes.

## Modelling and Editing

- [x] Add named node/member groups and global-Y levels as editing metadata:
  native capture/rename/delete/select/isolate/show-all, optional level snapping,
  XZ-plane placement, canonical persistence (23/24), migration, split/delete
  reference maintenance, undo/redo and retained solver/result identity.

- [x] Add 2D node dragging with snapping and undo/redo.
- [x] Add tree/canvas multiple selection, geometry box selection, and atomic
  bulk support/member/load-property editing with one-step undo/redo.
- [x] Add editable node/member/load tables with unit-aware numerical entry,
  row addition/removal, atomic validation, and one-step undo/redo.
- [x] Add member splitting and an explicit connect-at-intersection operation.
- [x] Add atomic equal subdivision of selected 2D/3D frame members with
  assignment/release/load preservation, existing-node reuse and one-step undo.
  Reject axial-only trusses rather than introduce unbraced intermediate joints.
- [x] Add previewed perpendicular node-to-member and member-midpoint connections
  in 2D/3D: explicit shared joints, load-preserving splits, default frame
  properties, existing-node reuse, overlap/crossing checks and one-step undo.
- [x] Detect overlapping members, disconnected components, and unintended
  intermediate-node connections before analysis.
- [x] Add in-plane member end moment releases for hinges and pin-jointed frames.
- [x] Add explicit axial-only truss members, joint-load validation, lumped
  self-weight, mixed frame/truss analysis, and a joint-loaded example.
- [x] Add member-local axial DX and transverse DY end releases, validated release
  combinations, released-end deformation recovery, and editing/report support.
- [x] Add per-member materials with reusable definitions and legacy-file migration.
- [x] Add a unit-aware material library with reference elastic/weight-density
  presets, safe imports, provenance, and custom classification after edits.
- [x] Add per-member sections with reusable definitions and legacy-file migration.
- [x] Add a section library and distinguish custom properties from named sections.
  Searchable offline AISC starter subset, strong/weak-axis assignment, unit-aware
  previews, persisted provenance, and custom classification after property edits.
  Dimensioned native sketches now cover all 15 shapes using sourced actual
  dimensions, strong/weak-axis orientation and nominal/design HSS thicknesses;
  idealized outlines never recalculate solver properties.
- [x] Add configurable global DX, DY, and RZ support degrees of freedom.
- [x] Add global bilateral DX, DY, and RZ support springs with unit-aware
  stiffness entry, reaction/deformation benchmarks, and model persistence.
- [ ] Add imposed support settlements/rotations with explicit units, reaction
  and equilibrium benchmarks. These are model-level imposed displacements in
  the engine, not automatically case-specific loads. On hold with solver work.
- [ ] Add inclined support orientation (separate constrained-coordinate feasibility work).

## Loads and Analysis

- [x] Add angled nodal/member point forces with automatic FX/FY resolution,
  global angle input, component previews, and oriented arrows.
- [x] Extend angled force input to distributed member loads and add local-axis
  load directions with explicit angle/reference conventions.
- [x] Add uniform and varying distributed member loads, including partial spans
  and distribution-preserving member splitting.
- [x] Add load cases and combinations, including results and diagram selectors.
- [x] Add an editing load-case visibility filter and hide/show controls.
- [x] Add retained 2D/3D **Compare Combinations** member curves: solid/dashed
  overlays on shared axes, exact left/right station values and signed governing
  value by absolute magnitude (A wins ties). Both selections use one snapshot
  and method; units, themes and PNG/SVG provenance follow the retained window.
- [x] Add result envelopes across selected combinations: node bounds, exact
  solver member extrema, governing combinations, sampled member curves,
  one-sided station inspection, and snapshot-aware CSV export.
- [x] Include selected-combination envelopes in printable reports: node/member
  summaries, governing combinations, checked case factors, and snapshot identity.
- [x] Add optional self-weight with an explicit load case, per-member weight
  density/area, multiplier, generated load display, and safe legacy migration.
- [x] Add SI/imperial presets with validated dimensional input/output conversion,
  persistent selection, and physical-model preservation for existing projects.
- [x] Add mm/N and ft/kip unit presets alongside the original in/kip and m/kN.
- [x] Add independent mm/cm/m/in/ft and N/kN/lbf/kip choices, derived-unit
  previews, persistent 2D/3D unit keys, undo/redo and result preservation.
- [x] Improve instability messages with affected nodes and degrees of freedom.
- [x] Add scalable sparse mechanism checks/localization beyond 600 free planar
  degrees of freedom: scaled near-zero modes, direct zero-stiffness checks,
  affected joint directions, and no acceptance of incomplete diagnostics.
- [x] Add an analysis progress indicator and cancellation for large models.
  Isolated cancellable solver processes, real phase messages, previous-result
  preservation, stale-reply rejection, and safe close/unsaved-change handling.
- [x] Add opt-in live linear recalculation after completed edits: 750 ms debounce,
  cloned background solves, latest-revision scheduling, cancellation, visible
  pending/failed/current states and nonmodal automatic failure findings.
  Manual Analyze remains the default in each window.

## Results and Presentation

- [x] Group compact desktop toolbar controls for file/view/edit/load/analysis/
  results, with theme-aware icons, tooltips, vertical separators instead of group
  labels, active modes and solved-result gating.
- [x] Add optional All tools/Model/Results workspaces and command-toolbar
  collapse, with draft-preserving dock visibility, unchanged selections/results,
  stable planar view centre/zoom, no spatial camera requests, MCP guards and
  consistent default-layout recovery. Keep All tools as the initial layout.
- [x] Add auto, true-scale, and custom deformed-shape amplification with actual
  maximum sampled displacement shown in the selected project units.
- [x] Add approximate straight deformation preview in 2D/3D: join displaced
  member ends without span sampling when force overlays are off, explicitly label
  nodal peak/Auto scaling, preserve sampled curves, numerical results and reports.
- [x] Add retained static deformation animation for 2D/3D member curves and
  solved surface wireframes: cached geometry, fixed undeformed reference,
  display-only loop timing, play/pause/reset/fraction controls, amplification,
  combination/unit/theme changes and provenance PNG/SVG frame export.
- [x] Add main-canvas 2D/3D model/deformation/member-force views in the resizable
  Results dock, with synchronized combination/scale controls, exact station/side
  probes, canvas click inspection and preserved retained Member Detail snapshots.
- [x] Add signed member colour maps with shared symmetric scales across solved
  combinations, numerical unit/sign legends, dashed negative/solid positive/
  dotted zero strokes, theme support and bounded 3D instanced rendering.
- [x] Add axial-force diagrams for the whole structure and Member Detail.
- [x] Add explicit node-pair storey drift in retained 2D/3D result windows:
  global Y heights, X/Z translation differences, signed ratios, governing
  combinations, independent combination selection and snapshot-aware atomic CSV.
  No rigid-floor assumption, seismic amplification or code pass/fail checks.
- [x] Add interactive value inspection at a chosen distance along a member.
- [x] Improve label placement for dense structures and overlapping diagrams.
  Renderer-aware, member-ID-first placement with leader lines; crowded labels
  are omitted and retried when zoomed/resized, including printed diagrams.
- [x] Add independent 2D Whole Structure controls for node/member IDs, end-value
  labels and sampled extrema alongside existing load/support visibility. Retain
  numerical data, labels at shared end/extreme locations, themes and unit changes.
- [x] Add matching 3D overlay and orthographic-report ID/end-value/sampled-extrema
  choices, retaining rolled local axes, unchanged ribbons/legend/camera and
  independent load/support visibility. Add boolean-validated print choices for
  2D/3D, initialize from the visible controls and record them per report page.
- [x] Add snapshot-aware PNG/SVG plot saving to native 2D whole/member, spatial
  member and envelope plot toolbars. Include visible analysis identity and embedded
  method/combination/units/context, use only the source basename, preserve live
  zoom/probes/layout and retain existing files on failed/cancelled writes.
- [x] Add diagram side/sign display preferences with clear conventions.
  Per-window whole-structure placement/sign controls; analytical tables and CSV
  retain solver signs, and report diagrams explicitly identify display conventions.
- [x] Show supports, springs, releases, and factored manual/self-weight loads
  across the editor, whole-structure results, and report diagrams; selected
  member context includes end supports/releases and combination loads.
  Result/report visibility controls never change analytical results. Envelopes
  retain combination provenance instead of depicting one misleading load state.
- [x] Add result tables for member end forces and extrema.
- [x] Add sortable linked node/displacement/reaction/member-force tables to the
  results dock: two-way geometry/tree selection, lazy member extrema, unit and
  combination refresh, multi-selection and Member Detail activation in 2D/3D.
- [x] Add explicit result snapshot identification in open diagram windows.
- [x] Show global equilibrium totals, residuals and tolerances for planar/spatial
  combinations, including manual and generated self-weight loads; label analysis
  lifecycle states and retained snapshots explicitly in the results dock.
- [x] Link recognized analysis failure and model-check diagnostics to affected
  geometry via a reviewable findings dock; clear findings after engineering edits.
- [x] Add finding-focused zoom and View > Fit Selection (Shift+F) in 2D/3D,
  including load stations/spans and whole surface recipes; preserve snapshot/
  model identity and the spatial viewing direction. Full-model Fit remains available.
- [x] Export reactions, forces, and displacements as CSV and a printable report.
- [x] Extend printable reports with model definitions and selected diagrams.
  Select definitions/result tables/axial/SFD/BMD diagrams; retain snapshot identity,
  unfactored load definitions, unit conversion, and a print-friendly palette.

## Project Quality

Current focus: usability, presentation and reliability; solver expansion is on
hold. Keep the analysis checklist's completed methods and pending scope intact.

- [x] Add a native Help menu with website/F1, Getting Started, searchable current
  keyboard shortcuts, About/version/license information and user-initiated source/
  issue links. Copy version details for support without submitting a report.
- [x] Use File/Edit/View/Tools/Help menu order and add View > Restore Default
  Layout for hidden/floating/moved panels and toolbars. Preserve model/selection,
  result snapshots, undo history and unapplied inspector inputs; verify both themes.

- [x] Add focused smoke/UI/model/engineering/surface/MCP/lifecycle/docs/release
  test groups, individual selectors and an explicit full-suite runner. Enforce
  test-class ownership, deduplicate combined groups, retain unittest discovery
  and keep viewport/docs builds explicit. Record change-based selection policy.

- [x] Route terminal Ctrl+C through normal Qt shutdown, preserving save/cancel
  prompts and modal editors; cover deferred/repeated signals and real-process exit.
- [x] Build a searchable Zensical documentation website with topic navigation,
  first-model tutorial, feature index, logo/screenshots and light/dark appearance.
  Generate detailed pages from the GUIDE/project records to avoid drift; add
  strict build/link checks and PR/build/GitHub Pages deployment workflow.
- [x] Switch the live GitHub Pages site from legacy deployment to GitHub Actions
  and verify the generated manual. Run 40602180800 deployed commit 953dc9a;
  Pages reports workflow/built, and live modelling tools, examples and format-25
  documentation returned HTTP 200 with the expected content (2026-10-27).
- [x] Illustrate Help/About, shortcut search, finding-focused navigation, recent
  history cleanup and the three-storey slab/P-Delta walkthroughs with real app
  screenshots. Add repeatable native captures and check image links on the site.
- [x] Prepare 1.0.0rc1 metadata, consistent desktop/MCP version reporting,
  release notes/checklist, source/wheel audits and isolated installed-wheel smoke scripts.
- [x] Publish the GitHub 1.0.0rc1 prerelease (see README for the published release).
- [x] Add CITATION.md and GitHub-readable CITATION.cff with release/commit
  identification, PyNite solver attribution and DOI archiving deferred to stable 1.0.
  Add Prakhar Sharma's name/ORCID and disclose Codex assistance separately from
  bibliographic authorship.
- [x] Prepare 1.0.0rc2 with an elastic frame/truss and restricted P-Delta stable
  scope, experimental surface/plate labels, full locked/installed-wheel validation,
  base/MCP and uv-tool installation checks, installed-asset viewport QA, hashes
  and PyPI/uv publishing guidance. Refresh the README with current screenshots,
  installation and scope. Keep visible-platform gates below open.
- [x] Publish RC2 to GitHub and PyPI through the configured Trusted Publisher;
  confirmed both public release endpoints on 2026-10-27. Later development
  changes remain outside the immutable RC2 artifacts.
- [x] Prepare an unpublished RC3 consolidation checkpoint: fresh base/MCP and
  uv-tool installs, full locked/installed suites, installed viewport assets,
  reproducible visible macOS checks, source/wheel audits and a draft with hashes.
  Fix the analysis-thread cleanup freeze found during native validation. The owner
  confirmed real macOS file pickers, F5 and Print Results on 2026-10-28; other
  platform/feedback gates remain in RELEASE.md.
- [x] Fix README screenshots/logo and repository-document links for PyPI using
  absolute HTTPS URLs; add uv/pip registry installation commands and record the
  need to check built long-description metadata before future uploads.
- [x] Add a manual GitHub Actions PyPI Trusted Publishing workflow that verifies
  published release assets/hashes against the source tag, then uploads the same
  files through a separate pypi environment job. Owner setup and dispatch remain
  separate from implementation; this does not publish RC2 or certify stable 1.0.
- [ ] Complete platform/manual validation gates in RELEASE.md and collect
  prerelease feedback before promoting to stable 1.0.0. This single item owns
  reproducible macOS installation/rendering/save-open/analysis/export checks and
  Windows installation/visible-workflow validation; record versions and evidence.

- [x] Use uv-managed Python and locked project dependencies without relying on
  Conda or a system interpreter; document setup and normal uv launches.
- [x] Add a File > Examples catalog of editable, validated beam/frame models.
- [x] Group examples into 2D Frames, 3D Frames, Trusses, Slabs and P-Delta; add
  a ready-to-solve three-storey/three-slab gravity model and segmented P-Delta
  column with independent reaction, load-path and analytical displacement checks.
- [x] Add File > Browse Examples with category/text search, native undeformed
  geometry previews, unit-aware loading summaries and explicit-unit reference
  checks. Preview without editing/solving, preserve drafts and use the existing
  current-unit/unsaved-change path for opening; verify empty searches and themes.
- [x] Add Gerber/internal-hinge and three-hinged polygonal-arch examples with
  hand-equilibrium reactions, zero hinge moments, inactive-rotation handling,
  persistence and menu tests. Retain the explicit 2D-to-3D release limitation.
- [x] Add recent projects and per-window atomic autosave/recovery.
- [x] Harden recent history against malformed/duplicate preferences, unavailable
  paths and files disappearing after menu display. Add history-only cleanup,
  refresh on menu opening, clear path labels and bounded menu-action ownership;
  retain project files, recovery snapshots, unsaved work and undo history.
- [x] Expand validation for malformed project files and supported format migrations,
  including safe rejection of future versions.
- [x] Add benchmark tests for multi-storey frames and varied support/load setups.
- [x] Record a successful macOS user smoke test (2026-10-09), with supplied
  diagnostics showing Qt 6.11.2 / Cocoa and a ready WebGL 2.0 viewport using
  ANGLE Metal on Apple M4 Max with platform defaults. macOS version,
  installation steps and individual workflows remain unrecorded.
- [ ] Package standalone desktop releases.
- [x] Add a separate 3D spatial-frame project and offline Three.js viewport,
  keeping the established 2D editor and file format intact.

## Optional MCP Automation

- [x] Add an optional `pynitegui[mcp]` extra (`uv sync --extra mcp` in this repo)
  without adding server dependencies to normal desktop installations.
- [x] Add **Tools > Automation Server** with localhost port/endpoint, explicit
  Start/Stop, connection status, token/configuration copying, permission groups
  and individual tool switches, and a secret-free request/error log. Start off;
  explain missing optional dependencies without installing packages automatically.
- [x] Use the official MCP SDK with Streamable HTTP and a queued Qt command
  bridge to the open model. Require localhost binding, optional token authentication and
  Host/Origin validation. Validate permissions on every call, not only tool listing.
- [x] Expose model/units/results reads and validated, undoable batch edits of
  nodes, members, supports, materials, sections, loads, cases and combinations.
  Changes appear immediately in the open GUI. Identify project sessions and
  check expected revisions so requests cannot overwrite intervening user edits.
- [x] Expose the existing Run analysis workflow, job progress/cancellation and
  snapshot-labelled results. Return structured errors instead of modal dialogs.
- [x] Expose exact entity/support schemas and examples in model reads and a
  read-schema tool, plus an MCP reference resource, so empty models need no guesses.
- [x] Explain specific editor-busy blockers and exclude automation controls,
  read-only inputs and unrelated windows from the unfinished-input guard.
- [x] Add explicit MCP mode while the server runs: lock manual controls and
  shortcuts, permit MCP commands, and unlock on exit, server stop/failure or close.
- [x] Add a remembered Require token checkbox for URL-only localhost connections,
  with authentication changes restricted to stopped listeners and both modes tested.
- [x] Clarify polling/session contracts and result units; expose solved combination
  names in status, optional schema omission and zero-based operation-local errors.
- [x] Test missing-extra startup, lifecycle/port conflicts, permissions/auth,
  Qt-thread dispatch, atomic undo, stale revisions and analysis cancellation.

No arbitrary Python/shell execution or file-management tools; the user opens
and saves projects normally. A separate REST API is not part of the first scope.

## 3D Follow-Ups

- [x] XYZ geometry, work-plane drawing/snapping, coordinate-based node insertion,
  orbit/pan/zoom, orientation presets, selection, and local-axis display.
- [x] Six global rigid restraints and bilateral support springs; member roll,
  per-member material/section assignment, and atomic numerical model tables.
- [x] Global/member-local point forces and moments, partial uniform/varying
  distributed forces, self-weight, cases/combinations and cancellable analysis.
- [x] All six nodal displacements/reactions, biaxial bending, shear and torsion
  member diagrams, true/auto/custom spatial deformation, CSV and numerical reports.
- [x] Editable 3D cantilever and space-frame examples; analytical benchmarks,
  native light/dark rendering, and desktop browser interaction checks.
- [x] Add startup software rendering, a persisted renderer preference and an
  actionable native recovery panel for failed WebGL/graphics contexts.
- [x] Verify and document NVIDIA hardware rendering on Wayland with matched
  EGL/Vulkan drivers, visible geometry, and GPU compositing enabled.
- [x] Apply the verified NVIDIA profile automatically for one NVIDIA display-driving
  GPU on Wayland, preserving software mode, hybrid setups, and explicit overrides.
- [x] Add a clickable signed-axis orientation gizmo, isometric reset, animated
  view changes, keyboard access, and synchronized native orientation selection.
- [x] Restore window controls for GNOME Wayland Vulkan windows without Qt
  decorations, retaining menu access and unsaved-work confirmation.
- [x] Add graphics diagnostics with the observed WebGL renderer/vendor/version
  and Qt window surface, separately labelled startup/saved preferences and
  requested backend overrides; retain unavailable/masked/failure states.
- [x] Whole-structure 3D axial/shear/bending/torsion overlays with shared scaling,
  combination/unit-aware legends, sampled-value labels and PNG view export.
- [x] Whole-structure 3D diagram PDF reports: six local force/moment components,
  selectable isometric/front/top/right projections, shared ordinate scaling,
  rolled axes and one-sided jumps, side/sign and support/load visibility,
  snapshot/unit/combination identity, independent print-friendly rendering,
  native preview/PDF and pagination/image/analytical regressions.
- [x] Spatial combination envelopes and interactive one-sided station inspection:
  all six global node motions/reactions, eight local member components, exact
  solver extrema, governing combinations, sampled curves, snapshot-aware CSV
  and printable numerical envelope summaries.
- [x] 3D bilateral axial-only trusses, joint-load validation, lumped self-weight,
  inactive rotation reporting, mixed frame/truss joints, analytical/mechanism
  benchmarks, type editing, numerical exports and a spatial tripod example.
- [ ] General 3D frame member end releases, with oblique-axis joint-rotation
  handling, released-end motion recovery and independent mechanism benchmarks.
- [x] 3D contained/crossing box selection, additive selection and cancellation;
  atomic bulk material/section/roll, six-DOF restraint/spring and load assignments.
- [x] 3D node dragging behind an explicit Select-mode tool: XY/XZ/YZ plane through
  the original node, frozen perpendicular coordinate, grid snapping, preview
  without stale analytical/load graphics, edge-on feedback, cancellation,
  revision/coordinate validation, collision rejection and single-command undo.
  Native edit/unit/result regressions and desktop gesture/graphics-loss checks.
- [x] Spatial member splitting and explicit XYZ crossing/T-junction/interior-node
  connections, preserving roll/assignments and point/distributed loads, with
  overlap rejection, atomic validation and one-step undo.
- [x] Explicit 2D-to-3D conversion for unreleased frames and axial-only trusses:
  independent unsaved window, optional Z offset, explicit planar/spatial support
  modes, preserved force components/cases/assignments, save/recovery isolation
  and in-plane response benchmarks. Released frames are rejected, never stripped.
- [ ] Extend 2D-to-3D conversion to released frames after general spatial frame
  releases and released-end recovery are independently benchmarked.
- [x] Spatial point/distributed forces by magnitude, global azimuth/elevation,
  XYZ component previews, angled arrows, editable tables and versioned persistence.
- [x] Dedicated global 3D rigid/spring symbols for all six DOFs, unit-aware
  per-DOF hover inspection, node-linked picking and non-analytical visibility.
- [x] Large-model rendering benchmarks and cached analytical sampling: shared
  snapshot/combination-specific read-only samples with a 32 MiB array budget,
  LRU eviction and serialization reset; native redraw/isolation regressions;
  repeatable cold/warm analytical timings and 144/616/1,580-member desktop
  label/geometry, pixel, orbit and graphics-resource checks.
- [x] Batch base frame geometry: two instanced node/member meshes with shared
  shapes/materials and per-instance colours/IDs, plus one grid line batch.
  Retain picking, drawing snaps, dragging, selection, supports, overlays and
  explicit instance-buffer disposal; enforce allocation/draw-call budgets in
  the recorded desktop benchmarks.
- [x] Reduce large-scene label, support and result-overlay rebuild costs with
  bounded text/colour texture reuse and incremental selection/tool updates;
  preserve visibility/picking, local-axis rebuilds and context-loss disposal.
  Hardware refresh comparisons and cache/overlay/budget regressions are recorded
  in GUIDE.md; payload construction and full scene rebuilds remain separate costs.

## Completed Foundation

- [x] Remove the legacy solver, Tkinter UI, notebooks, and experimental tests.
- [x] Qt Widgets application and 2D graphics editor.
- [x] Separate serializable project model and PyNite analysis adapter.
- [x] Member drawing, snapping, selection, and property inspection.
- [x] Node supports, nodal loads, and member point forces/moments.
- [x] Undo/redo and versioned project save/open.
- [x] Background analysis and invalidation of outdated results.
- [x] Reaction/displacement tables and deformed-shape overlay.
- [x] Whole-structure SFD/BMD with member detail plots.
- [x] Correct discontinuity sampling and orientation-independent frame diagrams.
- [x] Persistent light/dark themes with readable widgets, engineering canvas,
  and live result diagrams.
- [x] Focused project, analytical solver, diagram, and Qt interaction tests.
