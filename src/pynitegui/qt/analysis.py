"""PyNite adapter for planar frame models (inches and kips)."""
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import uuid

import numpy as np
from Pynite import FEModel3D
from scipy.sparse import diags
from scipy.sparse.linalg import ArpackNoConvergence, eigsh

from .model import Project
from .released_member import recover_released_translations


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
        for direction, restrained, motion in zip(("DX", "DY", "RZ"),
                                                 (fixed or stiffness > 0 for fixed, stiffness in zip(node.restraints, node.springs)),
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


def stiffness_issue(model, spatial=False):
    labels, indices = [], []
    for node in model.nodes.values():
        directions = tuple(enumerate(("DX", "DY", "DZ", "RX", "RY", "RZ"))) if spatial else ((0, "DX"), (1, "DY"), (5, "RZ"))
        for offset, direction in directions:
            if not getattr(node, "support_" + direction):
                indices.append(node.ID * 6 + offset)
                labels.append(f"{node.name} {direction}")
    if not indices:
        return None
    combination = next(iter(model.load_combos))
    stiffness = model.Ke(combination, check_stability=False, sparse=True).tocsr()
    matrix = stiffness[indices, :][:, indices]
    if not np.all(np.isfinite(matrix.data)):
        raise ValueError("The stiffness matrix contains nonfinite values.")
    diagonal = matrix.diagonal()
    missing = diagonal <= 0
    if np.any(missing):
        return "No effective joint stiffness at: " + affected_dofs(labels, missing) + "."
    # Diagonal scaling compares translations and rotations without mixing their units.
    scale = diags(1 / np.sqrt(diagonal))
    normalized = scale @ ((matrix + matrix.T) * 0.5) @ scale
    if len(indices) <= 600:
        eigenvalues, modes = np.linalg.eigh(normalized.toarray())
        bound = max(1.0, abs(eigenvalues[-1]))
    else:
        # An absolute row-sum bound avoids a second spectral solve. A small
        # negative shift keeps exact mechanisms factorable while targeting the
        # near-zero modes of this positive-semidefinite elastic stiffness.
        bound = max(1.0, float(np.asarray(abs(normalized).sum(axis=1)).max()))
        tolerance = 10 * np.finfo(float).eps * len(indices) * bound
        try:
            eigenvalues, modes = eigsh(normalized, k=6, sigma=-max(1e-8, 100 * tolerance), which="LM",
                                       tol=1e-9, maxiter=max(1000, 5 * len(indices)),
                                       v0=np.random.default_rng(0).normal(size=len(indices)))
        except ArpackNoConvergence as error:
            if error.eigenvalues is None or not np.any(error.eigenvalues <= tolerance):
                raise ValueError("The sparse stability check did not converge. Results were not accepted; review stiffness contrasts and model geometry.") from error
            eigenvalues, modes = error.eigenvalues, error.eigenvectors
    tolerance = 10 * np.finfo(float).eps * len(indices) * bound
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
    return "The solver could not localize the instability. Check supports, member end releases, and very small stiffnesses."


@dataclass
class AnalysisResult:
    solver: FEModel3D
    displacements: dict
    reactions: dict
    combination: str = "Service"
    inactive_rotations: frozenset[str | tuple[str, str]] = field(default_factory=frozenset)
    snapshot_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    analyzed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    model_signature: str = ""
    spatial: bool = False

    @classmethod
    def from_solver(cls, model, combination, inactive_rotations=frozenset(), spatial=False):
        if combination not in model.load_combos:
            raise ValueError(f"Unknown result combination: {combination}")
        if spatial:
            return cls(model,
                       {name: tuple(None if (name, key) in inactive_rotations else getattr(node, key)[combination]
                                    for key in ("DX", "DY", "DZ", "RX", "RY", "RZ")) for name, node in model.nodes.items()},
                       {name: tuple(0. if key.startswith("RxnM") and (name, "R" + key[-1]) in inactive_rotations
                                    else getattr(node, key)[combination]
                                    for key in ("RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ")) for name, node in model.nodes.items()},
                       combination, inactive_rotations, spatial=True)
        return cls(
            model,
            {name: (node.DX[combination], node.DY[combination], None if name in inactive_rotations else node.RZ[combination]) for name, node in model.nodes.items()},
            {name: (node.RxnFX[combination], node.RxnFY[combination], 0.0 if name in inactive_rotations else node.RxnMZ[combination]) for name, node in model.nodes.items()},
            combination,
            frozenset(inactive_rotations),
        )

    def for_combination(self, combination):
        return replace(self.from_solver(self.solver, combination, self.inactive_rotations, spatial=self.spatial),
                       snapshot_id=self.snapshot_id, analyzed_at=self.analyzed_at,
                       model_signature=self.model_signature)


def analyze(project: Project, progress=None) -> AnalysisResult:
    if getattr(project, "dimension", None) == "3D":
        from .spatial_analysis import analyze_spatial
        return analyze_spatial(project, progress)
    def phase(message):
        if progress is not None:
            progress(message)
    phase("Checking model and supports")
    project.validate()
    if not project.members:
        raise ValueError("Add at least one member before running analysis.")
    issues = project.analysis_topology_issues() + project.analysis_release_issues()
    if issues:
        raise ValueError("\n\n".join(issues))
    if not any(any(node.restraints) or any(node.springs) for node in project.nodes.values()):
        raise ValueError("Assign supports before running analysis.")
    issue = rigid_body_issue(project)
    if issue:
        raise ValueError(issue)
    inactive_rotations = project.inactive_rotations()
    phase("Building the analysis model")
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
        for direction, stiffness in zip(("DX", "DY", "RZ"), node.springs):
            if stiffness:
                model.def_support_spring(node.name, direction, stiffness)
    for member in project.members.values():
        model.add_member(member.name, member.start, member.end, member.material, member.section)
        release_start, release_end = member.moment_releases
        model.def_releases(member.name, Rzi=release_start, Rzj=release_end,
                           Dxi=member.release_start_x, Dxj=member.release_end_x,
                           Dyi=member.release_start_y, Dyj=member.release_end_y)
    for load in (*project.loads.values(), *project.self_weight_loads()):
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
    phase(f"Solving {len(project.combinations)} combination(s)")
    try:
        model.analyze_linear(check_stability=True, check_statics=True)
    except Exception as error:
        if not any(word in str(error).lower() for word in ("unstable", "singular", "instability")):
            raise
        phase("Checking instability details")
        raise ValueError("Structure is unstable.\n" + instability_details(model) +
                         "\nCheck supports and member releases; no extra restraints were added.") from error
    phase("Checking results and stiffness")
    if any(not math.isfinite(value) for node in model.nodes.values()
           for key in ("DX", "DY", "RZ", "RxnFX", "RxnFY", "RxnMZ")
           for value in getattr(node, key).values()):
        raise ValueError("Analysis returned nonfinite results; the structure may be unstable.\n" + instability_details(model))
    issue = stiffness_issue(model)
    if issue:
        raise ValueError("The stiffness matrix is singular or numerically ill-conditioned; the structure may be unstable.\n" +
                         issue + "\nCheck supports, member releases, and stiffness contrasts; no extra restraints were added.")
    phase("Collecting result snapshot")
    recover_released_translations(model)
    result = AnalysisResult.from_solver(model, next(iter(project.combinations)), inactive_rotations)
    result.model_signature = model_signature(project)
    return result
