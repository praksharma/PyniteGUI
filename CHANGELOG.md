# Changelog

## Unreleased

- Add a separate native/MCP first-order Steel Pushover workflow with explicit
  material fy and section Zy/Zz/material binding, elastic preload and nodal push,
  bounded step/retry/control limits, physically checked accepted histories,
  signed capacity and end-yield plots, tables and CSV/PNG/SVG/JSON exports.
  Keep partial prefixes explicit and reject stale/cancelled results. Verify
  plastic redistribution, mechanism limits, yield overshoot, interior interaction,
  weak-axis bending, pattern factors and refinement against independent mechanics.
  Add three editable hand-check examples. Save planar v33/spatial v40, with
  legacy elastic defaults. Combined P-Delta/plastic and RC/surface plasticity remain
  pending; the two official second-order pushover examples are not claimed.


- Add a separate native/MCP Vibration Modes workflow for unreleased bilateral
  elastic frames. Use explicit weight combinations/directions/gravity, verified
  consistent mass and finite eigenmodes without artificial inertia. Add frequency,
  period, mode-shape and mass-source tables/plots, snapshot-aware CSV/PNG/SVG/JSON,
  isolated jobs/cancellation, stale-result rejection and the official modal column.
  Verify independent continuum, tip, torsion, orientation and sparse-chain references
  plus pinned upstream frequency/shape parity. Static results remain separate.

- Add Iterative elastic with tension/compression-only axial trusses and one-way
  global support springs, activation/reactivation, independent combinations,
  prescribed motions and configurable load steps/tolerances. Reject convergence,
  stability and equilibrium failures. Add staged editing, snapshot activity and
  iteration histories, unit-aware CSV/print/MCP, inactive-bar rendering and three
  official examples with pinned upstream parity and independent mechanics checks.
  Save planar v31/spatial v38; migrate legacy definitions to bilateral defaults.
  The user lifted the new-solver hold on 2026-10-31; steel pushover was subsequently added as a separate bounded workflow.

- Enable imposed rigid-support movements within existing 2D/3D frame-only P-Delta
  analysis after independent continuum/energy checks. Preserve the same motion
  in every combination, including zero loads and shortening-induced preload;
  retain full geometric updates, free-equation/stability rejection and existing
  entity restrictions. Add a base-motion column example, native worker/undo/unit
  and MCP wire coverage. File formats and the solver-method hold are unchanged.

- Add a test-only Quad transverse-shear feasibility study with independent Navier
  and two-direction cantilever references, separate/coupled solves, refinement,
  all planes and signed/zero combinations. Compare raw shear, own-element moment
  derivatives and a complete neighbouring-centre moment fit; document convergent
  interior recovery and remaining boundary/interface gaps. Quad shear remains
  disabled in application results, exports and MCP; production code is unchanged.

- Add model-level support settlements/rotations and inclined-normal movements to
  existing linear workflows. Keep prescriptions unchanged across every combination,
  including zero loads; preserve zero spring rest positions and reject incompatible
  constraints. Add staged native/table/bulk editing, support copying/conversion,
  reports, explicit-unit MCP metadata, a beam example and independent mechanics/
  worker/wire checks. Save planar v29/spatial v36 with zero-motion legacy migration.
  Nonzero imposed movements remain excluded from P-Delta pending validation.

- Add inclined rollers across 2D/3D linear frames, trusses and supported releases,
  with global tangent angles in 2D and normal azimuth/elevation plus optional
  global restraints in 3D. Use sparse exact constraints, physical member recovery,
  separate rigid/spring reactions and stability/equilibrium rejection. Extend
  staged native editing, oriented symbols/reports, MCP six-DOF reactions, support
  copying and 2D-to-3D conversion. Add planar and spatial examples; save planar
  v27/spatial v34 with strict legacy migration. Existing frame P-Delta supports
  inclined constraints with geometric-stiffness convergence; its global truss,
  surface and release restrictions remain. Settlements, unilateral behaviour
  and plastic connections remain separate tasks. Retain independent beam,
  compliance, release/truss, shared-shell and second-order reference checks;
  the earlier test-only feasibility report remains reproducible separately.
- Add independent nonuniform flat-membrane traction benchmarks for pure in-plane
  bending and mixed normal/shear stress. Verify displacement/stress convergence,
  strain energy, exact load resultants and signed/zero combinations in every
  plane, with a reproducible numerical report and convergence figure. Separate
  continuum spin from nodal drilling; general wall/diaphragm and rotational
  frame–shell interfaces remain unvalidated. No production solver or UI changes.
