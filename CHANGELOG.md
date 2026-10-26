# Changelog

## Unreleased

- Illustrated Help, shortcuts, model findings, recent history and slab/P-Delta
  walkthroughs with real desktop/viewport screenshots. Adds a disposable-example
  native capture script and repository-to-site image-link rebasing with docs checks.

- Finding-focused zoom and View > Fit Selection (Shift+F) frame nodes, members,
  load points/spans and whole surfaces in 2D/3D. Preserve model/results and spatial
  viewing direction, reveal referenced load/surface graphics and retain full-model
  Fit. Pending viewport focus is discarded after model/session changes. Adds
  native and real-viewport framing, orientation and resource regressions.
- Recent history refreshes on File-menu opening, marks unavailable files and
  offers explicit remove-unavailable/clear-history actions without deleting files
  or touching unsaved work/recovery. Ignores malformed/duplicate preferences and
  disposes old menu actions during refresh. Corrects stale secondary-roadmap ticks
  for existing numerical tables/bulk assignments and combination envelopes.

- Native Help menu with documentation/F1 and Getting Started links, a searchable
  reference generated from current keyboard shortcuts, About/version/license
  information, source/issue links and copyable support version details. Dialogs
  are reusable and work in both themes. Restores conventional File/Edit/View/
  Tools/Help menu order and adds View > Restore Default Layout for misplaced
  panels/toolbars while preserving engineering work and unapplied Properties
  inputs. Solver expansion is on hold while usability/quality work takes priority.

- Categorized Examples submenus for 2D Frames, 3D Frames, Trusses, Slabs and
  P-Delta, retaining stable example identifiers. Adds a three-storey steel frame
  with three coupled elastic concrete slabs, Dead/Live pressures and independent
  load-path/reaction checks, plus a segmented P-Delta column demonstrating
  gravity-induced lateral amplification. Both open ready to analyze, preserve
  display units, save normally and prompt before replacing unsaved work.

- Saved, undoable Linear elastic/P-Delta elastic selection for 2D/3D frame-only
  analysis, shared by native/manual/live/MCP workflows. Solves combinations
  independently, checks actual effective stiffness against instability and labels
  snapshots, diagrams, CSV and printable results with the solved method. Planar
  format 21/spatial 22 retain the choice; older files remain linear. Adds analytical
  compression/tension, mesh refinement, biaxial bending, support-spring, release,
  buckling-rejection and worker/MCP regressions. P-Delta omits the inapplicable
  undeformed moment-balance check while retaining strict force residuals. This
  keeps materials elastic; steel pushover and reinforced-concrete plasticity
  remain explicitly separate pending work.

- Focused test groups and a standard-library runner: smoke/UI/model/engineering/
  surface/MCP/lifecycle/docs/release/tooling selection, dotted test selectors,
  deduplication and strict class ownership. Full Python, viewport and strict docs
  checks remain explicit; ordinary UI changes can use focused verification.

- Surface-aware MCP batches edit all recipe generators, pressure maps and the
  coupled-analysis opt-in with deferred assignment validation, production
  interface/conformity checks and one-step undo. Invalid candidates retain results
  and model history. Adds two-storey/two-slab load-path, combination, refinement,
  self-weight and official-client regressions.
- Main 3D box selection includes whole surface recipes: enclosed/crossing faces,
  empty openings, additive selection and cancellation, synchronized with the tree.

- Opt-in experimental rectangular Quad slab/frame analysis: coincident six-DOF
  solver nodes, physical-member subdivision, explicit conformity/overlap and
  connectivity checks, pressure cases/combinations, slab self-weight and global
  equilibrium. Rejects results if any combination fails independent balance,
  including lateral moment imbalance from the engine's drilling approximation.
  Adds pressure controls, deformed meshes, generated-node results,
  report context and a coupled example. Spatial format 20 migrates older files
  with coupling disabled. Curved/Rect main-model analysis, stress contours and
  surface edge-support editors remain pending.
- Terminal Ctrl+C now requests normal Qt shutdown instead of repeatedly raising
  KeyboardInterrupt inside timer callbacks. Preserves save/cancel prompts,
  open modal editors and existing analysis/server cleanup.
