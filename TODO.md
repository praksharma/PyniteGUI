# PyniteGUI Roadmap

Current scope: a 2D frame editor with SI/imperial input and display, per-member materials and
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
- [ ] Add explicit axial-only truss elements and additional release degrees of freedom.
- [x] Add per-member materials with reusable definitions and legacy-file migration.
- [x] Add a unit-aware material library with reference elastic/weight-density
  presets, safe imports, provenance, and custom classification after edits.
- [x] Add per-member sections with reusable definitions and legacy-file migration.
- [x] Add a section library and distinguish custom properties from named sections.
  Searchable offline AISC starter subset, strong/weak-axis assignment, unit-aware
  previews, persisted provenance, and custom classification after property edits.
- [ ] Expand the section library with additional regional catalogs and sizes.
- [x] Add configurable global DX, DY, and RZ support degrees of freedom.
- [ ] Add inclined support orientation and elastic support springs.

## Loads and Analysis

- [x] Add angled nodal/member point forces with automatic FX/FY resolution,
  global angle input, component previews, and oriented arrows.
- [x] Extend angled force input to distributed member loads and add local-axis
  load directions with explicit angle/reference conventions.
- [x] Add uniform and varying distributed member loads, including partial spans
  and distribution-preserving member splitting.
- [x] Add load cases and combinations, including results and diagram selectors.
- [x] Add an editing load-case visibility filter and hide/show controls.
- [ ] Add result envelopes across selected combinations.
- [x] Add optional self-weight with an explicit load case, per-member weight
  density/area, multiplier, generated load display, and safe legacy migration.
- [x] Add SI/imperial presets with validated dimensional input/output conversion,
  persistent selection, and physical-model preservation for existing projects.
- [x] Add mm/N and ft/kip unit presets alongside the original in/kip and m/kN.
- [ ] Add custom length/force unit choices.
- [x] Improve instability messages with affected nodes and degrees of freedom.
- [ ] Add scalable sparse mechanism checks/localization beyond 600 free planar
  degrees of freedom.
- [ ] Add an analysis progress indicator and cancellation for large models.

## Results and Presentation

- [x] Add auto, true-scale, and custom deformed-shape amplification with actual
  maximum sampled displacement shown in the selected project units.
- [x] Add axial-force diagrams for the whole structure and Member Detail.
- [x] Add interactive value inspection at a chosen distance along a member.
- [ ] Improve label placement for dense structures and overlapping diagrams.
- [ ] Add diagram side/sign display preferences with clear conventions.
- [ ] Show supports and load annotations consistently across result views.
- [x] Add result tables for member end forces and extrema.
- [x] Add explicit result snapshot identification in open diagram windows.
- [x] Export reactions, forces, and displacements as CSV and a printable report.
- [ ] Extend printable reports with model definitions and selected diagrams.

## Project Quality

- [x] Add a File > Examples catalog of editable, validated beam/frame models.
- [x] Add recent projects and per-window atomic autosave/recovery.
- [x] Expand validation for malformed project files and supported format migrations,
  including safe rejection of future versions.
- [x] Add benchmark tests for multi-storey frames and varied support/load setups.
- [ ] Test installation and desktop rendering on Windows and macOS.
- [ ] Package standalone desktop releases.
- [ ] Evaluate 3D modelling and its viewport separately after the 2D workflow matures.

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