- Add local DX/DY/DZ spatial frame end releases with recovered member-side motion,
  separate joint results, unstable-release/mechanism rejection and local/whole-model
  equilibrium checks. Add staged inspector/table/bulk/MCP editing, member reports,
  paginated MCP motion metadata and a fixed-guided sliding-beam example. Spatial
  files advance to v32; older files keep connected translations. Extend 2D-to-3D
  conversion to planar axial/shear releases. Linear frame-only; released P-Delta,
  frame/surface coupling and nonlinear connections remain unavailable.
- Extend standalone development packaging to native Windows portable ZIP and
  Linux tar.gz builds, retaining macOS app bundles. Check archive hashes before
  relocated frozen execution, record host/architecture and Linux libc, retain
  corresponding source/notices, and build on all three native Actions runners.
  Public installers, signing and broader platform coverage remain separate gates.
- Add a macOS development app-bundle recipe with locked runtime verification,
  pinned separate build tools, corresponding-source/notices, dependency identity,
  a native icon and symlink-preserving ZIP/checksums. Verify a relocated frozen
  executable through examples, spawned frame/plate workers, offline WebEngine,
  PNG/PDF and authenticated MCP. Add a manual artifact-only Actions workflow;
  signing/notarization remain separate pending gates.
- Fix a reproducible native macOS WebEngine/MCP handover crash in both Qt 6.11
  and 6.12: replace application-wide Python input filtering with filters on the
  editor's known widgets/actions, retaining manual-control and shortcut locks.
  Refresh the bounded set after model edits and remove it on unlock.

- Add local RX/RY/RZ end releases to linear, frame-only spatial analysis, with
  staged inspector/table/bulk/MCP editing, viewport labels and recovered member-
  end bending rotations. Handle oblique unused joint rotations through verified
  coordinate gauges; reject unresisted moments and real connection mechanisms.
  Check every free physical equation and whole-model equilibrium before accepting
  results. Undefined nodal rotation components remain n/a; MCP explains their
  global directional basis. Spatial files advance to v30 with strict migration.
- Add an oblique, rolled, biaxially loaded released-beam example. Permit explicit
  2D-to-3D conversion of rotationally released frames, including Gerber and arch
  examples. Spatial translations, releases at both torsion ends, released P-Delta
  frames and released frame/surface coupling remain rejected.

- Add local bending inspection to the separate plate workspace: click a material
  element or open Inspect Results, choose xi/eta, read signed moments (plus
  corrected Rect shear), inspect the element-centre table and export centre or
  probe CSV with units/axes/combination/snapshot provenance. Link an outline and
  probe marker to the plot; ignore opening holes and pan/zoom gestures. Units
  and combination changes retain selection; engineering edits clear stale data.
- Retain compact per-combination recovery data in the isolated plate worker's
  accepted snapshot, enabling off-centre probes without retaining a solver or
  running analysis again. Quad moments preserve the engine's within-element
  bilinear recovery; Quad shear, general membrane and combined face stresses
  remain unavailable. Plate files and engineering input schemas are unchanged.

- Independently validate solved uniform-traction membrane fields in all planes,
  including signed/zero combinations and refinement. Add coincident beam/slab
  strip pressure/member-load transfer benchmarks against a narrow-strip EI-sum
  reference for three stiffness ratios. Report weak drilling moment residuals
  under refinement while retaining all existing production rejection limits.
- Correct coupled YZ width/height axes for outer-edge supports and local result
  plots/probes: recipe width follows global Z and height follows global Y.
  Share the mapping with frame placement and add non-square/notch regressions.
  File schemas are unchanged; general wall/diaphragm behaviour and Quad shear
  remain unvalidated and no new solver is enabled.

- Extend the separate plate workspace with additional uniform pressure cases,
  named combinations and global -Y self-weight for horizontal XZ plates. Add a
  staged loading editor, solved-combination selector and snapshot-labelled CSV.
  Retain the primary-case Plate baseline and migrate old plate files to v3
  without adding loads. Display-unit edits/undo keep the current result snapshot.
- Check finite plate results and all six global force/moment balances for every
  combination before accepting any snapshot. Keep Quad shear unavailable and
  reject unsupported vertical membrane gravity; no general shell solver is added.

- Preserve Results dock visibility after solving in All tools/Model; hidden
  results stay hidden and open results update in place. The Results workspace
  continues to show them on completion, and View > Results remains available.

- Add a Slabs tab to the main Results dock: local Quad moment/membrane-stress
  centre contours, natural-coordinate probes, axes, unit/combination/snapshot
  identity, CSV and paginated MCP surface-element results. Keep the current
  experimental rectangular coupling and all-combination equilibrium gate.
- Add geometry-owned outer-edge global rigid supports with staged preview,
  presets/custom DOFs, remesh/rename/delete lifecycle, undo, spring-conflict
  rejection, viewport/report display and atomic MCP editing. Spatial files
  advance to version 28; older spatial files migrate with no edge assignments.
