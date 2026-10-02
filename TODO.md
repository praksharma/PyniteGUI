# PyniteGUI Roadmap

Current scope: a 2D frame editor using inch/kip units, per-member materials and
sections, distributed loads, and named load cases/combinations. This list tracks remaining work;
items are not promises of a particular release date.

## Modelling and Editing

- [ ] Add node dragging with snapping and undo/redo.
- [ ] Add multiple selection and bulk property editing.
- [ ] Add editable node/member/load tables for precise numerical entry.
- [x] Add member splitting and an explicit connect-at-intersection operation.
- [x] Detect overlapping members, disconnected components, and unintended
  intermediate-node connections before analysis.
- [x] Add in-plane member end moment releases for hinges and pin-jointed frames.
- [ ] Add explicit axial-only truss elements and additional release degrees of freedom.
- [x] Add per-member materials with reusable definitions and legacy-file migration.
- [x] Add per-member sections with reusable definitions and legacy-file migration.
- [ ] Add a section library and distinguish custom properties from named sections.
- [ ] Add configurable support degrees of freedom and support orientation.

## Loads and Analysis

- [x] Add uniform and varying distributed member loads, including partial spans
  and distribution-preserving member splitting.
- [x] Add load cases and combinations, including results and diagram selectors.
- [ ] Add an editing load-case visibility filter and hide/show controls.
- [ ] Add result envelopes across selected combinations.
- [ ] Add optional self-weight with an explicit load case.
- [ ] Add SI units and validated conversion of existing project data.
- [ ] Improve instability messages with affected nodes and degrees of freedom.
- [ ] Add an analysis progress indicator and cancellation for large models.

## Results and Presentation

- [x] Add axial-force diagrams for the whole structure and Member Detail.
- [ ] Add interactive value inspection at a chosen distance along a member.
- [ ] Improve label placement for dense structures and overlapping diagrams.
- [ ] Add diagram side/sign display preferences with clear conventions.
- [ ] Show supports and load annotations consistently across result views.
- [ ] Add result tables for member end forces and extrema.
- [ ] Add explicit result snapshot identification in open diagram windows.
- [ ] Export reactions, forces, and displacements as CSV and a printable report.

## Project Quality

- [ ] Add recent projects and autosave/recovery.
- [ ] Expand validation for malformed project files and future format migrations.
- [ ] Add benchmark tests for multi-storey frames and varied support/load setups.
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
- [x] Consistent light theme with readable labels and inputs.
- [x] Focused project, analytical solver, diagram, and Qt interaction tests.
