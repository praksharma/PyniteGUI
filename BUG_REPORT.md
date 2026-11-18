# Brecon (`PyniteGUI`) Bug Analysis Report

- **Audited Commit:** `4f1ec33` (`master`, also verified against `origin/master` at `cad3811`)
- **Scope:** Full static and dynamic analysis of `src/pynitegui/qt/` (2D/3D models, editors, post-processing dialogs, plate/mesh workspaces, bulk editing, modal/pushover windows, reports, and unit conversion pathways)
- **Verification Environment:** Headless Qt (`QT_QPA_PLATFORM=offscreen`, `PYNITEGUI_NO_WEBENGINE=1`), Python 3.12, PySide6 6.12.0, PyniteFEA

---

## Executive Summary

| ID | Severity | Component | Summary |
| :--- | :--- | :--- | :--- |
| **BUG-01** | High | Construction / Groups (`app.py`) | `MainWindow.construct_connection` (`Perpendicular Connection...` / `Connect Member Midpoints...`) fails to copy `candidate.groups`, silently dropping newly split member segments from saved groups. |
| **BUG-02** | High | Post-Analysis Tools (`diagrams.py`, `spatial_diagrams.py`, `envelopes.py`, `deformation_animation.py`, `spatial_reports.py`) | Unhandled `KeyError`, `ValueError`, and cascading `AttributeError` crashes across post-processing tools on valid joint-spring-only models (including built-in examples `joint_spring_series`, `joint_spring_one_way`, and `3d_joint_spring_network`). |
| **BUG-03** | Medium | Modal & Pushover Windows (`modal_window.py`, `pushover_window.py`) | `ModalWindow` and `PushoverWindow` cache `self.units` at initialization and never update unit labels, converted spinbox inputs, tables, or plots when project display units change. |
| **BUG-04** | Medium | Modal Window Lifecycle (`modal_jobs.py`, `modal_window.py`) | `ModalWindow.refresh()` is triggered via `QUndoStack.indexChanged` during `MainWindow` teardown after child `QPushButton` C++ widgets are destroyed, raising `RuntimeError: Internal C++ object (PySide6.QtWidgets.QPushButton) already deleted`. |
| **BUG-05** | Medium | 3D Identifiers (`spatial_model.py`, `model.py`, `model_tables.py`, `spatial_editor.py`, `app.py`, `joint_spring_editor.py`) | Auto-generated node/member/load names do not reserve `project.surfaces` IDs (violating `validate_surfaces`), and default `"S"` prefixes for surfaces and joint springs do not check each other for collisions. |
| **BUG-06** | Medium | 2D Geometry Operations (`model.py`) | `Project.split_member` and `Project.connect_intersections` mutate `self` in-place without transactional validation/rollback, and the mismatch between `validate()` (exact coordinate match) and `node_at()` (`1e-8` snap tolerance) can leave the project corrupted with duplicate members. |
| **BUG-07** | Medium | Plate & Mesh Workspaces (`plate_model.py`, `mesh_workspace.py`) | `PlateDefinition.validate()` computes element count and aspect ratio without accounting for `x_control`/`y_control`, and `MeshWorkspace.analyze_rectangle()` does not catch `ValueError` from `transfer_rectangle()`. |
| **BUG-08** | Low | Plate Workspace (`plate_workspace.py`) | `PlateWorkspace.configure_loading()` and `configure_mesh()` force `self.apply()` before opening their dialogs, locking the user out of `PlateLoadsDialog` when `Plane` is changed while `self_weight_case` is active. |
| **BUG-09** | Low | Bulk Inspector (`bulk_edit.py`) | `populate_bulk_inspector()` disables all `Restrain *` checkboxes whenever `Support` is `"Keep existing"`, preventing bulk restraint edits even when all selected nodes already have `"custom"` or 3D `"inclined"` supports. |

---

## Detailed Bug Reports

### BUG-01: `MainWindow.construct_connection` drops split member segments from saved groups

- **Severity:** High (silent model group corruption / loss of grouped members in isolated views)
- **Affected Files:**
  - `src/pynitegui/qt/app.py` (lines 1586–1589)
  - Compare: `src/pynitegui/qt/construction.py` (lines 62–67) and `src/pynitegui/qt/model.py` (lines 778, 851–854)

