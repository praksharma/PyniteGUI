# Brecon (`PyniteGUI`) Bug Analysis & Fix Report

- **Audited Commit:** `4f1ec33` (`master`, also verified against `origin/master` at `cad3811`)
- **Status:** All 9 bugs identified below are fixed and covered by automated regression tests in this Pull Request.
- **Scope:** Full static and dynamic analysis of `src/pynitegui/qt/` (2D/3D models, editors, post-processing dialogs, plate/mesh workspaces, bulk editing, modal/pushover windows, reports, and unit conversion pathways)
- **Verification Environment:** Headless Qt (`QT_QPA_PLATFORM=offscreen`, `PYNITEGUI_NO_WEBENGINE=1`), Python 3.12, PySide6 6.12.0, PyniteFEA

---

## Executive Summary

| ID | Severity | Status | Component | Summary |
| :--- | :--- | :--- | :--- | :--- |
| **BUG-01** | High | Fixed | Construction / Groups (`app.py`) | `MainWindow.construct_connection` (`Perpendicular Connection...` / `Connect Member Midpoints...`) fails to copy `candidate.groups`, silently dropping newly split member segments from saved groups. |
| **BUG-02** | High | Fixed | Post-Analysis Tools (`diagrams.py`, `spatial_diagrams.py`, `envelopes.py`, `deformation_animation.py`, `spatial_reports.py`) | Unhandled `KeyError`, `ValueError`, and cascading `AttributeError` crashes across post-processing tools on valid joint-spring-only models (including built-in examples `joint_spring_series`, `joint_spring_one_way`, and `3d_joint_spring_network`). |
| **BUG-03** | Medium | Fixed | Modal & Pushover Windows (`modal_window.py`, `pushover_window.py`) | `ModalWindow` and `PushoverWindow` cache `self.units` at initialization and never update unit labels, converted spinbox inputs, tables, or plots when project display units change. |
| **BUG-04** | Medium | Fixed | Modal & Pushover Lifecycle (`modal_window.py`, `pushover_window.py`) | `ModalWindow.refresh()` is triggered via `QUndoStack.indexChanged` during `MainWindow` teardown after child `QPushButton` C++ widgets are destroyed, raising `RuntimeError: Internal C++ object (PySide6.QtWidgets.QPushButton) already deleted`. |
| **BUG-05** | Medium | Fixed | 3D Identifiers (`spatial_model.py`, `model.py`, `model_tables.py`, `spatial_editor.py`, `app.py`, `joint_spring_editor.py`, `spatial_surfaces.py`) | Auto-generated node/member/load names do not reserve `project.surfaces` IDs (violating `validate_surfaces`), and default `"S"` prefixes for surfaces and joint springs do not check each other for collisions. |
| **BUG-06** | Medium | Fixed | 2D Geometry Operations (`model.py`) | `Project.split_member` and `Project.connect_intersections` mutate `self` in-place without transactional validation/rollback, and can leave the project corrupted with duplicate members. |
| **BUG-07** | Medium | Fixed | Plate & Mesh Workspaces (`plate_model.py`, `mesh_workspace.py`) | `PlateDefinition.validate()` computes element count and aspect ratio without accounting for `x_control`/`y_control`/`openings`, and `MeshWorkspace.analyze_rectangle()` does not catch `ValueError` from `transfer_rectangle()`. |
| **BUG-08** | Low | Fixed | Plate Workspace (`plate_workspace.py`, `plate_loads.py`) | `PlateWorkspace.configure_loading()` forces `self.apply()` before opening `PlateLoadsDialog`, locking the user out of the dialog when `Plane` is changed while `self_weight_case` is active. |
| **BUG-09** | Low | Fixed | Bulk Inspector (`bulk_edit.py`) | `populate_bulk_inspector()` disables all `Restrain *` checkboxes whenever `Support` is `"Keep existing"`, preventing bulk restraint edits even when all selected nodes already have `"custom"` or 3D `"inclined"` supports. |

---

## Detailed Bug Reports & Implemented Fixes

### BUG-01: `MainWindow.construct_connection` drops split member segments from saved groups

- **Severity:** High (silent model group corruption / loss of grouped members in isolated views)
- **Affected File:** `src/pynitegui/qt/app.py` (`MainWindow.construct_connection`)
- **Regression Test:** `tests/test_qt_construction.py` (`ConstructionWindowTests.test_connection_preserves_split_member_groups_in_2d_and_3d`)

#### Root Cause
When executing **Perpendicular Connection...** or **Connect Member Midpoints...**, `plan_connection()` clones the project into `candidate` and splits the target member(s) via `candidate._split_member(...)`. Inside `Project._split_member()` (`src/pynitegui/qt/model.py`), every group containing the original member is properly updated to include both replacement segments (`[first_name, second_name]`).

