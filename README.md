# PyniteGUI

<img src="assets/PyniteGUI%20Structural%20Frame%20Logo.png" alt="PyniteGUI structural frame logo" width="480">

A desktop editor for 2D frame and truss analysis, powered by PyNite and Qt.

Draw and edit frames or trusses, assign custom or library materials and sections, and apply point,
distributed, or automatic self-weight loads. Analyze combinations and inspect
reactions, deformed shapes, force diagrams, and envelopes across combinations. Supports
SI/Imperial units, light/dark themes, undo/redo, and autosave recovery.
Print selected model definitions, result tables, and force diagrams as a report.

## Quick Start

With Python 3.12+ and uv installed, run from this repository:

```sh
uv sync
uv run pynitegui
```

Try **File > Examples** to open a ready-to-analyze beam or frame.

## Screenshots

Frame editor with loads, deformed shape, and support reactions.

![Dark-mode frame editor with distributed loads and analysis results](assets/structure.png)

Whole-frame shear-force diagram.

![Shear-force diagram for a portal frame in dark mode](assets/SFD.png)

## More

- [User and developer guide](GUIDE.md): workflows, units, engineering scope, and tests.
- [Roadmap](TODO.md): completed and planned features.
- [Secondary ideas](TODO_SECONDARY.md): interface inspiration and PyNite-compatible extensions.
- [License](LICENSE): GNU AGPL v3.
