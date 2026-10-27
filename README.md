# PyniteGUI

<img src="assets/PyniteGUI%20Structural%20Frame%20Logo.png" alt="PyniteGUI structural frame logo" width="420">

A desktop application for modeling and analyzing **2D/3D frames and axial-only
trusses**, built with Qt and the PyNite solver.

[Documentation](https://praksharma.github.io/PyniteGUI/) ·
[Releases](https://github.com/praksharma/PyniteGUI/releases) ·
[Examples](GUIDE.md#examples-and-appearance) ·
[Report an issue](https://github.com/praksharma/PyniteGUI/issues)

**Current release candidate: 1.0.0rc2.** See [validation and platform status](RELEASE.md)
for the tested configurations and remaining checks before stable 1.0.

## What You Can Do

- **Build a model:** draw frames and trusses, edit tables, assign materials and
  sections, and define supports, springs, planar member releases and load combinations.
- **Analyze:** linear elastic analysis and restricted frame-only P-Delta, with
  progress, cancellation, self-weight and unit-aware inputs.
- **Inspect results:** 2D/3D force diagrams, signed colour maps, exact member
  station probes, combination comparisons, envelopes and explicit storey drift.
- **Work comfortably:** Model/Results workspaces, SI/Imperial units, light/dark
  themes, undo/redo, autosave recovery, CSV and printable reports.
- **Learn and automate:** categorized examples with previews, adapted official
  PyNite examples, and an optional MCP server for controlling the open editor.

Surface meshing, rectangular plate analysis and coupled rectangular Quad slabs
are **experimental**. P-Delta keeps materials elastic and has model restrictions;
plastic, modal and reinforced-concrete nonlinear workflows are not implemented.
Read the [engineering scope](GUIDE.md#engineering-scope) before relying on results.

## Install and Run

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python
3.12+. uv can manage Python and the application's isolated environment.

**From a release wheel:** download the wheel from [Releases](https://github.com/praksharma/PyniteGUI/releases),
then install it from the download directory. For RC2:

```sh
uv tool install --python 3.12 ./pynitegui-1.0.0rc2-py3-none-any.whl
pynitegui
```

If the command is not found, run `uv tool update-shell` and reopen your terminal.
The wheel is a Python package, not a standalone desktop installer. PyPI
publication is planned; the commands above install a downloaded file.

**From this repository:**

```sh
uv python install 3.12
uv sync --managed-python
uv run pynitegui
```

Open **File > Examples** to browse ready-to-analyze models, or choose
**File > New 3D Frame**. If 3D graphics fail to start, launch with
`pynitegui --software-rendering` (or `uv run pynitegui --software-rendering`).

**Optional MCP:** use `uv run --extra mcp pynitegui` from the checkout, or install
`"./pynitegui-1.0.0rc2-py3-none-any.whl[mcp]"` with `uv tool install --python 3.12`.
Configure permissions, exclusive MCP mode and authentication in
**Tools > Automation Server**. See the [MCP guide](GUIDE.md#optional-mcp-automation).

## Screenshots

Main-canvas results with a signed shear map, exact station inspection and linked tables.

![Native results workspace showing a signed shear map and exact member values](docs/assets/screenshots/canvas-colour-results.png)

Spatial moment results with signed colours, units and member inspection.

![3D frame moment results in the offline viewport](docs/assets/screenshots/spatial-colour-results.png)

## Project Links

- [User and developer guide](GUIDE.md): workflows, limits, testing and documentation preview.
- [Changelog](CHANGELOG.md), [release checks](RELEASE.md) and [roadmap](TODO.md).
- [Citation and AI-use acknowledgement](CITATION.md): author/ORCID, development tools and release/commit citation.
- [License](LICENSE): GNU AGPL v3. PyNite is a separate upstream solver.