However, when `MainWindow.construct_connection()` committed `candidate` back into `self.project`, it only copied `nodes`, `members`, and `loads`:

```python
def mutate(project):
    candidate = plan.definition.clone()
    project.nodes, project.members, project.loads = candidate.nodes, candidate.members, candidate.loads
```

Because `project.groups = candidate.groups` was omitted (unlike `Project.subdivide_members` and `SpatialProject.split_member`), `project.groups` retained only the pre-split member list. The newly created second segment was silently dropped from all groups containing the split member, and immediately disappeared from the canvas if that group was isolated.

#### Reproduction (Pre-Fix)
```python
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QDialog
from pynitegui.qt.app import MainWindow
from pynitegui.qt.construction import ConnectionPreview
from pynitegui.qt.model import Project

app = QApplication.instance() or QApplication([])
w = MainWindow()
p = Project()
p.add_member((0.0, 0.0), (100.0, 0.0))  # M1
p.node_at(50.0, 50.0)                   # N3
p.groups["G1"] = {"nodes": ["N1", "N2"], "members": ["M1"]}
w.load_project(p)
w.select_many([("nodes", "N3"), ("members", "M1")])

with patch.object(ConnectionPreview, "exec", return_value=QDialog.DialogCode.Accepted):
    w.construct_connection("perpendicular")

print("Project members:", list(w.project.members))
print("Group G1 members:", w.project.groups["G1"]["members"])
```
- **Pre-Fix Output:** `Group G1 members: ['M1']` (`M2` missing)
- **Post-Fix Output:** `Group G1 members: ['M1', 'M2']`

#### Implemented Fix
Updated `MainWindow.construct_connection()` in `src/pynitegui/qt/app.py` to copy `candidate.groups` alongside `nodes`, `members`, and `loads`.

---

### BUG-02: Post-analysis dialogs and 3D diagram reports crash on joint-spring-only models

- **Severity:** High (unhandled exceptions on built-in example projects; persistent UI corruption of `MainWindow.refresh()`)
- **Affected Files:**
  - `src/pynitegui/qt/diagrams.py` (`DiagramDialog.update_member`, `inspect_distance`, `update_inspection`)
  - `src/pynitegui/qt/spatial_diagrams.py` (`SpatialDiagramDialog.redraw`, `inspect_distance`, `update_inspection`)
  - `src/pynitegui/qt/envelopes.py` (`EnvelopeWidget.inspect_distance`)
  - `src/pynitegui/qt/deformation_animation.py` (`static_paths`, `StaticDeformationDialog.rebuild`, `set_unit_system`)
  - `src/pynitegui/qt/spatial_reports.py` (`diagram_geometry`)
- **Regression Test:** `tests/test_qt_joint_springs.py` (`JointSpringEditorTests.test_joint_spring_only_postprocessing_dialogs_and_reports`)

#### Root Cause
Brecon supports memberless joint-spring network models (and ships three built-in examples: `joint_spring_series`, `joint_spring_one_way`, and `3d_joint_spring_network`). After running a valid static analysis on any such model, five post-processing components assumed `project.members` (or `paths`) was non-empty:

1. **2D Diagrams (`DiagramDialog` in `src/pynitegui/qt/diagrams.py`):**
   `self.member` (`QComboBox`) had no items, so `self.member.currentText()` was `""`. `update_member()` and `inspect_distance()` indexed `self.project.members[name]` directly, raising `KeyError: ''` as soon as the user clicked **Diagrams...**.
2. **3D Diagrams (`SpatialDiagramDialog` in `src/pynitegui/qt/spatial_diagrams.py`):**
   `redraw()` and `inspect_distance()` called `member_breaks(self.project, self.member.currentText())` with `""`, raising `KeyError: ''` when opening **Diagrams...** on `3d_joint_spring_network`.
3. **Envelope Inspector (`EnvelopeWidget.inspect_distance` in `src/pynitegui/qt/envelopes.py`):**
   While `EnvelopeWidget.update_plot()` checked `if member else 0`, `inspect_distance()` unconditionally called `member_breaks(self.project, self.member.currentText())`, raising `KeyError: ''`.
