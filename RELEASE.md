# Release Preparation

Target: **1.0.0rc1**, GitHub prerelease **v1.0.0rc1**. Nothing is published or
tagged by preparation scripts. PyPI and standalone installers are later steps.

## Build and Verify

From the repository root, with uv installed:

```sh
uv sync --locked --extra mcp
QT_QPA_PLATFORM=offscreen PYNITEGUI_NO_WEBENGINE=1 uv run --locked --extra mcp python -B -m unittest discover -s tests -q
uv build --no-sources
uv run --locked python -B scripts/check_dist.py dist/pynitegui-1.0.0rc1-py3-none-any.whl dist/pynitegui-1.0.0rc1.tar.gz
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
uv pip install --python /tmp/pynitegui-rc-base/bin/python ./dist/pynitegui-1.0.0rc1-py3-none-any.whl
cd /tmp
/tmp/pynitegui-rc-base/bin/python /absolute/path/to/PyniteGUI/scripts/smoke_installed.py --version 1.0.0rc1
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

## Publication Checklist

- [x] Current full suite passes with MCP wire tests enabled, not skipped.
- [x] Wheel/source archive audits and base/MCP installed-wheel smoke checks pass.
- [ ] Native Linux visible startup, 2D/3D editing, save/open, analysis, reports and MCP checked.
- [ ] Repeat installation and visible workflows on macOS; record OS/Python/Qt/renderer versions.
- [ ] Windows installation and visible workflows checked, or explicitly labelled unverified.
- [x] Release notes and limitations documented; artifact hashes generated in SHA256SUMS.
- [ ] User approves tagging/pushing and creating the GitHub prerelease.

Upload the wheel, source distribution and SHA256SUMS to the approved GitHub
prerelease, using CHANGELOG.md for notes. Tag the verified commit, not a moving
branch. GitHub also provides source archives for the tag. No PyPI upload is
performed here. For stable 1.0.0, update version/lockfile/notes, rebuild and repeat
validation rather than renaming RC artifacts.

## Validation Record

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