#### Root Cause
When executing **Perpendicular Connection...** or **Connect Member Midpoints...**, `plan_connection()` clones the project into `candidate` and splits the target member(s) via `candidate._split_member(...)`. Inside `Project._split_member()` (`src/pynitegui/qt/model.py:851-854`), every group containing the original member is properly updated to include both replacement segments (`[first_name, second_name]`).

However, when `MainWindow.construct_connection()` commits `candidate` back into `self.project` (`src/pynitegui/qt/app.py:1586-1589`), it only copies `nodes`, `members`, and `loads`:

```python
def apply() -> None:
    candidate, _, _ = plan_connection(self.project, spec)
    self.project.nodes, self.project.members, self.project.loads = (
        candidate.nodes,
        candidate.members,
        candidate.loads,
    )
```

Because `self.project.groups = candidate.groups` is omitted (unlike `Project.subdivide_members` at `model.py:778` and `SpatialProject.split_member` at `spatial_model.py:430`), `self.project.groups` retains only the pre-split member list. The newly created second segment (`M2`) is silently dropped from all groups containing the split member, and immediately disappears from the canvas if that group is currently isolated.

#### Reproduction
```python
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.construction import ConnectionSpec
from pynitegui.qt.model import Group

app = QApplication.instance() or QApplication([])
w = MainWindow()
w.project.nodes.clear()
w.project.members.clear()
w.project.loads.clear()
w.project.add_member(0.0, 0.0, 100.0, 0.0)  # M1
w.project.add_node(50.0, 50.0)              # N3
w.project.groups["G1"] = Group("G1", members=["M1"])

w.construct_connection(ConnectionSpec("perpendicular", "M1", node="N3"))
print("Project members:", list(w.project.members))
print("Group G1 members:", w.project.groups["G1"].members)
```
- **Actual Output:**
  `Project members: ['M1', 'M2', 'M3']`
  `Group G1 members: ['M1']` (`M2`, the second half of the original `M1`, is missing from `G1`)
- **Expected Output:**
  `Group G1 members: ['M1', 'M2']`

#### Recommended Fix
Copy `candidate.groups` alongside `nodes`, `members`, and `loads` in `MainWindow.construct_connection()`:
```python
self.project.nodes, self.project.members, self.project.loads, self.project.groups = (
    candidate.nodes,
    candidate.members,
    candidate.loads,
    candidate.groups,
)
```

---

### BUG-02: Post-analysis dialogs and 3D diagram reports crash on joint-spring-only models

- **Severity:** High (unhandled exceptions on built-in example projects; persistent UI corruption of `MainWindow.refresh()`)
- **Affected Files:**
  - `src/pynitegui/qt/diagrams.py` (lines 490–507, 551)
  - `src/pynitegui/qt/spatial_diagrams.py` (lines 111–140)
  - `src/pynitegui/qt/envelopes.py` (lines 339–345)
  - `src/pynitegui/qt/deformation_animation.py` (lines 16–39, 135–175)
  - `src/pynitegui/qt/spatial_reports.py` (lines 46–54)

#### Root Cause
Brecon supports memberless joint-spring network models (and ships three built-in examples: `joint_spring_series`, `joint_spring_one_way`, and `3d_joint_spring_network`). After running a valid static analysis on any such model, `run.ok` is `True`, which enables the post-processing actions in `MainWindow`. However, five post-processing components assume `project.members` (or `paths`) is non-empty:

1. **2D Diagrams (`DiagramDialog` in `src/pynitegui/qt/diagrams.py:490-507, 551`):**
   `self.member` (`QComboBox`) has no items, so `self.member.currentText()` is `""`. `update_member()` and `inspect_distance()` index `self.project.members[name]` directly, raising `KeyError: ''` as soon as the user clicks **Diagrams...**.
2. **3D Diagrams (`SpatialDiagramDialog` in `src/pynitegui/qt/spatial_diagrams.py:111-140`):**
   `redraw()` and `inspect_distance()` call `member_breaks(self.project, self.member.currentText())` with `""`, raising `KeyError: ''` when opening **Diagrams...** on `3d_joint_spring_network`.
3. **Envelope Inspector (`EnvelopeWidget.inspect_distance` in `src/pynitegui/qt/envelopes.py:339-345`):**
   While `EnvelopeWidget.update_plot()` checks `if member else 0`, `inspect_distance()` unconditionally calls `member_breaks(self.project, self.member.currentText())`, raising `KeyError: ''` when the distance spinbox changes.
