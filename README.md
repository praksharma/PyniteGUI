# PyniteGUI

<img src="assets/PyniteGUI%20Structural%20Frame%20Logo.png" alt="PyniteGUI structural frame logo" width="480">

A desktop editor for 2D/3D frames and axial-only trusses, powered by PyNite and Qt.
**1.0.0rc1** is available as a [GitHub prerelease](https://github.com/praksharma/PyniteGUI/releases/tag/v1.0.0rc1).
See the [release validation record](RELEASE.md).

Draw and edit frames or trusses, assign custom or library materials and sections, and apply point,
distributed, or automatic self-weight loads. Analyze combinations and inspect
reactions, deformed shapes, force diagrams, and envelopes across combinations. Supports
SI/Imperial units, light/dark themes, undo/redo, and autosave recovery.
Model elastic support springs and 2D member-end axial, shear, or moment releases.
Analysis shows progress phases and can be cancelled without losing valid results.
Print selected definitions, results, envelopes, and 2D/3D force diagrams as a report.
3D mode adds an offline orbitable viewport, XYZ work planes, six-direction supports
and loads, constrained node dragging, member roll, biaxial bending/torsion results,
and spatial deformation, with batched node/member rendering for larger models.

## Quick Start

With uv installed, run from this repository:

```sh
uv python install 3.12
uv sync --managed-python
uv run pynitegui
```

Try **File > Examples** to open a ready-to-analyze beam or frame.
Start a spatial model with **File > New 3D Frame**, use **Create 3D Copy** for an
existing unreleased 2D model, or try the **3D** examples.
If 3D graphics fail to start, launch with `uv run pynitegui --software-rendering`.

Current development includes **Tools > Surface Meshing (Experimental)** with
PyNite's seven generators, options, 3D previews and recipe/export files; rectangles
with openings support the separate plate-analysis workspace.
See [scope and limits](GUIDE.md#experimental-surface-meshing); these are not in the rc1 wheel.

For the release wheel, install the downloaded file without cloning:

```sh
uv tool install --python 3.12 ./pynitegui-1.0.0rc1-py3-none-any.whl
pynitegui
```

If the command is not on your PATH, run `uv tool update-shell` and reopen the terminal.

Optional MCP: use `uv run --extra mcp pynitegui` from the repository, or install
the wheel with `[mcp]` appended to its quoted path. Configure **Tools > Automation Server**.
Requires Python 3.12+; the wheel is not a standalone desktop installer.

## Screenshots

Frame editor with loads, deformed shape, and support reactions.

![Dark-mode frame editor with distributed loads and analysis results](assets/structure.png)

Whole-frame shear-force diagram.

![Shear-force diagram for a portal frame in dark mode](assets/SFD.png)

## More

- [User and developer guide](GUIDE.md): workflows, units, engineering scope, tests and performance benchmarks.
- [Roadmap](TODO.md): completed and planned features.
- [Release notes](CHANGELOG.md) and [release validation](RELEASE.md).
- [Secondary ideas](TODO_SECONDARY.md): interface inspiration and PyNite-compatible extensions.
- [License](LICENSE): GNU AGPL v3.
