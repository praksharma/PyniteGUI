"""PyNite adapter for planar frame models (inches and kips)."""
from dataclasses import dataclass
import math

from Pynite import FEModel3D

from .model import Project


@dataclass
class AnalysisResult:
    solver: FEModel3D
    displacements: dict
    reactions: dict


def analyze(project: Project) -> AnalysisResult:
    project.validate()
    if not project.members:
        raise ValueError("Add at least one member before running analysis.")
    connected = {name for m in project.members.values() for name in (m.start, m.end)}
    if connected != set(project.nodes):
        raise ValueError("Remove or connect isolated nodes before analysis.")
    if not any(node.support != "free" for node in project.nodes.values()):
        raise ValueError("Assign supports before running analysis.")
    model = FEModel3D()
    model.add_material("Material", project.E, project.E / (2 * (1 + project.nu)), project.nu, project.rho)
    model.add_section("Section", project.A, project.Iy, project.Iz, project.J)
    for node in project.nodes.values():
        model.add_node(node.name, node.x, node.y, 0)
        model.def_support(
            node.name,
            support_DX=node.support in ("pin", "fixed"),
            support_DY=node.support != "free",
            support_DZ=True,
            support_RX=True,
            support_RY=True,
            support_RZ=node.support == "fixed",
        )
    for member in project.members.values():
        model.add_member(member.name, member.start, member.end, "Material", "Section")
    for load in project.loads.values():
        if load.target in project.nodes:
            model.add_node_load(load.target, load.direction, load.magnitude)
        else:
            member = project.members[load.target]
            a, b = project.nodes[member.start], project.nodes[member.end]
            model.add_member_pt_load(load.target, load.direction, load.magnitude, math.hypot(b.x - a.x, b.y - a.y) * load.position)
    model.add_load_combo("Service", {"Case 1": 1.0})
    model.analyze_linear(check_stability=True, check_statics=True)
    return AnalysisResult(
        model,
        {name: (node.DX["Service"], node.DY["Service"], node.RZ["Service"]) for name, node in model.nodes.items()},
        {name: (node.RxnFX["Service"], node.RxnFY["Service"], node.RxnMZ["Service"]) for name, node in model.nodes.items()},
    )