- Searchable Zensical documentation site with the project logo/screenshots,
  light/dark appearance, first-model tutorial and complete feature index. Builds
  topic pages from the maintained GUIDE and project records; includes strict
  link/anchor checks, an optional docs-only dependency group and GitHub Pages CI.
- Easier slab placement: fit rectangles to selected frame corners/perimeters or
  detected complete horizontal levels, with frame-context preview and fitting
  undo. New rectangles default to a valid selection or the highest level;
  existing surfaces move only on explicit fit. This is geometric alignment,
  not shared-node connectivity or coupled analysis.
- Spatial project version 19 owns surface-mesh recipes alongside frames. Adds
  native insertion/editing, main Three.js rendering/face picking, visibility,
  fitting, tree/inspector selection and deletion with undo, persistence and
  autosave/recovery. Surface nodes remain independent from frame joints.
  Manual/live/MCP/direct analysis is guarded against silently ignoring surfaces;
  MCP reads retain recipes; explicit opt-in gates experimental coupled analysis.
- Main toolbar groups use icons with tooltips and vertical separators, without
  repeated File/View/Edit/Loads/Analysis/Results labels; the menu bar is unchanged.
- PyNite surface-mesh catalog: Rectangle, Annulus, Annular Ring, Annular Transition
  Ring, Cylinder, Cylinder Ring and Conical Frustum. Exposes applicable families,
  controls/openings, placement, counts, material/modifiers and numbering; provides
  bounded validation, offline Three.js preview, recipe persistence/undo and neutral
  connectivity export. Curved/annular analysis is not yet enabled.
- Rectangular plate analysis now accepts Quad/Rect families, openings, control
  lines and origin/options from the mesh catalog; old plate files migrate to the
  new schema. Retains pressure/support ownership and net-area equilibrium checks.
- Experimental separate rectangular DKMQ transverse-plate workspace under Tools:
  PyNite mesh preview, geometry-owned pressure/edge supports, unit-aware input,
  separate plate files, undo/redo and cancellable analysis. Includes displacement
  and centre moment/shear contours, nodal CSV and Navier refinement regressions.
  This is not general membrane/shell or mixed frame/surface modelling; see GUIDE.md.

## 1.0.0rc1 - Release Candidate

First release candidate for the frame-focused desktop application, published as
a GitHub prerelease. Promote to 1.0.0 only after the release checklist is completed.

- Qt desktop editing for 2D/3D elastic frames and bilateral axial-only trusses.
- Materials/sections and starter libraries, support restraints/springs, 2D end
  releases, angled/point/distributed loads, self-weight, cases and combinations.
- Undo/redo, model tables, split/connect workflows, autosave/recovery and examples.
- Four unit presets, light/dark themes, cancellable analysis and snapshot-aware results.
- Member and whole-frame diagrams, envelopes, inspection, CSV and printable reports.
- Offline Three.js 3D viewport, orientation gizmo, explicit work-plane drawing
  and node dragging, batched base geometry and bounded analytical sampling.
- Optional localhost MCP server: schema discovery, permission-controlled atomic
  edits, session/revision guards, analysis status/cancellation and exclusive MCP mode.
- Release metadata, version reporting, distribution checks and installed-package smoke tests.
- MCP input filtering is installed only during exclusive control mode, avoiding
  inactive per-window global event-filter overhead during normal editing/testing.

### Scope and Limitations

Linear elastic frame/truss statics only. General 3D frame end releases, inclined
supports, unilateral elements/springs, P-Delta, modal/pushover analysis and plate,
mesh, wall/foundation workflows are not exposed. MCP viewport capture is pending.
Libraries are starter/reference data, not comprehensive design-code catalogs.
No structural design-code checks or certification are implied; independently
verify models, units, stability and engineering results before relying on them.

Python 3.12+ and compatible Qt/scientific dependencies are required. Wheels are
Python packages, not standalone installers. NVIDIA/Wayland graphics may require
the documented hardware profile or software rendering. The current release
validation record and platform gaps are maintained in RELEASE.md.
