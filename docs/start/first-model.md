# Your First Model

Use a supplied example first. It gives you a known result to check before
building your own structure.

## Open and Solve a Beam

1. Launch PyniteGUI and choose **File > Examples > Simply Supported Beam**.
2. Check the unit selector at the bottom-right. In the inch/kip preset, the beam
   spans **420 in** and has a **10 kip downward midspan load**.
3. Inspect the two support nodes: one pin and one roller. They constrain the
   beam without fixing its end rotations.
4. Press the Analyze triangle or **F5**. Wait for a completed result snapshot.
5. Check vertical support reactions: **5 kip at each end**. In SI (m, kN), the
   same physical example has a 10.668 m span, 44.4822 kN load and 22.2411 kN reactions.
6. Turn on **Deformed**. Choose Auto, True Scale or Custom; amplification changes
   only the displayed shape, not the numerical answer.
7. Open **Diagrams** to inspect axial force, shear and bending moment, then use
   Member Detail to inspect a station. Read the [sign conventions](../results/conventions.md).
8. Save under a new project filename. Examples start as unsaved models and do
   not overwrite an example file.

## Make One Change

Select the load in the structure tree and edit its signed magnitude, then Apply.
The previous editor results become outdated because the engineering model changed.
Analyze again, or use [opt-in live recalculation](../analysis/live.md).
Undo restores model definitions; it does not certify an earlier result as current.

Changing display units is different: it preserves the physical model and valid
results. Learn the four [unit presets](../reference/units.md) before entering data.

## Try a Spatial Model

Open **File > Examples > 3D Space Frame - Gravity and Wind**. Orbit the viewport,
use the signed-axis gizmo, and inspect the load cases and combinations.
The [3D workflow](../modeling/3d.md) explains work planes, XYZ nodes, member roll,
six-direction supports, spatial loads and result components.

To add a rectangular surface in a source checkout, open **Tools > Surface Meshing**.
The rectangle defaults to the highest detected complete frame level. Check the
reference frame in the preview and choose **Apply to 3D Model**.

!!! warning "A touching slab is not a connected slab"
    Main-model surfaces are geometry-only. Their nodes are not merged with frame
    joints, and analysis is intentionally blocked while they are present.
    Use the [separate plate tool](../surfaces/plates.md) for its supported plate-only
    bending workflow. See [slab placement](../surfaces/main-model.md) for the exact limits.

## Build Your Own

Continue with [drawing and selection](../modeling/drawing.md),
[materials and sections](../modeling/properties.md),
[supports](../modeling/supports.md), and [loads](../analysis/loads.md).
Use [model checks](../modeling/topology.md) before analysis; a crossing on screen
is not automatically a shared joint.
