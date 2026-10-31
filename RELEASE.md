# Release Preparation

Current release candidate: **Brecon 1.0.0rc4**, tag **v1.0.0rc4**. The owner authorized
GitHub publication and approved the PyPI environment on **2026-10-28**. The previous-name
**v1.0.0rc3** remains immutable. Check
[GitHub Releases](https://github.com/praksharma/PyniteGUI/releases) for published
assets; source tags and unpublished drafts do not imply a public binary release.
Stable 1.0 promotion follows a feature freeze and verification of the actual
release artifacts. Native macOS/Windows/Linux development packaging is available
in source; public signed installers and broader platform coverage remain later steps.

**Known RC4 plate limitation:** independent post-release checks found raw Rect
moment/shear recovery inconsistent with verified plate laws in PyNite 3.0/3.2.
Quad moments are preferable for RC4; Quad transverse shear is also unverified
and must not be relied on. Development disables Quad shear plots/data. The
Rect correction and independent opening/Rect benchmarks are in **1.0.0rc5.dev0** source development; RC4 assets
are unchanged. Non-unit Rect bending modifiers are rejected in development
because the supported engine ignores them in bending stiffness. See the
[plate guide](GUIDE.md#experimental-rectangular-plates) for scope and benchmarks.

**Publication status (2026-10-28):** Brecon RC4 is published on
[GitHub](https://github.com/praksharma/PyniteGUI/releases/tag/v1.0.0rc4) and
[PyPI](https://pypi.org/project/brecon/1.0.0rc4/).
[Workflow 40713196939](https://github.com/praksharma/PyniteGUI/actions/runs/40713196939)
verified the tagged assets and published the same files through Trusted Publishing.
The PyPI hashes match SHA256SUMS, and a fresh public-registry installation reports
**Brecon 1.0.0rc4** from both launch commands.

PyniteGUI RC3 remains published as a
[GitHub prerelease](https://github.com/praksharma/PyniteGUI/releases/tag/v1.0.0rc3)
and on [PyPI](https://pypi.org/project/pynitegui/1.0.0rc3/); its hashes match the
sealed checkpoint. Previous tags and assets are unchanged. Stable 1.0
platform and prerelease-feedback gates below remain open.

## Build and Verify

From the repository root, with uv installed:

```sh
uv sync --locked --extra mcp
QT_QPA_PLATFORM=offscreen PYNITEGUI_NO_WEBENGINE=1 uv run --locked --extra mcp python -B -m unittest discover -s tests -q
uv build --no-sources
uv run --locked python -B scripts/check_dist.py dist/brecon-1.0.0rc4-py3-none-any.whl dist/brecon-1.0.0rc4.tar.gz
```

The distribution checker audits versions, metadata, bundled runtime assets,
licenses and source contents and writes `dist/SHA256SUMS` for these two artifacts.
The wheel must contain the offline viewport/vendor assets and both libraries.
The README is also the PyPI long description: use absolute HTTPS image and
document URLs and check them in the built metadata, not just GitHub's renderer.
Updating the repository README does not update an already uploaded PyPI
description; publish a new version for such changes rather than replacing files.
The source archive also includes the lockfile, guide, release documents, tests,
scripts and README screenshots. Do not attach old-version artifacts.

Install the wheel into a fresh environment outside the checkout. Run the smoke
script with that environment's Python from a temporary working directory, not
with `uv run` in the repository (which would test the editable project instead).
Example POSIX commands; use the corresponding `Scripts/python.exe` on Windows:

```sh
uv venv --python 3.12 /tmp/pynitegui-rc-base
uv pip install --python /tmp/pynitegui-rc-base/bin/python ./dist/brecon-1.0.0rc4-py3-none-any.whl
cd /tmp
/tmp/pynitegui-rc-base/bin/python /absolute/path/to/PyniteGUI/scripts/smoke_installed.py --version 1.0.0rc4
```

Repeat in another fresh environment, installing the same wheel with `[mcp]`
and adding `--mcp` to the smoke command. The script checks that imports are not
editable, bundled assets are present, all examples save/open/analyze, exports
work and native windows initialize; the MCP variant also exercises a real local
SDK client and server lifecycle. It is not a visible desktop/WebGL smoke test.

For repeatable visible checks, use that MCP environment's Python in a desktop
session with WebEngine enabled:

```sh
cd /tmp
/tmp/pynitegui-rc-mcp/bin/python /absolute/path/to/PyniteGUI/scripts/smoke_desktop.py --output /tmp/pynitegui-desktop-qa --hold
```

Use a new output directory for each run. This script uses disposable settings,
real native widgets and the actual renderer, with QtTest/application commands
and supplied file paths. Its screenshots and JSON diagnostics are evidence of
those automated workflows, not human mouse/keyboard or OS file-picker checks.
With `--hold`, complete the remaining manual checks in the open test window:
Save As and reopen through the real pickers, F5 analysis, and File > Export
Results > Print Results. Record the outcome before ticking the macOS manual gate.

Run `tests/viewport3d.spec.cjs` with a separately installed Playwright/Chromium
as described in GUIDE.md. These browser tests supplement, not replace, native
desktop checks. Check the built wheel's 3D viewport on each target platform.
Set `VIEWPORT_ASSETS` to the installed wheel's `pynitegui/qt/viewport3d` directory
to serve its assets instead of the source checkout during browser testing.

## Stable 1.0 Scope

Elastic 2D/3D frames and bilateral axial-only trusses, plus frame-only P-Delta
within GUIDE.md restrictions. Surface meshing, plate analysis and coupled Quad
slabs remain explicitly experimental. Development after RC4 adds Iterative elastic
for unilateral axial bars/global support springs and a separate frame Vibration
Modes workspace, with the checkpoints below. Plastic and reinforced-concrete
workflows remain pending. Remaining UI roadmap items do not
block this scope.

## Historical RC3 Checklist and Future Publication Gates

- [x] Project citation guidance and GitHub citation metadata added without a DOI.
- For each release, review CITATION.md/CITATION.cff and preserve exact version and
  commit links. Consider Zenodo concept/version DOI archiving for stable 1.0;
  archive later releases as new versions of the same record.
- [x] RC3 full suite passes with MCP wire tests enabled, not skipped.
- [x] RC3 wheel/source archive audits and base/MCP installed-wheel smoke checks pass.
- [ ] Native Linux visible startup, 2D/3D editing, save/open, analysis, reports and MCP checked.
- [x] Repeat installation and automated visible workflows on macOS; record OS/Python/Qt/renderer versions.
- [x] Human macOS file-picker, F5 shortcut and interactive print-dialog checks confirmed.
- [ ] Windows installation and visible workflows checked, or explicitly labelled unverified.
- [x] RC3 release notes and limitations reviewed; artifact hashes generated in SHA256SUMS.
- [x] User approves the consolidation checkpoint: push changes and prepare an unpublished RC3 draft with assets.
- [x] RC3 GitHub/PyPI publication confirmed on 2026-10-28; its tag and assets remain unchanged.
- [x] Historical RC2 GitHub/PyPI publication completes; its artifacts and tag remain unchanged.

Upload the wheel, source distribution and SHA256SUMS to the approved GitHub
prerelease, using CHANGELOG.md for notes. Tag the verified commit, not a moving
branch. GitHub also provides source archives for the tag. Preparation scripts
do not upload to PyPI; use the manual publishing workflow below. For stable 1.0.0, update version/lockfile/notes, rebuild and repeat
validation rather than renaming RC artifacts.

## uv Tools and PyPI

uv installs tools from Python package indexes; PyPI is the intended public
distribution channel. The `brecon` entry point is canonical; `pynitegui` is a
compatibility alias. Use the publication status above to confirm availability.
A separate uv-specific package or registry submission is not needed.

After stable 1.0 is published to PyPI, users can run:

```sh
uv tool install --python 3.12 brecon
brecon
uv tool upgrade brecon
```

For optional MCP support, install `"brecon[mcp]"` instead. An RC published to
PyPI would require an explicit version, for example `"brecon==1.0.0rc4"`.
These registry commands describe the publication plan; no PyPI availability is
claimed by this checklist. Local-wheel installation above works before upload.

Before upload, confirm ownership/availability of the PyPI project name and set
up a PyPI account and publishing credentials, preferably GitHub Actions Trusted
Publishing. Upload only the reviewed wheel and source archive, with explicit
paths, after final approval. TestPyPI can be used as a separate dry run; it is
not a substitute for testing the artifacts locally. Never commit API tokens.

**One-time Trusted Publishing setup:** sign into PyPI, enable account 2FA if
needed, and open [Publishing](https://pypi.org/manage/account/publishing/). Add a
pending GitHub publisher with these exact values:

| Field | Value |
| --- | --- |
| PyPI project name | `brecon` |
| Owner | `praksharma` |
| Repository name | `PyniteGUI` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Brecon needs a **new pending publisher**, separate from the existing `pynitegui`
project. The owner confirmed configuring it on **2026-10-28**; the first RC4 upload
succeeded on that date. Keep the old project/releases for existing users.
Its package name is not reserved until the first successful publish. See the
[PyPI pending-publisher guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

A pending publisher creates the project on its first successful upload; it
does not reserve the name. If you already own the project, add this publisher
under that project's Publishing settings instead.

In GitHub repository Settings > Environments, create **pypi**, add yourself as
a required reviewer, allow your own review if you will dispatch the workflow,
and restrict deployment branches to **master**. No PyPI API-token secret is
needed. These account/environment changes are owner setup, not performed by
adding the workflow.

**Publish an approved release:** first publish the GitHub draft with its wheel,
source archive and SHA256SUMS attached. Then open Actions > **Publish Brecon to PyPI** >
Run workflow, choose **master**, and enter its tag (for example `v1.0.0rc4`, once prepared).
Review and approve the **pypi** environment job. This uploads to real PyPI;
it is not a dry run. The workflow derives the distribution name from the tag
metadata and accepts **Brecon only**. Old PyniteGUI RC2/RC3 tags are rejected
before assets are downloaded; deleting old releases is unnecessary. The rename
itself did not publish or replace RC3 assets; RC4 was released separately after validation.

The workflow is manual only. Its read-only verification job checks out the
requested tag, rejects a version mismatch or draft release, downloads the exact
GitHub assets, checks both hashes, and audits them against the tagged source.
The separate environment-gated publication job has OIDC permission and uploads
those verified files without rebuilding. It does not run on pushes or tags.
Do not move existing release tags or replace reviewed release assets to retry.

References: [uv tools](https://docs.astral.sh/uv/guides/tools/) and
[building and publishing](https://docs.astral.sh/uv/guides/package/).

## Post-RC4 Steel Pushover Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-31. Public RC4 artifacts remain
unchanged. New frame saves use planar **v33** and spatial **v40** for explicit
steel profile data; older definitions migrate to nullable elastic defaults.
Standalone mesh/plate formats remain unchanged and elastic-only.

- Add optional custom material fy and steel I-section Zy/Zz/material binding,
  native staged editors, cubic section units, material rename/delete guards,
  definition reports and typed MCP schema/batch edits. Binding checks apply in
  2D/3D; static and modal workflows remain elastic.
- Add Tools > Steel Pushover with elastic preload/full signed push combinations,
  control node/DOF and absolute stop limit, explicit reaction-node/component sum,
  bounded load steps/retries/yield overshoot and native material/section access.
  Support unreleased bilateral frames, including mixed elastic/plastic sections
  and bilateral ground springs. Push uses nodal forces/moments or member-end
  point loads; distributed/interior push loads are rejected, while member loads
  may form the strictly elastic preload.
- Independently check physical-scale plastic tangent, finite values, free-joint
  equilibrium, global force/moment balance, end yield overshoot and conservative
  interior interaction before recording increments. Retain only checked prefixes
  when a mechanism, overshoot, interior hinge or nonconvergence stops the run.
  Current/Partial and complete/termination/accepted_factor are explicit; no
  post-mechanism response, hidden residual stiffness or plastic rotation is supplied.
- Add signed capacity and undeformed end-yield plots, accepted-step motion,
  reaction, local node-on-member action and equilibrium tables; stamped PNG/SVG,
  CSV and full source/settings/canonical-history JSON. Reuse isolated workers,
  shared cancellation/busy lifecycle and revision/session guards. MCP adds
  run_pushover_analysis/read_pushover_results, guarded pagination and partial-state
  semantics; the native previous snapshot remains clearly labelled.
- Add three independent hand-check examples: redistribution below collapse,
  mechanism termination and rolled spatial weak-axis bending. The 240 in propped
  beam yields first at 22.222222 kip and collapses ideally at 25 kip. At 24 kip,
  the hand displacement is **−1.142068966 in**; 500 increments give
  **−1.141969655 in**, with substantially reduced error versus 100 increments.
  Also verify a true spatial axial/biaxial yield root, interior axial/bending
  interaction, signed compound push factors, member-end transfer, distributed
  preload and exact preload-only stopping.
- This is explicitly **first-order steel I-section plasticity**. No RC, nonlinear
  surfaces, hardening, shear/torsional yielding, releases, imposed/inclined supports,
  unilateral contacts or combined P-Delta/plastic response is claimed. Both pinned
  official pushover scripts request P_Delta=True and remain pending that validation.
  The catalog has **39 frame/truss/coupled/modal/steel definitions**, plus the plate
  example; **13 of 20** official examples are adapted.

- Validation: **1,093 full-suite tests**, no skips, **345.845 s**, including
  authenticated MCP wire tests. The installed wheel passes **21 focused tests**
  on PyNite 3.0.0 / Qt 6.11.2 (**28.263 s**) and PyNite 3.2.1 / Qt 6.12.0
  (**25.132 s**), including actual workers, cancellation, exports and MCP.
  Both installed environments pass all **39 examples** through save/open/static
  solve/export/native initialization and authenticated discovery/edit/undo.
  Strict documentation checks cover **57 HTML pages**; browser QA verifies the
  new steel page/image, search/navigation, GitHub Pages subpath and theme/layout.
  Wheel/source metadata, runtime assets, source contents and hashes are audited.

## Post-RC4 Modal Analysis Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-31. Frame/plate formats and public
RC4 artifacts are unchanged. Modal inputs/results use a separate workspace and
self-contained JSON export; the static analysis-method choice is preserved.

- Add explicit mass-source combination, global weight component, gravity and
  mode count for unreleased bilateral 2D/3D frames, including inclined supports
  and optional bilateral global springs. Reject surfaces, trusses/releases,
  unilateral contacts and imposed support motions. No geometric preload,
  damping, spectrum/time-history or earthquake-response calculation is claimed.
- Reuse checked PyNite elastic stiffness; integrate centreline point/line weights
  consistently at their actual stations, with physical polar rotary inertia for
  generated self-weight. Do not use the engine's negative member-load lumping or
  its artificial zero-DOF inertia. Solve the reciprocal mass/stiffness eigenproblem;
  reject unresolved/missing modes, nonfinite values, failed eigen-equations or
  failed mass orthogonality.
- Add a native Vibration Modes window with frequencies, periods, normalized node
  shapes, mass sources, amplified 2D/3D curves and spatial section-orientation ticks.
  Export snapshot tables, stamped PNG/SVG and a complete JSON archive with source
  model/configuration, engine version and canonical shapes. Keep static results
  separate; model revisions reject outdated replies and later stale reads.
- Use the existing isolated worker, shared busy/cancellation lifecycle and
  session/revision checks. Add MCP run_modal_analysis/read_modal_results with
  typed inputs and pagination; analysis_status/cancel_analysis serve either job.
- Add the official modal column with original mass factors and 386.4 in/s² gravity.
  First three frequencies: **1.15622542, 7.47866382, 20.16831186 Hz**. Compare all
  normalized shapes/frequencies to the pinned upstream fixture. Independently
  verify tip masses, distributed continuum convergence, gravity/weight scaling,
  orientation/roll invariance, physical torsional polar inertia, homogeneous
  normal constraints and a sparse **603-coordinate** mass/spring-chain spectrum.
- The catalog contains **36 frame/truss/coupled/modal definitions**, plus the
  separate plate example; **13 of 20** official examples are adapted.
- Validation: **1,072 tests**, no skips, **318.173 s**, including MCP wire tests.
  Final wheel checks pass **15 tests** on PyNite 3.0.0 / Qt 6.11.2 (14.876 s)
  and PyNite 3.2.1 / Qt 6.12.0 (11.203 s), including the actual modal worker,
  cancellation, exports, sparse benchmark and wire calls. Both installed
  environments pass all 36 examples through save/open/solve/export/native windows
  and MCP discovery/edit/undo. Strict docs verify **56 HTML pages**; browser checks
  cover navigation, images/search, subpath serving and theme/layout behaviour.
  Packaged runtime assets, wheel/source metadata and checksums are audited.

## Post-RC4 Iterative Elastic Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-31. The user explicitly lifted the
new-solver hold. Public RC4 assets remain unchanged. New saves use planar **v31**
and spatial **v38**, with strict bilateral/default migration from legacy files.

- Add tension/compression-only axial bars and positive/negative-displacement-only
  global ground springs. Frame members remain bilateral. Reject surfaces and
  spatial frame releases for this method.
- Solve each full combination independently with activation and reactivation,
  configurable load steps/iteration limits/switch tolerances, unchanged imposed
  support motions and physical reactions. Use sparse contact rows. Reject cycles,
  nonconvergence, nonfinite response, nonpositive active stiffness and failed
  force/moment balance. Certify neutral-contact directional stability; fail closed
  on unresolved mechanism cones above 600 free coordinates.
- Add staged native, Model Tables and bulk controls; method settings; snapshot
  Active state/Iterations tabs; CSV, printed contact states and paginated MCP
  contact/history results. Inactive bars keep joint-chord deformation, zero actual
  axial force and muted rendering. Trial axial force is tension-positive; spring
  trial is displacement/rotation, not reaction.
- Add three official examples under Iterative elastic, preserving the existing
  pinned source revision and MIT notice. Fixed vertical anchors in the source
  spring-supported frame are condensed exactly into global ground springs; no
  general node-to-node spring API is claimed. Compare all source nodal motions
  and transferred anchor reactions to a pinned PyNite 3.0.0 fixture. Independently
  verify reversed-foundation uplift against the simply supported beam formula,
  exhaustive bar active sets, member reactivation, load reversal, spring signs,
  inclined/prescribed constraints, neutral mechanisms and bilateral limits.
- The catalog now contains 35 frame/truss/coupled examples plus the separate
  official plate example; **12 of 20** official scripts are adapted.
- Validation: **1,056 full-suite tests**, no skips, **311.375 s**, including MCP;
  a further **21 focused mechanics/station-query tests** cover the final inactive
  bar chord correction. The installed wheel passes **24 tests** on PyNite 3.0.0 /
  Qt 6.11.2 and PyNite 3.2.1 / Qt 6.12.0, including a real wire solve; both also
  pass all 35 examples through save/reopen/solve/export/native windows and MCP.
  Strict documentation passes 55 HTML pages plus browser navigation/image/search
  checks. The offline 3D viewport checks inactive rendering/selection and its
  existing interaction/graphics suite. Native documentation capture is included.
  Wheel/source audits verify packaged runtime files and checksums.
- Modal analysis, steel pushover, RC plasticity and general surface interfaces
  remain separate pending milestones. Target-platform hardware checks and signing
  still require their documented evidence.

## Post-RC4 P-Delta Support-Movement Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. Public RC4 assets and file
formats (planar v29 / spatial v36) are unchanged. This extends an existing
analysis method; the hold on new iterative/unilateral, modal and plastic solvers
remains in place.

- Remove the blanket nonzero-motion P-Delta guard after independently validating
  the existing sparse affine solver. Every geometric update includes the full
  prescribed displacement in its right-hand side. Retain geometric-stiffness
  convergence, positive effective free stiffness, physical equation checks and
  independent global force balance before publication. Update progress/error
  context to cover prescribed as well as inclined support constraints.
- Prescribed global translations/rotations and inclined-normal motions retain
  their model-level values in every combination, including zero applied loads.
  Support shortening can itself produce axial preload and second-order response.
  Ground springs keep zero rest positions. Retain exclusions for trusses,
  surfaces, released translations and spatial rotational releases; supported
  planar moment releases still transfer zero released-end moment.
- Independent references import neither application nor PyNite: solve the exact
  elastic beam-column state-transfer equation for compression/tension, base
  translation/rotation, differential support movement, imposed axial shortening,
  biaxial bending, uniform loading and a ground spring. Check mesh convergence
  at 1/4/24 segments, nodal/reaction fields and approximate interior deformation.
  A separate six-DOF energy reference integrates cubic Hermite curvature/slope
  products and uses KKT constraints plus a scalar axial root. Check arbitrary
  spatial normals, additional rigid rotation, six base motions, springs, planar
  conversion, signed/zero combinations, released chord response, rigid translation,
  shortening-induced buckling and forced nonconvergence rejection.
- Distinguish the strain-derived geometric preload from external axial force:
  the engine's axial geometric term gives `N + N^2/(EA) = applied axial force`
  for a uniform force-controlled axial state. This is the existing small-strain
  geometric-stiffness convention, not a new finite-strain constitutive law.
  P-Delta interior member recovery remains approximate; mesh refinement and the
  existing force-only global equilibrium convention remain explicit in GUIDE.
- Add **P-Delta > Column - Imposed Base Motion**, including Browse Examples:
  480 in column in eight segments, base DX +0.03 in / RZ +0.0007 rad, gravity
  -60 kip and lateral +1 kip. Combined nodal tip DX is **3.5186619 in** versus
  continuum **3.5186638 in**; Gravity gives **-0.47371345 in**. Base motion only
  gives **-0.306 in** and zero member forces. Add the actual native screenshot,
  staged edit/method undo, spawned worker, unit conversion, snapshot invalidation
  and authenticated MCP edit/solve/zero-state result coverage. MCP discovery
  states the supported method scope and unchanged-per-combination motion rule.
- Validation: **1,040 tests**, no skips, **295.656 s**, including the optional
  MCP wire suite. The final installed wheel passes **63 focused tests** on
  PyNite **3.0.0** / Qt **6.11.2** (**4.774 s**) and PyNite **3.2.1** / Qt
  **6.12.0** (**4.823 s**). All **32 examples** save/reopen/analyze/export and
  native windows initialize; authenticated installed MCP discovery/edit/undo
  also passes. The installed Python files match the wheel bytes. Strict docs
  and local links cover **55 HTML pages**; browser QA verifies the new native
  screenshot, existing imagery, search, subpath, dark mode and layout. Distribution
  metadata/assets/licenses/source audit passes. Test ownership covers **158
  classes / nine groups**. Manual platform/signing gates remain unchanged.

## Post-RC4 Quad Shear Feasibility Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. Test/documentation changes
only; production solver, snapshots, UI, file formats and published RC4 assets
are unchanged. Quad transverse shear remains unavailable in results, CSV and MCP.

- Add a reproducible comparison of raw Quad shear, the divergence of each
  element's bilinear moment field, and a quadratic fit to neighbouring element-
  centre moments. The fit uses only complete 3 × 3 rectangular patches and
  reports no value at incomplete patches. Manufactured quadratic tensors check
  derivatives, signed/zero scaling and coordinate conditioning. Missing-centre
  tests prevent crossing a hole or extrapolating to an edge; nonuniform and
  invalid grids are rejected.
- Solve 120 × 180 × 0.6 in isotropic rectangles under -1e-7 kip/in², E=3600 ksi:
  simply supported Navier plate and coupled slab with negligible-stiffness edge
  beam (E=1e-6 ksi), plus nu=0 cantilevers clamped in either local direction.
  Three meshes (24/96/384 Quads), XY/XZ/YZ and Service/-2 Reverse/Zero produce
  **36 model solves / 108 reported combination records** per engine version.
  Every combination passes the existing six-component global equilibrium gate;
  no application guard or tolerance is relaxed.
- Check the independent Navier shear series at 160 versus 320 terms over the
  fine-mesh comparison region; component changes stay below **0.02%**. Compare
  methods on identical complete interior patches, excluding centres within
  20 in of the outer boundary. At the fine mesh, raw shear has **58.41%** vector
  L2 error and own-element moment differentiation **22.73%**. The neighbouring
  fit converges from **2.829% → 0.667% → 0.148%**; its largest fine component
  error is **0.170%**. All three methods pass the simple cantilever cuts,
  demonstrating why those cuts alone cannot validate general plate shear.
- Locked PyNite **3.0.0** and installed **3.2.1** reproduce the same bounded
  comparison and pass all 108 reported records. The fit remains a test-only
  candidate: boundary/opening recovery, irregular meshes, material/stiffness
  jumps, thick plates, curved shells, peaks and rotational interfaces remain
  unvalidated. It smooths across neighbours and does not replace unsmoothed
  production probes. Preserve the original unchecked exposure task and add
  explicit integration prerequisites to TODO.md.
- Reproduce JSON and the comparison figure with
  `scripts/benchmark_quad_shear.py --output /tmp/quad-shear.json --figure /tmp/quad-shear.png`.
  The report's `checks_passed` refers only to the bounded research checks;
  individual raw/candidate error metrics remain explicit.
- Validation: **143 surface/docs/tooling tests**, no skips, **115.815 s**.
  An installed locked-engine wheel passes **six new tests**, **56.120 s**;
  installed PyNite 3.2.1 / Qt 6.12 passes **26 recovery/surface/probe tests**,
  **63.090 s**. Ownership covers **157 classes / nine groups**. Strict docs
  and local links cover **55 HTML pages**; browser QA checks the new figure,
  existing workflows, search, subpath, dark mode and layout. Distribution audit
  passes; the full frame/MCP suite is not repeated for this test/documentation-
  only change. The previous production checkpoint remains recorded below.

## Post-RC4 Imposed Support-Movement Checkpoint

Development **1.0.0rc5.dev0**, 2026-10-29; public RC4 assets remain unchanged.

- Add signed global support translations/rotations and inclined-normal displacement
  to the existing linear solve. Use canonical inches/radians and display-unit-aware
  staged Properties, numerical tables and explicit bulk opt-ins. Prescriptions are
  model-level and unchanged in every combination, including zero applied loads.
- Solve with an affine physical lift and free-coordinate elimination. Preserve
  global spring rest positions at zero; independently recover physical reactions,
  released-end motions and all-combination free/global equilibrium. Support exact
  redundant constraints only when their prescribed motions agree. Shared shell
  edge constraints remain active; incompatible prescriptions reject analysis.
- Cover linear 2D/3D frames/trusses and supported releases, explicit shared surface
  joints, support copying/collision identity, conversion, snapshot invalidation,
  process-worker transport, definition reports and paginated unit-labelled MCP
  movement metadata alongside normal/unused-rotation metadata.
- Add **Beam - Support Settlement and Rotation**, with right DY -0.1 in and RZ
  +0.001 rad. Its zero-load **Settlement only** case has N1 FY +16.433333 kip /
  MZ +862.75 kip-in and N2 FY -16.433333 kip / MZ +1109.25 kip-in. Record a
  reproducible native offscreen illustration and explicit load-factor semantics.
- Advance planar saves to **v29** and spatial saves to **v36**. Current movement
  fields are required; older files migrate zero motion without changing supports.
  Reject malformed values, nonzero old-schema motion and free-direction prescriptions.
- Nonzero support movements reject P-Delta pending independent second-order
  recovery checks. No case-specific prescriptions, moving spring rest positions,
  staged-construction or plastic/nonlinear connection method is introduced.

Validation of the support-movement extension:

- Full locked source suite with optional MCP: **1,022 tests**, no skips,
  **254.851 s**; **156 classes / nine groups**. Focused model/editor/MCP/table
  follow-up: **61 tests**, no skips, **3.345 s**.
- The installed wheel, outside the checkout, passes **100 focused tests** on each
  of PyNite **3.0.0** / Qt **6.11.2** (**7.302 s**) and PyNite **3.2.1** /
  Qt **6.12.0** (**6.681 s**), without skips. Installed smoke passes all
  **31 examples** through save/open/analysis/export and native initialization,
  plus real authenticated MCP discovery/edit/undo.
- The full suite includes an authenticated HTTP client that edits a settlement,
  runs the real process worker, reads unchanged prescribed motion in the zero-load
  combination, and verifies invalid-edit rollback without changing the revision.
  Independent references cover fixed-ended beam stiffness/Hermite fields, 2D/3D
  normal compliance, ground springs, rigid-body motions, trusses, detached
  member-side translations and fully released joint rotations without false torques.
- Strict documentation/local links pass across **55 HTML pages**; documentation
  browser checks include the inspected native settlement illustration, search,
  subpath, dark mode and layout. Offline viewport interaction/support/hover,
  graphics-resource and context-loss checks pass. Wheel/source metadata, runtime
  assets, notices and source-content audit pass. No public release or additional
  human OS/hardware/signing validation is implied.

The following sections record earlier development checkpoints and their historical
scope/validation; the imposed-motion exclusions there are superseded by this
linear-only extension.

## Post-RC4 General Inclined-Support Checkpoint

Development **1.0.0rc5.dev0**, 2026-10-29; public RC4 assets remain unchanged.
This extends the planar checkpoint below across existing model and analysis types.

- Spatial v34 stores required normal azimuth/elevation. Two tangent translations
  remain free; optional global restraint flags add exact homogeneous constraints.
  Exact redundancy is deduplicated; nearly dependent constraints and springs on
  fully constrained directions reject the model. Planar v27 keeps tangent angles.
- The sparse constrained solve includes trusses, linear end releases and shared
  coupled-surface nodes. Physical free equations use the unaugmented matrix;
  unused-rotation gauges never become ground torques. Existing shell drilling,
  release/surface and independent equilibrium gates remain active.
- Existing frame P-Delta starts each combination elastically and updates geometric
  stiffness until physical equilibrium closes, with at most 30 updates and positive
  constrained effective stiffness required. This closes axial-strain coupling beyond
  the engine's ordinary two-step approximation. Global P-Delta checks remain force-
  only; no truss/surface/translation-release/spatial-rotation-release P-Delta scope
  is added. Settlements and plastic/nonlinear connection methods remain separate.
- Staged native Properties, tables, bulk edits, global support copying, 2D-to-3D
  conversion, normal-facing offline viewport symbols/picking, orthographic reports
  and six-component paginated MCP reaction metadata use the same definitions.
  Released-rotation metadata is retained alongside inclined reaction metadata.
- Add **3D Cantilever - Oblique Roller Normal** and a native Properties capture.
  Independent cantilever compliance and dense P-Delta references cover all six
  motions/reactions, poles, oblique normals, signed/zero combinations, spring axes,
  additional constraints/redundancy, releases/trusses, conversion, coupled nodes,
  buckling/nonconvergence and process-worker snapshot transport.

Validation of this extension:

- Full locked source suite with MCP: **1,009 tests**, no skips, **252.652 s**;
  **154 classes / nine groups**. Final schema/editor/mechanics follow-up:
  **40 tests**, no skips, **4.047 s**.
- Installed-wheel compatibility outside the checkout: **76 focused tests** each
  on PyNite **3.0.0** / Qt **6.11.2** (**5.459 s**) and PyNite **3.2.1** /
  Qt **6.12.0** (**5.378 s**), with no skips. The installed locked runtime also
  passes all **30 examples** through save/open/analysis/export/native initialization
  and a real authenticated MCP discovery/edit/undo session.
- Wheel/source metadata, bundled assets, notices and source-content audit pass.
  Offline viewport checks cover normal-facing geometry, roller/pick identity and
  actual example hover alongside existing interaction/result/context-loss checks.
  Focus-resource tests explicitly render pending texture uploads before retaining
  their exact leak assertions. The native offscreen Properties capture was inspected.
- Strict documentation/local links cover **55 HTML pages**. Browser documentation
  checks pass imagery (including spatial normal controls), search, subpath, dark
  mode and layout. Public releases and manual OS/hardware/signing gates are unchanged.

The following section records the earlier, narrower checkpoint and its historical
validation results; its exclusions are superseded by this extension.

## Post-RC4 Planar Inclined-Roller Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. This extends the existing
linear frame adapter; new solver methods remain on hold and public RC4 assets
are unchanged.

- Add an `inclined` node support with a signed global tangent angle in degrees.
  Its normal translation is fixed; tangent translation and RZ stay free. Assemble
  sparse node-local free coordinates without penalty stiffness or artificial
  grounding. Verify constrained rigid-body/stiffness stability (including the
  sparse spectral branch and pre-cancellation roundoff bound), free physical
  equations and all-combination independent global force/moment equilibrium.
- Store physical global displacements for ordinary engine member recovery.
  Independently recover rigid normal force and global bilateral spring reactions;
  ordinary node tables retain their global totals. Native Properties shows the
  signed rigid normal force; paginated MCP node reads provide separate rigid/spring
  vectors, normal force, explicit units and chosen normal direction.
- Add staged Properties, Model Tables and bulk edits, rotated native/report
  symbols, tree/tooltips, definition reports and an editable **Beam - Inclined
  Roller** example. Its 120 in pin/30-degree roller beam under -0.01 kip/in gives
  Service N2 **FX -0.346410 / FY +0.6 kip**, rigid normal force **+0.692820 kip**;
  N1 balances FX and carries **FY +0.6 kip**. Reversed combinations flip signs.
  The guide includes an inspected native offscreen capture; it is not a human
  OS-dialog/hardware validation claim.
- Planar saves advance to **v27**, with required node `support_angle`. Older
  versions migrate to zero angle and retain their original supports. Reject
  malformed angles, old-version inclined inputs and missing current fields.
  Spatial stays **v32** and omits the inactive inherited angle field; nonzero
  spatial angles are rejected. Plate files remain v3.
- Require unreleased planar linear frame members. Reject P-Delta, trusses,
  released/spatial frames and spatial conversion before solving or changing the
  source. Copied support orientations remain global, with explicit collision
  handling; changing inclination invalidates snapshots while unit-only changes
  retain them. Real process-worker, metadata pagination/unit conversion, undo,
  input precision and invalid-batch rollback regressions are included.
- Independent axial/Euler–Bernoulli cantilever and pin/roller references cover
  oblique/reversed beams, member fields, signed/zero combinations, global springs,
  nonuniform subdivisions and deliberately corrupted recovery. Sparse failure and
  near-mechanism cases reject results. No nonlinear connection, imposed movement
  or additional solver method is enabled.
- Full locked source suite with MCP: **994 tests**, no skips, **247.393 s**;
  **152 classes / nine groups**. Installed locked PyNite **3.0.0** / Qt **6.11.2**:
  **52 focused tests**, no skips, **4.095 s**. A second installed wheel runtime
  using PyNite **3.2.1** / Qt **6.12.0** passes the same **52 tests**, no skips,
  **5.160 s**. The final smoke/UI/inclined-support follow-up passes **192 tests**,
  no skips, **72.793 s**, including reaction-label updates after solving/combination
  changes without losing unapplied edits. Installed smoke verifies **29 examples** through save/open/analysis/
  export and native initialization, plus real authenticated MCP discovery/edit/undo.
  Strict documentation/local links cover **55 HTML pages**; browser QA verifies
  support-page imagery, search, subpath, dark mode and layout. Public releases and
  the manual platform/signing gates remain unchanged.

## Post-RC4 Inclined-Support Feasibility Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. This is a test-only feasibility
study. No production adapter, UI, file format, MCP schema, public tag or RC4 asset changes.

- Demonstrate exact homogeneous planar support constraints through a free
  coordinate basis, without penalties or artificial grounding. Scale translational
  and rotational coordinates, reject dependent/nearly dependent constraints,
  require positive stiffness on every physical free mode, and verify constraint
  and free-equation residuals before recovering global rigid reactions.
  Carry a pre-cancellation matrix-product roundoff bound through diagonal scaling;
  reduced normalization alone initially missed a near-mechanism. Reject that
  unresolved mode rather than accepting its small positive numerical stiffness.
- Prepare actual engine member stiffness and equivalent nodal loads (including
  fixed-end vectors) on a disposable all-clamped copy. Discard its displacements;
  solve the test-only constrained system without creating AnalysisResults.
  Compare with independent axial/Euler–Bernoulli cantilever flexibility and
  statically determined pin/roller beam fields. No application guard is bypassed.
- The reproducible report covers **153 cases**: four beam orientations, nine
  roller angles, three subdivisions, three global-spring setups, signed/zero
  combinations. Maximum reference errors: **1.01e-15 in** translation,
  **3.94e-17 rad** rotation, **3.29e-13 kip** force and **1.80e-12 kip-in** moment.
  Independent global balance residuals stay below **4.45e-14 kip / 2.66e-12 kip-in**.
  Six unsupported/dependent configurations are rejected, including zero-load
  mechanisms; on a horizontal beam, a pin plus a horizontal-normal roller does
  not prevent rigid rotation.
- Tests also compare a separate Lagrange-multiplier system, individual nodal and
  uniform member load patterns, coordinate/normal-sign/scaling invariance and
  existing global-axis production supports. Keep global bilateral spring axes
  unchanged and separate their external `-k*d` reactions from rigid reactions.
  Quadratic-energy identities refer only to the equivalent nodal system, not
  total distributed-load strain-energy recovery.
- Production integration remains a separate unchecked TODO: sparse node-local
  transformations, constraint-aware stability/rigid-body checks, member recovery,
  reaction metadata, persistence/migration, staged UI and MCP, drawing/reporting,
  conversion/transform semantics and worker/snapshot validation. Proposed angle
  convention: roller tangent counterclockwise from global +X, in degrees.
  Inclined supports are still unavailable; P-Delta, spatial/released frames and
  imposed movements are outside this checkpoint. Solver-method work stays on hold.
- Locked PyNite **3.0.0** / Qt **6.11.2**: **256 focused engineering/support tests**,
  no skips, **4.950 s**. Installed PyNite **3.2.1** / Qt **6.12.0**: **11 new tests**,
  no skips, **0.187 s**. Docs/tooling: **16 tests**, **0.487 s**. Ownership checks
  cover **150 classes / nine groups**. Strict docs/local links cover **55 HTML
  pages**; browser checks pass for images, search, subpath, dark mode and layout.
  Reproduce the bounded numeric report with
  `scripts/benchmark_inclined_supports.py`.

## Post-RC4 Nonuniform Membrane Validation Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. This is a test/documentation
checkpoint; no production solver, UI, file format, public tag or RC4 artifact changes.

- Add two independent zero-body-force Airy plane-stress references: pure in-plane
  bending and mixed nonuniform normal/shear stress on a 120 × 80 × 0.8 in rectangle.
  Integrate edge tractions consistently, retaining the exact force/end-moment
  resultants. Only three in-plane scalar restraints remove rigid motions;
  normal-displacement edge supports suppress bending. An off-plane corner frame
  anchor carries zero load; no solved displacement is prescribed.
- Solve the unchanged application path on **6/24/96/384 Quad** meshes in **XY/XZ/YZ**,
  with Service, -2 Reverse and Zero combinations: **24 solves / 72 result records**.
  Every combination passes the existing independent six-component equilibrium
  gate. Displacement and symmetric stress-tensor L2 errors use 3 × 3 Gauss
  integration; compare external work/2 with independent closed-form strain energy.
  All three errors decrease monotonically. Fine-mesh Service errors are:

  | Field | Displacement L2 | Stress-tensor L2 | Strain energy |
  | --- | --- | --- | --- |
  | In-plane bending | 0.2804% | 3.9081% | 0.1785% |
  | Mixed normal/shear | 0.3064% | 3.1585% | 0.1047% |

- Independently check constitutive compatibility, stress divergence, energy and
  rigid-mode gauges. Cover translated origins, alternate Poisson ratio, canonical
  unit metadata, file round-trips and unchanged input definitions. Confirm that
  nonzero continuum spin coexists with zero independent nodal drilling rotation;
  these membrane checks do not validate frame–shell rotational interfaces.
- Locked PyNite **3.0.0** / Qt **6.11.2**: **121 surface tests**, no skips,
  **58.506 s**. Installed PyNite **3.2.1** / Qt **6.12.0**: the **five new tests**
  pass without skips in **32.869 s**. Docs/tooling: **16 tests**, **0.474 s**;
  ownership checks cover **149 classes / nine groups**. Strict docs/local links
  cover **55 HTML pages**; browser checks pass for images, search, GitHub Pages
  subpath, dark mode and desktop layout. Reproduce the report/figure with
  `scripts/benchmark_nonuniform_membrane.py`; the guide includes the convergence plot.
- General wall/diaphragm behaviour, corner stress peaks, drilling treatment and
  rotational interface validation remain pending. The separate lateral drilling
  case is still rejected under refinement. Quad shear stays withheld; no stiffness
  or acceptance tolerance is changed. Solver-method implementation stays on hold.

## Post-RC4 Spatial Translational Release Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. Implementation commit
**5bef8ad**. This extends the existing linear adapter; solver-method work stays
on hold and RC4 release artifacts are unchanged.

- Add start/end local DX/DY/DZ releases alongside RX/RY/RZ. Validate boolean flags,
  forbid releasing axial DX or torsional RX at both ends and internally singular bending patterns,
  and retain global mechanism checks. Translations never enter the unused-rotation
  coordinate gauge; unsupported disconnected joint translations remain rejected.
- Recover eliminated member-side motions from the uncondensed linear stiffness
  and fixed-end vector. Check every recovered released-end force/moment equation,
  every free physical joint equation and all six global balances for each combination.
  Independent axial/Euler–Bernoulli flexibility checks cover either end, both
  planes, partial/varying/point loads, oblique/vertical/reversed axes, roll,
  signed/zero combinations, springs/other incident members, splitting and transport.
  Deliberately corrupted recovery must fail before its result is used.
- Expose staged Properties, Model Tables, bulk and atomic MCP editing, viewport
  labels/deformed member paths, local end translations in Properties/reports and
  paginated `released_end_translations` metadata in MCP member reads. Preserve unit-
  only snapshots, undo and invalid-batch rollback. Extend 2D-to-3D conversion to
  axial/shear releases with independent source windows and field/reaction parity.
- Spatial files advance to **v32**; older versions retain connected translations.
  Reject old-version nonfalse flags, missing required fields and malformed flags.
  Planar files stay v25 and plate files stay v3. Add **3D Fixed-Guided Beam -
  Translational End Releases**, with an independently checked 204 in sliding-end
  beam. Recovered Service end DX/DY/DZ are **+0.000139324 / -0.00487912 /
  -0.0975823 in**, while both joints have zero translation.
- Full source suite with MCP: **966 tests**, no skips, **215.315 s**; 148 classes
  belong to nine groups. Independently installed locked wheel: **58 focused tests**,
  no skips, **3.892 s**. Strict docs/local links cover **55 HTML pages**; documentation
  browser QA, offline spatial viewport QA and wheel/source audits pass.
  A second installed runtime using PyNite **3.2.1** / Qt **6.12.0** passes **23**
  focused numerical/connection/UI checks, no skips, **2.934 s**.
- [Native standalone run 40909523162](https://github.com/praksharma/PyniteGUI/actions/runs/40909523162)
  passes on Windows Server 2025 x86_64, Ubuntu 22.04/glibc 2.35 x86_64 and macOS
  15.8.2 arm64, with Python 3.12.16 / Qt 6.11.2 / PyNite 3.0.0. Each relocated app
  passes seven native check stages covering **28 examples**, including actual
  translational-release worker/control/diagram checks, plate worker, PDF and
  authenticated MCP. Native screenshots were inspected; downloaded archives match
  their SHA256SUMS. The guide includes the actual Linux release-control screenshot.
- Released P-Delta, frame/surface coupling, nonlinear connections and translational
  coordinate gauges remain unavailable. Standalone signing/installers and human
  platform gates remain open; no new public release or PyPI upload was made.

## Post-RC4 Native Windows/Linux Packaging Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. Source commit **15bbfa7**;
[native validation run 40861868669](https://github.com/praksharma/PyniteGUI/actions/runs/40861868669)
passes on all three operating systems. These temporary Actions artifacts do not
publish a release, create a tag or upload to PyPI. RC4 remains unchanged.

| Native host | Architecture | Portable archive | Size |
| --- | --- | --- | --- |
| Windows Server 2025, 10.0.26100 | x86_64 | ZIP containing `Brecon/Brecon.exe` and `_internal` | 281.1 MiB |
| Ubuntu 22.04, Linux 6.8.0-1070-azure, glibc 2.35 | x86_64 | tar.gz containing `Brecon/Brecon` and `_internal` | 301.8 MiB |
| macOS 15.7.9 | arm64 | ZIP containing `Brecon.app` | 228.3 MiB |

- Build on each native host using Python **3.12.16**, locked Qt **6.11.2** /
  PyNite **3.0.0**, PyInstaller **6.22.3** and hooks **2026.9**. Pin platform-specific
  build dependencies, render the existing mark as Windows ICO/macOS ICNS/Linux
  PNG, record host/architecture/libc and keep the reviewed wheel/source identity.
  macOS/Linux archives preserve symlinks; Linux also preserves executable modes.
- Verify wheel/source metadata, assets and recipe bytes before freezing. Verify
  archive SHA-256 before extraction. Launch from a new directory with PYTHONHOME,
  PYTHONPATH and VIRTUAL_ENV removed and PATH limited to system locations; audit
  the exact reported executable, bundled imports, notices/source hash, WebEngine
  helper and version metadata. Retain the macOS ad-hoc signature check.
- All three frozen apps pass the six check stages: **27 examples** each through
  save/open/analyze/export, spawned released-member analysis with hidden All tools
  Results retained, offline WebEngine/PNG, Qt PDF output, spawned plate analysis/
  local inspection/Matplotlib PNG and authenticated MCP schema/edit/solve/results.
  Saved native-window, viewport and plate images were inspected; downloaded
  archives match their SHA256SUMS. Retain JSON, images, PDF, dependency/build record and
  corresponding source with the artifacts. Actions retention is **14 days**.
- Native packaging/tooling tests: **27** on each host; Windows omits two explicitly
  POSIX-only symlink/mode tests. Linux and macOS have no skips. The initial native
  run caught a missing Linux XCB shape library and case-sensitive lookup after
  copying the Windows environment; both are fixed, with a Windows regression test.
  Local packaging/tooling/docs tests, strict documentation/link checks across
  **55 HTML pages**, browser documentation QA and wheel/source audits pass.
- CI uses software graphics, with Xvfb on Linux; it does not validate consumer
  Windows versions, every Linux distribution, Wayland/GPU drivers, native file
  pickers or printing to physical devices. Windows/Linux previews are unsigned;
  macOS remains ad-hoc signed. Public installers, signing/notarization,
  SmartScreen/Finder quarantine and human platform feedback remain release gates.

## Post-RC4 Desktop Packaging Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. This work creates local macOS
development artifacts and a manually dispatched artifact-only build workflow;
it does not create a release tag, publish a release or upload to PyPI.

- Build an architecture-specific `Brecon.app` from the reviewed installed wheel
  and corresponding source archive, with PyInstaller 6.22.3 / hooks 2026.9 and
  a fresh locked runtime. Reject editable/stale installations, source/recipe
  mismatches and runtime drift. Include the existing vector mark as the app icon,
  distribution metadata/licenses, AGPL/citation files, source archive and dependency/
  wheel/source-hash provenance. Derive the minimum macOS bound from Python and
  native wheel tags without claiming manual coverage of that lower bound.
- Archive with symlink-preserving `ditto`; retain SHA256SUMS and build-info.json.
  Extract the ZIP to a different location and run the embedded desktop check
  with Python paths removed and PATH limited to system utilities. Audit resources,
  symlinks, corresponding-source hash and the ad-hoc signature separately.
- The frozen check covers all 27 examples through save/open/analyze/export,
  spawned frame/released-member and plate workers, actual offline Qt WebEngine
  and PNG export, Matplotlib/local plate inspection, Qt PDF output and authenticated
  MCP schema/edit/background-analysis/result reads. It uses disposable settings
  and writes a record plus native/plot/PDF evidence for that exact executable.
- The packaging exercise exposed a real native WebEngine/MCP transition crash
  under both Qt 6.11.2 and 6.12, including the regular installed application.
  Replace the application-wide Python input filter with a bounded set on known
  editor widgets/actions, refresh after edits and remove on unlock. The original
  native reproduction now completes with input/shortcut protections retained.
- Verified locally on macOS 27.2 arm64, Python 3.12.13, locked PyNite 3.0.0 /
  Qt 6.11.2. The relocated frozen app completes every check, including the plate-
  to-MCP transition, and passes the bundle/source/signature audit. Native
  screenshots and plate/PDF exports were inspected. The archive is about 228 MiB;
  its exact identity is recorded in its SHA256SUMS and embedded build-info.json.
- Full source suite with MCP: **948 tests**, no skips, **252.752 s**. The
  independently installed wheel using the exact locked bundle dependencies:
  **948 tests**, no skips, **272.837 s**. Test ownership: 147 classes in nine
  groups. Final focused input-filter/packaging/tooling checks pass. The native
  crash reproduction also passes with the repaired code under Qt 6.12.
  Strict documentation/link checks cover 55 HTML pages and browser QA passes.
  Wheel/source audits include all desktop recipes, scripts, tests and workflow.
- At this earlier checkpoint, Developer ID signing, notarization, Finder/quarantine
  handling, Intel and Windows/Linux artifacts were unverified. The preview has an ad-hoc
  signature and must not be presented as a notarized public installer.

## Post-RC4 Spatial Rotational Release Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. This checkpoint does not
publish RC5 or alter the immutable RC4 artifacts.

- Add local RX/RY/RZ start/end frame releases for Linear elastic spatial models
  without surfaces, with staged inspector/table/bulk/MCP editing, definition
  reports, endpoint labels and an inclined biaxial beam example. One RX end may
  release torsion; releasing both is rejected. Translational releases, released
  P-Delta and released frame/surface interfaces remain unsupported.
- Compute oblique/rolled unused joint-rotation bases, verify K G = 0 and
  Gᵀ(P − FER) = 0, and use a numerical coordinate gauge equivalent to eliminating
  those coordinates. Physical supports/springs are unchanged. Real connection
  mechanisms, nearly dependent axes and unresisted moments are rejected.
  Verify every free physical equation and whole-model equilibrium for every
  combination before accepting a snapshot.
- Recover local member-side end motion from PyNite's uncondensed matrices.
  Properties shows local RY/RZ end slopes separately from undefined global joint
  components, which remain n/a in tables/CSV/MCP. MCP exposes page-scoped global
  unused-rotation directions. Free uniform torsional angles are not unique.
- Spatial files advance to v30 with strict release fields and legacy migration.
  Explicit 2D-to-3D conversion now preserves rotationally released frames,
  including Gerber/three-hinged arch response; translational releases still block
  conversion. There are 27 built-in examples; upstream coverage stays nine of 20.
- Independent references cover biaxial beam moments/deflections/end slopes,
  fixed-pinned internal hinges, free-tip releases, point torque, signed/zero
  combinations, roll and oblique/reversed/vertical axes, springs, mixed incident
  connections and actual mechanisms. Fault injection verifies rejection of an
  entire snapshot when only a later combination has bad physical equations or
  reactions. Native installed-wheel checks use the actual background worker and
  preserve hidden Results in All tools. A visually inspected native screenshot
  documents the new controls and recovered slopes.
- Full locked suite with MCP: **939 tests**, no skips, **249.353 s**. The
  independently installed wheel with PyNite 3.2 / Qt 6.12 passes **939 tests**,
  no skips, **277.210 s**. After adding the later-combination fault-injection
  regression, all **11 release benchmarks** pass in both environments. Test
  ownership: 146 classes in nine groups. Offline frame viewport QA and strict
  documentation/link/browser checks pass, including the new native screenshot;
  the site contains 55 HTML pages. Installed smoke checks pass all 27 examples
  through save/open/analyze/export plus authenticated MCP discovery/edit/undo.
  Final wheel/source audits pass and all packaged runtime bytes match the tested
  independent installation. Human platform gates remain open.

## Post-RC4 Plate Inspection Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-29. The published RC4 assets and
plate input/file schemas remain unchanged; this does not publish RC5.

- Add a modeless separate-plate inspector with element-centre table, explicit
  element/natural-coordinate probes, material-face picking and linked outline/
  cross marker. Opening holes and pan/zoom gestures do not change selection.
  Read signed Mx/My/Mxy and corrected Rect Qx/Qy with units, global coordinates,
  local axes and combination/snapshot identity. Quad shear remains unavailable;
  no general membrane or combined face-stress analysis is enabled.
- Accepted worker snapshots retain compact local recovery data, rather than a
  live solver. Probes use the corrected Rect polynomial or the engine's exact
  within-element bilinear Quad moment field without another solve. Compare
  off-centre/corner probes against explicit polynomial derivatives and actual
  solved elements, including non-square XY/XZ/YZ plates, origins, openings,
  signed/zero combinations and process serialization. Corner peaks remain unverified.
- Export all centres or one probe as CSV with xi/eta, local/global coordinates,
  units, axes, family/recovery description, case factors, snapshot/time/signature.
  Combination and display-unit changes retain the selection and snapshot;
  engineering edits/re-analysis clear inspection and disable stale exports.
- Focused surfaces: **116 tests**, **26.094 s**. Full locked suite with MCP:
  **925 tests**, no skips, **243.636 s**. The independently installed development
  wheel with PyNite 3.2 / Qt 6.12 passes **925 tests**, no skips, **270.692 s**.
  Test ownership: 144 classes in 9 groups.
- Automated native macOS checks use the independently installed wheel and actual
  worker: face picking, off-centre inspection, selected combination, both CSVs,
  unit retention and stale-result clearing pass. The guide includes an inspected
  native screenshot. Strict documentation/link checks cover 55 HTML pages;
  browser QA covers the new image, search, subpath and dark mode. Human platform
  gates remain separate. This batch changes no Three.js viewport assets.

## Post-RC4 Coupled Validation Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-28. This source checkpoint does
not create an RC5 tag or replace the published RC4 assets.

- Solve applied-traction membrane patches against independent plane-stress
  displacement/stress formulas, rather than prescribing the solution. Cover a
  non-square 120 × 80 in rectangle in XY/XZ/YZ, three mesh sizes, signed/zero
  combinations, uniaxial Poisson contraction and pure shear. Numerical errors
  remain below the explicit 1e-10 in / 1e-9 ksi regression bounds.
- Verify load transfer in both directions between a coincident beam and a nu=0
  slender slab strip: pressure on the slab and equivalent member line loading.
  Independent narrow-strip EI-sum references cover three stiffness ratios and
  refinement. Fine-mesh maxima: **0.0781%** displacement-field error relative to
  reference peak, **0.2587%** beam midspan moment error, **0.1338%** slab Mx L2
  error. These are bounded flat-strip checks, not general diaphragm/composite
  or eccentric-connection validation. PyNite 3.0 and 3.2 reproduce these values.
- Quantify the lateral weak-drilling limitation independently: external MY
  residuals of about **0.296 / 0.604 / 1.046 kip-in** on 12/48/192 slab elements
  agree with summed weak local drilling torque. All three actual application
  solves reject the result using unchanged equilibrium limits. No stiffness
  substitution or tolerance relaxation is introduced; Quad shear stays withheld.
- Correct coupled YZ outer-edge support and contour/probe coordinates to the
  upstream width-Z / height-Y convention, sharing the mapping with rectangle
  placement. Non-square, notch, remesh and off-centre native probe regressions
  prevent the square-fixture blind spot. No file-format change; review YZ edge
  assignments saved by earlier development builds.
- Focused surfaces: **110 tests**, **21.360 s**. Full locked suite with MCP:
  **919 tests**, no skips, **237.281 s**. An independently installed development
  wheel with PyNite 3.2 / Qt 6.12 also passes **919 tests**, no skips,
  **262.552 s**. Test ownership: 143 classes in 9 groups.
- Automated native macOS checks use the installed development wheel, actual
  analysis worker, corrected YZ support preview/plot and the retained All tools
  hidden-Results behaviour. They do not replace human OS-dialog/platform gates.
  Strict docs/link checking covers 55 HTML pages; documentation browser and
  offline mesh viewport checks pass. The guide includes a reproducible numeric
  report command and inspected scientific convergence figure.

## Post-RC4 Plate Loading Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-28. No new release tag or registry
upload is created by this checkpoint; the published RC4 files remain immutable.

- The separate rectangular plate tool supports up to 32 uniform pressure cases
  and 32 combinations. Its original primary-case Plate combination remains the
  baseline; named combinations mix cases. A staged editor handles pressures,
  factor maps, reference-preserving case renames and horizontal self-weight.
- Opt-in self-weight uses material weight density and global -Y. XZ plates carry
  the complete gravity as normal pressure, factored through its selected case.
  XY/YZ membrane gravity is rejected. Openings remove both pressure and weight.
  This does not enable general membrane, curved shells or a nonlinear solver.
- Every combination must have finite results and pass six-component global
  force/moment equilibrium before any snapshot is accepted. Cached selection,
  unit-only changes and their undo/redo preserve snapshot identity; engineering
  edits clear results. CSV and plot titles identify the selected combination and
  snapshot. Quad shear remains withheld; corrected Rect shear is separate.
- Plate files advance to version 3 with strict loading fields. Version 1/2 files
  migrate without adding cases or gravity. Frame/spatial file formats are unchanged.
- Independent checks cover signed/zero-result superposition for both element
  families in every plane, self-weight/Navier deflection within 1% on the chosen
  fine mesh, off-centre opening force/first-moment balance, migration and whole-
  snapshot rejection after force, moment or nonfinite errors. Native checks cover
  the worker, four combinations, staged controls, unit retention and CSV export.
- Full locked suite: **912 tests**, no skips, **220.145 s**. Installed development
  wheel with PyNite 3.2 / Qt 6.12: **912 tests**, no skips, **242.787 s**.
  Focused surfaces: **103 tests** passed. Test ownership: 142 classes in 9 groups.
  Strict documentation build/link checks cover 55 HTML pages; browser QA verifies
  new screenshots, navigation, search, GitHub Pages subpath and dark mode.
- Native screenshots document the actual plate controls and selected-combination
  moment plot. Development wheel/source metadata and contents are audited.
  Stable 1.0 platform/manual feedback gates remain open.

## Post-RC4 Coupled Slab Inspection Checkpoint

Development **1.0.0rc5.dev0**, checked 2026-10-28; no RC5 tag or PyPI upload is
created by this checkpoint. The RC4 assets remain unchanged.

- The existing Results dock now has local rectangular Quad moment/membrane-stress
  contours, element/natural-coordinate probes, axes, combination/unit/snapshot
  labels, provenance CSV and paginated MCP surface-element reads.
- Geometry-owned outer-edge global rigid restraints have presets/custom DOFs,
  staged preview, shared-joint unions, spring-conflict rejection, remesh/lifecycle
  handling, undo, viewport/report display and MCP editing. Spatial version 28
  migrates old files with empty edge assignments; frame/slab coupling remains opt-in.
- Manufactured constant-strain/curvature recovery checks cover all three planes.
  An independently referenced thin square plate has fine interior moment errors
  below 0.6% and peak-deflection error below 0.01%; all meshes pass equilibrium.
  This bounded check does not validate general membrane/drilling response or
  corner peaks. The existing all-combination equilibrium gate remains strict.
- Raw Quad Qx/Qy has about 59% relative L2 error on the fine Navier check in both
  PyNite 3.0 and 3.2. Do not publish those numbers: coupled outputs omit them,
  plate-pilot Quad shear choices are disabled, and its `shears` payload is None.
  Rect shear recovery is separate. Reproduce with
  `scripts/benchmark_coupled_surfaces.py --output /tmp/coupled-plate.json`.
- Full locked Python suite: **902 tests**, no skips, **219.723 s**.
  Installed development wheel with PyNite 3.2 / Qt 6.12: **902 tests**, no skips,
  **245.163 s**. Final UI checks: 184 tests; focused recovery-error clearing and
  export re-enabling: 5 tests. Test ownership: 141 classes in 9 groups.
- Native macOS checks verified the slab tab, table/contour/probe, global edge
  presets and staged preview in the real desktop window. Light/dark result plots
  and the new documentation screenshots were visually inspected. Offline surface
  viewport QA includes support visibility/pixels, mesh families, picking/box
  selection and bounded resources. Strict docs: 55 HTML pages; browser QA passed
  screenshots, search, navigation, GitHub Pages subpath and dark mode.
- Wheel/source contents and metadata are audited. Platform/manual prerelease
  feedback gates remain open; this is not a stable 1.0 certification.

## Post-RC4 Plate Recovery Validation

Unreleased **1.0.0rc5.dev0**, verified 2026-10-28. The published RC4 files and
tags are unchanged; the known limitation above applies to that release.

- **892 tests passed without skips** in the locked environment (202.900 seconds,
  PyNiteFEA 3.0.0 / Qt 6.11.2) and the isolated development wheel (228.243 seconds,
  PyNiteFEA 3.2.0 / Qt 6.12.0), including real MCP wire tests.
- The affected surface group passed **85 tests**, including the Rect subprocess
  solve and signed SI contour-array checks. New engineering tests cover intact
  Navier equivalence, independent Ritz basis convergence, opening deflection and
  patch moments, polynomial/rigid fields, mixed derivatives, cantilever strips,
  mesh refinement and plane/origin/factor invariance. Rect bending modifiers are
  rejected while their recipe/preview compatibility is retained.
- In the documented 512-element opening case, opening-edge deflection errors
  against the 13×13-mode reference are **0.214% Quad / 0.085% Rect**. Largest
  material-patch mean moment errors are **0.636% / 0.398%** respectively. The
  11→13-mode reference patch-moment change is at most **0.158%**. These are
  observed bounded-case comparisons, not universal element accuracy guarantees.
- `scripts/benchmark_plate_recovery.py` produces the numerical JSON record and
  standalone figure. Strict docs/link checks cover the new illustration and
  scope limits; the source/wheel audit includes the new recovery module, tests
  and reproducible benchmark script.

## RC4 Release Validation

First Brecon release, **1.0.0rc4**, prepared 2026-10-28 on macOS 27.2 arm64 /
Python 3.12.13. Publication is explicitly authorized; this is a prerelease,
with the stable-1.0 platform and independent-feedback gates still open.

- Full locked suite: **882 tests passed**, no skips (200.177 seconds), including
  real MCP wire tests. Qt 6.11.2, PyNiteFEA 3.0.0, Matplotlib 3.11.1,
  NumPy 2.5.3, SciPy 1.18.1, MCP 2.3.0.
- Full installed-wheel suite: **882 tests passed**, no skips (228.083 seconds).
  Qt 6.12.0, PyNiteFEA 3.2.0, Matplotlib 3.11.2, NumPy 2.5.4, SciPy 1.18.1,
  MCP 2.3.0. Final runtime files match the fully tested wheel byte for byte.
- Fresh base/MCP profiles verify the final wheel, both launch commands and all
  **26 examples** through save/open/analyze/export and native-window startup.
  MCP verifies Brecon identity/version, authenticated discovery, atomic edit,
  undo and server shutdown. Isolated uv-tool installation checks both commands.
- Both viewport suites pass against installed Brecon assets: spatial frame
  editing/results/probes and all seven mesh families, mixed/surface-only scenes,
  picking, context recovery and resource limits. Headless Chromium uses
  SwiftShader; hardware evidence comes from the native check below.
- The visible installed RC4 Cocoa run recorded in the rename validation passed
  all workflows with ANGLE Metal / Apple M4 Max; its runtime is unchanged in the
  release build. Human OS-dialog confirmation remains the earlier RC3 evidence,
  not a new RC4 manual certification. Linux/Windows RC4 workflows are unverified.
- Strict docs/local links pass across **55 HTML pages**; documentation browser QA
  covers images, search, existing Pages subpath, dark mode and layout. Source
  audit includes the publishing workflow and executable Brecon-only gate tests.
- The release carries a wheel, source archive and SHA256SUMS. GitHub and PyPI
  receive the same audited files; the workflow verifies tag/version, Brecon
  metadata and hashes before the environment-gated upload, without rebuilding.
- Publication completed through workflow 40713196939 after the owner's required
  `pypi` environment review. Public PyPI metadata and both artifact hashes match
  the reviewed build. A fresh installation from `https://pypi.org/simple`
  verifies the canonical and compatibility commands. This post-publication
  record does not move the sealed tag or replace its release artifacts.

## Brecon Rename Validation

Development **1.0.0rc4**, 2026-10-28. This is a source/package rename, not a
new published release. Existing RC1/RC2/RC3 tags and assets remain unchanged.

- **258 focused tests passed** without skips: UI, MCP, recovery compatibility,
  release metadata, documentation and tooling. A regression checks that the
  Brecon identity uses the original recovery path; version checks cover both
  entry modules, and real wire checks read both MCP reference URIs.
- Fresh independent base/MCP wheels passed all **26 examples** through
  save/open/analyze/export, native-window startup, canonical `brecon` and legacy
  `pynitegui` version commands. MCP identifies itself as Brecon and passes
  authenticated discovery, atomic edit, undo and shutdown.
- An isolated local-wheel uv-tool installation creates both commands, each
  reporting **Brecon 1.0.0rc4**, without changing user tools/PATH.
- Visible installed-wheel Cocoa checks passed previews/generators/arrays,
  undo/redo, save/reopen with supplied paths, background solves, station queries,
  CSV/PDF/report preview, both official spatial frames and MCP lock/unlock.
  Runtime: macOS 27.2 arm64, Python 3.12.13, Qt 6.12.0, ANGLE Metal / Apple M4 Max.
  These automated checks do not replace human OS-dialog/platform verification;
  the previous RC3 owner confirmation below remains historical evidence.
- Strict documentation/link checks passed across **55 HTML pages**. Browser QA
  checks the new SVG wordmark, refreshed About/Help screenshots, search, retained
  GitHub Pages subpath, dark mode and desktop layout. Its stale pre-coupled-slab
  search assertion now checks the current page title and experimental scope.
- Wheel/source audit checks both Python namespaces, both console commands,
  metadata, runtime assets, sources, citations and the new wordmark, with hashes.
  The initial rename validated both tag identities; the later Brecon-only
  publishing gate accepts `brecon` and rejects old `pynitegui` and mismatched
  tags in executable regression tests. No remote publishing was performed.

## RC3 Validation Record

RC3 adds named groups/levels, scoped envelope summaries,
continuous-segment governing-location queries, previewed transforms/generators/
node merging, and independent material G with two official spatial frames.
New project saves use formats 25/26; older files migrate without changing their
physics, and older applications reject new formats. Surface/plate recipes remain
derived-G only. Stable 1.0 platform/feedback gates remain separate.

Verified on macOS 27.2 arm64 / Python 3.12.13, 2026-10-27–28:

- Locked environment: **879 tests passed**, no skips (192.827 seconds), including
  real MCP wire checks. Qt 6.11.2, PyNiteFEA 3.0.0, Matplotlib 3.11.1,
  NumPy 2.5.3, SciPy 1.18.1, MCP 2.3.0.
- Fresh non-editable MCP wheel: **879 tests passed**, no skips (192.374 seconds),
  with Qt 6.12.0,
  PyNiteFEA 3.2.0, Matplotlib 3.11.2, NumPy 2.5.4, SciPy 1.18.1 and MCP 2.3.0.
  These are observed dependency versions, not a guarantee for future releases.
- Separate base/MCP profiles passed all **26 examples** through save/open,
  analysis and CSV/report export. MCP also passed authenticated SDK discovery,
  atomic edit, undo and server shutdown. Final artifacts are audited against
  the tagged source, including the repeatable desktop smoke script.
- An isolated local-wheel `uv tool install` passed; the generated entry point
  reports **1.0.0rc3**. User tools and PATH were not changed.
- Both offline viewport suites passed against installed-wheel assets, covering
  frame results/probes and all seven mesh families, mixed scenes, picking,
  context recovery and resource limits. Chromium used SwiftShader; this is
  separate from the native hardware check below.
- The visible installed-wheel Cocoa check passed generator/array previews and
  apply, undo/redo, save/reopen with supplied paths, worker analysis, governing
  stations, CSV/PDF and native report preview, both official spatial frames,
  deformation/torsion and MCP lock/unlock/shutdown on an ephemeral port.
  Diagnostics report WebGL 2.0, ANGLE Metal, **Apple M4 Max**, context not lost.
  `scripts/smoke_desktop.py` records screenshots, versions and renderer details.
- Native validation found an analysis teardown race: the finished signal can
  precede deferred Python worker cleanup; deleting its QThread then blocked the
  GUI while that cleanup waited for the GIL. Frame and plate windows now poll a
  nonblocking join before deletion/control handover. A delayed-cleanup regression
  covers both workspaces; the complete native workflow passes with the fix.
- Strict documentation build and local-link/image/anchor checks passed across
  **55 HTML pages**; documentation/tooling/release checks also pass. Pages was
  switched to Actions: [run 40602180800](https://github.com/praksharma/PyniteGUI/actions/runs/40602180800)
  successfully deployed commit 953dc9a, with live content verified for modelling
  tools, examples and current formats.

The native automated check used visible QtTest/application commands and supplied
file paths. After the desktop-control attachment timed out, the owner completed
the remaining human checks in that installed RC3 window on **2026-10-28**:
Save As/Open through the real pickers, F5 analysis and the interactive Print
Results dialog **all worked**. This confirmation arrived after the RC3 tag was
created and is recorded separately without moving the tag or replacing assets.
Linux and Windows visible installed-RC3 workflows are unverified. Those and
independent prerelease feedback remain stable-1.0 gates. The consolidation creates
an **unpublished draft** with wheel, source archive and SHA256SUMS; it does not
publish RC3 to GitHub or PyPI.

## RC2 Validation Record

Automated preparation verified on macOS 27.2 arm64 / Python 3.12.13,
2026-10-27:

- Locked editable environment: **831 tests passed**, no skips, including real
  MCP wire tests (175.986 seconds). Qt 6.11.2, Matplotlib 3.11.1, PyNiteFEA 3.0.0,
  NumPy 2.5.3, SciPy 1.18.1, MCP 2.3.0.
- Non-editable wheel in a fresh MCP environment: **831 tests passed**, no skips
  (202.407 seconds). Qt 6.12.0, Matplotlib 3.11.2, PyNiteFEA 3.2.0, NumPy 2.5.4,
  SciPy 1.18.1, MCP 2.3.0. These are observed dependency versions, not a promise
  about future releases.
- Base and MCP wheel profiles independently passed installed version/entrypoint,
  bundled assets, all **24 examples** save/open/analyze/export, and offscreen
  native-window checks. MCP also passed authenticated SDK discovery, a real
  atomic edit, undo and server shutdown.
- A real `uv tool install` of the local wheel passed with isolated temporary
  tool/bin directories. The generated `pynitegui --version` reports **1.0.0rc2**.
  User tool installations and PATH were not changed.
- Both offline viewport suites passed against installed-wheel assets: spatial
  frames/results/probes and all seven mesh families, mixed/surface-only scenes,
  picking, context recovery and bounded resources. Chromium used SwiftShader;
  these checks do not certify native Qt/WebEngine hardware rendering.
- Strict documentation build and local-link/image/anchor validation passed
  across **54 HTML pages**. Distribution audit verifies matching runtime assets,
  metadata, licenses, citation files and source contents, with SHA256SUMS.
- The first full run found an obsolete two-tab assertion in the spatial results
  dialog test. It now explicitly checks Member Detail, Compare Combinations,
  Storey Drift and Combination Envelopes. The focused six tests and both full
  reruns pass; no product behaviour was changed to satisfy the assertion.

Visible macOS inspection was attempted, but the UI automation attachment to the
installed Python window timed out. No visible-workflow gate is marked complete.
Visible installed-app checks on the claimed platforms and independent prerelease
feedback remain required before stable 1.0. Windows is currently unverified.
The automated validation above performed no tag/push, release publication,
PyPI upload or DOI deposit. Publication is a separate step from these checks.

## Historical RC1 Validation Record

Automated preparation verified on Linux x86_64 / Python 3.12.15, 2026-10-09:

- Locked editable environment: **628 tests passed**, no skips, including real MCP
  wire tests (160.753 seconds). Qt 6.11.2, Matplotlib 3.11.1, PyNiteFEA 3.0.0,
  MCP 2.3.0.
- Non-editable wheel, fresh dependency resolution outside the checkout:
  **628 tests passed**, no skips (198.200 seconds). Qt 6.12.0, Matplotlib 3.11.2,
  PyNiteFEA 3.2.0, MCP 2.3.0. These are recorded versions, not a guarantee for
  untested future dependency releases.
- Base and MCP wheel profiles separately passed installed version/entrypoint,
  bundled asset, 13-example save/open/analyze/export and offscreen native-window
  checks. The MCP profile also passed authenticated SDK discovery, version
  identity, a schema-valid atomic edit, undo and server shutdown.
- The README's `uv tool install` command was verified using temporary tool
  directories; `pynitegui --version` reports 1.0.0rc1 without loading Qt.
- Installed wheel viewport assets passed Chromium 151 / SwiftShader desktop
  pixels, framing, picking, gizmo, drawing/dragging, supports, overlays, PNG,
  dark-mode and context-loss checks. This is software-rendered browser QA,
  not visible native Qt/WebEngine hardware validation.
- Initial full-suite attempts were interrupted after accumulated inactive MCP
  application filters caused severe cross-window/test overhead. The filter is
  now installed only during exclusive control mode and removed on unlock/stop
  (commit 7ad23f2); its new lifecycle regression and both complete reruns pass.

Earlier Linux viewport/Wayland checks and the user-supplied macOS M4 Max smoke
test are useful history, not installed-RC certification. Visible installed-RC
Linux/macOS workflows still require manual verification. Windows and standalone
installers remain unverified. No tag, push, GitHub release or PyPI upload was made.
