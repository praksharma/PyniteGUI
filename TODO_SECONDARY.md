# Secondary Roadmap: Stabileo-Inspired Ideas

Scope reduced 2026-10-27. This is a focused UI/modelling backlog, not a list of
features to copy from another product. [TODO.md](TODO.md) owns engineering
capabilities, completed implementation records, official examples and release
validation. New solver work remains on hold.

Historical inspiration: [Stabileo](https://github.com/lambdaclass/stabileo) and
its [Basic](https://stabileo.com/app/basic) and [PRO](https://stabileo.com/app/pro)
editors, reviewed 2026-10-03. Those observations do not establish PyNite or GUI
support. The installed/pinned engine and independent benchmarks remain the
basis for engineering features.

## Result Reading

- [x] **In-canvas results.** Switch the main model view between model,
  deformation, axial, shear and moment without opening another window. Reuse
  the results dock for combination, scale and station inspection. Preserve
  retained Member Detail windows and their snapshot identity. Completed in the
  resizable Results dock for 2D/3D, with synchronized existing 3D controls,
  exact left/right probes, click-to-station inspection and current analysis status.
- [x] **Signed result colour maps.** Offer a colour-map alternative to offset
  diagrams using existing member samples. Include numerical units, a legend,
  zero/sign distinction and consistent comparison scales; colour alone must
  not communicate sign. Completed for member forces/moments using a symmetric
  scale shared across all combinations in the same snapshot, numerical legends,
  negative dashed/positive solid/zero dotted strokes and theme-aware colours.
  Surface stress maps remain outside this member-result task.
- [ ] **Scoped result queries.** Filter by member ID, current selection or all
  members (and named groups once available), then minimum, maximum, absolute
  extreme or a unit-aware threshold. Include interior extrema/discontinuities,
  locate the governing member/station and export snapshot-labelled results.
  Extend the linked tables/envelopes rather than adding another parallel system.

## Larger-Model Editing

- [x] **Named groups and levels.** Save node/member selection sets for frames,
  storeys or zones; reselect/isolate them and define explicit Y-elevation levels
  with optional snapping. These are editing metadata, not diaphragms or solver
  constraints. Keep references valid after splitting or deleting entities.
  Completed with native select/isolate/show-all controls, persisted global-Y
  elevations, optional drawing/drag snapping, 3D XZ-plane placement, unit-aware
  input, undo/redo and preserved analysis snapshots. New project formats 23/24.
- [ ] **Previewed transforms.** Repeat, mirror, rotate or move selected geometry
  about explicit points or bay/storey offsets. Preview before applying; provide
  separate load/support-copy choices and resolve collisions explicitly. Preserve
  global/local load meaning, stations, releases and IDs in one undo transaction.
- [ ] **Planar beam/frame generators.** Generate continuous beams and multi-bay,
  multi-storey frames from explicit spacing lists, beam/column sections,
  materials, base supports and insertion point. Preview counts, dimensions and
  assumptions before adding ordinary validated nodes/members/loads. No automatic
  sizing or code design.
- [ ] **Previewed topology fixes.** Extend existing findings/select/zoom and
  split/connect tools with reviewable fixes, starting with controlled node
  merging. Rewrite every affected reference and resolve support/load conflicts
  explicitly. Never silently remove a loaded/supported joint or connect a crossing.

## Already Delivered

Implementation details and completion ticks remain in the primary roadmap:

- Compact grouped toolbars, Model/Results workspaces and command-strip collapse.
- Linked result tables, comparison curves, envelopes and exact station probes.
- 2D/3D readability controls and snapshot image/report exports.
- Numerical tables, bulk assignment and opt-in live linear recalculation.
- Dimensional section previews and searchable categorized examples.
- Plain node-pair storey drift, fast deformation preview and static animation.
- Linear/P-Delta frames, bilateral trusses/support springs and spatial viewing,
  within the limits recorded in the [capability audit](TODO.md#pynite-capability-coverage).

## Scope Boundaries

Unrequested exploration workspaces, spreadsheet-template import, reusable model
piece libraries, tapered-member generators and educational stiffness-matrix
inspection have been removed from planned scope. They are not completed features.
Solver duplicates have been consolidated into the primary roadmap rather than
tracked a second time here.

Keep the native desktop workflow. This shortlist does not add a Design tab,
code checks, automatic wind/seismic loads, web accounts/hosting, arbitrary CAD
inference or unverified solver capabilities. Retain existing validation gates;
removing speculative tasks does not remove engineering limitations.
