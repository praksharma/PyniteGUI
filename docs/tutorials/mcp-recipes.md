# Tutorial: MCP Automation & Headless Scripting Cookbook

Brecon can be driven either **interactively over localhost** via its built-in Model Context Protocol
(MCP) server (`Tools > Automation Server`) or **headlessly from Python scripts** using the verified
`pynitegui.qt` model and solver modules. This cookbook provides ready-to-use JSON and Python snippets
for common workflows.

---

## 1. Connecting an MCP Client

Start Brecon with the optional `mcp` extra and launch the server from **Tools > Automation Server**:

```sh
uv sync --extra mcp
uv run --extra mcp brecon
```

### Client Configuration (`mcpServers`)
With **Require token** checked (default):
```json
{
  "mcpServers": {
    "Brecon": {
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Authorization": "Bearer <copied-token>"
      }
    }
  }
}
```

With **Require token** unchecked while stopped (token-free loopback mode):
```json
{
  "mcpServers": {
    "Brecon": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

!!! tip "Enable Write & Analysis Permissions"
    In **Tools > Automation Server**, `read_model`, `read_schema`, `read_units`, `analysis_status`,
    and result reads start enabled. Enable the **Model Edits** (`apply_batch`) and **Analysis**
    (`run_analysis`, `run_modal_analysis`, `run_pushover_analysis`, `cancel_analysis`) switches
    before running mutation or solver tools. Click **Enter MCP mode** in the status bar to grant
    exclusive editor control while your agent works.

---

## 2. Discovering Session ID, Revision & Schema

Always start by calling `read_model` without arguments to obtain the active window's `session_id`,
`revision` (`expected_revision`), and schema:

```json
// Tool: read_model
{
  "include_schema": true
}
```

Subsequent reads in the same session can omit the schema payload to save tokens:

```json
// Tool: read_model
{
  "session_id": "a1b2c3d4e5f6...",
  "include_schema": false
}
```

---

## 3. Recipe: Build a 2D Frame with Load Cases & Combinations (`apply_batch`)

All `apply_batch` numeric values use canonical **inch-kip-radian-degree** units regardless of the
window's current display unit preset. The entire batch validates transactionally and creates a
single undo step:

```json
// Tool: apply_batch
{
  "session_id": "<read_model.session_id>",
  "expected_revision": 1,
  "operations": [
    {"op": "put", "collection": "nodes", "key": "N1", "value": {"x": 0.0, "y": 0.0, "support": "fixed"}},
    {"op": "put", "collection": "nodes", "key": "N2", "value": {"x": 0.0, "y": 144.0, "support": "free"}},
    {"op": "put", "collection": "nodes", "key": "N3", "value": {"x": 240.0, "y": 144.0, "support": "free"}},
    {"op": "put", "collection": "nodes", "key": "N4", "value": {"x": 240.0, "y": 0.0, "support": "pin"}},
    {"op": "put", "collection": "members", "key": "M1", "value": {"start": "N1", "end": "N2"}},
    {"op": "put", "collection": "members", "key": "M2", "value": {"start": "N2", "end": "N3"}},
    {"op": "put", "collection": "members", "key": "M3", "value": {"start": "N4", "end": "N3"}},
    {"op": "put", "collection": "load_cases", "key": "Dead"},
    {"op": "put", "collection": "load_cases", "key": "Wind"},
    {"op": "set", "collection": "settings", "value": {
      "default_load_case": "Dead",
      "self_weight_case": "Dead",
      "self_weight_factor": 1.0,
      "analysis_method": "p_delta"
    }},
    {"op": "put", "collection": "loads", "key": "L1", "value": {
      "target": "M2", "kind": "distributed", "direction": "FY",
      "magnitude": -0.1, "end_magnitude": -0.1, "position": 0.0, "end_position": 1.0, "case": "Dead"
    }},
    {"op": "put", "collection": "loads", "key": "L2", "value": {
      "target": "N2", "kind": "point", "direction": "FX", "magnitude": 12.0, "case": "Wind"
    }},
    {"op": "put", "collection": "combinations", "key": "Combined", "value": {"Dead": 1.2, "Wind": 1.0}}
  ]
}
```

---

## 4. Recipe: Add Joint Springs & Unilateral Iterative Elastic Settings (`apply_batch`)

```json
// Tool: apply_batch
{
  "session_id": "<read_model.session_id>",
  "expected_revision": 2,
  "operations": [
    {"op": "put", "collection": "joint_springs", "key": "S1", "value": {
      "start": "N1",
      "end": "N3",
      "stiffness": 50.0,
      "behavior": "tension_only"
    }},
    {"op": "set", "collection": "settings", "value": {
      "analysis_method": "iterative",
      "unilateral_max_iterations": 40,
      "unilateral_load_steps": 10,
      "unilateral_tolerance": 1e-9
    }}
  ]
}
```

---

## 5. Recipe: Coupled 3D Rectangular Slab, Edge Supports & Pressures (`apply_batch`)

In a 3D project (`dimension == "3D"`), a single batch can place a conforming rectangular `Quad`
slab, assign outer-edge supports, apply downward gravity pressure (`kip/in²`), and enable coupled
analysis:

```json
// Tool: apply_batch
{
  "session_id": "<read_model.session_id>",
  "expected_revision": 3,
  "operations": [
    {"op": "put", "collection": "surfaces", "key": "Floor1", "value": {
      "generator": "rectangle",
      "plane": "XZ",
      "origin": [0.0, 144.0, 0.0],
      "parameters": {"width": 240.0, "height": 180.0},
      "mesh_size": 60.0,
      "thickness": 6.0,
      "element_type": "Quad"
    }},
    {"op": "put", "collection": "surface_pressures", "key": "Floor1", "value": {
      "Case 1": 0.001
    }},
    {"op": "put", "collection": "surface_supports", "key": "Floor1", "value": {
      "left": ["DY"],
      "right": ["DY"]
    }},
    {"op": "set", "collection": "settings", "value": {
      "surface_analysis_enabled": true
    }}
  ]
}
```

---

## 6. Recipe: Run Static, Modal & Steel Pushover Jobs via MCP

### Static / P-Delta / Iterative Elastic Solve
```json
// 1. Start the solve (Tool: run_analysis)
{
  "session_id": "<read_model.session_id>",
  "expected_revision": 4
}