4. **3D Deformation Animation (`StaticDeformationDialog` in `src/pynitegui/qt/deformation_animation.py:16-39, 135-175`):**
   `static_paths()` only collects polylines from `project.members` and `project.surfaces`, skipping `project.joint_springs`. On `3d_joint_spring_network`, `self.paths` is `[]`, and `StaticDeformationDialog.rebuild()` crashes at line 142:
   ```python
   pts = np.vstack([p for p, _ in self.paths])
   # ValueError: need at least one array to concatenate
   ```
   Worse, because `StaticDeformationDialog.__init__()` calls `super().__init__(parent)` (registering itself as a `QObject` child of `MainWindow`) *before* `self.rebuild()` raises `ValueError` (before `self.reference` is created on line 106), the half-constructed dialog remains attached to `MainWindow`. Every subsequent `MainWindow.refresh()` call (`src/pynitegui/qt/app.py:1110`, `dialog.set_unit_system(self.project.units)`) then crashes with:
   `AttributeError: 'StaticDeformationDialog' object has no attribute 'reference'`.
5. **3D Report Diagram Renderer (`diagram_geometry` in `src/pynitegui/qt/spatial_reports.py:46-54`):**
   When generating/printing a 3D report on `3d_joint_spring_network` with any internal force diagram checkbox enabled (`include_axial`, `include_shear_y`, etc.), `diagram_rows()` returns `[]` and passes it to `diagram_geometry(project, rows, component)`, which executes `min(val for _, pts in rows for *_, val in pts)` and crashes with `ValueError: min() iterable argument is empty`.

#### Reproduction
```python
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.solver import analyze_project
from pynitegui.qt.spatial_solver import analyze_spatial_project
from pynitegui.qt.spatial_reports import ReportOptions, render_spatial_diagram_png

app = QApplication.instance() or QApplication([])
w = MainWindow()

# 1. 2D joint-spring example -> Diagrams
w.example("joint_spring_series")
w.analysis_revision = w.revision
w.analysis_finished(w.revision, analyze_project(w.project))
try:
    w.diagrams()
except Exception as exc:
    print("2D diagrams() crashed:", type(exc).__name__, exc)

# 2. 3D joint-spring example -> Diagrams, Report, Deformation Animation
w.saved = w.project.to_dict()
w.example("3d_joint_spring_network")
w.analysis_revision = w.revision
w.analysis_finished(w.revision, analyze_spatial_project(w.project))

try:
    w.diagrams()
except Exception as exc:
    print("3D diagrams() crashed:", type(exc).__name__, exc)

try:
    render_spatial_diagram_png(w.project, w.run, "Combo 1", "axial", ReportOptions())
except Exception as exc:
    print("3D report diagram crashed:", type(exc).__name__, exc)

try:
    w.animate_deformation()
except Exception as exc:
    print("3D animate_deformation() crashed:", type(exc).__name__, exc)

try:
    w.refresh()
except Exception as exc:
    print("Subsequent MainWindow.refresh() crashed:", type(exc).__name__, exc)
```
- **Actual Output:**
  - `2D diagrams() crashed: KeyError ''`
  - `3D diagrams() crashed: KeyError ''`
  - `3D report diagram crashed: ValueError min() iterable argument is empty`
  - `3D animate_deformation() crashed: ValueError need at least one array to concatenate`
  - `Subsequent MainWindow.refresh() crashed: AttributeError 'StaticDeformationDialog' object has no attribute 'reference'`

#### Recommended Fix
- Guard `DiagramDialog.update_member` / `inspect_distance`, `SpatialDiagramDialog.redraw` / `inspect_distance`, and `EnvelopeWidget.inspect_distance` when `name not in self.project.members` (clear plots/readouts and disable controls when no members exist, or show a user-facing status prompt in `MainWindow.diagrams()`).
- In `deformation_animation.py`, include `project.joint_springs` in `static_paths()` (or guard empty `self.paths` in `rebuild()`, `update_frame()`, and `set_unit_system()`, and ensure `self.rebuild()` is called only after all widget attributes like `self.reference` are initialized).
- In `spatial_reports.py`, guard `if not rows:` in `diagram_geometry()` / `render_spatial_diagram_png()`.

---

### BUG-03: `ModalWindow` and `PushoverWindow` cache `self.units` at construction and ignore unit changes