4. **Deformation Animation (`StaticDeformationDialog` in `src/pynitegui/qt/deformation_animation.py`):**
   `static_paths()` only collected polylines from `project.members` and `project.surfaces`, skipping `project.joint_springs`. On spring-only networks, `self.paths` was `[]`, and `StaticDeformationDialog.rebuild()` crashed with `ValueError: need at least one array to concatenate` on `np.vstack([p for p, _ in self.paths])`. Worse, because `StaticDeformationDialog.__init__()` registered itself as a `QObject` child of `MainWindow` before `self.rebuild()` raised `ValueError` (before `self.reference` was created), the half-constructed dialog remained attached to `MainWindow`, causing every subsequent `MainWindow.refresh()` call to fail with `AttributeError: 'StaticDeformationDialog' object has no attribute 'reference'`.
5. **3D Report Diagram Renderer (`diagram_geometry` in `src/pynitegui/qt/spatial_reports.py`):**
   When generating/printing a 3D report on `3d_joint_spring_network` with any force diagram option enabled, `samples()` returned `rows = []` and passed it to `diagram_geometry()`, which called `min(...)` / `max(...)` on an empty generator and crashed with `ValueError: min() iterable argument is empty`.

#### Implemented Fix
- Guarded `DiagramDialog.update_member` / `inspect_distance` / `update_inspection`, `SpatialDiagramDialog.redraw` / `inspect_distance` / `update_inspection`, and `EnvelopeWidget.inspect_distance` when `name not in self.project.members`.
- Included `project.joint_springs` in `static_paths()` for both 2D and 3D models, and guarded empty `self.paths` in `StaticDeformationDialog.rebuild()` and `set_unit_system()`.
- Added `default=0.` to `min(...)` and `max(...)` in `spatial_reports.diagram_geometry()`.

---

### BUG-03: `ModalWindow` and `PushoverWindow` cache `self.units` at construction and ignore unit changes

- **Severity:** Medium (stale unit labels and unconverted numerical inputs/results after switching project display units)
- **Affected Files:**
  - `src/pynitegui/qt/modal_window.py` (`ModalWindow.__init__`, `set_inputs`, `refresh`, `mode_changed`)
  - `src/pynitegui/qt/pushover_window.py` (`PushoverWindow.refresh`)
- **Regression Tests:**
  - `tests/test_qt_modal.py` (`ModalEditorTests.test_modal_window_unit_changes_and_teardown`)
  - `tests/test_qt_pushover.py` (`PushoverEditorTests.test_spatial_hinge_map_and_rotation_limit_units`)

#### Root Cause
Both `ModalWindow` and `PushoverWindow` are lazily created once and cached on `controller.panel`. In `__init__`, each window assigned `self.units = window.project.units` once. When the user changed display units in `MainWindow` (`MainWindow.set_units()`), `ModalWindow.refresh()` and `PushoverWindow.refresh()` were invoked via `controller.changed`, but neither updated `self.units`, form unit labels (`Gravity (<unit>/s²)`, `Display amplitude (<unit>)`, `Absolute stop limit (<unit>)`), spinbox values (`self.gravity`, `self.amplitude`, `self.limit`), or the displayed result tables and plots. Additionally, `ModalWindow.set_inputs()` updated `self.gravity.setValue(...)` without updating `original_value` and `initial_value` properties used by `unit_value()`.

#### Implemented Fix
- Updated `ModalWindow.refresh()` and `PushoverWindow.refresh()` to detect `self.window.project.units != self.units`, convert active spinbox values from `old_units` to the new display unit system, update unit labels, and re-render result tables and plots when a result snapshot is loaded.
- Updated `ModalWindow.set_inputs()` and `ModalWindow.mode_changed()` to keep `original_value` and `initial_value` synchronized on `self.gravity` and `self.amplitude`.

---

### BUG-04: `ModalWindow` raises `RuntimeError` (`QPushButton already deleted`) during `MainWindow` teardown

- **Severity:** Medium (unhandled `RuntimeError` from Qt signal emission during window destruction)
- **Affected Files:**
  - `src/pynitegui/qt/modal_window.py` (`ModalWindow.refresh`)
  - `src/pynitegui/qt/pushover_window.py` (`PushoverWindow.refresh`)
- **Regression Test:** `tests/test_qt_modal.py` (`ModalEditorTests.test_modal_window_unit_changes_and_teardown`)

#### Root Cause
`ModalController` and `PushoverController` connect `window.undo.indexChanged.connect(lambda index: self.changed.emit())`, and `ModalWindow` / `PushoverWindow` connect `controller.changed.connect(self.refresh)`. When `MainWindow` is destroyed after at least one undo command has been pushed and `ModalWindow` has been opened, Qt destroys `ModalWindow`'s child `QWidget`s (`self.solve`, `self.cancel`, etc.) before `window.undo` (`QUndoStack`) finishes destructing and emitting `indexChanged`. `ModalWindow.refresh()` then attempted to call `self.solve.setEnabled(...)` on the already-deleted C++ `QPushButton`, raising `RuntimeError: libshiboken: Internal C++ object (PySide6.QtWidgets.QPushButton) already deleted`.

