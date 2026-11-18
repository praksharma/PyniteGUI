# Tutorial: 2D/3D Axial-Only Trusses & Mixed Frame-Truss Models

This tutorial explains how to build, load, and analyze **axial-only trusses** (`kind="truss"`)
and **mixed frame-truss structures** in 2D and 3D, including how Brecon handles inactive rotational
DOFs, lumped self-weight, and unilateral tension-only/compression-only truss bracing.

---

## 1. Planar Triangular & Multi-Bay Trusses

1. Open **File > Examples > Trusses > Triangular Truss - Joint Loads** (`truss`).
2. Select any member and inspect **Properties**:
   - **Type:** `truss` (axial-only bar; bending moments $M$ and transverse shears $V$ are identically zero,
     and cross-section moments of inertia $I_y, I_z, J$ do not affect stiffness—only $E \cdot A / L$ enters).
   - **Axial behaviour:** `Bilateral` (or `Tension only` / `Compression only` when using **Iterative elastic**).
   - **End releases:** Manual frame end-release checkboxes are disabled on `truss` members because
     truss bars are inherently pin-ended.
3. **Loading Rules for Trusses:**
   - Truss members accept **nodal forces at their endpoint joints only**. Attempting to place an
     interior point load, distributed member load, or nodal moment at a truss-only joint is rejected
     with an explicit diagnostic.
   - When **Automatic Self-Weight** (**Edit > Self-Weight…**) is enabled on a truss, each truss bar's
     weight ($\rho \cdot A \cdot L \cdot \text{factor}$) is automatically lumped into two equal vertical
     nodal forces at its start and end joints (`i` and `j`).
4. Press **F5** to solve:
   - In the **Results > Nodes / Displacements** table, rotational DOFs (`RZ` in 2D; `RX, RY, RZ` in 3D)
     at joints connected only to truss members are displayed as `n/a` rather than misleading zeros.
   - In **Member forces** and **Diagrams**, axial force $N$ is **positive in compression** and
     **negative in tension**.

### Headless Python Snippet: 2D Triangular Truss with Self-Weight
```python
from pynitegui.qt.analysis import analyze
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.examples import example_project

truss = example_project("truss")
truss.self_weight_case = "Case 1"
truss.self_weight_factor = 1.0
truss.validate()

result = analyze(truss)
assert check_equilibrium(truss, result).passed
print("Inactive rotational joints:", sorted(truss.inactive_rotations()))
for name in truss.members:
    axial = result.solver.members[name].max_axial(result.combination)
    print(f"Member {name} axial force (+compression / -tension) = {axial:.4f} kip")
```

---

## 2. 3D Space Trusses & Tripods

1. Open **File > Examples > Trusses > 3D Truss Tripod - Joint Load** (`3d_tripod`) or
   **Official PyNite - Space Truss with Nodal Load** (`3d_official_truss`).
2. Press **F5** to solve.
   - On `3d_official_truss` (in `SI (m, kN)` display units), check the member axial forces in `Combo 1`:
     - `BC`: `-32.65333 kN` (tension)
     - `BD`: `-45.23538 kN` (tension)
     - `BE`: `+112.05467 kN` (compression)
   - Notice that a 3D truss joint requires non-coplanar axial bars (or translational support restraints)
     spanning all three global translational directions `(DX, DY, DZ)` to be kinematically stable.
     If a joint lies in a single plane without out-of-plane bracing or restraint, Brecon's stability
     diagnostics identify the exact affected joint and direction.

### Headless Python Snippet: 3D Space Truss Verification
```python
from pynitegui.qt.analysis import analyze
from pynitegui.qt.examples import example_project

space_truss = example_project("3d_official_truss", unit_system="si")
res_space = analyze(space_truss)
u = space_truss.units
for member_name in ("BC", "BD", "BE"):
    n_kip = res_space.solver.members[member_name].max_axial("Combo 1")
    n_kn = u.to_display(n_kip, "force")
    print(f"{member_name}: N = {n_kn:.5f} {u.force}")
```

---

## 3. Mixed Frame-Truss Structures (Braced Frames)

You can freely mix bending `frame` members (columns and girders) and axial-only `truss` members
(diagonal braces or tie rods) in the same 2D or 3D project:

- At any joint where at least one un-hinged `frame` member arrives, rotational stiffness is active,
  so the joint has a well-defined nodal rotation and can carry applied nodal moments, while incident
  `truss` bars connect only to the joint's translational DOFs.
- **Note on Member Subdivision:** **Tools > Subdivide Members…** intentionally rejects `truss` members
  because inserting an unbraced intermediate node inside an axial-only bar creates a collinear
  mechanism. Only subdivide bending `frame` members, or add explicit triangulated bracing at intermediate
  truss joints.

### Headless Python Snippet: Portal Frame with Diagonal Truss Bracing
```python
from pynitegui.qt.analysis import analyze
from pynitegui.qt.model import Load, Project

project = Project(unit_system="imperial")
project.add_member((0.0, 0.0), (0.0, 144.0))      # M1: Frame column
project.add_member((0.0, 144.0), (240.0, 144.0))  # M2: Frame girder
project.add_member((240.0, 0.0), (240.0, 144.0))  # M3: Frame column
project.add_member((0.0, 0.0), (240.0, 144.0))    # M4: Diagonal truss brace
project.members["M4"].kind = "truss"

project.nodes["N1"].support = "pin"
project.nodes["N4"].support = "pin"
project.loads["L1"] = Load("L1", "N2", "FX", 20.0)
project.validate()

result = analyze(project)
print("Roof drift N2 DX =", round(result.displacements["N2"][0], 5), "in")
print("Brace M4 axial force =", round(result.solver.members["M4"].max_axial("Service"), 4), "kip")
```

See [Axial-only trusses](../modeling/trusses.md) and [Stability diagnostics](../analysis/stability.md).
