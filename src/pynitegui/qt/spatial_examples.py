"""Spatial examples with true out-of-plane loading."""
import math
from .spatial_model import SpatialLoad, SpatialProject


def example_project(key, unit_system="imperial"):
    if key == "3d_multistorey_slabs":
        from .mesh_model import MeshDefinition
        from .model import Material
        project = SpatialProject(unit_system=unit_system, load_cases=["Dead", "Live"],
            default_load_case="Dead", combinations={"Gravity": {"Dead": 1., "Live": 1.},
                "Dead": {"Dead": 1.}, "Factored": {"Dead": 1.2, "Live": 1.6}})
        corners = ((0., 0.), (240., 0.), (240., 180.), (0., 180.))
        for floor in range(1, 4):
            height = floor*144.
            for x, z in corners:
                project.add_member((x, height-144., z), (x, height, z))
                if floor == 1:
                    project.nodes[project.node_at(x, 0., z)].support = "fixed"
            for index, (x, z) in enumerate(corners):
                end_x, end_z = corners[(index+1) % len(corners)]
                project.add_member((x, height, z), (end_x, height, end_z))
            name = f"Floor{floor}"
            project.surfaces[name] = MeshDefinition(name=name, plane="XZ", origin=[0., height, 0.],
                parameters={"width": 240., "height": 180.}, mesh_size=60., thickness=6.,
                material=Material("Slab concrete", E=3600., nu=.2, rho=.0000868), unit_system=unit_system)
            project.surface_pressures[name] = {"Dead": .001, "Live": .00025 if floor == 3 else .0005}
        project.surface_analysis_enabled = True
        project.validate()
        return project
    if key == "3d_slab_frame":
        from .mesh_model import MeshDefinition
        project = example_project("3d_space_frame", unit_system)
        project.loads.clear()
        project.set_load_case("Uplift", "Wind")
        project.set_combination("Uplift", {"Uplift": 1}, "Wind")
        project.surfaces["Floor"] = MeshDefinition(name="Floor", plane="XZ", origin=[0., 144., 0.],
            parameters={"width": 240., "height": 180.}, mesh_size=30., thickness=6., unit_system=unit_system)
        project.surface_pressures = {"Floor": {"Gravity": .001, "Uplift": -.0003}}
        project.surface_analysis_enabled = True
        project.validate()
        return project
    project = SpatialProject(unit_system=unit_system)
    def load(target, direction, magnitude, **kwargs):
        name = project.next_name("L", project.loads)
        project.loads[name] = SpatialLoad(name, target, direction, magnitude, **kwargs)
    if key == "3d_cantilever":
        member = project.add_member((0, 0, 0), (120, 0, 0))
        project.nodes["N1"].support = "fixed"
        load("N2", "FY", -1)
        load("N2", "FZ", 0.5)
        load("N2", "MX", 5)
        load(member, "Fy", -0.005, kind="distributed", position=0, end_magnitude=-0.01)
    elif key == "3d_tripod":
        for point in ((60, 0, 0), (-30, 0, 30 * math.sqrt(3)), (-30, 0, -30 * math.sqrt(3))):
            member = project.add_member(point, (0, 80, 0))
            project.members[member].kind = "truss"
            project.nodes[project.members[member].start].support = "pin"
        load(project.node_at(0, 80, 0), "FY", -3)
    elif key == "3d_space_frame":
        project.set_load_case("Gravity", "Case 1")
        project.set_load_case("Wind")
        project.set_combination("Gravity", {"Gravity": 1}, "Service")
        project.set_combination("Wind", {"Wind": 1})
        project.set_combination("Combined", {"Gravity": 1, "Wind": 1})
        corners = [(0, 0), (240, 0), (240, 180), (0, 180)]
        for x, z in corners:
            project.add_member((x, 0, z), (x, 144, z))
            project.nodes[project.node_at(x, 0, z)].support = "fixed"
        for index, (x, z) in enumerate(corners):
            end_x, end_z = corners[(index + 1) % 4]
            member = project.add_member((x, 144, z), (end_x, 144, end_z))
            load(member, "FY", -0.015, position=0, kind="distributed", end_magnitude=-0.015, case="Gravity")
        load(project.node_at(0, 144, 0), "FZ", 1.5, case="Wind")
        load(project.node_at(240, 144, 0), "FX", 1, case="Wind")
    else:
        raise ValueError("Unknown 3D example.")
    project.validate()
    return project