#### Implemented Fix
Guarded `ModalWindow.refresh()` and `PushoverWindow.refresh()` with `shiboken6.isValid(...)` checks on `self` and child widgets before accessing them.

---

### BUG-05: Identifier collisions between 3D `surfaces` and `nodes` / `members` / `loads` / `joint_springs`

- **Severity:** Medium (auto-generated entity names could fail `project.validate()` or collide across dialogs)
- **Affected Files:**
  - `src/pynitegui/qt/model.py` (`node_at`, `add_member`, `_split_member`)
  - `src/pynitegui/qt/spatial_model.py` (`node_at`, `add_member`)
  - `src/pynitegui/qt/spatial_surfaces.py` (`validate_surfaces`)
  - `src/pynitegui/qt/model_tables.py` (`ModelTablesDialog.add_row`)
  - `src/pynitegui/qt/spatial_editor.py` (`add_load`)
  - `src/pynitegui/qt/app.py` (`manage_surfaces`)
  - `src/pynitegui/qt/joint_spring_editor.py` (`JointSpringsDialog.perform`)
- **Regression Test:** `tests/test_qt_spatial_surfaces.py` (`SpatialSurfaceModelTests.test_surface_and_spring_ids_reserved_across_geometry_and_tables`)

#### Root Cause
1. `validate_surfaces()` enforces that surface names cannot overlap with `nodes`, `members`, or `loads`, yet auto-naming call sites (`node_at`, `add_member`, `_split_member`, `add_load`, `ModelTablesDialog.add_row`) did not include `project.surfaces` in the reserved set passed to `next_name()`. If a surface was named `"M1"`, `"N3"`, or `"L1"`, subsequently adding or splitting a member, node, or load auto-generated a colliding identifier that immediately failed `project.validate()`.
2. Both new surfaces (`app.py`) and new joint springs (`joint_spring_editor.py`) default to prefix `"S"` (`S1`, `S2`, ...), but neither reserved the other collection when generating default names, nor did `validate_surfaces()` check `project.joint_springs`.

#### Implemented Fix
Reserved `surfaces` and `joint_springs` across all auto-naming call sites (`node_at`, `add_member`, `_split_member`, `add_load`, `ModelTablesDialog.add_row`, `manage_surfaces`, `JointSpringsDialog.perform`) and included `project.joint_springs` in `validate_surfaces()`.

---

### BUG-06: 2D `Project.split_member` and `Project.connect_intersections` mutate `self` in-place without transactional validation or rollback

- **Severity:** Medium (in-place project corruption on duplicate or near-coincident geometry)
- **Affected Files:**
  - `src/pynitegui/qt/model.py` (`Project.split_member`, `Project.connect_intersections`)
  - `src/pynitegui/qt/spatial_model.py` (`SpatialProject.connect_intersections`)
- **Regression Test:** `tests/test_qt_topology.py` (`TopologyTests.test_invalid_split_does_not_mutate`)

