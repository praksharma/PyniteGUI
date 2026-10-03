"""Fresh, editable demonstration models stored in canonical inch-kip units."""
from .model import Load, Project


EXAMPLES = {
    "simple_beam": "Simply Supported Beam",
    "portal": "Portal Frame - Distributed Load",
    "cantilever": "Cantilever - Mixed Loads",
    "continuous": "Continuous Beam - Partial Loads",
    "pitched": "Pitched Frame - Local Loads",
    "multistorey": "Two-Storey Frame - Gravity and Wind",
}


def example_project(key, unit_system="imperial"):
    if key not in EXAMPLES:
        raise ValueError(f"Unknown example: {key}")
    project = Project(unit_system=unit_system)

    def member(a, b):
        return project.add_member(a, b)

    def support(point, kind):
        project.nodes[project.node_at(*point)].support = kind

    def load(target, direction, magnitude, **kwargs):
        name = project.next_name("L", project.loads)
        project.loads[name] = Load(name, target, direction, magnitude, **kwargs)

    if key == "simple_beam":
        beam = member((0, 0), (420, 0))
        support((0, 0), "pin")
        support((420, 0), "roller")
        load(beam, "FY", -10)
    elif key == "portal":
        member((0, 0), (0, 144))
        beam = member((0, 144), (240, 144))
        member((240, 144), (240, 0))
        support((0, 0), "fixed")
        support((240, 0), "fixed")
        load(beam, "FY", -0.025, position=0, kind="distributed", end_magnitude=-0.025)
        load(project.node_at(0, 144), "FX", 2)
    elif key == "cantilever":
        beam = member((0, 0), (240, 0))
        support((0, 0), "fixed")
        load(beam, "FY", -0.015, position=0, kind="distributed", end_magnitude=-0.015, end_position=0.6)
        load(beam, "Angle", 2, position=0.65, angle=-60)
        tip = project.node_at(240, 0)
        load(tip, "FY", -3)
        load(tip, "MZ", -40)
    elif key == "continuous":
        left = member((0, 0), (240, 0))
        right = member((240, 0), (480, 0))
        support((0, 0), "pin")
        support((240, 0), "roller")
        support((480, 0), "roller")
        load(left, "FY", -0.025, position=0.2, kind="distributed", end_magnitude=-0.025, end_position=0.8)
        load(right, "FY", 0, position=0, kind="distributed", end_magnitude=-0.04)
        load(right, "FY", -4, position=0.4)
    elif key == "pitched":
        member((0, 0), (0, 120))
        left = member((0, 120), (180, 192))
        right = member((180, 192), (360, 120))
        member((360, 120), (360, 0))
        support((0, 0), "fixed")
        support((360, 0), "fixed")
        for beam in (left, right):
            load(beam, "Local y", -0.02, position=0, kind="distributed", end_magnitude=-0.02)
    else:
        project.set_load_case("Gravity", "Case 1")
        project.set_load_case("Wind")
        project.set_combination("Gravity", {"Gravity": 1}, "Service")
        project.set_combination("Wind", {"Wind": 1})
        project.set_combination("Combined", {"Gravity": 1, "Wind": 1})
        for floor in range(2):
            height = (floor + 1) * 144
            member((0, floor * 144), (0, height))
            beam = member((0, height), (240, height))
            member((240, height), (240, floor * 144))
            load(beam, "FY", -0.02, position=0, kind="distributed", end_magnitude=-0.02, case="Gravity")
            load(project.node_at(0, height), "FX", 1 + floor, case="Wind")
        support((0, 0), "fixed")
        support((240, 0), "fixed")
    project.validate()
    return project