// 2. Poll until running == false (Tool: analysis_status)
{
  "session_id": "<read_model.session_id>",
  "job_id": "<run_analysis.job_id>"
}

// 3. Read paginated results in current display units (Tool: read_results)
{
  "session_id": "<read_model.session_id>",
  "snapshot_id": "<analysis_status.snapshot.snapshot_id>",
  "kind": "nodes",
  "combination": "Combined",
  "offset": 0,
  "limit": 100
}
```
Supported `read_results` `kind` values:
- `"nodes"` (displacements and support reactions)
- `"members"` (end forces and solver extrema)
- `"equilibrium"` (independent global force/moment balance rows)
- `"joint_springs"` (extension, axial force, and active state)
- `"active_states"` and `"iterations"` (Iterative elastic unilateral status and convergence history)
- `"surface_elements"` (coupled slab element centre moments, membrane stresses, and shear recovery metadata)

### Vibration Modes Job
```json
// 1. Start modal job (Tool: run_modal_analysis)
{
  "session_id": "<read_model.session_id>",
  "expected_revision": 4,
  "combination": "Mass",
  "modes": 3,
  "direction": "Y",
  "gravity": 386.08858267716535
}

// 2. Read frequencies, mode shapes, or mass sources (Tool: read_modal_results)
{
  "session_id": "<read_model.session_id>",
  "snapshot_id": "<analysis_status.snapshot.snapshot_id>",
  "kind": "frequencies",
  "offset": 0,
  "limit": 50
}
```

### Steel Pushover Job
```json
// 1. Start pushover job (Tool: run_pushover_analysis)
{
  "session_id": "<read_model.session_id>",
  "expected_revision": 4,
  "preload": "Preload",
  "push": "Push",
  "control_node": "N2",
  "control_direction": "DY",
  "stop_limit": 5.0,
  "base_nodes": ["N1", "N3"],
  "resultant": "FY",
  "steps": 500,
  "iteration_limit": 30,
  "yield_tolerance": 0.01
}

// 2. Read capacity curve or step tables (Tool: read_pushover_results)
{
  "session_id": "<read_model.session_id>",
  "snapshot_id": "<analysis_status.snapshot.snapshot_id>",
  "kind": "capacity",
  "offset": 0,
  "limit": 100
}
```

---

## 7. Recipe: Standalone Rectangular Plate Analysis in Python

You can also run the standalone transverse plate solver (`Quad` or `Rect`, with openings,
control lines, linear pressure profiles, and guarded recovered centre shear) directly from Python:

```python
from pynitegui.qt.plate_model import PlateDefinition, analyze_plate, select_plate_combination

plate = PlateDefinition(
    width=120.0,
    height=120.0,
    thickness=1.0,
    mesh_size=15.0,
    plane="XZ",
    element_type="Quad",
    load_case="Dead",
    pressure=-0.001,
    additional_pressures={"Live": -0.002},
    combinations={"Factored": {"Dead": 1.2, "Live": 1.6}},
    x_control=[30.0, 60.0, 90.0],
)
plate.validate()

snapshot = analyze_plate(plate)
factored = select_plate_combination(snapshot, "Factored")
print("Max |w| =", max(abs(factored["displacement"])), "in")
print("Total normal reaction =", factored["reactions"].sum(), "kip")
```

See [Optional MCP server](../automation/mcp.md) and [Rectangular plate analysis](../surfaces/plates.md).
