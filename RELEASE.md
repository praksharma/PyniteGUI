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
slabs remain explicitly experimental. Nonlinear/plastic, modal, unilateral and
reinforced-concrete workflows are deferred. Remaining UI roadmap items do not
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
- Developer ID signing, notarization, Finder/quarantine handling, Intel and
  Windows/Linux desktop artifacts remain unverified. The preview has an ad-hoc
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
