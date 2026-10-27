"""Planar adaptations of PyNite's MIT-licensed official beam examples.

Source revision and differences are documented in GUIDE.md, Examples and
Appearance. Upstream copyright/permission notice: licenses/pynite-examples.txt.
"""
from .model import Load, Material, Project, Section


SOURCE_COMMIT = "e3a0bbd912b6cf13140f01ca0ed3a2ee55069f45"
SOURCES = {
    "official_beam_point": "Simple Beam - Point Load.py",
    "official_beam_uniform": "Simple Beam - Uniform Load.py",
    "official_beam_envelope": "Simple Beam - Factored Envelope.py",
}


def example_project(key, unit_system="imperial"):
    if key not in SOURCES:
        raise ValueError(f"Unknown official example: {key}")
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
