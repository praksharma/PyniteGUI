"""Exact, sparse homogeneous support constraints for planar linear frames.

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
    for name, node in project.nodes.items():
        if node.support == "inclined":
            tangent, _ = directions(node.support_angle)
            add(name, (0, 1), tangent, "roller tangent", True)
            add(name, (5,), (1.,), "RZ", False)
        else:
            for offset, fixed, label in zip((0, 1, 5), node.restraints, ("DX", "DY", "RZ")):
                if not fixed:
                    add(name, (offset,), (1.,), label, offset != 5)
    return coo_matrix((values, (rows, columns)), shape=(6*len(model.nodes), len(labels))).tocsr(), labels, translations


def factor_stiffness(K, basis, labels, translations, length):
    if not np.isfinite(K.data).all():
        raise ValueError("Inclined-support stiffness contains nonfinite values.")
    S = np.array([length if translation else 1. for translation in translations])
    transform = basis @ diags(S)
    reduced = (transform.T @ K @ transform).tocsr()
    if not len(labels):
        return transform, None, np.empty(0)
    diagonal = reduced.diagonal()
    if np.any(diagonal <= 0):
        affected = ", ".join(label for label, bad in zip(labels, diagonal <= 0) if bad)
        raise ValueError("Unstable inclined-support model: no free stiffness at "+affected+".")
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
            raise ValueError("Inclined-support stability check did not converge; no results were accepted.") from error
        value, mode = values[0], vectors[:, 0]
    if value <= limit:
        affected = ", ".join(label for label, size in zip(labels, abs(mode)) if size > abs(mode).max()*1e-7)
        raise ValueError("Unstable or ill-conditioned inclined-support model. Affected free coordinates: "+affected+".")
    return transform, splu(normalized.tocsc()), scale


def solve_inclined(model, project, phase):
    from .equilibrium import FORCE_TOLERANCE, MOMENT_TOLERANCE, RELATIVE_TOLERANCE, check_equilibrium
    from .analysis import AnalysisResult, model_signature
    Analysis._prepare_model(model)
    basis, labels, translations = free_basis(model, project)
    first = next(iter(model.load_combos))
    K = FEModel3D.Ke(model, first, check_stability=False, sparse=True).tocsr()
    x, y = [node.x for node in project.nodes.values()], [node.y for node in project.nodes.values()]
    length = max(1., math.hypot(max(x)-min(x), max(y)-min(y)))
    phase("Checking inclined-support constrained stiffness")
    transform, factor, scale = factor_stiffness(K, basis, labels, translations, length)
    model._pynitegui_support_reactions = {}
    signature = model_signature(project)
    for combination in model.load_combos:
        phase(f"Linear elastic | {combination}: solving inclined supports")
        force, fixed_end = model.P(combination), model.FER(combination)
        rhs = np.asarray(transform.T @ (force-fixed_end)).ravel()
        q = scale*factor.solve(scale*rhs) if factor is not None else np.empty(0)
        displacement = np.asarray(transform @ q).reshape(-1, 1)
        raw = np.asarray(K @ displacement+fixed_end-force).ravel()
        magnitude = np.asarray(abs(K) @ abs(displacement)+abs(fixed_end)+abs(force)).ravel()
        if not np.isfinite(displacement).all() or not np.isfinite(raw).all():
            raise ValueError(f"Nonfinite inclined-support results in {combination}; no results were accepted.")
        model._D[combination] = displacement
        records = {}
        for name, definition in project.nodes.items():
            node = model.nodes[name]
            start = 6*node.ID
            d = displacement[start:start+6, 0]
            for index, key in enumerate(("DX", "DY", "DZ", "RX", "RY", "RZ")):
                getattr(node, key)[combination] = float(d[index])
            positions = np.array((start, start+1, start+5))
            reaction = raw[positions]
            tolerance = np.array((FORCE_TOLERANCE, FORCE_TOLERANCE, MOMENT_TOLERANCE))+RELATIVE_TOLERANCE*magnitude[positions]
            rigid = np.zeros(3)
            if definition.support == "inclined":
                tangent, normal = directions(definition.support_angle)
                rigid[:2] = normal*float(normal @ reaction[:2])
                if abs(float(normal @ d[:2])) > 1e-10*max(1., float(abs(d[:2]).max())):
                    raise ValueError(f"Inclined constraint displacement failed at {name} in {combination}.")
            else:
                rigid = np.where(definition.restraints, reaction, 0.)
            if np.any(abs(reaction-rigid) > tolerance):
                raise ValueError(f"Inclined-support free physical equilibrium failed at {name} in {combination}.")
            spring = -np.array(definition.springs)*d[[0, 1, 5]]
            external = rigid+spring
            for key, value in zip(("RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ"),
                                  (external[0], external[1], 0., 0., 0., external[2])):
                getattr(node, key)[combination] = float(value)
            if definition.support == "inclined":
                records[name] = dict(tangent_angle_deg=definition.support_angle, normal=normal.tolist(),
                    rigid_reaction=rigid.tolist(), spring_reaction=spring.tolist(),
                    normal_reaction_kip=float(normal @ rigid[:2]))
        model._pynitegui_support_reactions[combination] = records
        result = AnalysisResult.from_solver(model, combination)
        result.model_signature = signature
        if not check_equilibrium(project, result).passed:
            raise ValueError(f"Inclined-support global equilibrium failed in {combination}; no results were accepted.")
    model.solution = "Linear"
