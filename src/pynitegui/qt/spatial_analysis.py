"""Six-DOF elastic frame analysis without artificial planar restraints."""
import math
import numpy as np

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
    if project.surfaces and project.surface_analysis_enabled:
        from .spatial_surfaces import surface_geometry
        from .surface_supports import resolved_supports, PLANE_AXES
        for name, definition in project.surfaces.items():
            supports = resolved_supports(project, name)
            normal = PLANE_AXES[definition.plane][2]
            for index, point in enumerate(surface_geometry(definition)[2]):
                x, y, z = (np.asarray(point) - origin) / span
                rows = ((1, 0, 0, 0, z, -y), (0, 1, 0, -z, 0, x), (0, 0, 1, y, -x, 0),
                        (0, 0, 0, 1, 0, 0), (0, 0, 0, 0, 1, 0), (0, 0, 0, 0, 0, 1))
                for offset, (dof, row) in enumerate(zip(DOFS, rows)):
                    # Shell-normal drilling stiffness must not stabilize a rigid
                    # rotation. Tangential rotations are physical bending DOFs.
                    if offset == normal + 3:
                        continue
                    if dof in supports.get(index, ()):
                        constraints.append(row)
                    else:
                        motions.append(row)
                        labels.append(f"{name} node {index+1} {dof}")
    _, singular, modes = np.linalg.svd(np.array(constraints).reshape(-1, 6), full_matrices=True)
    rank = int(np.count_nonzero(singular > 1e-10))
    if rank < 6:
        participation = np.linalg.norm(np.array(motions).reshape(-1, 6) @ modes[rank:].T, axis=1)
        if not np.any(participation > 1e-7):
            return None
        return "Insufficient supports: the spatial structure can move as a rigid body.\nAffected global degrees of freedom: " + affected_dofs(labels, participation) + "."
    return None


def analyze_spatial(project, progress=None):
    from .analysis import AnalysisResult, FrameSolver, model_signature, stiffness_issue, solve_model
    phase = progress or (lambda message: None)
    phase("Checking 3D model and supports")
    project.validate()
    from .analysis_method import analysis_method_issue
    issue = analysis_method_issue(project)
    if issue:
        raise ValueError(issue)
    from .spatial_surfaces import surface_analysis_issue
    issue = surface_analysis_issue(project)
    if issue:
        raise ValueError(issue)
    if not project.members:
        raise ValueError("Draw at least one 3D frame member.")
    issues = project.analysis_topology_issues() + project.analysis_release_issues()
    if issues:
        raise ValueError("\n\n".join(issues))
    issue = rigid_body_issue(project)
    if issue:
        raise ValueError(issue)
    phase("Building spatial solver model")
    model = FrameSolver()
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
    if project.surfaces:
        from .surface_solver import attach_surfaces
        phase("Connecting rectangular shells and physical frame members")
        maps = attach_surfaces(project, model)
        shell_nodes = {name for mesh in maps.values() for name in mesh["nodes"]}
        inactive = {entry for entry in inactive if entry[0] not in shell_nodes}
        for node in project.nodes.values():
            model.def_support(node.name, **{"support_" + dof: fixed or (node.name, dof) in inactive
                                           for dof, fixed in zip(DOFS, node.restraints)})
        # The inactive-rotation update above preserves explicit node restraints;
        # reapply shared edge restraints so it cannot overwrite their union.
        from .surface_supports import apply_supports
        apply_supports(project, model, maps)
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
        solve_model(model, project, phase)
    except Exception as error:
        if project.analysis_method == "p_delta":
            raise
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
    result.analysis_method = project.analysis_method
    if project.surfaces:
        from .equilibrium import check_equilibrium
        phase("Verifying coupled force and moment equilibrium")
        for combination in project.combinations:
            check = check_equilibrium(project, result.for_combination(combination))
            failed = [row for row in check.rows if not row.passed]
            if failed:
                details = "; ".join(f"{row.component}: residual {row.residual:.6g} (limit {row.tolerance:.6g})" for row in failed)
                raise ValueError(f"Coupled surface equilibrium failed for {combination}: {details}. Canonical kip/in units. "
                                 "PyNite's weak drilling-rotation approximation can cause moment imbalance under lateral/membrane loading. "
                                 "No coupled results were accepted; review the loading, mesh and element formulation.")
    return result
