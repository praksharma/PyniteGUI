"""Spatial end releases and exact gauges of unused joint rotations.

A joint's unused rotation need not be a global axis. G spans only rotational
directions that none of the incident member ends, supports or springs use.
Verify K G=0 and G.T(P-FER)=0, then solve with K+G S G.T. This imposes G.T D=0
as a numerical coordinate gauge, with zero physical energy/reaction. It is
equivalent to eliminating those unused coordinates, not grounding a mechanism.
Translations and connected rotational mechanisms are never included in G.
Translational end releases use ordinary condensation/recovery; disconnected
joint translations are rejected by the physical stiffness check, never gauged.
"""
import numpy as np
from scipy.sparse import coo_matrix, diags

from .analysis import FrameSolver, stiffness_issue
from Pynite import FEModel3D
from .released_member import ReleasedMember


ROTATION_FIELDS = ("release_start_rx", "release_start_ry", "release_start",
                   "release_end_rx", "release_end_ry", "release_end")
TRANSLATION_FIELDS = tuple(f"release_{end}_{axis}" for end in ("start", "end") for axis in ("x", "y", "z"))
RELEASE_FIELDS = tuple(key for end in ("start", "end") for key in
                      (*(f"release_{end}_{axis}" for axis in ("x", "y", "z", "rx", "ry")), f"release_{end}"))


def release_axis(key):
    suffix = key.rsplit("_", 1)[-1]
    return "D"+suffix.upper() if suffix in ("x", "y", "z") else suffix.upper() if suffix in ("rx", "ry") else "RZ"


def has_releases(project):
    return any(member.kind == "frame" and any(getattr(member, key) for key in RELEASE_FIELDS)
               for member in project.members.values())


def has_rotational_releases(project):
    return any(member.kind == "frame" and any(getattr(member, key) for key in ROTATION_FIELDS)
               for member in project.members.values())


def unused_rotation_axes(project, model=None):
    """Global orthonormal columns for each node's physically unused rotations."""
    from .spatial_results import member_axes
    directions = {name: [] for name in project.nodes}
    for name, member in project.members.items():
        if member.kind != "frame":
            continue
        axes = model.members[name].T()[:3, :3] if model is not None else member_axes(project, name)
        first, last = member.rotation_releases
        for node, flags in ((member.start, first), (member.end, last)):
            for index, released in enumerate(flags):
                if not released and (index != 0 or not (first[0] or last[0])):
                    directions[node].append(axes[index])
    result = {}
    for name, node in project.nodes.items():
        rows = [*directions[name], *(np.eye(3)[index] for index, (fixed, spring) in
                 enumerate(zip(node.restraints[3:], node.springs[3:])) if fixed or spring)]
        _, values, vectors = np.linalg.svd(np.array(rows).reshape(-1, 3), full_matrices=True)
        zero = 50*np.finfo(float).eps*max(3, len(rows))*max(1., values[0] if len(values) else 0.)
        if np.any((values > zero) & (values < 1e-8)):
            raise ValueError(f"Joint {name}: nearly dependent released rotation axes. Revise the connection geometry; no results were accepted.")
        rank = int(np.count_nonzero(values > zero))
        if rank < 3:
            result[name] = vectors[rank:].T
    return result


def inactive_components(axes):
    return {(name, "R"+"XYZ"[index]) for name, basis in axes.items()
            for index in range(3) if np.linalg.norm(basis[index]) > 1e-10}


