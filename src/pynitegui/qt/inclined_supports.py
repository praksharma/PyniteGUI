"""Exact, sparse affine support constraints for planar and spatial frames.

Only the node-local free coordinate basis changes. Member stiffness and fixed-
end vectors remain those of PyNite. Store global physical displacements for its
ordinary member recovery; recover rigid and spring reactions independently.
"""
import math

import numpy as np
from Pynite import Analysis, FEModel3D
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import eigsh, ArpackNoConvergence, splu


def directions(angle):
    a = math.radians(angle)
    tangent = np.array((math.cos(a), math.sin(a)))
    tangent[abs(tangent) < 1e-14] = 0.
    return tangent, np.array((-tangent[1], tangent[0]))


def has_inclined(project):
    return any(node.support == "inclined" for node in project.nodes.values())


def free_basis(model, project):
    rows, columns, values, labels, translations = [], [], [], [], []
    def add(name, offsets, vector, label, translation):
        column = len(labels)
        for offset, value in zip(offsets, vector):
            if value:
                rows.append(model.nodes[name].ID*6+offset)
                columns.append(column)
                values.append(float(value))
        labels.append(f"{name} {label}")
        translations.append(translation)
    from .support_axes import support_normal, translation_spaces
    spatial = getattr(project, "dimension", "2D") == "3D"
    offsets = (0, 1, 2) if spatial else (0, 1)
    for name, node in model.nodes.items():
        definition = project.nodes.get(name)
        normal = support_normal(definition) if definition is not None and definition.support == "inclined" else None
        fixed = [getattr(node, "support_D"+"XYZ"[index]) for index in offsets]
        free, _ = translation_spaces(fixed, normal)
        if definition is not None:
            for index, stiffness in enumerate(definition.springs[:len(offsets)]):
                if stiffness and np.linalg.norm(free[index]) < 1e-12:
                    raise ValueError(f"Node {name}: a global spring conflicts with the combined rigid support constraints.")
        for index, vector in enumerate(free.T):
            add(name, offsets, vector, "free translation "+str(index+1), True)
        for offset in ((3, 4, 5) if spatial else (5,)):
            dof = "R"+"XYZ"[offset-3]
            if not getattr(node, "support_"+dof):
                add(name, (offset,), (1.,), dof, False)
    return coo_matrix((values, (rows, columns)), shape=(6*len(model.nodes), len(labels))).tocsr(), labels, translations


def factor_stiffness(K, basis, labels, translations, length):
    if not np.isfinite(K.data).all():
        raise ValueError("Support-constraint stiffness contains nonfinite values.")
    S = np.array([length if translation else 1. for translation in translations])
    transform = basis @ diags(S)
    reduced = (transform.T @ K @ transform).tocsr()
    if not len(labels):
        return transform, None, np.empty(0)
    diagonal = reduced.diagonal()
    if np.any(diagonal <= 0):
        affected = ", ".join(label for label, bad in zip(labels, diagonal <= 0) if bad)
        raise ValueError("Unstable support-constrained model: no free stiffness at "+affected+".")
    scale = 1/np.sqrt(diagonal)
    normalized = (diags(scale) @ ((reduced+reduced.T)*.5) @ diags(scale)).tocsr()
    # Preserve the pre-cancellation error bound: reduced-diagonal scaling alone
    # can make a nearly rigid physical motion appear numerically well resolved.
    error = diags(scale) @ (abs(transform).T @ abs(K) @ abs(transform)) @ diags(scale)
    bound = max(1., float(np.asarray(abs(normalized).sum(axis=1)).max()))
    limit = max(10*np.finfo(float).eps*K.shape[0]*float(np.asarray(error.sum(axis=1)).max()),
                10*np.finfo(float).eps*len(labels)*bound)
    if len(labels) <= 600:
        values, vectors = np.linalg.eigh(normalized.toarray())
        value, mode = values[0], vectors[:, 0]
    else:
        try:
            values, vectors = eigsh(normalized, k=1, which="SA",
                tol=1e-9, maxiter=max(1000, 5*len(labels)), v0=np.random.default_rng(0).normal(size=len(labels)))
        except ArpackNoConvergence as error:
            raise ValueError("Support-constraint stability check did not converge; no results were accepted.") from error
        value, mode = values[0], vectors[:, 0]
    if value <= limit:
        affected = ", ".join(label for label, size in zip(labels, abs(mode)) if size > abs(mode).max()*1e-7)
        raise ValueError("Unstable or ill-conditioned support-constrained model. Affected free coordinates: "+affected+".")
    return transform, splu(normalized.tocsc()), scale


