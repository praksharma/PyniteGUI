# Release Preparation

Target: **1.0.0rc2**, GitHub tag **v1.0.0rc2**. Check
[GitHub Releases](https://github.com/praksharma/PyniteGUI/releases) for published
assets; source tags and unpublished drafts do not imply a public binary release.
Stable 1.0 promotion follows a feature freeze and verification of the actual
release artifacts. Standalone installers remain a later step.

## Build and Verify

From the repository root, with uv installed:

```sh
uv sync --locked --extra mcp
QT_QPA_PLATFORM=offscreen PYNITEGUI_NO_WEBENGINE=1 uv run --locked --extra mcp python -B -m unittest discover -s tests -q
uv build --no-sources
uv run --locked python -B scripts/check_dist.py dist/pynitegui-1.0.0rc2-py3-none-any.whl dist/pynitegui-1.0.0rc2.tar.gz
```

The distribution checker audits versions, metadata, bundled runtime assets,
licenses and source contents and writes `dist/SHA256SUMS` for these two artifacts.
The wheel must contain the offline viewport/vendor assets and both libraries.
The source archive also includes the lockfile, guide, release documents, tests,
scripts and README screenshots. Do not attach old-version artifacts.

Install the wheel into a fresh environment outside the checkout. Run the smoke
script with that environment's Python from a temporary working directory, not
with `uv run` in the repository (which would test the editable project instead).
Example POSIX commands; use the corresponding `Scripts/python.exe` on Windows:

```sh
uv venv --python 3.12 /tmp/pynitegui-rc-base
uv pip install --python /tmp/pynitegui-rc-base/bin/python ./dist/pynitegui-1.0.0rc2-py3-none-any.whl
cd /tmp
/tmp/pynitegui-rc-base/bin/python /absolute/path/to/PyniteGUI/scripts/smoke_installed.py --version 1.0.0rc2
```

Repeat in another fresh environment, installing the same wheel with `[mcp]`
and adding `--mcp` to the smoke command. The script checks that imports are not
editable, bundled assets are present, all examples save/open/analyze, exports
work and native windows initialize; the MCP variant also exercises a real local
SDK client and server lifecycle. It is not a visible desktop/WebGL smoke test.

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

## Publication Checklist

- [x] Project citation guidance and GitHub citation metadata added without a DOI.
- For each release, review CITATION.md/CITATION.cff and preserve exact version and
  commit links. Consider Zenodo concept/version DOI archiving for stable 1.0;
  archive later releases as new versions of the same record.
- [x] RC2 full suite passes with MCP wire tests enabled, not skipped.
- [x] RC2 wheel/source archive audits and base/MCP installed-wheel smoke checks pass.
- [ ] Native Linux visible startup, 2D/3D editing, save/open, analysis, reports and MCP checked.
- [ ] Repeat installation and visible workflows on macOS; record OS/Python/Qt/renderer versions.
- [ ] Windows installation and visible workflows checked, or explicitly labelled unverified.
- [x] RC2 release notes and limitations reviewed; artifact hashes generated in SHA256SUMS.
- [x] User approves tagging/pushing and creating an unpublished draft with assets.
- [ ] Owner reviews and publishes the GitHub prerelease.

Upload the wheel, source distribution and SHA256SUMS to the approved GitHub
prerelease, using CHANGELOG.md for notes. Tag the verified commit, not a moving
branch. GitHub also provides source archives for the tag. No PyPI upload is
performed here. For stable 1.0.0, update version/lockfile/notes, rebuild and repeat
validation rather than renaming RC artifacts.

## uv Tools and PyPI

uv installs tools from Python package indexes; PyPI is the intended public
distribution channel. The existing `pynitegui` entry point is sufficient.
A separate uv-specific package or registry submission is not needed.

After stable 1.0 is published to PyPI, users can run:

```sh
uv tool install --python 3.12 pynitegui
pynitegui
uv tool upgrade pynitegui
```

For optional MCP support, install `"pynitegui[mcp]"` instead. An RC published to
PyPI would require an explicit version, for example `"pynitegui==1.0.0rc2"`.
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
| PyPI project name | `pynitegui` |
| Owner | `praksharma` |
| Repository name | `PyniteGUI` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

A pending publisher creates the project on its first successful upload; it
does not reserve the name. If you already own the project, add this publisher
under that project's Publishing settings instead.

In GitHub repository Settings > Environments, create **pypi**, add yourself as
a required reviewer, allow your own review if you will dispatch the workflow,
and restrict deployment branches to **master**. No PyPI API-token secret is
needed. These account/environment changes are owner setup, not performed by
adding the workflow.

**Publish an approved release:** first publish the GitHub draft with its wheel,
source archive and SHA256SUMS attached. Then open Actions > **Publish to PyPI** >
Run workflow, choose **master**, and enter its tag (for example `v1.0.0rc2`).
Review and approve the **pypi** environment job. This uploads to real PyPI;
it is not a dry run. RC2 remains a prerelease and does not imply stable 1.0.

The workflow is manual only. Its read-only verification job checks out the
requested tag, rejects a version mismatch or draft release, downloads the exact
GitHub assets, checks both hashes, and audits them against the tagged source.
The separate environment-gated publication job has OIDC permission and uploads
those verified files without rebuilding. It does not run on pushes or tags.
Do not move existing release tags or replace reviewed release assets to retry.

References: [uv tools](https://docs.astral.sh/uv/guides/tools/) and
[building and publishing](https://docs.astral.sh/uv/guides/package/).

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
