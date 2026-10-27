"""Adaptations of PyNite's MIT-licensed official structural examples.

Source revision and differences are documented in GUIDE.md, Examples and
Appearance. Upstream copyright/permission notice: licenses/pynite-examples.txt.
"""
from .model import Load, Material, Member, Node, Project, Section


SOURCE_COMMIT = "e3a0bbd912b6cf13140f01ca0ed3a2ee55069f45"
SOURCES = {
    "official_beam_point": "Simple Beam - Point Load.py",
    "official_beam_uniform": "Simple Beam - Uniform Load.py",
    "official_beam_envelope": "Simple Beam - Factored Envelope.py",
    "official_moment_frame": "Moment Frame - Lateral Load.py",
    "official_p_delta": "P-Delta Analysis.py",
    "3d_official_truss": "Space Truss - Nodal Load.py",
    "3d_official_space_frame_1": "Space Frame - Nodal Loads 1.py",
    "3d_official_space_frame_2": "Space Frame - Nodal Loads 2.py",
}
BEAM_KEYS = ("official_beam_point", "official_beam_uniform", "official_beam_envelope")


def example_project(key, unit_system="imperial"):
    if key not in SOURCES:
        raise ValueError(f"Unknown official example: {key}")
    if key == "official_moment_frame":
        return moment_frame(unit_system)
    if key == "official_p_delta":
        return p_delta_column(unit_system)
    if key.startswith("3d_official_space_frame_"):
        return space_frame(int(key[-1]), unit_system)
    if key == "3d_official_truss":
        return space_truss(unit_system)
    uniform = key == "official_beam_uniform"
    point = key == "official_beam_point"
    cases = ["Case 1"] if uniform else (["D", "L"] if point else ["D", "S", "L"])
    combinations = {"Combo 1": {"Case 1": 1.}} if uniform else {
        "1.4D": {"D": 1.4}, "1.2D+1.6L": {"D": 1.2, "L": 1.6}}
    if not uniform and not point:
        combinations["1.2D+1.6S"] = {"D": 1.2, "S": 1.6}
    project = Project(unit_system=unit_system,
        materials={"Steel": Material("Steel", E=29000., nu=.3, rho=2.836e-4)},
        default_material="Steel",
        sections={"MySection": Section("MySection", A=20., Iy=100., Iz=150., J=250.)},
        default_section="MySection", load_cases=cases, default_load_case=cases[0],
        combinations=combinations)
    beam = project.add_member((0., 0.), (168., 0.))
    # Both ends restrain X/Y in the official scripts. The planar solver omits
    # their out-of-plane and torsional DOFs, retaining free in-plane rotations.
    for node in project.nodes.values():
        node.support = "pin"
    if uniform:
        project.loads["L1"] = Load("L1", beam, "Local y", -200./1000./12.,
                                   position=0., kind="distributed", end_magnitude=-200./1000./12.)
    else:
        # Preserve the executable source's signs, even where its comments say
        # "downward": the envelope example really applies positive D/S loads.
        loads = (("D", -5., 84.), ("L", -8., 84.)) if point else (
            ("D", 5., 48.), ("S", 8., 108.), ("L", -8., 144.))
        for index, (case, magnitude, station) in enumerate(loads, 1):
            name = f"L{index}"
            project.loads[name] = Load(name, beam, "Local y", magnitude, station/168., case=case)
    project.validate()
    return project


def moment_frame(unit_system):
    project = Project(unit_system=unit_system, analysis_method="p_delta",
        materials={"Steel": Material("Steel", E=29000., nu=.3, rho=.490/12**3)}, default_material="Steel",
        sections={"W10x33": Section("W10x33", A=9.71, Iy=36.6, Iz=171., J=.58),
                  "W8x24": Section("W8x24", A=7.08, Iy=18.3, Iz=82.7, J=.346)}, default_section="W10x33",
        load_cases=["D", "W"], default_load_case="D",
        combinations={"1.2D+1.0W": {"D": 1.2, "W": 1.}, "0.9D+1.0W": {"D": .9, "W": 1.}})
    project.nodes = {name: Node(name, x, y, support=support) for name, x, y, support in (
        ("N1", 0., 0., "fixed"), ("N2", 0., 144., "free"),
        ("N3", 180., 144., "free"), ("N4", 180., 0., "fixed"))}
    project.members = {name: Member(name, a, b, "Steel", section) for name, a, b, section in (
        ("Col1", "N1", "N2", "W10x33"), ("Col2", "N4", "N3", "W10x33"), ("Beam", "N2", "N3", "W8x24"))}
    for i, (target, direction, weight) in enumerate((
            ("Beam", "Local y", -.024/12), ("Col1", "Local x", -.033/12), ("Col2", "Local x", -.033/12)), 1):
        name = f"L{i}"
        project.loads[name] = Load(name, target, direction, weight, 0., "distributed", weight, case="D")
    project.loads["L4"] = Load("L4", "N2", "FX", 10., case="W")
    project.validate()
    return project


