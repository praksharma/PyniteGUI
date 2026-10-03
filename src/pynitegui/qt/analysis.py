"""PyNite adapter for planar frame models (inches and kips)."""
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import uuid

from Pynite import FEModel3D

from .model import Project


def model_signature(project):
    data = project.to_dict()
    data.pop("unit_system")
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


@dataclass
class AnalysisResult:
    solver: FEModel3D
    displacements: dict
    reactions: dict
    combination: str = "Service"
    inactive_rotations: frozenset[str] = field(default_factory=frozenset)
    snapshot_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    analyzed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    model_signature: str = ""

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
        return replace(self.from_solver(self.solver, combination, self.inactive_rotations),
                       snapshot_id=self.snapshot_id, analyzed_at=self.analyzed_at,
                       model_signature=self.model_signature)


def analyze(project: Project) -> AnalysisResult:
    project.validate()
    if not project.members:
        raise ValueError("Add at least one member before running analysis.")
    issues = project.analysis_topology_issues() + project.analysis_release_issues()
    if issues:
        raise ValueError("\n\n".join(issues))
    if not any(any(node.restraints) for node in project.nodes.values()):
        raise ValueError("Assign supports before running analysis.")
    inactive_rotations = project.inactive_rotations()
    model = FEModel3D()
    for material in project.materials.values():
        model.add_material(material.name, material.E, material.G, material.nu, material.rho)
    for section in project.sections.values():
        model.add_section(section.name, section.A, section.Iy, section.Iz, section.J)
    for node in project.nodes.values():
        model.add_node(node.name, node.x, node.y, 0)
        restraint_x, restraint_y, restraint_rz = node.restraints
        model.def_support(
            node.name,
            support_DX=restraint_x,
            support_DY=restraint_y,
            support_DZ=True,
            support_RX=True,
            support_RY=True,
            # An all-hinged joint has no shared rotation DOF. This numerical
            # restraint cannot transfer moment through its released members.
            support_RZ=restraint_rz or node.name in inactive_rotations,
        )
    for member in project.members.values():
        model.add_member(member.name, member.start, member.end, member.material, member.section)
        model.def_releases(member.name, Rzi=member.release_start, Rzj=member.release_end)
    for load in project.loads.values():
        if load.target in project.nodes:
            for direction, magnitude in load.components(project):
                model.add_node_load(load.target, direction, magnitude, case=load.case)
        else:
            member = project.members[load.target]
            a, b = project.nodes[member.start], project.nodes[member.end]
            length = math.hypot(b.x - a.x, b.y - a.y)
            if load.kind == "distributed":
                for (direction, start), (_, end) in zip(load.components(project), load.components(project, load.end_magnitude)):
                    model.add_member_dist_load(load.target, direction, start, end,
                                               length * load.position, length * load.end_position, case=load.case)
            else:
                for direction, magnitude in load.components(project):
                    model.add_member_pt_load(load.target, direction, magnitude, length * load.position, case=load.case)
    for name, factors in project.combinations.items():
        model.add_load_combo(name, dict(factors))
    model.analyze_linear(check_stability=True, check_statics=True)
    result = AnalysisResult.from_solver(model, next(iter(project.combinations)), inactive_rotations)
    result.model_signature = model_signature(project)
    return result
