# Changelog

## 1.0.0rc1 - Release Candidate

First release candidate for the frame-focused desktop application. Not yet
published; promote to 1.0.0 only after the release checklist is completed.

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
