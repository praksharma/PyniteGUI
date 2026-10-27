"""Official transverse Quad example in the existing separate plate workspace.

Source: PyNite Examples/Rectangular Plate Bending - Qauds.py at the revision
in official_examples.SOURCE_COMMIT. MIT notice: licenses/pynite-examples.txt.
"""
from .model import Material
from .plate_model import PlateDefinition


PLATE_EXAMPLES = {"official_plate_quad": "Official PyNite - Clamped Rectangular Quad Plate"}
PLATE_CATEGORY = "Plates (Experimental)"
PLATE_NOTES = {
    "official_plate_quad": (
        "Official PyNite adaptation: 10 × 20 ft clamped concrete plate, 1 ft thick, under +250 psf normal pressure. Opens the separate plate workspace.",
        "200 Quads; applied +50 kip; normal reactions total -50 kip. Classical thin-plate centre displacement +0.00171054 in (DKMQ +0.00191955 in); DKMQ includes transverse shear.")}


def example_definition(key="official_plate_quad", unit_system="imperial"):
    if key not in PLATE_EXAMPLES:
        raise ValueError(f"Unknown official plate example: {key}")
    definition = PlateDefinition(width=120., height=240., thickness=12., mesh_size=12.,
        material=Material("Concrete", E=57000.*4000.**.5/1000., nu=.17, rho=150./1000./12**3),
        pressure=250./1000./12**2, load_case="W", load_factor=1.,
        edges=dict.fromkeys(("Left", "Right", "Bottom", "Top"), "Clamped"),
        unit_system=unit_system, mesh_name="MSH1")
    definition.validate()
    return definition


def preview_project(definition):
    """Geometry only; plate inputs remain owned by PlateDefinition."""
    from .spatial_model import SpatialProject
    project = SpatialProject(unit_system=definition.unit_system)
    project.surfaces = {definition.mesh_name: definition.mesh_definition()}
    return project


def loading_summary(definition):
    u = definition.units
    return (f"Separate plate workspace · {u.summary}\n"
            f"Size: {u.to_display(definition.width, 'length'):.6g} × {u.to_display(definition.height, 'length'):.6g} {u.length}\n"
            f"Thickness: {u.to_display(definition.thickness, 'length'):.6g} {u.length}\n"
            f"Mesh: {u.to_display(definition.mesh_size, 'length'):.6g} {u.length} · Quad · all edges clamped\n"
            f"W pressure: +{u.to_display(definition.pressure, 'pressure'):.6g} {u.pressure} along +Z\n"
            "Combinations: Plate = 1.0W (upstream name: 1.0W)\n"
            "Linear elastic transverse plate bending; self-weight off.\n"
            "The main frame model and unsaved inputs remain unchanged.")
