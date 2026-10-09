# PyniteGUI Guide

A Python desktop editor for 2D/3D frames and axial-only trusses with PyNite.

For an audited comparison of PyNite engine capabilities with features actually
exposed here, see [PyNite Capability Coverage](TODO.md#pynite-capability-coverage).

## Run

Install uv, then run from the repository. uv installs and manages Python as well
as the project dependencies; Conda and a separately installed system Python are
not needed:

```sh
uv python install 3.12
uv sync --managed-python
uv run pynitegui
```

The project sets uv's `python-preference` to `only-managed`, so normal launches
also use uv-managed Python instead of discovering a Conda or system interpreter.

The application uses PySide6 / Qt Widgets and PyNite for structural analysis.

### Platform Checks

- macOS: the user reported successful operation on 2026-10-09. This is a smoke
  test, not an independently reproduced installation or full regression run.
  The supplied diagnostics show Qt 6.11.2 / Cocoa, a MetalSurface, and a ready
  WebGL 2.0 viewport using ANGLE's Apple M4 Max Metal renderer. Startup and
  next-launch preferences are auto, with platform defaults and no requested
  backend overrides. This records a working hardware-rendering path on that Mac;
  the macOS version, installation steps and individual workflows remain unrecorded.
- Linux: native NVIDIA/Wayland rendering and desktop interactions have been
  checked on the development host; backend-specific recovery is documented below.
- Windows: installation and native rendering checks remain pending.

## Spatial Frames

Use **File > New 3D Frame** for a new spatial project. **File > Examples** includes
**3D Cantilever - Biaxial Bending and Torsion** and **3D Space Frame - Gravity and Wind**.
**3D Truss Tripod - Joint Load** provides a pin-jointed spatial benchmark.
The existing New command still creates a 2D project. Dimensions never change
implicitly. Use **File > Create 3D Copy** to convert an existing 2D definition into
an independent, unsaved 3D window; the original geometry, undo history, file and
result snapshot remain untouched. Save the copy to its own file and analyze it
again. Closing the source window does not close the copy.

- Conversion places the original XY geometry at the entered global Z offset.
  **Preserve planar constraints** (default) explicitly fixes DZ/RX/RY at every
  node and preserves the original global DX/DY/RZ restraints and springs. These
  are real, editable custom supports, not hidden solver stabilization, and retain
  the original in-plane linear response.
- **Use spatial supports** removes the planar adapter constraints: free nodes
  have six free directions, pins restrain XYZ translations, fixed supports
  restrain all six directions, rollers remain global Y-only, and custom supports
  keep only their explicitly defined in-plane restraints/springs. Review supports
  before analysis; a planar truss or Y-only-supported frame may be unstable out
  of plane. No missing stiffness is silently restrained.
- IDs, assignments, material/section provenance, units, grid, cases/combinations,
  load fractions/intensities and self-weight settings are copied. Angled and
  member-local planar forces become global spatial azimuth/elevation forces with
  the same actual XY components, including on reversed/vertical members. Generated
  self-weight is regenerated, not duplicated; member roll starts at zero.
- Unreleased frames and axial-only trusses can be converted. Frame members with
  any DX/DY/RZ end release are rejected by name until general spatial end releases
  are supported; conversion never drops their releases. Redundant planar truss
  moment flags become the spatial axial-only type. Conversion copies definitions,
  not analytical results, and does not infer new joints at crossings.

- The central viewport uses bundled Three.js and Qt WebEngine, offline. Drag to
  orbit in Select mode, use Pan for translation, and wheel to zoom. Fit and the
  isometric/front/top/right/back/bottom/left camera presets reframe the model.
- The lower-right orientation gizmo rotates with the camera. Click a signed axis
  to animate to that view while preserving the current zoom and orbit center;
  **ISO** restores the isometric fitted view. The native view selector follows
  gizmo choices and shows **Orbit** during free navigation. With the gizmo focused,
  X/Y/Z select positive axes, Shift+X/Y/Z select negative axes, and Home restores
  isometric. This uses the bundled Three.js r180 `ViewHelper`, under its MIT license.
- In Member mode choose an XY, XZ or YZ work plane and its perpendicular offset.
  Two clicks draw a snapped member. Existing picked nodes take priority over the
  work plane, allowing connections between different planes. Escape cancels a
  pending member. Add Node opens exact XYZ entry; Model Tables can define complete
  node/member connectivity numerically. All engineering edits support undo/redo.
- In Select mode, enable **Move nodes**, choose **XY**, **XZ** or **YZ**, then drag
  a node sphere. Only the two in-plane coordinates move; the perpendicular
  coordinate stays at that node's original value, independently of the drawing
  offset. The preview grid temporarily follows this plane through the node.
  In-plane coordinates snap to the canonical model grid in every unit preset.
  Clicks still select; dragging empty space still orbits. Box select takes priority
  and the two explicit toggles are mutually exclusive; Shift-drag still starts a box.
  Escape, lost pointer capture, camera/viewport changes or an incoming model redraw
  cancel the preview without changing the project. An edge-on work plane shows
  feedback instead of guessing coordinates; choose its matching front/top/right view.
  Preview hides analytical overlays, loads and local-axis arrows until release or
  cancellation. Release validates one atomic move and one undo command; duplicate
  node positions and zero-length members are rejected without dropping results.
  Stale revisions/coordinates, disabled tools and out-of-plane/off-grid requests
  are rejected. A successful move selects the node and invalidates results.
  Supports, IDs, assignments, roll and manual load fractions are retained;
  self-weight is regenerated using the new lengths. Moving does not merge nodes
  or connect crossings; use the explicit topology commands and reanalyze.
- Select a member and choose **Split...** in its inspector or **Edit > Split
  Selected Member**. Enter a fraction measured from its start. The first segment
  retains the original member ID; new segments preserve material, section and roll.
  Existing coincident joints retain their supports, springs and nodal loads.
  Point loads keep their physical XYZ stations and reference directions; a 3D
  point force/moment at a cut remains a member-end load on the preceding segment,
  preserving its ID and rolled local axes instead of resolving it into nodal loads.
  Partial uniform/varying distributed loads are clipped and interpolated onto
  the segments; new pieces get new load IDs and retain cases/angles. Self-weight
  is regenerated from segment lengths without double counting.
- **Edit > Connect Intersections** explicitly connects actual XYZ crossings,
  T-junctions and existing interior nodes by creating shared endpoints and segments.
  Skew lines and crossings seen only in projection do not connect. Collinear
  overlaps are rejected before any changes. Both topology commands are atomic,
  undo in one step and invalidate results; repeat analysis after editing.
  Drawing or analysis never silently connects a crossing, and solver-only
  physical-member segmentation remains outside this workflow.
- **Edit > Subdivide Selected Members** divides each selected frame into 2–100
  equal segments. It uses the same load/roll-preserving split rules, retains
  coincident nodes and applies the entire selection as one undoable edit.
  Axial-only trusses are rejected because subdivision introduces unbraced joints.
- In Select mode, enable **Box select** or hold Shift while dragging a rectangle.
  Left-to-right selects enclosed nodes and complete members; right-to-left also
  selects members crossing the box. Ctrl/Command adds to the current selection;
  an empty replacement box clears it. Escape cancels without changing selection.
  Selection uses projected undeformed nodes and straight member centerlines,
  including geometry behind other members, not visible diagram/deformation curves
  or load arrows. Geometry behind the camera/near-far clip is excluded. Ordinary
  clicks still pick individual entities; orbit resumes when box mode is off.
- With multiple entities selected, the inspector offers explicit **Keep existing**
  choices. Assign member materials/sections and optional roll, node support presets
  or custom global restraints, all six support-spring stiffnesses, and load cases
  or a signed magnitude multiplier. A custom support starts from each node's
  current effective restraints; untouched checkboxes retain those values. Scaling
  changes both intensities of varying loads and preserves their angles/stations.
  All chosen changes are validated together and applied as one undoable edit.
  Invalid combinations, such as a spring on a rigidly restrained DOF, reject the
  entire batch. Geometry and unselected properties remain unchanged.
- XYZ coordinates, grid and plane offset use the selected project length units.
  SI/imperial selection preserves the physical model and valid results. Y is
  vertical; automatic self-weight acts in global -Y using full 3D member length.
- Nodes have DX, DY, DZ, RX, RY, RZ global degrees of freedom. Fixed restrains all
  six; Pin restrains XYZ translations only; Roller restrains global Y only.
  Custom exposes all six restraints. Positive bilateral springs are available
  on each DOF; a spring and rigid restraint on the same DOF are rejected.
- Members use per-member materials/sections and a roll angle about their local
  x axis. Local x runs from start to end; local y/z follow PyNite's transformation
  including roll. The inspector gives local-axis vectors in global XYZ, and the
  Local axes toggle displays the selected member's triad. A/Iy/Iz/J remain section
  properties; changing roll rotates the section without swapping stored values.
- Loads accept global FX/FY/FZ/MX/MY/MZ and member-local Fx/Fy/Fz/Mx/My/Mz.
  Load dialogs label the reference explicitly. In Model Tables, uppercase means
  global and mixed case means local. Nodal loads use global directions only.
  Uniform/varying distributed forces support partial spans; magnitudes are force
  per full member length, not projected length. Distributed moments are excluded.
- **Global angle** enters nodal/member point forces or distributed member forces
  by signed magnitude, azimuth and elevation. Azimuth is measured in global XZ
  from +X toward +Z (0 = +X, 90 = +Z); elevation tilts toward global +Y
  (+90 = upward, -90 = downward). The preview lists global FX/FY/FZ, including
  both end intensities for varying distributions. Negative magnitudes reverse
  the chosen direction. One saved load retains its angles; resolution into
  solver components is automatic. Angles are also editable in Model Tables
  and included in model-definition reports. Angular moments and local-axis
  azimuth/elevation input are not offered.
- Background analysis solves all six DOFs without planar stabilizing restraints.
  Insufficient restraints report affected global directions. Named cases,
  combination factors, progress/cancellation and stale-result rejection are shared
  with the 2D workflow. Reactions and nodal motions are global; rotations are radians.
- Choose **Type = truss** in the spatial member inspector, bulk inspector or Model
  Tables for a bilateral axial-only element. PyNite releases both bending planes
  and torsion at one end; the element transfers axial force only. E and A determine
  stiffness; Iy/Iz/J and roll do not add bending/torsion stiffness. Truss members
  use thinner spring/axial-colored lines and a `[truss]` label. This is not a
  tension-only or compression-only element.
  Manual member loads are rejected; apply forces at braced/restraint-compatible
  joints. Conversion to truss never silently removes existing member loads.
  Self-weight is lumped half to each end joint; frame self-weight remains distributed.
  At a truss-only joint, unsprung/unrestrained rotations are inactive and reported
  as **n/a**. Numerical elimination of these unused rotations cannot restrain
  translations or transfer moments through trusses. Explicit rotational supports
  and springs can react joint moments; moments on an inactive rotation are rejected.
  A joint shared with a frame retains its frame rotation DOFs. Shear, torsion and
  bending truss results are zero; deformed truss lines interpolate joint translations
  linearly, without a bending curve. Splitting a truss introduces a joint that must
  be appropriately braced; an unbraced intermediate joint is a real mechanism.
- The viewport **Supports** toggle controls global rigid-restraint and bilateral
  spring symbols without changing the model or results. Each constrained DOF has
  its own symbol: translational rigid stems end at grounded pads, rotational rigid
  restraints use stopped rings, translational springs use coils and rotational
  springs use spirals. Rotation symbols sit farther along the same negative global
  axis to distinguish them from translation symbols. Symbol sizes are illustrative,
  not physical dimensions or stiffness magnitudes. Rigid restraints use the support
  color; springs use the spring/axial color in both themes.
  Hover a symbol to highlight its DOF in a six-row global support tooltip, or hover
  a node to inspect all DX/DY/DZ/RX/RY/RZ states. Spring stiffnesses use the selected
  force/length or moment/radian units. Clicking a symbol selects its node for editing.
  Hover details remain available on nodes when symbols or labels are hidden.
  Tooltips disappear during navigation/drawing and are not part of PNG exports;
  visible support symbols are included in the exported viewport image.
- Deformed shows all three translational components, sampled in rolled local axes
  and transformed to global XYZ. Auto uses 15% of the largest coordinate extent;
  True Scale uses 1x; Custom uses the chosen factor. Peak is the actual sampled
  translational displacement magnitude, not an exact optimization or twist angle.
  Fit includes displayed deformed paths. Torsional rotation is reported numerically;
  this line-member viewport does not render cross-section twisting.
- Diagrams opens a retained member snapshot with N, Vy, Vz, T, My, Mz, dy and dz.
  Curves use local solver signs, with N positive in compression, and sample both
  sides of point-load boundaries. Combination and member selectors are independent
  of subsequent model edits. Enter **Distance** or click a member plot to inspect
  all eight values at that station. **Left side / Right side** queries the solver
  immediately before/after interior load boundaries, rather than interpolating
  screen curves. End stations query the member endpoint. Units change without
  changing the physical station; changing members resets the station to zero.
  CSV includes all six global node responses and member end values/extrema.
  Printable numerical reports split wide results into readable tables.
- The retained diagram window's **Combination Envelopes** tab compares checked
  analyzed combinations independently of the single-combination selector. Node
  bounds cover all six global motions and reactions; member summaries use exact
  solver extrema of N, Vy, Vz, T, My, Mz, dy and dz over each entire member.
  **Member Curves** shows sampled lower/upper bounds and solver-based one-sided
  station values with their governing combinations. First checked combination
  wins ties. These are independent bounds, not one simultaneous load state.
  Export envelope summaries as CSV or select them in **Print Results**; both
  retain snapshot identity, selected combination factors and project units.
  Whole-structure report diagrams are single-combination views; the envelope
  sections remain numerical summaries, not ribbons depicting one governing state.
- The viewport **Result** selector overlays N, Vy, Vz, T, My or Mz across the
  entire undeformed frame for the currently selected result combination. **Scale**
  multiplies automatic diagram height: 1x maps the largest absolute sampled value
  to 15% of the largest model coordinate extent (at least one grid spacing).
  This is a display scale, not a change to forces or stiffness. **Values** toggles
  member endpoint and sampled-extrema labels; **Loads** independently hides or
  shows load arrows. Fit includes diagram extents, and deformed shape can be
  displayed alongside them. Changing geometry clears stale result overlays.
- Diagram ordinates follow PyNite's local solver signs, with N positive in
  compression. Positive values offset toward local y for N, Vy, T and Mz, or
  local z for Vz and My, including member roll. The N/T offset direction is a
  plotting convention, not their force/moment vector direction. Point-load
  discontinuities retain both one-sided values. Legend ranges and value labels
  are sampled, not exact optimized extrema; use the member detail/CSV for
  solver-reported extrema. Units follow the current SI/imperial display choice.
- The save icon on the viewport result toolbar exports the current camera view
  as PNG, including visible geometry, diagram labels, signed-axis gizmo and the
  combination/unit/sign legend. The native controls and editing sidebars are
  excluded. For printable diagrams use **File > Export Results > Print Results**
  or the retained diagram window's export menu. Select N, Vy, Vz, T, My and/or Mz
  and check **Isometric**, **Front XY**, **Top XZ** and/or **Right YZ** views.
  Each component/view pair gets a page with snapshot ID, combination and units.
  Preview offers native printing/save-to-PDF. These are deterministic orthographic
  diagrams from the analyzed snapshot, not captures of the live orbit camera;
  they work without WebGL and always use a light, print-friendly palette.
  Diagram amplitude maps the largest absolute sampled ordinate across the whole
  model to the chosen percent of model extent (at least one grid spacing).
  Side/sign controls change only printed geometry and display labels, not solver
  tables, CSV or envelope bounds. Supports/springs and factored combination loads
  have separate visibility controls. Triangles identify rigid supports, squares
  bilateral springs, and labels identify global DOFs. Moment double arrows follow
  their global/rolled axes; normal-to-view forces/moments use a circle toward the
  viewer or cross away. Projected members and offsets can overlap or be edge-on;
  choose additional views. Dense labels are omitted instead of overlapped; use
  numerical model/results tables for exact definitions and solver extrema.

Current spatial scope is linear, unreleased frame members and bilateral axial-only
trusses. No plates/shells, solids, nonlinear effects, manual frame member releases,
or implicit physical-member segmentation
are implemented in this mode yet. Multi-selection supports bulk assignments and
deletion; use Model Tables for coordinated geometry editing. Geometry requires explicit shared endpoints;
overlaps, interior nodes, crossings without a shared joint and disconnected groups
are rejected before analysis. Skew lines are not mistaken for intersecting members.
Dedicated support/spring symbols and hover details show global DOFs and selected-unit
stiffnesses; the inspector and model tables provide exact editing controls.

Qt WebEngine is included with the full PySide6 dependency. Three.js 0.180.0 and
OrbitControls are bundled unmodified under their MIT license in
`src/pynitegui/qt/viewport3d/vendor/`; no CDN is used. The Chromium sandbox is not
disabled by the application. On Linux Conda hosts with a mismatched Brotli common
library, a narrowly scoped loader retries the system library only for the known
missing-symbol import failure. Other import failures are displayed explicitly;
numeric model editing remains available but rendering is unavailable.

### Graphics Recovery

When a Linux graphics driver/EGL/Vulkan mismatch prevents WebGL2 from starting,
close PyniteGUI after saving and launch with:

```sh
uv run pynitegui --software-rendering
```

This requests Chromium's CPU-based ANGLE/SwiftShader driver before Qt initializes,
disables GPU compositing, and requests software OpenGL for Qt. Qt can select its
platform-specific WebGL driver instead; the tested NVIDIA/Wayland configuration
uses Mesa llvmpipe, while offscreen Qt selects the NVIDIA driver with CPU compositing.
This is a compatibility mode, not a guarantee that every GPU operation is disabled.
No `QT_QUICK_BACKEND` override is applied because
Qt WebEngine's software GL driver is incompatible with that override on some hosts.
This mode does not install drivers, alter the operating
system, disable Chromium sandboxing, or enable the unsafe-WebGL fallback flag.
The view uses only bundled local content. Some EGL/driver warnings may remain even
when the viewport renders successfully. CPU rendering can be slower for large
models. Qt's `--disable-gpu` workaround alone is insufficient for this WebGL2
viewport; it may disable the context Three.js needs.

**View > 3D Rendering > Software (CPU Compositing)** saves this preference for normal future
launches; rendering changes require an application restart. A failed viewport
also offers **Use Software Rendering on Restart**, keeping model data and unsaved
work intact. **Automatic (GPU)** restores the normal backend on subsequent starts.
The command-line options `--graphics=software` / `--graphics=auto` override saved
preferences for one launch. Existing unrelated Chromium flags are retained;
explicit software mode replaces conflicting graphics-disable/backend flags.

Backend references: [Chromium SwiftShader driver documentation](https://chromium.googlesource.com/chromium/src/+/main/docs/gpu/swiftshader.md)
and [Qt WebEngine hardware acceleration](https://doc.qt.io/qt-6.10/qtwebengine-features.html#hardware-acceleration).
Terminal warning/output lines are not shell commands; paste only the command above.

### NVIDIA Hardware Rendering on Linux

Automatic rendering now applies the verified NVIDIA/Wayland configuration before
Qt starts when exactly one GPU drives connected displays, that GPU is NVIDIA,
both driver manifests exist, and no explicit graphics overrides are present.
On that setup, launch normally with `uv run pynitegui`; New 3D Frame needs no
additional terminal settings. A saved software preference remains respected:
select View > 3D Rendering > Automatic (GPU) and restart to use hardware rendering.
Connected hybrid/multiple-GPU displays, non-Wayland sessions, and explicit backend
settings are left untouched rather than guessed.

`nvidia-smi` confirms the NVIDIA driver is running, but Qt and its embedded browser
must also select compatible graphics backends. On the tested Ubuntu Wayland host
with a Quadro RTX 4000 and driver 580.178.04, automatic EGL selection chose Mesa
llvmpipe, causing WebGL2 to be blocklisted. Selecting NVIDIA EGL alone enabled
WebGL but left Qt unable to create its OpenGL context. Selecting NVIDIA EGL and
Vulkan together rendered the frame with GPU compositing enabled:

```sh
env -u QT_OPENGL -u QT_QUICK_BACKEND -u QTWEBENGINE_CHROMIUM_FLAGS \
  QSG_RHI_BACKEND=vulkan \
  __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json \
  VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json \
  VK_LOADER_LAYERS_DISABLE='*MESA*' \
  uv run pynitegui --graphics=auto
```

Run from the project directory after saving and closing the existing app. These
environment settings apply only to this process; no system graphics configuration
or browser blocklist/sandbox is changed. `--graphics=auto` overrides a saved
software preference for this launch. The driver JSON paths must exist on your
distribution. Use the uv-managed environment from the setup instructions above;
the stale Conda-based environment on the test host has been replaced.
On this host, the managed-Python launch also required disabling Mesa Vulkan
layers: without that setting, the native Vulkan loader crashed during
`vkCreateInstance`. The layer setting is launch-scoped, not a system-wide change,
preserves unrelated layers, and does not disable the Chromium sandbox or GPU blocklist.

For diagnostics, add `QT_LOGGING_RULES='qt.webenginecontext=true;qt.webengine.compositor=true'`
to the command. Successful hardware rendering should report the Quadro as the
`QSG RHI Device`, NVIDIA in `GL Renderer`, and `GPU Compositing: Enabled`; viewing
the model must also succeed. A working context alone does not prove Qt can display it.
Use software rendering if this configuration does not work on another machine.

On GNOME Wayland, Qt currently omits its own client-side decorations for Vulkan
windows. PyniteGUI supplies a compact title bar for affected main windows and
its own box/form-layout dialogs, with close, minimize/maximize where applicable,
title dragging and double-click maximize. Closing still uses the existing
unsaved-work confirmation. Other platforms/backends retain their native controls.
See [Qt's Vulkan decoration limitation](https://codebrowser.dev/qt6/qtbase/src/plugins/platforms/wayland/qwaylandwindow.cpp.html).

References: [Qt NVIDIA graphics integration](https://doc.qt.io/qt-6.10/qtwebengine-features.html#nvidia-on-linux),
[NVIDIA EGL vendor selection](https://github.com/NVIDIA/libglvnd/blob/master/src/EGL/icd_enumeration.md),
and [Vulkan driver selection](https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderDriverInterface.md).
See also [Vulkan layer filtering](https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderLayerInterface.md).

**View > 3D Rendering > Diagnostics** shows the observed WebGL renderer,
vendor, WebGL/shader versions and information source. Driver details may be
masked by the platform; unavailable values stay explicit. Startup preference,
next-launch preference and requested environment overrides are listed separately
from the observed Qt window surface and WebGL driver. Selecting Automatic is
not proof of hardware rendering, and Software describes requested compositing,
not a guarantee about the platform's chosen WebGL driver. Refresh rechecks the
active 3D viewport; a missing/failed viewport does not invent GPU details.
This panel does not query the compositor's physical GPU or a driver package version.

## Workflow

- The unit selector also offers SI (mm, N) and Imperial (ft, kip). The mm/N
  preset uses N-mm moments, N/mm line loads, MPa stresses, and mm2/mm4 sections.
  The ft/kip preset uses kip-ft moments and kip/ft line loads, while keeping
  section properties in in2/in4 and material stiffness in kip/in2. Weight
  density follows the geometry volume units (N/mm3 or kip/ft3).
- File > Examples opens fresh, editable models: a simply supported beam,
  distributed-load portal frame, cantilever with partial distributed/angled/tip
  loads and a moment, partially loaded continuous beam, pitched frame with local
  roof loads, and a two-storey gravity/wind frame with separate combinations.
  A seventh example demonstrates a beam loaded only by automatic self-weight.
  A triangular truss example demonstrates axial-only members and joint loads.
  Examples retain the current unit system and prompt before replacing unsaved
  work. They start as unsaved projects, not as files to overwrite.
- View > Appearance selects Light or Dark. The preference is saved between app
  sessions, separately from project files. It updates all open editor/diagram
  windows, including the grid, engineering symbols, labels, tables, and plots,
  without changing units, undo history, results, inspection positions, or plot
  zoom/navigation history. Printed reports remain light for paper/PDF output.
  Properties scroll when the dock is too short for all fields.
- Choose Imperial or SI from the unit selector at the bottom-right, or use
  Edit > Units. All dimensional inputs, inspectors, coordinate readouts, load
  labels, property tables, results, and open diagrams use the selected system.
  Switching is undoable, preserves the physical model and valid results, and is
  saved with the project. New projects keep the currently selected system.
- Choose Member (M), then click two points. Coordinates snap to the project grid
  or an existing node. Escape or right-click cancels an unfinished member.
- Choose Select (V) and click a node or member, or select it in the structure
  tree. Edit properties in the inspector and press Apply.
- In Select mode, Ctrl/Shift-click toggles nodes/members on the canvas. Drag an
  empty area to box-select nodes and any members that cross the rectangle;
  Ctrl/Shift adds that box to the current selection. Escape/right-click cancels
  the box without changing the selection. A plain empty click clears it. The
  tree supports Ctrl-click toggles and Shift-click ranges, including manual
  loads. Edit > Select All (Ctrl+A) selects all geometry and visible manual loads;
  generated self-weight remains read-only. Selected geometry and load arrows
  are highlighted, and selections stay synchronized with the tree.
  Multiple items show a bulk inspector: assign member materials/sections and
  end hinges, node supports/custom restraints, or load cases and a signed
  magnitude multiplier. The multiplier scales both distributed-load intensities,
  preserving fractions, angles, and directions. Keep existing and partially
  checked boxes leave properties unchanged; checked sets on and unchecked sets
  off. Choose custom before editing restraint boxes; unmodified restraints retain
  each node's effective previous support. Apply validates all selected edits in
  one transaction; Delete Selection removes selected items and their dependents
  in one undo step. Selection alone never invalidates results; actual bulk edits
  do. Single-node dragging and single-entity commands still require one target.
  Hiding a load case removes its loads from the selection without clearing
  selected geometry. Opening another project clears the selection.
- Edit > Model Tables opens draft Nodes, Members, and Loads tables. Enter signed
  coordinates and load values directly (scientific notation is accepted), choose
  endpoints/materials/sections/cases, and set custom restraints or end hinges.
  Add rows or remove selected rows to build/edit the model numerically. IDs are
  generated and read-only; references to newly added rows are available immediately.
  OK validates all three tables and applies one undoable edit; Cancel discards
  the draft. Removing a referenced row requires explicitly removing or reassigning
  its dependent members/loads before OK. Invalid input never partially changes
  the active model. Untouched numbers preserve their full stored precision.
  Coordinates use the selected length unit; each load row shows its magnitude
  units, and the end-intensity header identifies distributed-load units. Changing
  load type/direction reinterprets the entered magnitude in those units. Positions
  are member fractions, angles are degrees, and end intensity/fraction apply to
  distributed loads only. Preset restraint checkboxes show the effective supports
  but are editable only for custom supports. Generated self-weight is not listed
  as a manual load; configure it separately in Edit > Self-Weight.
- Select a member and choose Split in its inspector, or Edit > Split Selected
  Member, to divide it at a fraction measured from its start node. The first
  segment keeps the original member ID. Point loads and moments retain their
  physical locations; a load at the split becomes a nodal load at the new joint.
- Edit > Connect Intersections splits crossing members and T-junctions into
  explicit segments sharing one node. Existing interior nodes are also connected.
  Splitting and connecting are each a single undoable edit.
- Edit > Check Model reports overlapping members, interior-node connections that
  need splitting, and disconnected groups in the **Model Findings** dock.
  Select a finding and press **Select affected geometry**, or double-click it,
  to highlight its referenced entities in the canvas and tree. Analysis failures
  also populate this dock, including recognized node/DOF instability references.
  General failures without a specific reference remain readable with selection
  disabled. Navigation does not edit the model. Engineering edits clear findings;
  unit changes preserve them. Analysis also runs the model checks.
- **Edit > Subdivide Selected Members** divides selected frame members into
  2–100 equal segments in one undoable edit. The first segment retains the member
  ID; outer-end releases, assignments, load locations/cases and distributed
  intensity profiles are preserved. Existing coincident nodes retain their
  engineering properties. New internal frame connections are rigid. Axial-only
  trusses are rejected because subdivision creates unbraced intermediate joints;
  use explicit split/connect operations with appropriate bracing instead.
- Select a member and check Released for its Start or End moment RZ in
  the inspector, then press Apply. Hollow circles mark released member ends.
  These releases disconnect in-plane moment transfer at the member connection;
  they do not change node supports or disconnect axial/shear translations.
  Splitting and connecting preserve releases at original outer ends only;
  newly created internal connections stay rigid.
- Member properties also offer axial DX and transverse shear DY releases at
  either end, in member-local axes. Two crossbars mark an axial release; a hollow
  square marks a shear release. Hover for the released directions. The editor
  rejects internally unstable combinations: DX at both ends, DY at both ends,
  or more than two DY/RZ releases on one member. Joint mechanisms are still checked
  during analysis. Clear axial/shear releases before converting a frame to truss.
- Assign a node support using Support, or select a node/member and use Load (L).
- The desktop app keeps a separate autosave snapshot of unsaved changes every
  30 seconds in Qt's per-user application-data recovery directory. These files
  never overwrite your project. After an interrupted session, startup offers
  Recover/Discard; File > Recover Autosave reopens that list. Snapshots owned by
  another running process are excluded. Saving or intentionally closing clears
  this window's snapshot; a cancelled close retains it. Unsaved recovered work
  stays marked dirty. File > Recent Projects remembers the latest ten files.
- Choose custom in the node Support inspector for independent global horizontal
  (DX), vertical (DY), and rotational (RZ) restraint checkboxes. Checked means
  restrained. Existing free/pin/roller/fixed presets remain available. Custom
  support symbols show horizontal/vertical restraint lines and a square for
  rotational restraint; hovering identifies the restrained degrees of freedom.
- Node properties include Spring DX, DY, and RZ stiffness. Zero means absent;
  positive values create bilateral springs along global X/Y or about global Z.
  Translational stiffness uses force/length; rotational stiffness uses moment/rad
  in the selected unit system. A rigid restraint and a spring cannot occupy the
  same direction: explicitly free that direction or set its spring to zero.
  Springs and releases are also editable atomically through bulk properties and
  Model Tables, with normal undo/redo and result invalidation.
- In Select mode, drag a node to move it with snapping. Dashed connected members
  preview the move; releasing creates one undoable edit. Escape/right-click
  cancels. Coincident nodes and collapsed members are rejected without changing
  the model. Moving geometry invalidates analysis results.
- The selector above the structure tree shows all load cases, one case, or hides
  loads. It filters load arrows and tree entries only; analysis still includes
  all loads according to the selected combination.
- For an angled point force on a node or member, choose Direction > Angle,
  then enter a signed magnitude and an angle in degrees. Angles are global,
  counterclockwise from +X: 0 points right, 90 up, -90 down, and 180 left for
  positive magnitudes. A negative magnitude reverses the chosen direction.
  The live FX/FY preview shows each component on its own line in the selected
  force units. One angled load is saved
  and edited as a single object; its components are resolved automatically for
  analysis. Negative combination factors reverse the force normally.
- Member loads can be Point or Distributed. Distributed loads use start/end
  intensities in kip/in or kN/m and start/end fractions along the member. Equal intensities
  give a uniform load; different intensities give a linear ramp, including
  triangular or sign-changing loads. Choose FX/FY for global axis loading or
  Angle for a global angled distribution; one angle applies to both endpoint
  intensities. Negative intensities reverse that direction. Intensities remain
  force per unit member length, not projected length. Select a load in the tree
  to edit it in the inspector.
  Splitting clips each loaded region and interpolates its endpoint intensities,
  preserving the original distribution without creating artificial nodal forces.
- Member forces also offer Local x, Local y, and Local angle for both point and
  distributed loads. +local x runs from the member start node to its end node;
  +local y is 90 degrees counterclockwise from that direction in the XY plane.
  Local angle is counterclockwise from +local x. These definitions are resolved
  to global FX/FY at the solver boundary, independently of PyNite's internal
  3D axis orientation. The preview always shows global components. Local loads
  rotate with member geometry, including when its endpoints are reversed.
  Split segments retain the local reference. A point force at a split becomes
  a global angled nodal load with the same vector, since a node has no unique
  member-local axes. Reassigning a local point load to a node in the inspector
  also preserves its current global vector.
- Edit > Load Cases and Combinations manages named load cases and linear
  combinations. Assign each load a Case in its creation dialog or inspector.
  Set Default chooses the case for new loads without reassigning existing loads.
  Renaming a case updates all references; a case used by loads, combinations,
  or the default cannot be deleted until those references are removed.
  Add or edit a combination by checking its included cases and entering factors.
  At least one combination is required; zero and negative factors are supported.
- Edit > Materials opens reusable material definitions. Add or edit a name, E,
  Poisson ratio, and density; G is calculated for an isotropic material. Select
  a member, choose Material in its inspector, and press Apply to assign it.
  Set Default controls newly drawn members without changing existing assignments.
  Renaming a definition updates its references; assigned/default materials cannot
  be deleted until members are reassigned and a different default is chosen.
  Library provides five reference presets: US/EU typical steel, generic aluminum,
  and C30/37 concrete with plain or reinforced-concrete weight. Search, preview
  E/Poisson ratio/G/weight density, and Add to Project. Imports do not reassign
  members or change the default. Source distinguishes Library from Custom;
  renaming retains the preset, while numerical edits make it custom.
- Edit > Sections manages reusable area, Iy, Iz, and J definitions. Choose
  Section in a selected member inspector and press Apply. Section defaults,
  renaming, deletion protection, and undo work like material definitions.
  Library opens a searchable, family-filtered AISC starter catalog. Choose the
  in-plane strong or weak bending axis and Add to Project, then assign the
  definition to members or Set Default. Imports never replace existing sections;
  duplicate names receive a suggested suffix. The Source column distinguishes
  catalog definitions from custom properties. Renaming preserves provenance;
  changing any numerical property makes the definition custom.
  Edit > Grid changes the drawing grid spacing.
- Use Pan (P) to drag the view, the mouse wheel to zoom, and Fit (F) to frame it.
- Analyze (F5) runs PyNite in an isolated worker process supervised off the GUI
  thread. The status bar shows a busy indicator and actual phases: checking the
  model/supports, building the model, solving combinations, checking stiffness,
  and collecting the snapshot. It does not invent a percentage or completion
  time. The stop icon cancels even during numerical solves or diagnostics and
  waits for worker cleanup; editing remains available while analysis runs.
  A rerun retains the last valid results until a new snapshot succeeds. Cancelled
  or failed reruns do not remove them; engineering edits still invalidate results
  normally, and stale worker replies are rejected. Unit-only changes can be made
  during a solve without changing the physical model. Closing while analysis
  runs cancels the worker first, then uses the normal unsaved-change prompt.
  Reactions and nodal displacements
  appear in Results. Choose a combination above the result table to update
  reactions, displacements, deformation, and factored load annotations without
  another analysis. Deformed overlays the displaced members. Its toolbar offers
  Auto (maximum displayed displacement is 15% of the model extent), True Scale
  (1x), and Custom amplification. The current factor and actual maximum sampled
  displacement are shown separately; scaling never changes analysis results.
  The maximum is sampled at 41 positions per member, not an exact extremum search.
  Fit (F) includes the visible deformed shape. Diagrams opens whole-structure axial, shear, and bending moment
  diagrams with one common amplitude scale for every member.
  Whole Structure also offers Default/Opposite side and Reverse display signs.
  Side changes placement only; sign reversal changes plotted values and labels
  the convention in the title (+ tension for reversed axial diagrams).
  These per-window controls survive unit/combination/theme changes but do not
  change Member Detail, numerical tables, CSV, analysis results, or saved models.
  Whole-structure labels use screen-space collision checks, prioritize member
  IDs, and add leader lines when moved away from their values. If no readable
  placement exists, a crowded label is omitted; zooming/resizing retries it.
  Labels stay within the plot and use the same placement logic in print images.
  Numerical tables and Member Detail remain the authoritative way to inspect
  every value; label placement never changes geometry or computed results.
  New diagram windows start with the standard convention. Member Detail
  provides axial force, local shear, bending moment, and transverse deflection
  plots for any member, sharing one distance axis.
  Supports and Loads toggles show/hide rigid restraints, spring symbols/stiffness,
  and combination-factored manual/generated loads on Whole Structure. Moment
  arrows respect the global clockwise/counterclockwise sign. Symbols share their
  geometry with the editor; spring/load labels avoid other text and symbols.
  Member Detail shows end support/spring and local-release context plus loads on
  that member and its end joints; longer load summaries are available by hovering.
  Joint loads in this context describe applied loads, not the member's share.
  Printed diagram choices inherit these toggles. Envelopes do not depict a single
  load state because their bounds can come from different combinations.
  In Member Detail, enter a distance or click a plot to inspect N, Fy, Mz, and dy.
  Left/Right side selects one-sided values at point-load jumps. Dashed cursors
  align all four plots. Member Results lists start/end values and solver minimum/
  maximum values for each member in local axes and current units; each extrema
  column is independent, not a set of forces at one common station.
  Diagram windows have their own combination selector and retain the analyzed
  snapshot even when the editor changes. The inspector always edits original
  case values, not the factored values displayed after analysis.
- Diagrams > Envelopes compares checked combinations from that analyzed
  snapshot without another solve. The main combination selector does not change
  the envelope selection. Nodes lists displacement/reaction bounds; Members
  lists exact solver extrema for N, Fy, Mz, and dy over entire members. Each
  minimum and maximum identifies its governing combination. Ties use the first
  checked combination in list order; undefined truss-joint rotations remain n/a.
  These are independent bounds, not a simultaneous force/displacement state.
  Member Curves shows sampled min/max envelopes in local axes, including both
  sides of load jumps. Curve peaks are sampled, not exact extrema searches; use
  Members for solver extrema. Enter a distance or click a curve to inspect exact
  one-sided station bounds and their governing combinations. Left/Right side
  chooses the side at point-load jumps. Axial N remains positive compression;
  Whole Structure placement/sign controls do not change envelopes.
  The envelope export icon saves both summary tables as CSV with units, source,
  snapshot identity, selected combinations/factors, and self-weight metadata.
  Its export menu also offers Print envelopes, opening report choices with an
  envelope-only selection and the currently checked combinations. General Print
  Results can include envelopes alongside model definitions, single-combination
  results, and force diagrams. Report combination checkboxes are independent
  copies: changing them does not change the diagram window's selection.
  Printed envelopes contain exact node/member summary bounds and governing
  combinations, not sampled curves. Selected factors, units, conventions, and
  analysis identity are included; undefined rotations remain n/a. In mixed
  reports, single-combination sections and envelope sections are labelled
  separately. Unit/theme changes retain the selection. Envelope choices are
  window-local, not saved in the project.
- File > Export Results saves node reactions/displacements or member end/extrema
  values as CSV in the selected units and combination. Files include source,
  analysis ID, UTC timestamp, model signature, and unit system. Undefined joint
  rotations export as n/a; CSV/report metadata also identifies the self-weight
  case and multiplier when enabled. Extrema have no common station, so x is blank.
  Text identifiers that could be interpreted as spreadsheet formulas are
  prefixed with an apostrophe; numeric loads/results retain their signs.
  Print Results first opens content choices for model definitions, node/member
  results, and selected axial/SFD/BMD diagrams, then opens native print preview.
  Model definitions include nodes/effective supports, frame/truss assignments
  and local releases, spring stiffnesses, materials/section properties and provenance, manual and generated
  unfactored loads, defaults, and load combinations. Diagrams use the selected
  analyzed combination, snapshot ID, units, and explicitly labelled display
  side/sign/amplitude. Printing from a diagram window starts with its current
  diagram settings. Charts use a light print palette even in dark mode and have
  their own pages. Reports can be printed or saved to PDF through the print
  dialog. Cancelling content selection does not open preview or change the model.
- Diagram windows show their analysis ID, analysis time, original editor revision,
  and whether their model matches the current editor. A new analysis of the same
  model is distinguished from the earlier snapshot. The export icon in a diagram
  window exports/prints that snapshot, even after editor results are invalidated.
  Unit and combination changes retain the snapshot ID; engineering changes
  require a new analysis before exporting from the main editor.
- Save/Open uses versioned `.pynite.json` project files. Ctrl+Z and Ctrl+Shift+Z
  undo and redo model edits. Delete removes the selected entity and its dependent
  members/loads. Unsaved changes are marked in the title and checked on exit.
- File > Examples > Simply Supported Beam loads a 420-inch beam with a 10-kip downward
  midspan load. Each support should react with 5 kip. In SI the same physical
  example displays a 10.668 m span, 44.4822 kN load, and 22.2411 kN reactions.

## Linked Results

The native Results dock contains **Nodes**, **Displacements**, **Reactions** and
**Member forces** tabs. Nodes retains the combined overview. Header clicks sort
numbers by their full values; six-significant-digit display does not determine
the order. Undefined released-joint rotations remain `n/a`.
Selecting rows highlights the corresponding geometry and structure-tree items;
Ctrl/Command/Shift selection supports multiple entities. Selecting geometry
reveals and scrolls to its result rows, switching between node and member tabs
when needed. These selection changes do not edit the model or invalidate results.

The member tab loads end values and independent minimum/maximum values on demand.
The extrema in a row can occur at different stations; they are not one combined
force state. Double-click a member row to open **Member Detail** for that member
and snapshot. Unit and combination changes refresh the tables while preserving
entity selection. Engineering edits clear all active result tables until another
analysis; retained diagram windows continue to identify their own snapshots.

The **Equilibrium** tab compares global applied loads and support reactions for
the selected combination, including generated self-weight and partial distributed
loads. Planar models show FX, FY and MZ; spatial models show all six components.
Moments are taken about the first project node, whose coordinates are displayed.
Residuals and tolerances use the selected units. Each tolerance is `1e-7` times
the sum of absolute component contributions, plus an absolute floor of `1e-8`
kip for forces or `1e-6` kip-in for moments. Balance alone does not verify
structural design or modelling assumptions.

The dock labels analysis as analyzing, cancelling, cancelled, failed, current or
outdated. If a previous snapshot is retained during a new attempt, its identity
and combination remain explicit. Engineering edits clear its tables. A failed
attempt leaves the previous valid snapshot available, with failure details in
the status tooltip.

## Units

Use **Edit > Units** to choose length (mm, cm, m, in, ft) and force
(N, kN, lbf, kip) independently. All 20 combinations also appear in the
bottom-right selector; the four original preset names remain unchanged.
The dialog previews derived units before applying a change. Apply is undoable;
Cancel leaves the project unchanged. These choices persist in 2D/3D projects,
recovery snapshots and 3D copies without changing canonical engineering values
or invalidating valid results.

For custom choices with mm/cm/m geometry, material stress uses MPa and section
properties use mm2/mm4. With in/ft geometry, sections use in2/in4; stress uses
kip/in2 for kip forces and psi for other force choices. Moments, distributed
loads, weight density and support stiffness use the chosen length/force units.
The dialog shows these conventions even for mixed metric/Imperial choices.
Files retain their current schema versions and store a deterministic unit key;
older application builds that lack the custom choices reject those unit keys.

| Quantity | Imperial (in, kip) | SI (m, kN) | SI (mm, N) | Imperial (ft, kip) |
| --- | --- | --- | --- | --- |
| Coordinates, lengths, grid, displacements | in | m | mm | ft |
| Forces | kip | kN | N | kip |
| Moments | kip-in | kN-m | N-mm | kip-ft |
| Distributed intensity | kip/in | kN/m | N/mm | kip/ft |
| E and G | kip/in2 | MPa | MPa | kip/in2 |
| Weight density | kip/in3 | kN/m3 | N/mm3 | kip/ft3 |
| Section area | in2 | mm2 | mm2 | in2 |
| Iy, Iz, J | in4 | mm4 | mm4 | in4 |
| Rotation | rad | rad | rad | rad |

Density is weight per volume, not mass density in kg/m3. Load fractions,
Poisson ratio, combination factors, and deformation amplification are
dimensionless and do not change with units. Switching preserves grid spacing;
enter a new value in Edit > Grid when a round metric spacing is wanted.
Section and material names are identifiers and are not renamed by conversion.

The model, saved engineering numbers, and solver use canonical inch-kip units.
Only input/output boundaries convert. This avoids repeated conversion drift and
keeps old projects physically unchanged. Unedited property fields retain their
full internal precision even when displayed with fewer decimals. Open diagram
windows retain their analyzed geometry and loading, but follow the active unit
selection. Unit changes alone do not require another analysis.
Conversions use exact inch and pound-force definitions from
[NIST SP 811](https://pml.nist.gov/cuu/pdf/sp811.pdf), with other factors derived
by their physical dimensions.

## Engineering Scope

Dimensional inputs and results use the selected system listed above.
The editor models frames in the global XY plane. Out-of-plane translation and
rotations are restrained at every node. A pin restrains X/Y translation, a
roller restrains Y translation, and a fixed support also restrains Z rotation.
Custom supports independently restrain global DX, DY, and RZ. Bilateral elastic
springs may resist any otherwise free global DX/DY/RZ direction. Spring reactions
are the opposing stiffness times displacement/rotation and are included in all
reaction tables, envelopes, and exports. Inclined supports, one-sided springs,
and semi-rigid member-end springs are not implemented. Point loads support global FX, FY,
MZ, and signed angled forces. Member point/distributed forces additionally
support local x/y and member-relative angles. Nodal forces use global axes only;
distributed moments are not implemented.
Loads belong to named cases. User-defined combinations superpose those cases
with finite factors using linear elastic analysis. The initial project has
Case 1 and a Service combination at factor 1. No design-code factors or
envelopes are generated automatically.
Edit > Self-Weight opts into automatic gravity loading in a chosen load case,
with a positive multiplier and total unfactored weight in the current force
units. Frame members receive global downward FY uniform loads using their
own weight density times section area. Truss weight is lumped equally to the
two end nodes; it never creates transverse member bending. Zero-density members contribute no
weight. The case must appear in a combination to affect that combination;
combination factors apply normally. Existing manual loads are additional, so
do not also enter the same member self-weight manually. Generated loads appear
as read-only entries in the structure tree and respect case visibility filters.
They are recalculated after material/section changes and member splitting,
not duplicated as editable project loads. Disabling or changing self-weight is
undoable and invalidates results; case renaming follows the reference, and a
referenced case cannot be deleted. Density is weight per volume, not kg/m3;
do not multiply it by gravity again.
Member load positions are fractions measured from the start node.

Member moment releases act about local Z, normal to the XY frame. End releases
are independent: one member may hinge at a shared node while other members
retain a rigid connection. Releasing both ends supports pin-jointed frames with
nodal loads, but the member remains a beam and can still bend under transverse
member loads; it is not a separate axial-only truss element. Axial DX and shear DY
releases disconnect their corresponding member-end translations without changing
joint supports or other members at that node. Released member ends can therefore
move relative to the joint: node tables show joint displacement while member
deflections show the member side of the release. Out-of-plane and partial-stiffness
releases are not exposed in this editor.

PyNite 3.0.0 condenses translational releases correctly for forces but its member
deflection reconstruction otherwise uses joint translations at released ends.
The linear-analysis adapter recovers the eliminated end displacements from
PyNite's uncondensed stiffness and fixed-end vectors with zero released-end force,
then uses PyNite's own deflection/extrema routines. It does not alter the global
solve or nodal reactions. Analytical axial-release and fixed-guided bending
benchmarks cover this behavior, including split members and result transport.

Choose Type = truss in the member inspector, bulk inspector, or Model Tables
for an explicitly axial-only member. Truss ends are implicitly pinned; saved
frame hinge settings are retained but ignored until switched back to frame.
Dashed member lines and end circles distinguish trusses on the editing canvas.
Materials and section area determine EA stiffness; Iy/Iz/J remain stored for
switching back to a frame but do not affect the planar truss response.
The adapter uses [PyNite rotational end releases](https://pynite.readthedocs.io/en/latest/member.html)
with strict joint-only loading to enforce this behavior in the XY model.
Member point/distributed forces and moments are rejected on trusses, including
when changing a loaded frame to truss. Move loads to nodes explicitly; there is
no silent conversion. Splitting a straight truss bar creates a new joint that
must be properly restrained or braced: an unbraced intermediate joint generally
introduces a transverse mechanism. Mixed frame/truss structures are supported;
a rigid frame connection at a shared joint retains its rotational DOF.

When every connected member end at a node without an RZ restraint or spring is hinged, the shared
rotation has no stiffness. Analysis removes that unused rotation from the
unknowns without restraining translations or transferring connection moments.
Results show RZ as n/a for those joints, not a physical zero rotation. Individual
member end rotations and deformations remain governed by the released beam.
A net nodal MZ on such a joint is rejected for each analyzed combination unless
a moment-resisting connection, rotational support restraint, or RZ spring is provided. Real translational
mechanisms are not hidden by adding translational restraints.

Analysis checks whether the actual supports prevent planar rigid-body motion
and lists affected global DX/DY/RZ directions when they do not. Solver
instability errors are translated into joint-level messages where possible.
A diagonally scaled stiffness check rejects singular/numerically ill-conditioned
results even when the solver returns finite values. Up to 600 free planar degrees
of freedom it uses a dense spectral check. Larger models retain sparse matrices
and inspect up to six near-zero modes with a shifted sparse eigensolver. This
targets mechanisms in the positive-semidefinite elastic stiffness, not buckling
modes. Zero-stiffness directions are detected directly, including in large
models. Diagnostics show up to 24 affected node/direction labels; these are hints,
not a unique identification of every defective member. Very large stiffness
contrasts can cause poor conditioning without a physical mechanism. An incomplete
sparse check does not certify the model: a found mechanism is reported, otherwise
results are rejected with a convergence message. Nonfinite-result checks remain
active. These are linear-model checks, not nonlinear stability verification;
sparse factorization can still consume substantial memory for large models.

Each member references a reusable material definition. Editing that definition
updates every member assigned to it and invalidates results. Split member
segments inherit the original material. The default definition is Steel_A992;
E/G and weight density use the selected units. Materials are isotropic
and linear elastic; yield strength and nonlinear constitutive models are not
currently represented.

Material-library presets are reference starting points, not certified grades.
US steel uses the [PyNite Quickstart](https://pynite.readthedocs.io/en/latest/quickstart.html)
elastic constants and weight density. EU steel and C30/37 concrete use
[JRC Handbook 3](https://eurocodes.jrc.ec.europa.eu/sites/default/files/2021-12/handbook3.pdf)
(steel Annex Table 2; concrete Chapter VI and Annex Table 9). Aluminum uses
the [MIT material database](https://www.mit.edu/~6.777/matprops/aluminum.htm).
Mass densities for EU steel/aluminum are converted with standard gravity
9.80665 m/s2; the UI and PyNite receive weight density, not mass density.
Concrete presets assume uncracked, short-term stiffness. The RC-weight variant
changes density only, not reinforcement stiffness. No preset adds cracking,
creep, plasticity, yield strength, buckling, or a design-code check. Verify
properties for the actual grade, alloy, aggregate, and conditions of use.

Each member also references a reusable section definition. Area uses in2 or mm2;
Iy, Iz, and J use in4 or mm4 in the member local axes. Iz governs in-plane bending
for the current XY frame model. Custom properties are entered directly;
definition names alone do not perform a section-catalog lookup. The initial
default uses W18x35 properties but is classified as custom, like older saved
definitions. Split segments inherit their original section.

The offline library contains 15 doubly symmetric wide-flange, square,
rectangular, and round HSS sections, not a complete catalog. Its numerical
properties come from the August 2023 [AISC Shapes Database v16.0](https://www.aisc.org/aisc/publications/steel-construction-manual/aisc-shapes-database-v160/),
consistent with the 16th Edition Manual, first printing. The source workbook was
retrieved from this [public mirror](https://github.com/OpenCivil-Project/Open-Structures/blob/main/app/resources/aisc-shapes-database-v16.0.xlsx)
because the official download returned HTTP 403. Its SHA-256 is
`82d0ceb96a0d938ae1a6bd9637cb10a1e269225b5d668dce5b0bdc8d86013496`.
Only designation and A/Iy/Ix/J numerical facts are bundled, not the workbook.
Values use U.S. customary columns C, F, AQ, AM, AX; metric previews convert
these values rather than using the workbook's separately rounded metric columns.
Strong-axis bending maps catalog Ix to PyNite Iz and catalog Iy to PyNite Iy.
Weak-axis bending swaps those inertias; A and torsional J stay unchanged.
HSS design properties are taken directly from the database, not recalculated
from nominal wall thickness. Imported catalog properties and orientation are
validated on reopen; modified values must be classified as custom. Materials
remain a separate assignment, and imports do not change them. This is a stiffness
library, not a strength, buckling, or code-compliance check. Verify suitability
and section properties independently for engineering use.

Version 1 files migrate their shared material to a named Project material.
Version 1 and 2 files migrate their shared section to a named Project section.
Versions 1 through 4 migrate existing loads into Case 1 with the original
Service combination. Version 3 point loads and version 4 distributed loads
remain supported. Versions 1 through 5 migrate to rigid member ends.
Versions 1 through 6 open in Imperial, preserving their original inch-kip values.
New 2D saves use version 15 and retain material/section definitions, member
assignments, load cases, combination factors, the default load case, and each
member end moment release, plus the selected unit system, point-load angle,
and custom support restraints. Version 10 adds local force directions and
angled distributed loading; version 9 and older files retain their saved global
force directions and physical magnitudes.
Version 11 adds the optional self-weight case and factor. Versions 1 through 10
open with automatic self-weight off so existing reactions do not change.
Version 12 adds section catalog provenance and strong/weak-axis orientation.
Older files retain their exact numerical properties as custom definitions.
Version 13 adds material-library provenance; older materials remain custom.
Version 14 adds the frame/truss member type. Earlier files keep frame behavior,
including any existing end moment releases, without changing their response.
Version 15 adds global support-spring stiffnesses and member-local axial/shear
releases. Older files default to zero springs and connected translations.
Older project loads retain their original directions and magnitudes. The JSON units field
remains in-kip to identify the canonical storage units; unit_system controls
presentation and input conversion.
Malformed files are rejected before replacing the active project. Missing fields,
incorrect collection/entity shapes, unknown entity fields, invalid references,
boolean/string/nonfinite numerical values, and duplicate JSON keys produce
readable errors. JSON syntax errors include their line and column. Supported
planar versions 1 through 15 are migrated without modifying the input; spatial
versions 16/17/18 require an explicit `dimension: "3D"` marker and are validated separately.
Spatial version 17 adds global angular forces with azimuth (`angle`) and
`elevation`; version 16 axis-based loads migrate without changing their physics.
Unsupported future versions and angular fields in version 16 are rejected.
Spatial version 18 adds axial-only truss members; versions 16/17 remain frame-only
inputs and migrate without changing their geometry, supports or loads.
Spatial files retain XYZ, all six restraints/springs, and roll. Unknown/future
versions are rejected rather than guessed. Node and member identifiers must be
distinct so load targets are unambiguous.
Editing a definition updates all members assigned to it and
invalidates analysis results.
No self-weight is applied automatically. Drawing an intersection alone does not
connect it: use Edit > Connect Intersections to create explicit shared endpoints.
Analysis requires one connected structure and rejects overlapping members or
nodes inside unsplit members, avoiding implicit solver connections. Geometry
connections use an absolute tolerance of 1e-8 inches. Distributed intensity is
force per unit member length, not projected length. The connection/splitting commands
in this section apply to 2D; spatial editing currently requires explicit segments.

Results are invalidated after engineering edits and belong to the analyzed project revision.
Unit selection changes presentation only and retains valid analysis results.
Result diagrams already open remain snapshots of that analysis.

Whole-structure diagrams use a consistent cut orientation from the endpoint with
the smaller (X, Y) coordinate to the larger endpoint. Positive shear and moment
offsets lie on the left normal of that direction. This makes diagram geometry
independent of member drawing order; negative sagging moments appear below a
horizontal beam. Axial force N uses the PyNite convention: positive compression
and negative tension. Axial force is independent of member drawing direction;
compression offsets lie on the same canonical left normal, and tension offsets
lie on the opposite side. Each whole-structure quantity has a common amplitude
scale across all members. Member Detail retains PyNite local Fy/Mz signs. Point forces
and concentrated moments include both sides of each discontinuity.

## Architecture

- `src/pynitegui/qt/model.py`: validated, serializable project data.
- `src/pynitegui/qt/units.py`: canonical-to-display conversion factors and presets.
- `src/pynitegui/qt/annotations.py`: shared support/release symbols and factored load context.
- `src/pynitegui/qt/released_member.py`: linear released-translation recovery using PyNite matrices.
- `src/pynitegui/qt/analysis.py`: project-to-PyNite adapter and analysis results.
- `src/pynitegui/qt/spatial_model.py`: separate six-DOF spatial definitions and format.
- `src/pynitegui/qt/spatial_analysis.py`: linear spatial solver and mechanism checks.
- `src/pynitegui/qt/spatial_view.py` and `viewport3d/`: native controls/bridge and Three.js.
- `src/pynitegui/qt/spatial_results.py`, `spatial_diagrams.py`: spatial sampling/exports/plots.
- `src/pynitegui/qt/analysis_jobs.py`: isolated solver processes, phase messages,
  thread-safe cancellation, and cleanup before publishing results.
- `src/pynitegui/qt/results_panel.py`: native sortable result tabs, entity links,
  lazy member tables, equilibrium display and analysis/snapshot status.
- `src/pynitegui/qt/equilibrium.py`: independent global load resultants and
  reaction balance with explicit force/moment tolerances.
- `src/pynitegui/qt/model_findings.py`: model/analysis finding review and
  conservative navigation for recognized geometry references.
- `src/pynitegui/qt/app.py`: Qt graphics editor, inspector, undo commands,
  background analysis, and a consistent light application theme.
- `src/pynitegui/qt/diagrams.py`: whole-frame axial/SFD/BMD views, member detail plots,
  and sampling on both sides of force and moment discontinuities.
- `src/pynitegui/qt/envelopes.py`: combination bounds, governing combinations,
  envelope tables/curves, exact station inspection, and atomic CSV export.
- `src/pynitegui/qt/diagram_labels.py`: renderer-aware diagram label placement
  for interactive views and printed images.
- `src/pynitegui/qt/materials.py`: material definition manager and property editor.
- `src/pynitegui/qt/sections.py`: section definition manager and property editor.
- `src/pynitegui/qt/section_library.py`: offline catalog facts and axis mapping.
- `src/pynitegui/qt/material_library.py`: reference elastic and weight-density presets.
- `src/pynitegui/qt/load_cases.py`: load-case manager and combination factor editor.
- `src/pynitegui/qt/recovery.py`: per-window atomic recovery snapshots and validation.
- `src/pynitegui/qt/reports.py`: unit-aware CSV exports and native printable reports.
- `src/pynitegui/qt/examples.py`: fresh, canonical-unit example beam/frame models.
- `src/pynitegui/qt/theme.py`: shared light/dark widget, canvas, and plot styling.
- `src/pynitegui/qt/self_weight.py`: opt-in case/factor editor and weight preview.
- `src/pynitegui/qt/model_tables.py`: atomic numerical geometry/load editing.
- `src/pynitegui/qt/spatial_conversion.py`: explicit, independently validated
  2D-to-3D definitions and support/force convention mapping.
- `src/pynitegui/qt/spatial_reports.py`: snapshot-based, WebGL-independent spatial
  diagram projections, rolled-axis ribbons and print-friendly report images.
- `src/pynitegui/qt/bulk_edit.py`: explicit multi-entity property assignments.
- `tests/`: project, solver, diagram, and Qt interaction regression tests.

## Development

Run the project, solver, diagram, and Qt interaction tests:

```sh
uv run python -m unittest discover -s tests
```

The Qt interaction tests run offscreen. The suite covers project persistence,
undo/redo, result invalidation, analytical beam checks, portal-frame diagrams,
inclined/reversed members, point-force/moment jumps, explicit member connections,
load preservation during splitting, rejection of invalid model topology,
mixed-material/section stiffness, legacy-file migration, and material/section
assignment with undo.

Spatial regressions cover all six cantilever DOFs, biaxial tip moments, torsion,
roll/inertia changes, oblique local/global transformations, uniform/varying loads,
springs, missing out-of-plane restraints, self-weight, spatial combinations,
version dispatch, units, editing history, snapshots and reports. Widget tests use
`PYNITEGUI_NO_WEBENGINE=1` to avoid initializing Chromium; this is a test-only switch.
For real viewport checks, install Playwright in a separate developer environment
with its Chromium browser, then run `node tests/viewport3d.spec.cjs` with Playwright
available to Node (or set `PLAYWRIGHT_MODULE` to its installed package directory).
The script serves local assets temporarily and closes both browser/server after
testing desktop canvas pixels, framing, six signed gizmo views, keyboard reset,
zoom/selection preservation, orbit, node picking, all three work-plane drawing
modes, six force/moment overlays with rolled members, PNG capture and dark
appearance. Screenshots go to `/tmp/pynite-3d-qa`
by default, configurable with `VIEWPORT_QA_OUTPUT`. It does not launch the user's GUI.
`PLAYWRIGHT_EXECUTABLE_PATH` optionally selects an installed Chromium-compatible
test browser; otherwise Playwright uses its downloaded Chromium.

### Spatial Performance Checks

Spatial member sampling is cached in canonical model units, shared by the
viewport, Member Detail, envelopes and report diagrams. Each solver snapshot
owns a least-recently-used cache with a 32 MiB sample-array budget. Keys separate
snapshots, combinations, members, geometry/roll/type and load-boundary stations;
unit, selection and display-only changes reuse read-only arrays. Fresh analyses
use fresh caches, and solver serialization drops cached arrays. There is no
change to numerical sampling density, one-sided load jumps or solver signs.

Run the optional analytical benchmark from the repository root:

```sh
uv run --locked python -B tests/benchmark_spatial.py
```

It solves 10-, 50- and 100-segment spatial cantilevers and emits JSON with solve,
cold sampling, five warm reads, station counts and cache bytes. On this Linux
Python 3.12.15 run (2026-10-09), the 100-member cold read took 0.85 seconds and
warm reads took 0.15-0.21 milliseconds, retaining 585,600 sample-array bytes.
These are sampling-only measurements, not complete UI redraw or solver speedups.

For optional large-model desktop rendering checks, use the same separate
Playwright installation as above:

```sh
VIEWPORT_BENCHMARK=1 node tests/viewport3d.spec.cjs
```

The ordinary interaction suite still runs. The benchmark additionally draws
144-, 616- and 1,580-member lattices at 1280x720 with labels on/off, checks canvas
pixels, framing, orbit interaction and graphics-resource counts after model
replacement, and records scene rebuild and frame timings. Screenshots and
`desktop-benchmark.json` use the same output directory. Synthetic lattice data
benchmarks rendering only, not structural analysis. The harness uses Chromium's
SwiftShader software renderer; record the reported driver when comparing runs.
Timings are observations, not hardware-independent pass/fail thresholds.
The pre-batching baseline rebuilt the 1,580-member geometry in about 152 ms,
or 520 ms with labels enabled, with roughly 2,600 draw calls. Base frame rendering
now uses two instanced meshes (one unit cylinder shape for members and one unit
sphere shape for nodes) with per-instance transforms/colours/IDs, and the grid
uses one line-segment batch. Picking, node-dragging and drawing snaps resolve
instance IDs back to model IDs. Disposal releases instance buffers and deduplicates
geometry/material/texture disposal. Supports, labels, loads and analytical
overlays remain independent objects; their rebuilding and JSON/payload costs
are not removed by geometry batching or the analytical cache. The benchmark
enforces fewer than 30 unlabelled draw calls and 20 geometries for the lattices,
in addition to visible model pixels and resource-replacement checks.
The post-batching run recorded 18 unlabelled draw calls and seven geometries at
all three sizes. The 1,580-member unlabelled rebuild took about 14 ms (12 ms on
replacement), while labels still brought rebuilds into the hundreds of
milliseconds. SwiftShader frame timings remained variable; these measurements
demonstrate lower allocation/submission costs, not a guaranteed frame-rate gain.

Selection and tool-mode changes now recolour the two base instance buffers and
update interaction settings without rebuilding supports, loads, deformation or
force overlays. The complete remaining payload is compared, so geometry,
work-plane, units, theme, visibility and result changes still rebuild. When local
axes are shown, selection also rebuilds because it changes the displayed axes.
JSON serialization and native payload construction still scale with model size.

Label textures are shared by exact text/colour through a least-recently-used
cache capped at 512 entries and an 8 MiB estimated RGBA texture budget (including
a mipmap allowance). Active sprites pin their entries. Labels beyond the budget
use transient textures that are disposed with their sprites. Hiding ordinary
labels clears unused entries; required diagram values remain independent.
Context loss and page teardown clear retained entries and dispose scene objects;
browser history suspension retains its scene for restoration. The cache bounds
retained resources, not the memory required by all live labels in a large scene.

The interaction harness includes real-canvas cache lifetime/eviction checks,
selection colours, all six force-overlay refreshes, support-anchor preservation,
geometry/theme/visibility/local-axis rebuilds, and context-loss cleanup.
Large-model benchmarks also record selection/tool refresh times and enforce no
scene rebuilds, additional graphics resources or cache-budget overruns for those
display-only updates.

A hardware comparison on 2026-10-09 used the Codex in-app Chromium browser,
WebGL 2 / ANGLE Metal on Apple M4 Max, a 552x853 viewport, the same 144/616/1,580
member lattices and five selection/tool updates per case. Median labelled
selection refreshes changed from 5.8/22.3/76.9 ms to 0.6/0.9/1.3 ms; tool changes
changed from 5.7/24.6/71.7 ms to 0.5/0.8/1.0 ms. Unlabelled refresh times stayed
around 0.4-1.5 ms. Resource counts stayed constant across the new refreshes;
the largest scenes retained 512 label entries with an estimated 6,856,128 bytes.
These are payload-to-scene update observations, not complete native GUI latency,
solver timings, full-rebuild speedups or guaranteed frame rates. The targeted
browser contracts and context-loss check passed on this hardware. The standalone
Playwright interaction suite could not launch here because the macOS sandbox
denied Chromium's Mach bootstrap registration; the recorded hardware comparison
does not substitute for that suite's gesture coverage.

### Additional Regression Coverage

Distributed-load checks cover analytical uniform/triangular beam responses,
partial-span resultants, inclined global loading, orientation-independent
diagrams, interpolated split loads, persistence, and editor creation/undo.
Load-case checks cover independent results, linear superposition, negative/zero
factors, reference-safe renaming/deletion, persistence/migration, default case
assignment, result/diagram switching, deformation, and analyzed snapshots.
Hinge checks cover analytical released beams, pin-jointed frames, mixed rigid
and hinged connections, real mechanisms, unsupported nodal moments, inactive
rotation reporting, split/intersection preservation, persistence, and undo.
Axial-force checks cover tension/compression signs, inclined and reversed members,
point-force jumps, distributed axial loading, pin-jointed frames, common scaling,
combination switching, snapshot preservation, and compact plot-label layout.
Unit checks cover known conversion factors, SI analytical beam responses,
precision-preserving input, grid snapping, all dimensional editors/result columns,
live diagram switching, persistence/migration, undo, and repeated unit changes.
Additional-preset checks cover known mm/N and ft/kip conversion factors and
preservation of model data, analysis identity, result exports, and persistence.
Editing checks cover drag preview/commit/cancel, snapping, collision rejection,
and non-destructive load visibility. Custom support checks cover preset
equivalence, independent restraints, hinged joints, persistence, and undo.
Member-result checks cover extrema, exact-distance queries, one-sided jumps,
click inspection, combination switching, and SI conversion. Recovery checks
cover atomic write failures, untouched project files, multiple windows,
malformed snapshots, recovery dirtiness, cancelled closing, and recent projects.
Local-loading checks cover inclined/vertical/reversed axes, angled triangular
resultants, manual component equivalence, sign-changing ramps, split/node
conversion, SI input, persistence, and unedited angle/intensity precision.
Export checks cover SI/imperial values, combination identity, undefined rotations,
CSV quoting/formula safety, atomic failures, cancellation, stale-model rejection,
retained snapshot exports, report escaping, and native PDF rendering.
File-validation checks cover malformed shapes and values, duplicate keys,
versions 1 through 15, future-version rejection, non-mutating migrations, and
preservation of the active project and source file after a failed open.
Stability checks cover inadequate pins/rollers, custom restraints, translated
coordinates, zero-stiffness and internal sway mechanisms, valid released beams,
uniformly soft materials, nonfinite results in any combination, unrelated solver
errors, and the dense-localization size limit.
Larger-model benchmarks compare a twenty-segment mixed-material/section column
against independently integrated bending/axial formulas. Four-storey, two-bay
frames check global force/moment equilibrium, combination superposition,
triangular beam loads, lateral floor loads and nodal moments, fixed/pinned/mixed
supports, partial end releases, and endpoint reversal. These are numerical
regression benchmarks, not wall-clock performance targets or design certification.
Example checks solve every supplied model/combination, verify a cantilever's
analytical reactions, and cover fresh copies, SI equivalence, menu loading,
unsaved-state handling, and cancellation. Theme checks cover preference restore,
live recoloring, multi-window synchronization, contrast, toolbar icons, compact
inspector scrolling, pending input, and preservation of results/plot inspection.
Self-weight checks cover analytical beam deflection/reactions, per-member
materials/sections, inclined/reversed axes, case omission/factors/renaming,
zero density, splitting, old-file migration, validation, preview precision,
manual-load superposition, repeated analysis without duplication, undo/filtering,
snapshot invalidation, and export metadata.
Model-table checks cover all unit presets, unchanged-value precision, force/moment/
intensity interpretation, custom restraints, assignments/releases, new references,
dependent deletion, invalid drafts, the active numeric editor, cancellation,
self-weight separation, and one-step undo/redo.
Bulk-edit checks cover tree/canvas modifier selection, rectangle intersections,
cancellation, selection synchronization, mixed entity types, preserved properties,
all load quantities, atomic failure, cascading deletion, filtering, history,
selected-load highlighting, and result preservation/invalidation.
Section-library checks cover all entries, strong/weak-axis stiffness, all unit
presets, source metadata validation, legacy custom definitions, save/reopen,
search/family filters, duplicate-name protection, cancellation, one-step import
undo/redo, rename provenance, and custom classification after property edits.
Material-library checks cover reference conversions, mass/weight distinction,
all unit presets, source validation, old-file preservation, safe imports,
search, cancellation, conflicts, undo/redo, and property-edit classification.
Truss checks cover triangle joint equilibrium and virtual-work displacement,
zero shear/moment, inertia independence, reversed endpoints, mixed joints,
joint moments, lumped/mixed self-weight and combinations, split mechanisms,
migration, type validation, inspector/bulk/table edits, generated force units,
load rejection, and undo.
Presentation/report checks cover placement and sign independence, unchanged
solver probes, unit/combination updates, model definition conversions and HTML
escaping, selected sections, embedded light-palette images, inherited diagram
settings, invalid/empty choices, snapshot validation, and cancellation.
Elastic-support/release checks cover parallel axial stiffness, a spring-only
cantilever base, hinged-joint rotational springs, opposing reactions, weak-support
rejection, all 64 planar release patterns, released axial/bending deflection,
split/combination equivalence, isolated-result transport, all unit presets,
legacy migration, atomic editor failures, glyphs, reports, and undo/redo.
Annotation checks cover distinct support/spring geometry, signed moment arrows,
factored loads/self-weight, partial spans, unchanged force diagrams under
visibility changes, collision-free text/symbols, member context, and report choices.

Keep workflow and engineering-scope changes documented here. Track remaining
features and known limitations in [TODO.md](TODO.md), updating it as work lands.
Commit completed, verified changes in coherent groups; keep implementation and
its regression tests together.