- **Severity:** Medium (stale unit labels and unconverted numerical inputs/results after switching project display units)
- **Affected Files:**
  - `src/pynitegui/qt/modal_window.py` (lines 24–37, 78–80, 89–108)
  - `src/pynitegui/qt/pushover_window.py` (lines 22–31, 93–100, 110–127)

#### Root Cause
Both `ModalWindow` and `PushoverWindow` are lazily created once and cached on `controller.panel`. In `__init__`, each window snapshots `self.units = window.project.units` (`modal_window.py:29`, `pushover_window.py:27`) and configures its unit labels and spinboxes using that initial unit system.

When the user switches the project's display units in `MainWindow` (`MainWindow.set_units()`), `MainWindow.refresh()` emits `_modal_controller.changed` and `_pushover_controller.changed`, which invoke `ModalWindow.refresh()` and `PushoverWindow.refresh()`. However:
1. Neither `refresh()` updates `self.units = self.window.project.units`.
2. Neither updates the form labels (`Gravity (in/s²)`, `Absolute stop limit (in)`) or converts the spinbox values (`self.gravity`, `self.amplitude`, `self.limit`) to the new unit system.
3. Because changing display units does not alter the model's structural snapshot ID (`fresh.snapshot_id == self.result.snapshot_id`), neither window re-renders its result table headers/values or plot axes into the new unit system.
4. Additionally, `ModalWindow.set_inputs()` (`modal_window.py:80`) calls `self.gravity.setValue(self.units.from_length(inputs.gravity))` without updating the `original_value` and `initial_value` Qt properties that `bind_exact_unit_spin()` / `unit_value()` rely on to preserve exact base-unit values when the spinbox hasn't been manually edited.

#### Reproduction
```python
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.units import UNIT_SYSTEMS

app = QApplication.instance() or QApplication([])
w = MainWindow()
w.open_modal_window()
w.open_pushover_window()
modal = w._modal_controller.panel
pushover = w._pushover_controller.panel

print("Before unit change:", modal.units.name, modal.gravity.value(), pushover.units.name, pushover.limit.value())
w.set_units(UNIT_SYSTEMS["SI (N, mm)"])
print("After unit change:", modal.units.name, modal.gravity.value(), pushover.units.name, pushover.limit.value())
```
- **Actual Output:**
  `Before unit change: US (kip, in) 386.08858267716535 US (kip, in) 20.0`
  `After unit change: US (kip, in) 386.08858267716535 US (kip, in) 20.0` (both windows remain stuck in `US (kip, in)`)
- **Expected Output:**
  Both windows update `self.units` to `SI (N, mm)`, update form labels (`mm/s²`, `mm`), convert spinbox values (`9806.65 mm/s²`, `508.0 mm`), and re-render any displayed result tables and plots.

#### Recommended Fix
In `ModalWindow.refresh()` and `PushoverWindow.refresh()`, check `if self.units != self.window.project.units:`, capture current `self.current_inputs()` under the old units, update `self.units = self.window.project.units`, update unit-dependent form labels, call `self.set_inputs(...)` (ensuring `ModalWindow.set_inputs` also updates `original_value` and `initial_value` on `self.gravity`), and re-run `self.apply_result(self.result)` when a result is present.

---

### BUG-04: `ModalWindow` raises `RuntimeError` (`QPushButton already deleted`) during `MainWindow` teardown

- **Severity:** Medium (unhandled `RuntimeError` from Qt signal emission during window destruction)
- **Affected Files:**
  - `src/pynitegui/qt/modal_jobs.py` (line 51)
  - `src/pynitegui/qt/modal_window.py` (lines 64, 89–92)

#### Root Cause
In `ModalController.__init__()` (`src/pynitegui/qt/modal_jobs.py:51`), the controller connects:
```python
window.undo.indexChanged.connect(lambda index: self.changed.emit())
```
And `ModalWindow.__init__()` (`src/pynitegui/qt/modal_window.py:64`) connects:
```python
controller.changed.connect(self.refresh)
```
Both `window.undo` (`QUndoStack(self)`) and `ModalWindow(window, ...)` are `QObject` children of `MainWindow`. When `MainWindow` is destroyed after at least one undo command has been pushed and `ModalWindow` has been instantiated, Qt destroys `ModalWindow`'s child widgets (`self.solve`, `self.cancel`) before `window.undo` finishes destructing. When `QUndoStack::~QUndoStack()` clears its stack and emits `indexChanged`, `ModalController.changed` fires `ModalWindow.refresh()`, which accesses `self.solve.setEnabled(...)` on the already-deleted C++ `QPushButton` and raises:
`RuntimeError: libshiboken: Internal C++ object (PySide6.QtWidgets.QPushButton) already deleted.`

