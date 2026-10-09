"""Spatial examples with true out-of-plane loading."""
import math
from .spatial_model import SpatialLoad, SpatialProject


def example_project(key, unit_system="imperial"):
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