class ReleasedSpatialSolver(FrameSolver):
    """Use the engine's linear solver with unused-rotation coordinate gauges."""
    rotation_nullspaces = None

    def gauge_matrix(self):
        rows, columns, values = [], [], []
        column = 0
        for name, basis in self.rotation_nullspaces.items():
            for vector in basis.T:
                for index, value in enumerate(vector):
                    rows.append(6*self.nodes[name].ID+3+index)
                    columns.append(column)
                    values.append(float(value))
                column += 1
        return coo_matrix((values, (rows, columns)), shape=(6*len(self.nodes), column)).tocsr()

    def Ke(self, combo_name="Combo 1", log=False, check_stability=True, sparse=True):
        # The engine's zero-diagonal check must run after gauge elimination,
        # otherwise even an unused canonical rotation is called a mechanism.
        matrix = super().Ke(combo_name, log, check_stability=False, sparse=True).tocsr()
        basis = self.gauge_matrix()
        if basis.shape[1]:
            residual = np.asarray(abs(matrix @ basis).sum(axis=0)).ravel()
            bound = np.asarray((abs(matrix) @ abs(basis)).sum(axis=0)).ravel()
            if np.any(residual > 1e-10*np.maximum(bound, 1e-20)):
                raise ValueError("Spatial release rotation is not an unused coordinate: K G is nonzero. No result was accepted.")
            diagonal = abs(matrix.diagonal())
            rotational = diagonal.reshape(-1, 6)[:, 3:]
            positive = rotational[rotational > 0]
            fallback = float(np.median(positive)) if len(positive) else 1.
            scales = []
            for name, local in self.rotation_nullspaces.items():
                scales.extend([max(float(rotational[self.nodes[name].ID].max()), fallback)]*local.shape[1])
            matrix = matrix + basis @ diags(scales) @ basis.T
        if check_stability:
            issue = stiffness_issue(self, spatial=True, stiffness=matrix)
            if issue:
                raise ValueError("Spatial structure is unstable. "+issue)
        return matrix.tocoo() if sparse else matrix.toarray()

    def P(self, combo_name="Combo 1"):
        force = super().P(combo_name)
        basis = self.gauge_matrix()
        if basis.shape[1]:
            fixed_end = super().FER(combo_name)
            residual = np.asarray(basis.T @ (force-fixed_end)).ravel()
            scale = np.asarray(abs(basis).T @ (abs(force)+abs(fixed_end))).ravel()
            if np.any(abs(residual) > 1e-10*np.maximum(scale, 1e-20)):
                raise ValueError(f"Unresisted moment on an unused joint rotation in {combo_name}. No result was accepted.")
        return force


def recover_spatial_releases(model):
    # Check every free physical equation against the unaugmented engine matrix.
    # A global equilibrium sum alone could miss equal/opposite spurious torques.
    from .equilibrium import FORCE_TOLERANCE, MOMENT_TOLERANCE, RELATIVE_TOLERANCE
    for combination in model.load_combos:
        matrix = FEModel3D.Ke(model, combination, check_stability=False, sparse=True).tocsr()
        force, fixed_end, displacement = FEModel3D.P(model, combination), model.FER(combination), model.D(combination)
        residual = np.asarray(matrix @ displacement+fixed_end-force).ravel()
        scale = np.asarray(abs(matrix) @ abs(displacement)+abs(fixed_end)+abs(force)).ravel()
        if not np.isfinite(residual).all() or not np.isfinite(scale).all():
            raise ValueError("Released frame physical equilibrium returned nonfinite values. No results were accepted.")
        for node in model.nodes.values():
            inclined = getattr(model, "_pynitegui_support_reactions", {}).get(combination, {}).get(node.name)
            if inclined:
                residual[node.ID*6:node.ID*6+6] -= inclined["rigid_reaction"]
            for index, dof in enumerate(("DX", "DY", "DZ", "RX", "RY", "RZ")):
                position = node.ID*6+index
                tolerance = (FORCE_TOLERANCE if index < 3 else MOMENT_TOLERANCE)+RELATIVE_TOLERANCE*scale[position]
                if not getattr(node, "support_"+dof) and abs(residual[position]) > tolerance:
                    raise ValueError(f"Released frame physical equilibrium failed at {node.name} {dof} in {combination}. No results were accepted.")
    for physical in model.members.values():
        if getattr(physical, "_pynitegui_truss", False):
            continue
        for name, sub in list(physical.sub_members.items()):
            if any(sub.Releases):
                recovered = ReleasedMember.from_member(sub)
                for combination in model.load_combos:
                    recovered.d(combination)
                physical.sub_members[name] = recovered
        physical._solved_combo = None