- Withhold Quad transverse shear after an independent Navier refinement check
  found PyNite 3.0/3.2 recovery inaccurate. Disable plate-pilot Quad Qx/Qy plots
  and return `shears=None` for that formulation; corrected Rect shear remains.

- Independently benchmark thin plates with a free centred opening using a
  converged Rayleigh–Ritz energy reference, deflection probes, material-patch
  moments and mesh refinement. Add Navier signed moment/shear, manufactured
  polynomial and two-direction strip checks for Rect recovery.
- Correct Rect postprocessing: derive moments/shears from its solved local
  displacement polynomial with isotropic plate constitutive coefficients.
  PyNite 3.0/3.2 raw Rect bending signs and twisting recovery are inconsistent
  with the independently verified convention. Reject non-unit Rect bending
  modifiers because the supported engine ignores them in bending stiffness.
  Geometry previews/recipes remain available; frame and Quad recovery are unchanged.
  This correction is after the immutable RC4 release; development is 1.0.0rc5.dev0.

## 1.0.0rc4 — 2026-10-28

- Restrict PyPI publishing to Brecon release metadata; reject old PyniteGUI tags
  and mismatched versions before downloading assets. Preserve old releases and
  add executable workflow-gate regressions.

- Rename PyniteGUI to **Brecon**, named after a place visited by the author.
  Distribution/command: `brecon`; app, Help/About, reports, MCP, citation and
  documentation use Brecon. Keep `pynitegui` command/imports, existing file formats,
  settings/recovery storage and MCP reference URI compatible. Add a Brecon
  reference URI and vector mountain/frame wordmark. Development version advances
  to 1.0.0rc4; existing releases, tags and repository URLs stay unchanged.

## 1.0.0rc3 — 2026-10-28 (PyniteGUI)

- Avoid a native desktop freeze when analysis finishes before deferred worker
  cleanup has joined. Keep frame/plate controls busy until thread teardown
  completes, without blocking the GUI; cover delayed cleanup in both workspaces.
- Add a repeatable visible installed-wheel desktop smoke script, recording
  native renderer diagnostics, screenshots and workflow checks separately from
  human file-picker, keyboard and printing verification.
- Deploy the generated documentation through GitHub Actions and verify live
  modelling, examples and project-format pages.

- Add optional independent frame/truss shear modulus with derived-G defaults,
  unit-aware native editing, provenance/validation, reports and MCP schema support.
  New project formats 25/26 preserve it; plate/surface recipes remain derived-G only.
- Add both official Space Frame - Nodal Loads examples with their original E/G/nu,
  geometry, IDs and loads. Verify pinned-source parity and an independent stiffness
  assembly; nine of twenty official examples are now available.

- Add a shared native Modelling Tools dock for previewed move/repeat/rotate/mirror,
  planar continuous-beam and multi-bay/storey frame generation, and controlled
  two-node merging. Canvas ghosts, explicit collision/support/load choices,
  atomic undo, stale-preview guards and preserved assignments keep edits reviewable.
- Add governing-station queries in retained envelopes using verified continuous
  solver-segment derivative roots and both jump sides, with snapshot-labelled CSV
  and curve navigation. Document numerical tolerances and unsupported-contract failures.

- Add scope/component/value filters to existing envelope summaries with physical
  thresholds retained across units, snapshot/filter-labelled CSV, cached extrema
  and row-to-member-curve navigation. Reconcile RC2 publication and live/legacy
  Pages deployment records.

- Add editing-only named groups and global-Y levels with native select/isolate,
  optional drawing/node-drag snapping and 3D level work-plane placement. Preserve
  analysis snapshots and keep split/deleted references valid. New saves use
  planar 23/spatial 24 with legacy migration; older applications reject them.

- Fix README image and repository-document URLs for PyPI's standalone description
  rendering; document the now-available PyPI installs with uv and pip.

- Add Prakhar Sharma's name and ORCID to citation metadata, with a separate
  acknowledgement of substantial OpenAI Codex assistance in development.

- Add a manual PyPI Trusted Publishing workflow and owner setup instructions.
  Verify the published GitHub release's exact wheel/source assets and checksums
  against its tag; publish from a separate OIDC/environment job without rebuilding.

## 1.0.0rc2 — 2026-10-27

Published on GitHub and PyPI; incorporates the changes below since rc1.
Stable 1.0 targets the documented elastic frame/truss and restricted frame-only
P-Delta workflows. Surface/plate tools remain experimental; nonlinear/plastic,
modal and reinforced-concrete workflows remain deferred.

- Refresh the README with current result workflows, RC2 installation guidance,
  documentation links, scope limits and current native/3D screenshots.

- Add project-level citation guidance and GitHub citation metadata, with exact
  release/commit guidance, separate PyNite attribution and deferred DOI archiving.