def p_delta_column(unit_system):
    # Convert the source's ft/kip definitions to canonical in/kip. Explicit
    # members replace PyNite's physical-member subdivision at its six nodes.
    project = Project(unit_system=unit_system, analysis_method="p_delta",
        materials={"Steel": Material("Steel", E=29000., nu=.3, rho=.490/12**3)}, default_material="Steel",
        sections={"MySection": Section("MySection", A=10., Iy=100., Iz=100., J=200.)}, default_section="MySection",
        combinations={"Combo 1": {"Case 1": 1.}})
    for i in range(5):
        project.add_member((0., 48.*i), (0., 48.*(i+1)))
    project.nodes["N1"].support = "fixed"
    project.loads = {"L1": Load("L1", "N6", "FY", -100.), "L2": Load("L2", "N6", "FX", 5.)}
    project.validate()
    return project


def space_truss(unit_system):
    from .spatial_model import SpatialLoad, SpatialMember, SpatialNode, SpatialProject
    from .units import INCH_TO_METRE, KIP_TO_KN
    length, force = INCH_TO_METRE, KIP_TO_KN
    project = SpatialProject(unit_system=unit_system,
        materials={"Rigid": Material("Rigid", E=99999999.*length**2/force, nu=.3, rho=length**3/force)},
        default_material="Rigid",
        sections={"TrussSection": Section("TrussSection", A=100./length**2,
                  Iy=100./length**4, Iz=100./length**4, J=100./length**4)}, default_section="TrussSection",
        combinations={"Combo 1": {"Case 1": 1.}})
    project.nodes = {name: SpatialNode(name, x/length, y/length, z=z/length,
                                      support="fixed" if name in "CDE" else "free")
                     for name, x, y, z in (("A", 1.1, -.4, 0.), ("B", 1., 0., 0.),
                                          ("C", 0., 0., .6), ("D", 0., 0., -.4), ("E", 0., .8, 0.))}
    project.members = {name: SpatialMember(name, name[0], name[1], "Rigid", "TrussSection", kind="truss")
                       for name in ("AB", "AC", "AD", "BC", "BD", "BE")}
    project.loads = {f"L{i}": SpatialLoad(f"L{i}", "A", direction, magnitude/force)
                     for i, (direction, magnitude) in enumerate((("FX", 10.), ("FY", 60.), ("FZ", 20.)), 1)}
    project.validate()
    return project


def space_frame(number, unit_system="imperial"):
    """Preserve the pinned scripts' IDs, XYZ geometry, E/G/nu and nodal loads."""
    from .spatial_model import SpatialLoad, SpatialMember, SpatialNode, SpatialProject
    first = number == 1
    project = SpatialProject(unit_system=unit_system,
        materials={"Steel": Material("Steel", E=30000., nu=.3, rho=2.836e-4, shear_modulus=10000.)},
        default_material="Steel",
        sections={"MySection": Section("MySection", A=10. if first else 100.,
                    Iy=100. if first else 200., Iz=100. if first else 1000., J=50. if first else 100.)},
        default_section="MySection", combinations={"Combo 1": {"Case 1": 1.}})
    positions = (("N1", 0., 0., 0.), ("N2", -100., 0., 0.), ("N3", 0., 0., -100.), ("N4", 0., -100., 0.)) if first else (
        ("N1", 0., 0., 0.), ("N2", 120., 0., 0.), ("N3", 120., 0., -120.), ("N4", 120., -240., -120.))
    fixed = ("N2", "N3", "N4") if first else ("N1", "N4")
    project.nodes = {name: SpatialNode(name, x, y, z=z, support="fixed" if name in fixed else "free")
                     for name, x, y, z in positions}
    members = (("M1", "N2", "N1"), ("M2", "N3", "N1"), ("M3", "N4", "N1")) if first else (
        ("M12", "N1", "N2"), ("M23", "N2", "N3"), ("M34", "N3", "N4"))
    project.members = {name: SpatialMember(name, start, end, "Steel", "MySection") for name, start, end in members}
    loads = (("N1", "FY", -50.), ("N1", "MX", -1000.)) if first else (("N2", "FY", -5.), ("N2", "MX", -1200.), ("N3", "FZ", 40.))
    project.loads = {f"L{i}": SpatialLoad(f"L{i}", target, direction, value)
                     for i, (target, direction, value) in enumerate(loads, 1)}
    project.validate()
    return project