#### Reproduction
```python
import sip  # or shiboken6
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.units import UNIT_SYSTEMS

app = QApplication.instance() or QApplication([])
w = MainWindow()
w.set_units(UNIT_SYSTEMS["SI (N, m)"])  # pushes an entry onto w.undo
w.open_modal_window()
w.deleteLater()
app.sendPostedEvents(None, 0)
```
- **Actual Output:**
  `RuntimeError: libshiboken: Internal C++ object (PySide6.QtWidgets.QPushButton) already deleted.`

#### Recommended Fix
Pass `self` as the Qt context receiver or guard widget liveness (`shiboken6.isValid(self.solve)`) in `ModalWindow.refresh()` and `PushoverWindow.refresh()`, or disconnect `controller.changed` in `destroyed` / teardown.

---

### BUG-05: Identifier collisions between 3D `surfaces` and `nodes` / `members` / `loads` / `joint_springs`

- **Severity:** Medium (auto-generated entity names can fail `project.validate()` or collide across dialogs)
- **Affected Files:**
  - `src/pynitegui/qt/spatial_surfaces.py` (lines 63–64)
  - `src/pynitegui/qt/spatial_model.py` (lines 313, 323)
  - `src/pynitegui/qt/model.py` (lines 801, 820)
  - `src/pynitegui/qt/model_tables.py` (lines 285–289)
  - `src/pynitegui/qt/spatial_editor.py` (line 396)
  - `src/pynitegui/qt/app.py` (line 1986)
  - `src/pynitegui/qt/joint_spring_editor.py` (line 68)

#### Root Cause
1. **`surfaces` omitted from `next_name()` reserved sets:**
   `validate_surfaces()` (`src/pynitegui/qt/spatial_surfaces.py:63-64`) enforces that surface IDs cannot overlap with `{*project.nodes, *project.members, *project.loads}`:
   ```python
   reserved = {*project.nodes, *project.members, *project.loads}
   if key in reserved:
       raise ValueError(f"Surface {key} duplicates an existing model identifier.")
   ```
   However, when new nodes, members, or loads are added or split, their auto-naming calls do **not** include `project.surfaces` in the existing-ID set passed to `next_name()`:
   - `SpatialProject.node_at` (`spatial_model.py:313`): `next_name("N", {*self.nodes, *self.joint_springs})`
   - `SpatialProject.add_member` (`spatial_model.py:323`): `next_name("M", {*self.members, *self.joint_springs})`
   - `Project._split_member` (`model.py:801, 820`): `next_name("M", {*self.members, *self.joint_springs})`
   - `SpatialCanvas.add_load` (`spatial_editor.py:396`): `next_name("L", {*self.project.loads, *self.project.joint_springs})`
   - `ModelTablesDialog.add_row` (`model_tables.py:285-289`): reserves `joint_springs` (added in commit `5aff930`), but still omits `getattr(self.project, "surfaces", {})`.

   Consequently, if a user creates a surface with custom name `"M1"`, `"N1"`, or `"L1"` (which is valid when no member/node/load yet has that name), subsequently adding or splitting a member, node, or load auto-generates `"M1"` / `"N1"` / `"L1"`, immediately causing `project.validate()` to raise `ValueError: Surface M1 duplicates an existing model identifier.`

2. **Surface and Joint Spring default `"S"` prefix collision:**
   Both `MainWindow.add_surface` (`src/pynitegui/qt/app.py:1986`) and `JointSpringDialog` (`src/pynitegui/qt/joint_spring_editor.py:68`) use the `"S"` prefix (`S1`, `S2`, ...), but neither checks the other collection when picking the next default name:
   - `app.py:1986`: `next_name("S", {*self.project.surfaces, *self.project.nodes, *self.project.members, *self.project.loads})` (omits `joint_springs`)
   - `joint_spring_editor.py:68`: `next_name("S", {*project.joint_springs, *project.nodes, *project.members, *project.loads})` (omits `surfaces`)
   (Note that `geometry_tools.unique_name()` at `src/pynitegui/qt/geometry_tools.py:26-29` already reserves all five collections: `nodes`, `members`, `loads`, `surfaces`, and `joint_springs`.)

