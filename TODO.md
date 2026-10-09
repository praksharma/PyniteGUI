# PyniteGUI Roadmap

Current scope: a 2D frame/truss and linear 3D spatial-frame editor with SI/imperial input and display, per-member materials and
sections, custom global support restraints, global/member-local angled forces, distributed loads,
and named load cases/combinations. This list tracks remaining work;
items are not promises of a particular release date.

See [Secondary roadmap](TODO_SECONDARY.md) for Stabileo-inspired interface ideas
and verified PyNite extensions. This file remains the primary implementation list.

## Modelling and Editing

- [x] Add node dragging with snapping and undo/redo.
- [x] Add tree/canvas multiple selection, geometry box selection, and atomic
  bulk support/member/load-property editing with one-step undo/redo.
- [x] Add editable node/member/load tables with unit-aware numerical entry,
  row addition/removal, atomic validation, and one-step undo/redo.
- [x] Add member splitting and an explicit connect-at-intersection operation.
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
- [ ] Add custom length/force unit choices.
- [x] Improve instability messages with affected nodes and degrees of freedom.
- [x] Add scalable sparse mechanism checks/localization beyond 600 free planar
  degrees of freedom: scaled near-zero modes, direct zero-stiffness checks,
  affected joint directions, and no acceptance of incomplete diagnostics.
- [x] Add an analysis progress indicator and cancellation for large models.
  Isolated cancellable solver processes, real phase messages, previous-result
  preservation, stale-reply rejection, and safe close/unsaved-change handling.

## Results and Presentation

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
- [x] Add explicit result snapshot identification in open diagram windows.
- [x] Export reactions, forces, and displacements as CSV and a printable report.
- [x] Extend printable reports with model definitions and selected diagrams.
  Select definitions/result tables/axial/SFD/BMD diagrams; retain snapshot identity,
  unfactored load definitions, unit conversion, and a print-friendly palette.

## Project Quality

- [x] Use uv-managed Python and locked project dependencies without relying on
  Conda or a system interpreter; document setup and normal uv launches.
- [x] Add a File > Examples catalog of editable, validated beam/frame models.
- [x] Add recent projects and per-window atomic autosave/recovery.
- [x] Expand validation for malformed project files and supported format migrations,
  including safe rejection of future versions.
- [x] Add benchmark tests for multi-storey frames and varied support/load setups.
- [ ] Test installation and desktop rendering on Windows and macOS.
- [ ] Package standalone desktop releases.
- [x] Add a separate 3D spatial-frame project and offline Three.js viewport,
  keeping the established 2D editor and file format intact.

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
- [ ] Display the actual viewport GPU/driver/backend in graphics diagnostics,
  distinguishing selected preferences from the renderer Qt actually uses.
- [ ] Whole-structure 3D axial/shear/bending/torsion overlays and image reports.
- [ ] Spatial combination envelopes and interactive one-sided station inspection.
- [ ] 3D member end releases and axial-only trusses, with mechanism benchmarks.
- [ ] 3D node dragging, box selection, and bulk inspector assignments.
- [ ] Spatial member splitting and explicit intersection connection workflows.
- [ ] Explicit 2D-to-3D conversion with preserved loads/support conventions.
- [ ] Spatial force-by-magnitude/azimuth/elevation entry and coordinate previews.
- [ ] Dedicated 3D support/spring symbols with per-DOF hover inspection.
- [ ] Large-model rendering benchmarks and cached analytical sampling.
- [ ] Plate/shell modelling, mesh workflows, and nonlinear analysis as separate,
  verified PyNite-supported milestones; no solids or design-code claims.

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
