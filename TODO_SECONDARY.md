# Secondary Roadmap: Stabileo-Inspired Ideas

Reviewed 2026-10-03. Inspiration: [Stabileo](https://github.com/lambdaclass/stabileo)
and its [live Basic editor](https://stabileo.com/app/basic). This is a wishlist,
not a commitment to copy its interface or replace Qt/PyNite.

[TODO.md](TODO.md) remains the primary implementation roadmap. When an item
below overlaps it, the primary item owns completion; promote new work there
when selected. Existing loads, materials, units, themes, examples, and result
inspection are not new tasks just because Stabileo also has them.

## Compatibility Gate

Checked against the installed **PyniteFEA 3.0.0** source, not only the latest
online documentation. Our application currently exposes linear static XY
frames; solver capability does not mean a feature is already usable here.

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
- [ ] **Linked result tables (UI).** Select a row to highlight its node/member;
  select geometry to reveal its result row. Separate displacements, reactions,
  and member forces, with sortable values and correct units. Build on the
  existing result tables and coordinate with the editable-table task in TODO.md.
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

## Later: Verified Solver Extensions

- [ ] **Elastic supports and settlement (Adapter).** Expose global DX/DY/RZ
  support stiffness via `def_support_spring` and imposed displacement/rotation
  via `def_node_disp`. Start with bilateral springs. Spring units, reaction
  signs, and mechanism checks need dedicated tests. Imposed displacements are
  model-level in this API, not automatically case-specific loads. Primary owner
  for springs: elastic support springs in TODO.md; inclined supports are separate.
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
- [ ] **3D frame viewport (Deferred adapter).** PyNite accepts spatial nodes and
  members, but our planar schema, restraints, loads, diagrams, and interaction
  model all need redesign. Preserve planar mode as a first-class workflow.
  Primary owner: separate 3D evaluation in TODO.md.

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

## Evidence and Recheck Points

- [Stabileo repository and feature/status overview](https://github.com/lambdaclass/stabileo).
- [Live Basic editor](https://stabileo.com/app/basic): reviewed Project, portal-frame
  results, Advanced, and Explore panels; observations are not implementation guarantees.
- [PyNite model API overview](https://pynite.readthedocs.io/en/latest/FEModel3D.html).
- [PyNite member conventions and result APIs](https://pynite.readthedocs.io/en/latest/member.html).
- Local check: installed `Pynite/FEModel3D.py` and `Pynite/Member3D.py` in `.venv`,
  version 3.0.0. Online documentation currently describes 3.2.0; recheck the
  installed/pinned version when promoting any solver extension.

Recommended starting batch: grouped toolbar, in-canvas result workspace, linked
tables, then comparison/envelopes. These improve daily use without widening the
engineering assumptions.
