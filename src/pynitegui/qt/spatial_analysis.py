"""Six-DOF linear PyNite analysis without artificial planar restraints."""
import math
import numpy as np
from Pynite import FEModel3D

from .spatial_model import DOFS


def rigid_body_issue(project):
    from .analysis import affected_dofs
    origin = np.array(next(iter(project.nodes.values())).coords)
    span = max(1.0, *(math.dist(node.coords, origin) for node in project.nodes.values()))
    constraints, motions, labels = [], [], []
    frame_nodes = {name for member in project.members.values() if member.kind == "frame" for name in (member.start, member.end)}
    inactive = project.inactive_rotations()
    for node in project.nodes.values():
        x, y, z = (np.array(node.coords) - origin) / span
        rows = ((1, 0, 0, 0, z, -y), (0, 1, 0, -z, 0, x), (0, 0, 1, y, -x, 0),
                (0, 0, 0, 1, 0, 0), (0, 0, 0, 0, 1, 0), (0, 0, 0, 0, 0, 1))
        for direction, fixed, k, row in zip(DOFS, node.restraints, node.springs, rows):
            if (fixed or k) and (not direction.startswith("R") or node.name in frame_nodes):
                constraints.append(row)
            if not fixed and (not direction.startswith("R") or node.name in frame_nodes) and (node.name, direction) not in inactive:
                motions.append(row)
                labels.append(f"{node.name} {direction}")
    _, singular, modes = np.linalg.svd(np.array(constraints).reshape(-1, 6), full_matrices=True)
    rank = int(np.count_nonzero(singular > 1e-10))
    if rank < 6:
        participation = np.linalg.norm(np.array(motions).reshape(-1, 6) @ modes[rank:].T, axis=1)
        if not np.any(participation > 1e-7):
            return None
        return "Insufficient supports: the spatial structure can move as a rigid body.\nAffected global degrees of freedom: " + affected_dofs(labels, participation) + "."
    return None


def analyze_spatial(project, progress=None):
    from .analysis import AnalysisResult, model_signature, stiffness_issue
    phase = progress or (lambda message: None)
    phase("Checking 3D model and supports")
    project.validate()
    if not project.members:
        raise ValueError("Draw at least one 3D frame member.")
    issues = project.analysis_topology_issues() + project.analysis_release_issues()
    if issues:
        raise ValueError("\n\n".join(issues))
    issue = rigid_body_issue(project)
    if issue:
        raise ValueError(issue)
    phase("Building spatial solver model")
    model = FEModel3D()
    inactive = project.inactive_rotations()
    for material in project.materials.values():
        model.add_material(material.name, material.E, material.G, material.nu, material.rho)
    for section in project.sections.values():
        model.add_section(section.name, section.A, section.Iy, section.Iz, section.J)
    for node in project.nodes.values():
        model.add_node(node.name, *node.coords)
        model.def_support(node.name, **{"support_" + dof: fixed or (node.name, dof) in inactive for dof, fixed in zip(DOFS, node.restraints)})
        for dof, stiffness in zip(DOFS, node.springs):
            if stiffness:
                model.def_support_spring(node.name, dof, stiffness)
    for member in project.members.values():
        model.add_member(member.name, member.start, member.end, member.material, member.section, rotation=member.roll)
        model.members[member.name]._pynitegui_truss = member.kind == "truss"
        if member.kind == "truss":
            model.def_releases(member.name, Rxi=True, Ryi=True, Rzi=True, Ryj=True, Rzj=True)
    for load in (*project.loads.values(), *project.self_weight_loads()):
        ends = dict(load.components(project, load.end_magnitude))
        for direction, magnitude in load.components(project):
            if load.target in project.nodes:
                model.add_node_load(load.target, direction, magnitude, case=load.case)
            else:
                member = project.members[load.target]
                length = math.dist(project.nodes[member.start].coords, project.nodes[member.end].coords)
                if load.kind == "distributed":
                    model.add_member_dist_load(load.target, direction, magnitude, ends[direction],
                                               length * load.position, length * load.end_position, case=load.case)
                else:
                    model.add_member_pt_load(load.target, direction, magnitude, length * load.position, case=load.case)
    for name, factors in project.combinations.items():
        model.add_load_combo(name, dict(factors))
    phase(f"Solving {len(project.combinations)} spatial combination(s)")
    try:
        model.analyze_linear(check_stability=True, check_statics=True)
    except Exception as error:
        if not any(word in str(error).lower() for word in ("unstable", "singular", "instability")):
            raise
        phase("Checking spatial instability")
        try:
            issue = stiffness_issue(model, spatial=True)
        except Exception:
            issue = None
        raise ValueError("Spatial structure is unstable.\n" + (issue or str(error)) + "\nNo extra restraints were added.") from error
    phase("Checking spatial results and stiffness")
    if any(not math.isfinite(value) for node in model.nodes.values()
           for key in (*DOFS, "RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ")
           for value in getattr(node, key).values()):
        raise ValueError("Spatial analysis returned nonfinite results.")
    issue = stiffness_issue(model, spatial=True)
    if issue:
        raise ValueError("Spatial stiffness is singular or numerically ill-conditioned.\n" + issue)
    phase("Collecting spatial result snapshot")
    result = AnalysisResult.from_solver(model, next(iter(project.combinations)), frozenset(inactive), spatial=True)
    result.model_signature = model_signature(project)
    return result