- Main-canvas 2D/3D result controls and exact member station/side inspection in
  the Results dock, synchronized with existing spatial controls and preserving
  draft Properties and retained result windows. Add signed member colour maps
  with shared combination scales, numerical legends, non-colour sign patterns,
  guarded click probes and bounded instanced 3D strokes. Surface stress contours
  and printable map reports remain outside this member-display change.

- Prune the roadmap to seven focused UI/modelling tasks. Remove unrequested
  what-if/spreadsheet/template/tapered/matrix-inspector extras, vague catalog/CAD
  expansion and optional MCP screenshots. Consolidate solver/support and platform
  validation tracking; retain nonlinear goals, official-example blockers and all
  engineering/release gates. Keep completed implementation history in TODO.md.

- Optional All tools/Model/Results command workspaces with focused dock visibility
  and a recoverable collapsed command strip. Preserve draft widgets, selection,
  results and zoom, retain planar view centre on resize, and avoid spatial camera
  requests. Respect MCP locking and reset controls with Restore Default Layout.

- Native static deformation playback for retained 2D/3D member curves and solved
  surface wireframes. Cache paths per combination, update existing artists,
  preserve a dashed reference and fixed limits, and provide pause/reset/fraction,
  display-only timing and amplification controls. Stop hidden/MCP-mode playback
  and export still frames with snapshot/fraction/amplification metadata.

- Dimensioned section chooser sketches for all 15 offline AISC shapes, with
  strong/weak-axis orientation, actual published depth/width/thickness, separate
  HSS nominal/design walls, unit conversion and theme-aware empty states. Keep
  numerical imports unchanged and preserve a source-workbook excerpt for checks.

- Plain static storey drift in retained planar/spatial result windows: explicit
  lower/upper node pairs, global Y heights, X/Z translation differences, signed
  ratios and per-pair governing combinations. Preserve pairs across display-unit
  changes and export atomic snapshot CSV, without rigid-floor or code assumptions.

- Add the official clamped rectangular Quad plate in the existing separate plate
  workspace, with menu/browser discovery, current-unit inputs and preserved frame
  drafts. Verify transverse upstream parity, equilibrium, classical reference and
  persistence. Audit all 20 upstream scripts: seven adapted; thirteen remain
  explicitly blocked by material, unilateral, shell, modal or plastic workflows.

- Optional approximate straight deformation preview for planar/spatial members,
  joining displaced end nodes and skipping span sampling when force diagrams are
  off. Label nodal-only peak/Auto scaling, retain full force-diagram samples and
  preserve numerical results, probes and reports. Keep sampled curves as default.

- Retained 2D/3D combination comparison: solid/dashed member curves on shared
  axes, exact left/right probes, signed governing value by absolute magnitude,
  deterministic ties and snapshot-aware PNG/SVG export. Preserve selections and
  physical probe distance across units/themes without editing or re-solving.

- Matching 3D overlay readability controls for node/member IDs, end values and
  sampled extrema, preserving local rolled axes, ribbons, sampled legends and
  camera/selection behaviour. Add independent boolean-validated 2D/3D print
  label choices initialized from the view and recorded per page. Preserve legacy
  viewport value payloads; add native, projection and real-renderer regressions.

- Independent 2D whole-structure node/member-ID, end-value and sampled-extrema
  visibility, retaining existing load/support controls and numerical results.
  Native plot toolbar PNG/SVG saving adds a visible analysis stamp and embedded
  snapshot/method/combination/units/context, including envelope selections and
  spatial member plots. Preserve live zoom/probes/layout, record only source
  basenames, and write atomically without damaging prior exports.

- Native searchable example browser with category filters, theme-aware geometry
  previews, current-unit loading summaries and explicit-unit reference checks.
  Preview without solving or changing the active model/drafts; open through the
  existing unsaved-work prompt. Add Gerber and three-hinged polygonal-arch models
  with hand-equilibrium/zero-hinge-moment checks, persistence and native menu
  coverage. Preserve the restriction on converting released frames to 3D.

- Official moment-frame, P-Delta column and space-truss examples with original
  IDs/load assumptions, canonical unit conversion and explicit adaptation notes.
  Retain second-order method selection and strict recovery checks; compare the
  frame to a pinned upstream result, refine the column against the tangent
  solution and verify truss forces by independent joint equilibrium. Add unit,
  save/reopen and menu coverage. Record independent-G material input as the
  dependency for the two remaining official space-frame examples.

- Three official PyNite beam adaptations in File > Examples > 2D Frames:
  point loads, uniform load and factored envelope, with pinned upstream source,
  retained MIT notice, documented planar/material differences and a worked
  tutorial. Preserve executable load signs and original section/case/factor
  data; add closed-form response, envelope provenance, save/reopen/unit and
  native menu checks. No new solver method is introduced.

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
