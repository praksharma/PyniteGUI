"""PyNite adapter for planar frame models (inches and kips)."""
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import uuid

import numpy as np
from Pynite import FEModel3D

from .model import Project


def model_signature(project):
    data = project.to_dict()
    data.pop("unit_system")
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


def affected_dofs(labels, participation):
    entries = [label for label, value in zip(labels, participation) if value > 1e-7]
    visible = ", ".join(entries[:24])
    if len(entries) > 24:
        visible += f", and {len(entries) - 24} more"
    return visible


def rigid_body_issue(project):
    nodes = list(project.nodes.values())
    inactive_rotations = project.inactive_rotations()
    origin_x, origin_y = nodes[0].x, nodes[0].y
    span = max(1.0, *(math.hypot(node.x - origin_x, node.y - origin_y) for node in nodes))
    constraints, motions, labels = [], [], []
    for node in nodes:
        x, y = (node.x - origin_x) / span, (node.y - origin_y) / span
        for direction, restrained, motion in zip(("DX", "DY", "RZ"), node.restraints,
                                                 ((1, 0, -y), (0, 1, x), (0, 0, 1))):
            if restrained:
                constraints.append(motion)
            elif direction != "RZ" or node.name not in inactive_rotations:
                motions.append(motion)
                labels.append(f"{node.name} {direction}")
    _, singular, modes = np.linalg.svd(np.asarray(constraints).reshape(-1, 3), full_matrices=True)
    rank = int(np.count_nonzero(singular > 1e-10))
    if rank == 3:
        return None
    participation = np.linalg.norm(np.asarray(motions) @ modes[rank:].T, axis=1)
    return ("Insufficient supports: the structure can move as a rigid body.\n"
            f"Affected global degrees of freedom: {affected_dofs(labels, participation)}.\n"
            "Check global X/Y restraints and restraint against rotation of the whole structure. "
            "A pin alone does not prevent rotation; Y-only rollers do not prevent horizontal motion.")


def stiffness_issue(model):
    labels, indices = [], []
    for node in model.nodes.values():
        for offset, direction in ((0, "DX"), (1, "DY"), (5, "RZ")):
            if not getattr(node, "support_" + direction):
                indices.append(node.ID * 6 + offset)
                labels.append(f"{node.name} {direction}")
    if not indices:
        return None
    if len(indices) > 600:
        return None
    combination = next(iter(model.load_combos))
    stiffness = model.Ke(combination, check_stability=False, sparse=True).tocsr()
    matrix = stiffness[indices, :][:, indices].toarray()
    diagonal = np.diag(matrix)
    missing = diagonal <= 0
    if np.any(missing):
        return "No effective joint stiffness at: " + affected_dofs(labels, missing) + "."
    # Diagonal scaling compares translations and rotations without mixing their units.
    scale = np.sqrt(diagonal)
    normalized = matrix / np.outer(scale, scale)
    eigenvalues, modes = np.linalg.eigh((normalized + normalized.T) / 2)
    tolerance = 10 * np.finfo(float).eps * len(indices) * max(1.0, abs(eigenvalues[-1]))
    unstable = eigenvalues <= tolerance
    if np.any(unstable):
        participation = np.linalg.norm(modes[:, unstable], axis=1)
        participation /= max(participation.max(), 1e-30)
        return "Possible mechanism or very weak stiffness involves: " + affected_dofs(labels, participation) + "."
    return None


def instability_details(model):
    try:
        issue = stiffness_issue(model)
        if issue:
            return issue
    except Exception:
        # Diagnostic failure must never replace the original analysis failure.
        pass
    return ("The solver could not localize the instability. Check supports, member end releases, and very small stiffnesses. "
            "Joint localization is limited to 600 free planar degrees of freedom.")


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
    issue = rigid_body_issue(project)
    if issue:
        raise ValueError(issue)
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
    if project.self_weight_case is not None:
        model.add_member_self_weight("FY", -project.self_weight_factor, project.self_weight_case)
    try:
        model.analyze_linear(check_stability=True, check_statics=True)
    except Exception as error:
        if not any(word in str(error).lower() for word in ("unstable", "singular", "instability")):
            raise
        raise ValueError("Structure is unstable.\n" + instability_details(model) +
                         "\nCheck supports and member releases; no extra restraints were added.") from error
    if any(not math.isfinite(value) for node in model.nodes.values()
           for key in ("DX", "DY", "RZ", "RxnFX", "RxnFY", "RxnMZ")
           for value in getattr(node, key).values()):
        raise ValueError("Analysis returned nonfinite results; the structure may be unstable.\n" + instability_details(model))
    issue = stiffness_issue(model)
    if issue:
        raise ValueError("The stiffness matrix is singular or numerically ill-conditioned; the structure may be unstable.\n" +
                         issue + "\nCheck supports, member releases, and stiffness contrasts; no extra restraints were added.")
    result = AnalysisResult.from_solver(model, next(iter(project.combinations)), inactive_rotations)
    result.model_signature = model_signature(project)
    return result