#### Reproduction
```python
from pynitegui.qt.spatial_model import SpatialProject
from pynitegui.qt.spatial_surfaces import SpatialSurface

p = SpatialProject()
p.add_node(0, 0, 0)
p.add_node(100, 0, 0)
p.add_node(100, 100, 0)
p.surfaces["M1"] = SpatialSurface("M1", ["N1", "N2", "N3"])
p.validate()  # Passes

p.add_member(0, 0, 0, 100, 0, 0)  # Auto-generates "M1", colliding with p.surfaces["M1"]
p.validate()  # Raises ValueError: Surface M1 duplicates an existing model identifier.
```

#### Recommended Fix
Use a single helper on `Project` / `SpatialProject` (matching `geometry_tools.unique_name()`) that reserves `{*project.nodes, *project.members, *project.loads, *project.joint_springs, *getattr(project, "surfaces", {})}` across all auto-naming call sites, and check `joint_springs` in `validate_surfaces()`.

---

### BUG-06: 2D `Project.split_member` and `Project.connect_intersections` mutate `self` in-place without rollback and can create duplicate members via `1e-8` snap tolerance

- **Severity:** Medium (in-place project corruption on boundary/near-coincident geometry)
- **Affected Files:**
  - `src/pynitegui/qt/model.py` (lines 597–599, 688–694, 750–753, 857–879)
  - Compare: `src/pynitegui/qt/spatial_model.py` (lines 421–448)

#### Root Cause
1. **Tolerance mismatch between `Project.validate()` and `Project.node_at()`:**
   `Project.validate()` (`src/pynitegui/qt/model.py:597-599`) checks duplicate node coordinates using exact floating-point tuple equality:
   ```python
   if (node.x, node.y) in coords:
       raise ValueError("Duplicate node coordinates are not allowed.")
   ```
   Meanwhile, `Project.node_at(x, y)` (`src/pynitegui/qt/model.py:688-694`) snaps to any existing node within `math.hypot(node.x - x, node.y - y) < 1e-8`.
   If node `N3(50.0, 5e-9)` is already connected to `N1(0.0, 0.0)` and lies within `1e-8` of member `M1(N1(0,0) -> N2(100,0))`, the project passes `p.validate()`. However, splitting `M1` at `0.5` (or calling `p.connect_intersections()`) calls `node_at(50.0, 0.0)`, which snaps to `N3`, creating a segment `(N1, N3)` that duplicates the existing member `(N1, N3)`.