def store_displacements(model, combination, displacement):
    model._D[combination] = displacement
    for node in model.nodes.values():
        for index, key in enumerate(("DX", "DY", "DZ", "RX", "RY", "RZ")):
            getattr(node, key)[combination] = float(displacement[6*node.ID+index, 0])


def solve_inclined(model, project, phase):
    from .equilibrium import check_equilibrium
    from .analysis import AnalysisResult, model_signature
    spatial = getattr(project, "dimension", "2D") == "3D"
    second_order = project.analysis_method == "p_delta"
    constraint_kind = "inclined/prescribed" if has_inclined(project) else "prescribed"
    Analysis._prepare_model(model)
    basis, labels, translations = free_basis(model, project)
    from .support_movements import movement_lift, movement_fields
    lift = np.zeros((6*len(model.nodes), 1))
    offsets = np.arange(6) if spatial else np.array((0, 1, 5))
    dofs = ("DX", "DY", "DZ", "RX", "RY", "RZ") if spatial else ("DX", "DY", "RZ")
    for name, definition in project.nodes.items():
        node = model.nodes[name]
        fixed = [getattr(node, "support_"+dof) for dof in dofs]
        lift[6*node.ID+offsets, 0] = movement_lift(definition, fixed)
    model._pynitegui_support_movements = {name: {key: getattr(node, key) for key in movement_fields(node) if getattr(node, key)}
        for name, node in project.nodes.items() if any(getattr(node, key) for key in movement_fields(node))}
    coordinates = np.array([(n.X, n.Y, n.Z) for n in model.nodes.values()])
    length = max(1., float(np.linalg.norm(np.ptp(coordinates, axis=0))))
    model._pynitegui_support_reactions = {}
    signature = model_signature(project)
    for combination in model.load_combos:
        method = "P-Delta" if second_order else "Linear elastic"
        phase(f"{method} | {combination}: checking {constraint_kind} support constraints")
        elastic = model.Ke(combination, check_stability=False, sparse=True).tocsr()
        physical = FEModel3D.Ke(model, combination, check_stability=False, sparse=True).tocsr()
        force, fixed_end = model.P(combination), model.FER(combination)
        stiffness, actual = elastic, physical
        for step in range(31 if second_order else 1):
            if second_order and step:
                phase(f"P-Delta | {combination}: solving second-order response ({constraint_kind} supports, update {step}/30)")
            transform, factor, scale = factor_stiffness(stiffness, basis, labels, translations, length)
            # Every geometric update also acts on the prescribed physical motion.
            # Keeping only elastic @ lift would lose settlement-induced P-Delta
            # forces, even in a combination with no applied loads.
            rhs = np.asarray(transform.T @ (force-fixed_end-stiffness @ lift)).ravel()
            q = scale*factor.solve(scale*rhs) if factor is not None else np.empty(0)
            displacement = lift+np.asarray(transform @ q).reshape(-1, 1)
            if not np.isfinite(displacement).all():
                raise ValueError(f"Nonfinite support-constraint displacement in {combination}.")
            store_displacements(model, combination, displacement)
            if second_order:
                # PyNite first preloads elastically, then adds geometric stiffness.
                # An oblique reaction can change axial strain on the second solve;
                # repeat Kg until its physical equations close, rather than accept
                # a two-step state with unbalanced free joint forces.
                geometric = FEModel3D.Kg(model, combination, sparse=True, first_step=False).tocsr()
                actual = physical+geometric
                stiffness = elastic+geometric
                if step == 0:
                    continue
            try:
                records = recover_reactions(model, project, combination, actual, force, fixed_end, displacement)
                if second_order:
                    residual = np.asarray(basis.T @ (actual @ displacement+fixed_end-force)).ravel()
                    bound = np.asarray(abs(basis).T @ (abs(actual) @ abs(displacement)+abs(fixed_end)+abs(force))).ravel()
                    limit = np.array([1e-11 if translation else 1e-9 for translation in translations])+1e-10*bound
                    if np.any(abs(residual) > limit):
                        raise FreeEquilibriumError(f"P-Delta support-constraint equilibrium did not converge in {combination} after {step} updates.")
                    factor_stiffness(stiffness, basis, labels, translations, length)
                break
            except FreeEquilibriumError:
                if not second_order or step == 30:
                    raise
        model._pynitegui_support_reactions[combination] = records
        model.solution = "P-Delta" if second_order else "Linear"
        result = AnalysisResult.from_solver(model, combination, spatial=spatial)
        result.model_signature = signature
        result.analysis_method = project.analysis_method
        if not check_equilibrium(project, result).passed:
            raise ValueError(f"Support-constraint global equilibrium failed in {combination}; no results were accepted.")
    model.solution = "P-Delta" if second_order else "Linear"


