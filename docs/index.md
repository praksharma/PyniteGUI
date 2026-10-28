# Brecon

![Brecon structural frame logo](assets/logo.svg){ .product-logo }

Desktop modeling and linear elastic analysis for **2D/3D frames and axial-only
trusses**, using PyNite and Qt. This manual covers building models, assigning
properties and loads, running analysis, interpreting results and using automation.

!!! note "Brecon 1.0.0rc4 release candidate"
    Brecon is the new name for PyniteGUI. This manual follows the source checkout;
    see the release record for published artifacts and platform validation.
    Existing PyniteGUI projects remain compatible. Surface/plate
    workflows remain experimental; see the release record for validation limits.

## Start Here

1. [Install and launch](start/install.md).
2. [Run your first beam model](start/first-model.md) and check its reactions.
3. Use the [feature index](features.md) to find a workflow, or search for a tool name.
4. Read the [engineering limits](reference/engineering.md) and
   [PyNite capability coverage](project/roadmap.md#pynite-capability-coverage)
   before relying on results.

## Workflows

| Task | Documentation |
| --- | --- |
| Draw, select, edit, split and connect members | [Modeling](modeling/index.md), [3D workflow](modeling/3d.md) |
| Assign materials, sections, supports and releases | [Properties](modeling/properties.md), [supports](modeling/supports.md), [releases](modeling/releases.md) |
| Apply point, angled, uniform, triangular and partial loads | [Loads](analysis/loads.md), [cases/combinations](analysis/combinations.md), [self-weight](analysis/self-weight.md) |
| Solve and inspect results | [Analysis](analysis/solve.md), [linked tables](results/linked.md), [envelopes](results/envelopes.md) |
| Export numerical data and reports | [CSV and printing/PDF](results/reports.md) |
| Create meshes and place slabs against a frame | [Mesh catalog](surfaces/meshing.md), [main-model placement](surfaces/main-model.md), [plate-only analysis](surfaces/plates.md) |
| Control the open desktop application | [Optional MCP server](automation/mcp.md) |
| Fix blank or interrupted 3D rendering | [Graphics recovery](start/graphics.md), [NVIDIA/Wayland](start/nvidia.md) |

## The Desktop Application

![Frame editor with distributed loads, deformed shape and support reactions](assets/structure.png)

![Portal-frame shear-force diagram](assets/sfd.png)

## Status and Development

The [roadmap](project/roadmap.md) distinguishes implemented GUI workflows from
engine capabilities not yet exposed. [Changelog](project/changelog.md) tracks
development; [release validation](project/releases.md) records platform gaps.
Model libraries are starter/reference data, not comprehensive design-code catalogs.
Independently verify geometry, units, stability, conventions and engineering results.

Source code and issue reports: [GitHub repository](https://github.com/praksharma/PyniteGUI).
