# PyniteGUI Roadmap

Current scope: a 2D/3D frame and bilateral axial-only truss editor with SI/imperial input and display, per-member materials and
sections, custom global support restraints, global/member-local angled forces, distributed loads,
and named load cases/combinations. This list tracks remaining work;
items are not promises of a particular release date.

See [Secondary roadmap](TODO_SECONDARY.md) for Stabileo-inspired interface ideas
and verified PyNite extensions. This file remains the primary implementation list.

## PyNite Capability Coverage

Audited 2026-10-09 against our application adapters, schemas and documented
workflows, plus the locked **PyniteFEA 3.0.0** source. The
[upstream capability list](https://github.com/JWock82/Pynite#current-capabilities)
describes the engine, not features automatically available in this GUI.
**Done** means usable in our current frame-focused scope; **Partial** identifies
the exact missing part. Summary: **7 done, 2 partial, 9 pending**.

| Engine capability | GUI status | Coverage or remaining task |
| --- | --- | --- |
| Elastic 3D statics | Done | Linear spatial-frame and axial-only truss analysis, six DOFs, rolled frame members, materials/sections and validated results. |
| Frame P-Delta | Pending | Add a separate analysis method, convergence feedback, method-labelled snapshots and second-order benchmarks. |
| Frame modal analysis | Pending | Add an explicit mass source, gravity/unit conversion, frequencies, mode shapes and a separate modal result workflow. |
| Steel-frame pushover | Pending | Add yield/plastic section data, push/control settings, load steps, convergence and capacity-curve results; benchmark supported steel assumptions. |
| Member point/distributed and nodal loading | Done | Nodal/member forces and moments, uniform/linear-varying distributed forces and partial spans in 2D/3D. Distributed member moments are excluded. |
| Cases and factored combinations | Done | Named cases, combination editing, selected-combination results and visible factored loads in 2D/3D. |
| Member shear, moment and deflection output | Done | Member detail curves in 2D/3D; spatial biaxial shear/bending, torsion and deformation; whole-frame force/moment overlays. |
| Physical-member internal joints | Partial | Explicit load-preserving split/connect workflows exist in 2D/3D. Automatic solver-only internal-node handling is not exposed; connections require explicit segments and shared endpoints. |
| Unilateral member behaviour | Pending | Add tension-only/compression-only flags, iterative active-set analysis and activation/mechanism benchmarks; ordinary 2D/3D trusses are not unilateral members. |
| Node-to-node spring elements | Pending | Add separate spring entities, axial stiffness units and bilateral/tension-only/compression-only behaviour; support springs are not spring elements. |
| Bilateral/unilateral support springs | Partial | Bilateral global DX/DY/RZ springs in 2D and all six DOFs in 3D are implemented. One-way support springs and iterative activation remain pending. |
| DKMQ quadrilaterals | Pending | Add shell geometry/thickness/material input, surface loads, connectivity checks and plate-result visualization with independent benchmarks. |
| Polynomial rectangles | Pending | Expose the separate rectangular plate formulation with geometry/orientation checks and formulation-specific tests. |
| Shape/opening meshing | Pending | Add supported mesh generators, opening definitions, preview/regeneration and convergence checks; preserve references and loads explicitly. |
| Support reactions | Done | Unit-aware reaction tables, CSV and printable output; all six components for spatial frames, including bilateral support springs. |
| Geometry/load/deformation rendering | Done | Current 2D/3D frame geometry, supports, case-filtered loads, factored combinations and scaled deformed shapes; no plate/mesh renderer yet. |
| Shear walls and mats | Pending | Add dedicated wall/foundation definitions, meshing, openings, soil/support input and specialized results; verify the locked engine before exposing workflows. |
| Model/result PDF output | Done | Native printable model definitions/results with save-to-PDF; 2D diagrams and numerical envelopes; 3D six-component diagrams with selectable orthographic views and numerical envelopes. |

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

## Modelling and Editing

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
- [ ] Expand the section library with additional regional catalogs and sizes.
- [x] Add configurable global DX, DY, and RZ support degrees of freedom.
- [x] Add global bilateral DX, DY, and RZ support springs with unit-aware
  stiffness entry, reaction/deformation benchmarks, and model persistence.
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
  results, with theme-aware icons, tooltips, active modes and solved-result gating.
- [x] Add auto, true-scale, and custom deformed-shape amplification with actual
  maximum sampled displacement shown in the selected project units.
- [x] Add axial-force diagrams for the whole structure and Member Detail.
- [x] Add interactive value inspection at a chosen distance along a member.
- [x] Improve label placement for dense structures and overlapping diagrams.
  Renderer-aware, member-ID-first placement with leader lines; crowded labels
  are omitted and retried when zoomed/resized, including printed diagrams.
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
- [x] Export reactions, forces, and displacements as CSV and a printable report.
- [x] Extend printable reports with model definitions and selected diagrams.
  Select definitions/result tables/axial/SFD/BMD diagrams; retain snapshot identity,
  unfactored load definitions, unit conversion, and a print-friendly palette.

## Project Quality

- [ ] Low priority: build a searchable documentation website on GitHub Pages,
  splitting and polishing GUIDE.md into repository-maintained pages rather than
  maintaining duplicate content. Cover installation/examples, modeling, analysis
  and limitations, 3D graphics troubleshooting, MCP and reference/release notes;
  include screenshots, light/dark themes and automatic documentation deployment.
- [x] Prepare 1.0.0rc1 metadata, consistent desktop/MCP version reporting,
  release notes/checklist, source/wheel audits and isolated installed-wheel smoke scripts.
- [ ] Publish the approved GitHub 1.0.0rc1 prerelease after completing the
  platform/manual validation gates in RELEASE.md; promote to 1.0.0 only after feedback.

- [x] Use uv-managed Python and locked project dependencies without relying on
  Conda or a system interpreter; document setup and normal uv launches.
- [x] Add a File > Examples catalog of editable, validated beam/frame models.
- [x] Add recent projects and per-window atomic autosave/recovery.
- [x] Expand validation for malformed project files and supported format migrations,
  including safe rejection of future versions.
- [x] Add benchmark tests for multi-storey frames and varied support/load setups.
- [x] Record a successful macOS user smoke test (2026-10-09), with supplied
  diagnostics showing Qt 6.11.2 / Cocoa and a ready WebGL 2.0 viewport using
  ANGLE Metal on Apple M4 Max with platform defaults. macOS version,
  installation steps and individual workflows remain unrecorded.
- [ ] Run and document a reproducible macOS installation/rendering/regression
  check, including save/open, analysis, selection and exports.
- [ ] Test installation and desktop rendering on Windows.
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
- [ ] Optionally add viewport screenshot capture after the core workflow.
  No arbitrary Python/shell execution or file-management tools; the user opens
  and saves projects normally. A separate REST API is not part of the first scope.
- [x] Test missing-extra startup, lifecycle/port conflicts, permissions/auth,
  Qt-thread dispatch, atomic undo, stale revisions and analysis cancellation.

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
- [ ] Implement the pending solver milestones in **PyNite Capability Coverage**
  above; keep plates/meshes and nonlinear methods independently benchmarked.

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