class FreeEquilibriumError(ValueError):
    """The physical free equations have not converged."""


def recover_reactions(model, project, combination, matrix, force, fixed_end, displacement):
    from .equilibrium import FORCE_TOLERANCE, MOMENT_TOLERANCE, RELATIVE_TOLERANCE
    from .support_axes import support_normal, translation_spaces
    spatial = getattr(project, "dimension", "2D") == "3D"
    offsets = np.arange(6) if spatial else np.array((0, 1, 5))
    count = 3 if spatial else 2
    raw = np.asarray(matrix @ displacement+fixed_end-force).ravel()
    magnitude = np.asarray(abs(matrix) @ abs(displacement)+abs(fixed_end)+abs(force)).ravel()
    if not np.isfinite(raw).all() or not np.isfinite(magnitude).all():
        raise ValueError(f"Nonfinite support-constraint reactions in {combination}.")
    inactive = project.inactive_rotations()
    records = {}
    for name, node in model.nodes.items():
        definition = project.nodes.get(name)
        positions = 6*node.ID+offsets
        d, reaction = displacement[positions, 0], raw[positions]
        fixed = np.array([getattr(node, "support_"+key) for key in
                          (("DX", "DY", "DZ", "RX", "RY", "RZ") if spatial else ("DX", "DY", "RZ"))])
        # Canonical inactive rotations are numerical gauges, never supports.
        if definition is not None:
            for index, dof in enumerate(("DX", "DY", "DZ", "RX", "RY", "RZ") if spatial else ("DX", "DY", "RZ")):
                unused = (name, dof) in inactive if spatial else dof == "RZ" and name in inactive
                if unused and not definition.restraints[index]:
                    fixed[index] = False
        normal = support_normal(definition) if definition is not None and definition.support == "inclined" else None
        _, constrained = translation_spaces(fixed[:count], normal)
        rigid = np.where(fixed, reaction, 0.)
        rigid[:count] = constrained @ (constrained.T @ reaction[:count])
        tolerance = np.array([FORCE_TOLERANCE]*count+[MOMENT_TOLERANCE]*(len(offsets)-count))+RELATIVE_TOLERANCE*magnitude[positions]
        if np.any(abs(reaction-rigid) > tolerance):
            raise FreeEquilibriumError(f"Support-constraint free physical equilibrium failed at {name} in {combination}; no results were accepted.")
        if normal is not None and abs(float(normal @ d[:count])-definition.settlement_normal) > 1e-10*max(1., float(abs(d[:count]).max())):
            raise ValueError(f"Inclined constraint displacement failed at {name} in {combination}.")
        spring_dofs = ('DX','DY','DZ','RX','RY','RZ') if spatial else ('DX','DY','RZ')
        springs = np.array([float(getattr(node,'spring_'+dof)[0] or 0.) if getattr(node,'spring_'+dof)[2] else 0.
                            for dof in spring_dofs])
        spring = -springs*d
        external = np.zeros(6)
        external[offsets] = rigid+spring
        for key, value in zip(("RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ"), external):
            getattr(node, key)[combination] = float(value)
        if normal is not None:
            # Additional global restraints own any redundant normal direction.
            # Otherwise the remaining normal component uniquely determines the
            # normal constraint force, separately from those global reactions.
            remaining = np.where(fixed[:count], 0., normal)
            denominator = float(remaining @ remaining)
            normal_force = float(remaining @ rigid[:count])/denominator if denominator > 1e-20 else 0.
            records[name] = dict(normal=normal.tolist(), rigid_reaction=rigid.tolist(),
                spring_reaction=spring.tolist(), normal_reaction_kip=normal_force,
                **(dict(normal_azimuth_deg=definition.support_angle, normal_elevation_deg=definition.support_elevation)
                   if spatial else dict(tangent_angle_deg=definition.support_angle)))
    return records