#### Root Cause
Unlike 3D `SpatialProject.split_member()` and `SpatialProject.connect_intersections()`, 2D `Project.split_member()` and `Project.connect_intersections()` mutated `self` in-place without cloning to a `candidate` and validating before committing. In addition, 2D `Project.split_member()` used `math.isfinite(fraction)` instead of `finite_number(fraction)` (allowing `bool` values like `True`) and raised a raw `KeyError` for unknown member names instead of `ValueError`. When a split or intersection operation snapped to an already-connected node (e.g. `p.add_member((0, 0), (120, 0)); p.add_member((0, 0), (60, 0)); p.split_member("M1", 0.5)`, or when a connected node lay within `node_at()`'s `1e-8` snap tolerance of a member), `self` was mutated in-place into an invalid state with duplicate members connecting the same nodes.

#### Implemented Fix
Made 2D `Project.split_member()` and `Project.connect_intersections()` transactional on a cloned `candidate` with pre- and post-validation and `finite_number(fraction)` / unknown-member checks, matching `SpatialProject`.

---

### BUG-07: `PlateDefinition.validate` ignores control lines when checking element count and aspect ratio, causing `MeshWorkspace.analyze_rectangle` to crash

- **Severity:** Medium (unhandled `ValueError` crash when transferring a rectangular mesh to the Plate workspace)
- **Affected Files:**
  - `src/pynitegui/qt/plate_model.py` (`PlateDefinition.validate`)
  - `src/pynitegui/qt/mesh_workspace.py` (`MeshWorkspace.analyze_rectangle`)
- **Regression Tests:**
  - `tests/test_plate_model.py` (`PlateModelTests.test_invalid_inputs`)
  - `tests/test_qt_mesh_workspace.py` (`MeshWorkspaceTests.test_analyze_rectangle_handles_control_lines_and_warns_on_invalid_plate`)

#### Root Cause
In `PlateDefinition.validate()`, element count and aspect ratio were computed from `nx, ny = math.ceil(self.width / self.mesh_size), math.ceil(self.height / self.mesh_size)` and `ratio = (self.width / nx) / (self.height / ny)` without accounting for `self.x_control`, `self.y_control`, or `self.openings`. A rectangular mesh subdivided by control lines (e.g. `width=100, height=4, mesh_size=100, x_control=[20, 40, 60, 80]`, which produces 5 elements each of aspect ratio 5:1) passed `MeshDefinition.validate()`, but failed `PlateDefinition.validate()`. Furthermore, `MeshWorkspace.analyze_rectangle()` called `transfer_rectangle()` and constructed `PlateWorkspace(self, definition=definition)` without catching `ValueError`, crashing with an unhandled exception whenever `PlateDefinition.validate()` rejected the transferred mesh.

#### Implemented Fix
- Updated `PlateDefinition.validate()` to validate the underlying mesh recipe first and compute element aspect ratios from the actual subdivided spans across `x_control`, `y_control`, and `openings`.
- Wrapped `transfer_rectangle()` and `definition.validate()` in `MeshWorkspace.analyze_rectangle()` in a `try/except ValueError` block that shows a `QMessageBox.warning` dialog on invalid plate geometry.

---

### BUG-08: `PlateWorkspace.configure_loading` forces `self.apply()` before opening `PlateLoadsDialog`, blocking recovery when `Plane` changes with self-weight enabled

- **Severity:** Low (UI validation deadlock requiring manual workaround)
- **Affected Files:**
  - `src/pynitegui/qt/plate_workspace.py` (`PlateWorkspace.candidate`, `configure_loading`)
  - `src/pynitegui/qt/plate_loads.py` (`PlateLoadsDialog.__init__`)
- **Regression Test:** `tests/test_qt_plate_workspace.py` (`PlateWorkspaceTests.test_configure_loading_allows_disabling_self_weight_after_plane_change`)

#### Root Cause
`PlateDefinition.validate()` requires `plane == "XZ"` whenever `self_weight_case` is set. However, the `Self-weight case` dropdown lives inside `PlateLoadsDialog`, which is opened via **Load Cases / Combinations…** (`PlateWorkspace.configure_loading()`). Because `configure_loading()` required `self.apply()` to succeed before opening `PlateLoadsDialog` (and `PlateLoadsDialog.__init__` disabled `self.weight_case` whenever `plane != "XZ"`), changing `Plane` in `PlateWorkspace` from `XZ` to `XY` or `YZ` while self-weight was active prevented the user from opening `PlateLoadsDialog` to turn self-weight off.

#### Implemented Fix
Updated `PlateWorkspace.configure_loading()` to pass a validated draft candidate (allowing a pending non-`XZ` plane with existing `self_weight_case`) into `PlateLoadsDialog`, and enabled `PlateLoadsDialog.weight_case` whenever `self.definition.plane == "XZ" or self.definition.self_weight_case is not None` so the user can turn off self-weight and commit both changes in one undoable edit.

---

### BUG-09: Bulk inspector disables `Restrain *` checkboxes when `Support` is `"Keep existing"`, even when all selected nodes already have `"custom"` or `"inclined"` supports

- **Severity:** Low (blocks direct bulk restraint editing without re-selecting support type)
- **Affected File:** `src/pynitegui/qt/bulk_edit.py` (`populate_bulk_inspector`)
- **Regression Test:** `tests/test_qt_bulk_edit.py` (`BulkEditTests.test_node_support_custom_preserves_preset_restraints`)

#### Root Cause
In `populate_bulk_inspector()`, `update_support()` enabled the `Restrain *` checkboxes only when `support.currentData() in (("custom", "inclined") if spatial else ("custom",))`. Because the bulk `Support` dropdown initializes to `"Keep existing"` (`None`), all `Restrain *` checkboxes remained disabled even when every selected node already had `support == "custom"` (or 3D `"inclined"`).

#### Implemented Fix
Updated `update_support()` in `src/pynitegui/qt/bulk_edit.py` to also enable the `Restrain *` checkboxes when `support.currentData() is None` (`"Keep existing"`) and all selected nodes already have `node.support in custom_supports`.