2. **Missing transactional clone/validate in 2D `split_member` and `connect_intersections`:**
   In 3D (`src/pynitegui/qt/spatial_model.py:421-448`), both `SpatialProject.split_member()` and `SpatialProject.connect_intersections()` operate on `candidate = self.clone()`, run `candidate.validate()`, and only copy state back to `self` if validation succeeds.
   In 2D (`src/pynitegui/qt/model.py:750-753, 857-879`), `Project.split_member()` and `Project.connect_intersections()` mutate `self` directly without validating on a clone (and `Project.split_member()` also lacks `SpatialProject.split_member()`'s `isinstance(fraction, bool)` check and `Unknown member` `ValueError`). When `split_member()` or `connect_intersections()` creates an invalid state, `self` is left mutated and fails `self.validate()`.

#### Reproduction
```python
from pynitegui.qt.model import Member, Node, Project

p = Project()
p.nodes = {
    "N1": Node("N1", 0.0, 0.0, "pinned"),
    "N2": Node("N2", 100.0, 0.0, "roller"),
    "N3": Node("N3", 50.0, 5e-9),
    "N4": Node("N4", 50.0, -50.0),
}
p.members = {
    "M1": Member("M1", "N1", "N2"),
    "M2": Member("M2", "N3", "N4"),
    "M3": Member("M3", "N1", "N3"),
}
p.loads = {}
p.validate()  # Valid before connect_intersections()

p.connect_intersections()
p.validate()  # Raises ValueError: Duplicate members connect the same nodes.
```

#### Recommended Fix
- Make 2D `Project.split_member()` and `Project.connect_intersections()` transactional using `candidate = self.clone()` followed by `candidate.validate()`, matching `SpatialProject.split_member()` and `SpatialProject.connect_intersections()`.
- Align `Project.validate()`'s duplicate node coordinate check with `node_at()`'s `1e-8` snap tolerance.

---

### BUG-07: `PlateDefinition.validate` ignores control lines when checking element count and aspect ratio, causing `MeshWorkspace.analyze_rectangle` to crash

- **Severity:** Medium (unhandled `ValueError` crash when transferring a valid control-line rectangular mesh to the Plate workspace)
- **Affected Files:**
  - `src/pynitegui/qt/plate_model.py` (lines 130–138)
  - `src/pynitegui/qt/mesh_workspace.py` (lines 496–503)

#### Root Cause
In `PlateDefinition.validate()` (`src/pynitegui/qt/plate_model.py:130-135`), element count and aspect ratio are checked using uniform division formulas that completely ignore `self.x_control` and `self.y_control`:
```python
nx, ny = math.ceil(self.width / self.mesh_size), math.ceil(self.height / self.mesh_size)
if nx * ny > 2500:
    raise ValueError("Plate mesh exceeds 2500 elements; increase mesh size.")
ratio = (self.width / nx) / (self.height / ny)
if max(ratio, 1.0 / ratio) > 20.0:
    raise ValueError("Element aspect ratio exceeds 20; adjust plate dimensions or mesh size.")
```
Even though line 138 immediately calls `self.mesh_definition().validate()` and `mesh_quality()` computes actual generated element aspect ratios, lines 130–135 reject valid control-line meshes (where `mesh_size` is large because subdivision is driven by `x_control` / `y_control`) or miss excess element counts added by dense control lines.

Furthermore, in `MeshWorkspace.analyze_rectangle()` (`src/pynitegui/qt/mesh_workspace.py:496-503`):
```python
def analyze_rectangle(self) -> None:
    if not self.apply():
        return
    if self.transfer_callback is not None:
        self.transfer_callback(self.definition)
```
`self.apply()` validates `self.definition` (`MeshDefinition.validate()`), which succeeds. Then `self.transfer_callback(self.definition)` calls `transfer_rectangle()`, which constructs a `PlateDefinition` and calls `PlateDefinition.validate()` **without** a `try/except ValueError` block, crashing with an unhandled `ValueError`.

#### Reproduction
```python
from PySide6.QtWidgets import QApplication
from pynitegui.qt.mesh_workspace import MeshWorkspace
from pynitegui.qt.plate_workspace import PlateDialog

app = QApplication.instance() or QApplication([])
dlg = PlateDialog()
mesh_ws = dlg.findChild(MeshWorkspace)

mesh_ws.width_spin.setValue(100.0)
mesh_ws.height_spin.setValue(4.0)
mesh_ws.mesh_size.setValue(100.0)
mesh_ws.x_control.setText("20, 40, 60, 80")  # 5 elements, each 20x4 (aspect ratio 5:1)
print("MeshWorkspace.apply() succeeded:", mesh_ws.apply())
mesh_ws.analyze_rectangle()  # Raises unhandled ValueError: Element aspect ratio exceeds 20
```

#### Recommended Fix
- In `PlateDefinition.validate()`, compute element count and aspect ratio from the actual generated `x_positions` and `y_positions` (via `self.mesh_definition()` or generated cell widths/heights) instead of `math.ceil(width / mesh_size)`.
- Wrap `self.transfer_callback(self.definition)` in `MeshWorkspace.analyze_rectangle()` (or `PlateDialog.open_rectangle_analysis()`) in a `try/except ValueError` block that shows a warning message box on failure.

---

### BUG-08: `PlateWorkspace.configure_loading` forces `self.apply()` before opening `PlateLoadsDialog`, blocking recovery when `Plane` changes with self-weight enabled

- **Severity:** Low (UI validation deadlock requiring manual workaround)
- **Affected Files:**
  - `src/pynitegui/qt/plate_workspace.py` (lines 428–452)
  - `src/pynitegui/qt/plate_model.py` (lines 152–156)

#### Root Cause
`PlateDefinition.validate()` requires `plane == "XZ"` whenever `self_weight_case` is set (`"Plate self-weight requires the horizontal XZ plane."`). However, the `self_weight_case` setting lives inside `PlateLoadsDialog`, which is opened by clicking **Load Cases / Combinations…** (`PlateWorkspace.configure_loading()`).

Because `PlateWorkspace.configure_loading()` calls `if not self.apply(): return` before opening `PlateLoadsDialog` (`src/pynitegui/qt/plate_workspace.py:440-441`), if a user has self-weight enabled on an `XZ` plate and switches the `Plane` combo box in `PlateWorkspace` to `XY` or `YZ`, clicking **Load Cases / Combinations…** to turn off self-weight fails `self.apply()`, pops up a warning dialog (`"Plate self-weight requires the horizontal XZ plane."`), and refuses to open `PlateLoadsDialog`. The user is forced to switch `Plane` back to `XZ`, open `PlateLoadsDialog`, disable self-weight, close the dialog, and switch `Plane` again.

#### Reproduction
```python
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from pynitegui.qt.plate_workspace import PlateWorkspace

app = QApplication.instance() or QApplication([])
ws = PlateWorkspace()
ws.definition.self_weight_case = "Dead"
ws.plane.setCurrentText("XY")

with patch.object(QMessageBox, "warning") as warn:
    ws.configure_loading()
    print("Warning shown, dialog blocked:", warn.call_args[0][2])
```
- **Actual Output:**
  `Warning shown, dialog blocked: Plate self-weight requires the horizontal XZ plane.`

#### Recommended Fix
Allow `PlateLoadsDialog` (and `PlateMeshDialog`) to open using the current dialog state without requiring full cross-field `self.apply()` validation up front, or automatically clear/prompt to disable `self_weight_case` when switching `Plane` away from `XZ`.

---

### BUG-09: Bulk inspector disables `Restrain *` checkboxes when `Support` is `"Keep existing"`, even when all selected nodes already have `"custom"` or `"inclined"` supports

- **Severity:** Low (blocks direct bulk restraint editing without re-selecting support type)
- **Affected Files:**
  - `src/pynitegui/qt/bulk_edit.py` (lines 64–69)

#### Root Cause
In `populate_bulk_inspector()` (`src/pynitegui/qt/bulk_edit.py:64-69`), `update_support()` enables the individual `Restrain *` checkboxes only when the bulk `Support` dropdown's current data is explicitly set to `"custom"` (or `"inclined"` in 3D):
```python
def update_support() -> None:
    custom = support.currentData() in (("custom", "inclined") if spatial else ("custom",))
    for box in restraints.values():
        box.setEnabled(custom)
```
Because the bulk `Support` dropdown always initializes to `"Keep existing"` (`currentData() is None`), all `Restrain *` checkboxes are permanently disabled until the user explicitly changes the `Support` dropdown away from `"Keep existing"`. Even when every selected node already has `support == "custom"` (or `"inclined"`), the user cannot toggle a single restraint DOF while keeping existing support types. Worse, in 3D, if the selected nodes are mixed `"custom"` and `"inclined"` or if the user selects `"inclined"` in the dropdown, `apply_bulk_nodes()` (`bulk_edit.py:217-225`) resets existing `"custom"` restraints before applying the bulk change.

#### Reproduction
```python
from PySide6.QtWidgets import QApplication, QCheckBox
from pynitegui.qt.app import MainWindow

app = QApplication.instance() or QApplication([])
w = MainWindow()
w.project.nodes["N1"].support = "custom"
w.project.nodes["N2"].support = "custom"
w.canvas.select_items(nodes={"N1", "N2"})

boxes = [b for b in w.selection_form.findChildren(QCheckBox) if b.text().startswith("Restrain")]
print("Restraint checkboxes enabled:", [b.isEnabled() for b in boxes])
```
- **Actual Output:**
  `Restraint checkboxes enabled: [False, False, False]`
- **Expected Output:**
  `[True, True, True]` when all selected nodes already use `"custom"` (or 3D `"inclined"`) supports, and `apply_bulk_nodes()` should apply any non-`PartiallyChecked` restraint checkboxes when `support_value is None` and the node's effective support is `"custom"` / `"inclined"`.

#### Recommended Fix
In `populate_bulk_inspector()`, enable the restraint checkboxes when `support.currentData() in allowed_custom_types` **or** when `support.currentData() is None` and all selected nodes have `node.support in allowed_custom_types`, and apply modified restraint checkboxes in `apply_bulk_nodes()` when `effective_support in allowed_custom_types`.
