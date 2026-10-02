"""PyNite adapter for planar frame models (inches and kips)."""
from dataclasses import dataclass, field
import math

from Pynite import FEModel3D

from .model import Project


@dataclass
class AnalysisResult:
    solver: FEModel3D
    displacements: dict
    reactions: dict
    combination: str = "Service"
    inactive_rotations: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_solver(cls, model, combination, inactive_rotations=frozenset()):
        if combination not in model.load_combos:
            raise ValueError(f"Unknown result combination: {combination}")
        return cls(
            model,
            {name: (node.DX[combination], node.DY[combination], None if name in inactive_rotations else node.RZ[combination]) for name, node in model.nodes.items()},
            {name: (node.RxnFX[combination], node.RxnFY[combination], 0.0 if name in inactive_rotations else node.RxnMZ[combination]) for name, node in model.nodes.items()},
            combination,
            frozenset(inactive_rotations),
        )

    def for_combination(self, combination):
        return self.from_solver(self.solver, combination, self.inactive_rotations)


def analyze(project: Project) -> AnalysisResult:
    project.validate()
    if not project.members:
        raise ValueError("Add at least one member before running analysis.")
    issues = project.analysis_topology_issues() + project.analysis_release_issues()
    if issues:
        raise ValueError("\n\n".join(issues))
    if not any(node.support != "free" for node in project.nodes.values()):
        raise ValueError("Assign supports before running analysis.")
    inactive_rotations = project.inactive_rotations()
    model = FEModel3D()
    for material in project.materials.values():
        model.add_material(material.name, material.E, material.G, material.nu, material.rho)
    for section in project.sections.values():
        model.add_section(section.name, section.A, section.Iy, section.Iz, section.J)
    for node in project.nodes.values():
        model.add_node(node.name, node.x, node.y, 0)
        model.def_support(
            node.name,
            support_DX=node.support in ("pin", "fixed"),
            support_DY=node.support != "free",
            support_DZ=True,
            support_RX=True,
            support_RY=True,
            # An all-hinged joint has no shared rotation DOF. This numerical
            # restraint cannot transfer moment through its released members.
            support_RZ=node.support == "fixed" or node.name in inactive_rotations,
        )
    for member in project.members.values():
        model.add_member(member.name, member.start, member.end, member.material, member.section)
        model.def_releases(member.name, Rzi=member.release_start, Rzj=member.release_end)
    for load in project.loads.values():
        if load.target in project.nodes:
            model.add_node_load(load.target, load.direction, load.magnitude, case=load.case)
        else:
            member = project.members[load.target]
            a, b = project.nodes[member.start], project.nodes[member.end]
            length = math.hypot(b.x - a.x, b.y - a.y)
            if load.kind == "distributed":
                model.add_member_dist_load(load.target, load.direction, load.magnitude, load.end_magnitude,
                                           length * load.position, length * load.end_position, case=load.case)
            else:
                model.add_member_pt_load(load.target, load.direction, load.magnitude, length * load.position, case=load.case)
    for name, factors in project.combinations.items():
        model.add_load_combo(name, dict(factors))
    model.analyze_linear(check_stability=True, check_statics=True)
    return AnalysisResult.from_solver(model, next(iter(project.combinations)), inactive_rotations)
