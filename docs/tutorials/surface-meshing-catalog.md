# Tutorial: Surface Mesh Generators Catalog (Rectangle, Annulus, Cylinder & Frustum)

This tutorial walks through Brecon's seven concrete PyNite mesh generators in
**Tools > Surface Meshing (Experimental)** (`MeshWorkspace`), covering recipe creation,
quality checks, `.pynitemesh` recipe files, neutral JSON mesh export, and transferring
rectangular recipes into the transverse plate workspace or main 3D model.

---

## 1. The Seven Mesh Generators

Open **Tools > Surface Meshing (Experimental)** to access the interactive 3D mesh generator
workspace. Select any generator from the **Generator** dropdown:

| Generator (`key`) | Shape Parameters | Supported Element Types | Orientation Control |
| :--- | :--- | :--- | :--- |
| **Rectangle** (`rectangle`) | `width`, `height` (+ `x_control`, `y_control`, `openings`) | `Quad`, `Rect` | `Plane`: `XY`, `XZ`, `YZ` |
| **Annulus** (`annulus`) | `outer_radius`, `inner_radius` (automatic radial/transition subdivision) | `Quad` | `Axis`: `X`, `Y`, `Z` |
| **Annular ring** (`annulus_ring`) | `outer_radius`, `inner_radius`, `num_quads` (single ring) | `Quad` | `Axis`: `X`, `Y`, `Z` |
| **Annular transition ring** (`annulus_transition`) | `outer_radius`, `inner_radius`, `num_inner_quads` (`1:3` radial refinement) | `Quad` | `Axis`: `X`, `Y`, `Z` |
| **Cylinder** (`cylinder`) | `radius`, `height`, `num_elements` (`0` = automatic from `mesh_size`) | `Quad`, `Rect` | `Axis`: `X`, `Y`, `Z` |
| **Cylinder ring** (`cylinder_ring`) | `radius`, `height`, `num_elements` (single course) | `Quad`, `Rect` | `Axis`: `X`, `Y`, `Z` |
| **Conical frustum** (`frustum`) | `large_radius`, `small_radius`, `height` | `Quad` | `Axis`: `X`, `Y`, `Z` |

---

## 2. Common Options, Numbering, Modifiers & Quality Safeguards

1. **Common Properties:**
   - **Target mesh size:** Controls element subdivision (ignored only by the direct single-ring helpers
     `annulus_ring`, `annulus_transition`, and `cylinder_ring`, which subdivide directly by circumferential count).
   - **Thickness & Material:** Isotropic elastic modulus $E$, Poisson ratio $\nu$, and weight density $\rho$
     (shear modulus $G = E / [2(1+\nu)]$ is always derived automatically for shell/plate recipes).
   - **Membrane stiffness modifiers:** `kx_mod` and `ky_mod` (preserved on every generated element,
     including cylinder courses).
   - **Origin `[X, Y, Z]` & Numbering Starts:** Uniformly numbers generated nodes from `N<node_start>`
     and elements from `Q<element_start>` (or `R<element_start>` for `Rect`) after translating from the origin.
2. **Automatic Quality Checks (`mesh_quality`):**
   - Before any mesh is accepted, Brecon checks that total element count is at most `1,600`
     (and `4,096` combined across up to `16` surfaces in a 3D project), all coordinates are finite,
     no edge is shorter than `1e-8 in`, every element's max/min edge ratio is at most `20`, every
     four-node face is coplanar, and all four Gauss points have strictly positive Jacobians.

### Headless Python Snippet: Generate & Check All Seven Mesh Families
```python
from pynitegui.qt.mesh_model import GENERATORS, MeshDefinition, generate_mesh, mesh_quality

for gen_key, (label, default_params) in GENERATORS.items():
    recipe = MeshDefinition(
        name=f"Mesh_{gen_key}",
        generator=gen_key,
        parameters=dict(default_params),
        mesh_size=15.0,
        thickness=1.0,
        origin=[10.0, 20.0, 30.0],
    )
    model = generate_mesh(recipe)
    stats = mesh_quality(model)
    print(f"{label:24s} -> {stats['elements']:3d} elements, {stats['nodes']:3d} nodes, max edge ratio = {stats['max_edge_ratio']:.2f}")
```

---

## 3. Rectangle Control Lines, Openings & Plate Transfer

When **Generator** is set to **Rectangle**:

1. Open the **Rectangle Options** tab in the mesh workspace:
   - Add **X control lines** and **Y control lines** (up to 32 internal coordinates each) to align mesh
     grid lines with columns, supporting beams, or load patches.
   - Add **Rectangular openings** (`name`, `x_left`, `y_bott`, `width`, `height`, up to 16 non-overlapping
     cutouts strictly inside the outer rectangle).
2. Click **Apply** to regenerate and preview the mesh in the 3D viewport.
3. Click **Analyze rectangular plate** to transfer the rectangular recipe (including control lines,
   openings, material, thickness, plane, origin, and element family) directly into the standalone
   **Rectangular Plate** bending workspace.
   - If the transferred mesh violates plate-specific constraints, a warning dialog explains the needed
     adjustment without losing your mesh recipe.

---

## 4. Saving `.pynitemesh` Recipes & Exporting Neutral Connectivity JSON

- **Save Recipe (`File > Save Mesh Recipe`):** Saves the compact, editable `.pynitemesh` recipe JSON
  (storing generator parameters, control lines, openings, and material properties in canonical inch-kip units).
- **Export Generated Mesh (`File > Export Generated Mesh`):** Writes neutral connectivity JSON containing
  the recipe plus every generated node's `[X, Y, Z]` coordinates and every element's 4-node connectivity
  list `[i, j, m, n]`, element type, thickness, and stiffness modifiers.

### Headless Python Snippet: Export Neutral Connectivity JSON
```python
from pynitegui.qt.mesh_model import MeshDefinition, generate_mesh, mesh_export

recipe = MeshDefinition(
    name="FloorWithOpening",
    generator="rectangle",
    parameters={"width": 120.0, "height": 80.0},
    mesh_size=20.0,
    x_control=[40.0, 80.0],
    openings=[{"name": "Shaft", "x_left": 40.0, "y_bott": 20.0, "width": 20.0, "height": 20.0}],
)
model = generate_mesh(recipe)
exported = mesh_export(recipe, model)
print("Exported format:", exported["format"])
print("Generated nodes:", len(exported["nodes"]), "| Generated elements:", len(exported["elements"]))
first_elem = next(iter(exported["elements"].items()))
print("Sample element:", first_elem)
```

See [Surface mesh generators](../surfaces/meshing.md) and
[Slab placement and main-model surfaces](../surfaces/main-model.md).
