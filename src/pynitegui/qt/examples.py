"""Fresh, editable demonstration models stored in canonical inch-kip units."""
from .model import Load, Project


EXAMPLES = {
    "simple_beam": "Simply Supported Beam",
    "portal": "Portal Frame - Distributed Load",
    "cantilever": "Cantilever - Mixed Loads",
    "continuous": "Continuous Beam - Partial Loads",
    "pitched": "Pitched Frame - Local Loads",
    "multistorey": "Two-Storey Frame - Gravity and Wind",
    "self_weight": "Simply Supported Beam - Self-Weight",
    "truss": "Triangular Truss - Joint Loads",
    "elastic": "Cantilever - Elastic Base",
    "inclined_roller": "Beam - Inclined Roller",
    "shear_release": "Fixed-Guided Beam - Shear Release",
    "3d_cantilever": "3D Cantilever - Biaxial Bending and Torsion",
    "3d_space_frame": "3D Space Frame - Gravity and Wind",
    "3d_released_beam": "3D Inclined Beam - Rotational End Releases",
    "3d_sliding_beam": "3D Fixed-Guided Beam - Translational End Releases",
    "3d_slab_frame": "3D Frame and Slab - Coupled Pressure (Experimental)",
    "3d_tripod": "3D Truss Tripod - Joint Load",
    "3d_multistorey_slabs": "Three-Storey Frame and Slabs (Experimental)",
    "p_delta_column": "Slender Column - Gravity and Lateral Load",
    "official_beam_point": "Official PyNite - Beam with Point Loads",
    "official_beam_uniform": "Official PyNite - Beam with Uniform Load",
    "official_beam_envelope": "Official PyNite - Beam with Factored Envelope",
    "official_moment_frame": "Official PyNite - Moment Frame with Lateral Load",
    "official_p_delta": "Official PyNite - P-Delta Column",
    "3d_official_truss": "Official PyNite - Space Truss with Nodal Load",
    "3d_official_space_frame_1": "Official PyNite - Space Frame with Nodal Loads 1",
    "3d_official_space_frame_2": "Official PyNite - Space Frame with Nodal Loads 2",
    "gerber": "Gerber Beam - Internal Hinge",
    "three_hinged_arch": "Three-Hinged Polygonal Arch",
}


# Keep stable example IDs and the flat catalog available to scripts/clients.
# The native menu uses this ordered grouping; each example belongs exactly once.
EXAMPLE_GROUPS = {
    "2D Frames": ("simple_beam", "portal", "cantilever", "continuous", "pitched",
                  "multistorey", "self_weight", "elastic", "inclined_roller", "shear_release",
                  "official_beam_point", "official_beam_uniform", "official_beam_envelope", "official_moment_frame",
                  "gerber", "three_hinged_arch"),
    "3D Frames": ("3d_cantilever", "3d_space_frame", "3d_released_beam", "3d_sliding_beam", "3d_official_space_frame_1", "3d_official_space_frame_2"),
    "Trusses": ("truss", "3d_tripod", "3d_official_truss"),
    "Slabs": ("3d_slab_frame", "3d_multistorey_slabs"),
    "P-Delta": ("p_delta_column", "official_p_delta"),
}


def example_project(key, unit_system="imperial"):
    if key not in EXAMPLES:
        raise ValueError(f"Unknown example: {key}")
    if key.startswith("official_"):
        from .official_examples import example_project as official_example
        return official_example(key, unit_system)
    if key.startswith("3d_"):
        from .spatial_examples import example_project as spatial_example
        return spatial_example(key, unit_system)
    project = Project(unit_system=unit_system)

    def member(a, b):
        return project.add_member(a, b)

    def support(point, kind):
        project.nodes[project.node_at(*point)].support = kind

    def load(target, direction, magnitude, **kwargs):
        name = project.next_name("L", project.loads)
        project.loads[name] = Load(name, target, direction, magnitude, **kwargs)

    if key == "inclined_roller":
        beam = member((0., 0.), (120., 0.))
        support((0., 0.), "pin")
        support((120., 0.), "inclined")
        project.nodes["N2"].support_angle = 30.
        load(beam, "FY", -.01, position=0., kind="distributed", end_magnitude=-.01)
        project.set_combination("Reverse", {"Case 1": -1.})
    elif key == "gerber":
        for a, b in (((0., 0.), (120., 0.)), ((120., 0.), (180., 0.)), ((180., 0.), (300., 0.))):
            beam = member(a, b)
            load(beam, "FY", -.01, position=0., kind="distributed", end_magnitude=-.01)
        support((0., 0.), "pin")
        support((120., 0.), "roller")
        support((300., 0.), "roller")
        project.members["M2"].release_end = True
        project.members["M3"].release_start = True
    elif key == "three_hinged_arch":
        points = ((0., 0.), (60., 60.), (120., 96.), (180., 60.), (240., 0.))
        for a, b in zip(points, points[1:]):
            member(a, b)
        support(points[0], "pin")
        support(points[-1], "pin")
        project.members["M2"].release_end = True
        project.members["M3"].release_start = True
        for point in points[1:-1]:
            load(project.node_at(*point), "FY", -5.)
    elif key in ("simple_beam", "self_weight"):
        beam = member((0, 0), (420, 0))
        support((0, 0), "pin")
        support((420, 0), "roller")
        if key == "self_weight":
            project.set_load_case("Self-weight", "Case 1")
            project.self_weight_case = "Self-weight"
        else:
            load(beam, "FY", -10)
    elif key == "p_delta_column":
        project.analysis_method = "p_delta"
        project.set_load_case("Gravity", "Case 1")
        project.set_load_case("Lateral")
        project.combinations = {"Combined": {"Gravity": 1., "Lateral": 1.},
                                "Gravity": {"Gravity": 1.}, "Lateral": {"Lateral": 1.}}
        # Eight explicit segments resolve the member curvature; all values are
        # canonical inch-kip and independent of the display-unit preference.
        for segment in range(8):
            member((0., segment*60.), (0., (segment+1)*60.))
        support((0., 0.), "fixed")
        tip = project.node_at(0., 480.)
        load(tip, "FY", -60., case="Gravity")
        load(tip, "FX", 1., case="Lateral")
    elif key == "elastic":
        member((0, 0), (120, 0))
        base = project.nodes[project.node_at(0, 0)]
        base.spring_x, base.spring_y, base.spring_rz = 1000, 1000, 500000
        load(project.node_at(120, 0), "FY", -10)
    elif key == "shear_release":
        beam = member((0, 0), (120, 0))
        support((0, 0), "fixed")
        support((120, 0), "fixed")
        project.members[beam].release_end_y = True
        load(beam, "FY", -10)
    elif key == "truss":
        for a, b in (((0, 0), (240, 0)), ((0, 0), (120, 96)), ((120, 96), (240, 0))):
            project.members[member(a, b)].kind = "truss"
        support((0, 0), "pin")
        support((240, 0), "roller")
        load(project.node_at(120, 96), "FY", -10)
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
