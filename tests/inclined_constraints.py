"""Dense, test-only feasibility solve for homogeneous planar constraints.

This is not an application solver or a coordinate gauge. Real rigid supports
restrict motion through C d=0; every remaining physical mode must have positive
stiffness, even for zero load. No penalties or extra restraints are introduced.
Production integration would need sparse node-local transformations, physical
recovery and all existing analysis gates; this prototype publishes no snapshots.
"""
import numpy as np


def solve(stiffness, force, constraints, length_scale=1.):
    K, f, C = (np.asarray(value, dtype=float) for value in (stiffness, force, constraints))
    if f.ndim != 1 or not len(f) or len(f) % 3 or K.shape != (len(f), len(f)) or C.ndim != 2 or C.shape[1] != len(f):
        raise ValueError("Expected planar K, force and constraint arrays.")
    if not all(np.isfinite(value).all() for value in (K, f, C)) or not np.isfinite(length_scale) or length_scale <= 0:
        raise ValueError("Inputs and positive length scale must be finite.")
    if not np.allclose(K, K.T, rtol=1e-12, atol=1e-12):
        raise ValueError("Stiffness must be symmetric.")
    # d=S x. Translational and rotational coordinates become comparable before
    # finding constraint rank or assessing the reduced stiffness spectrum.
    S = np.tile((length_scale, length_scale, 1.), len(f)//3)
    scaled_C = C*S
    norms = np.linalg.norm(scaled_C, axis=1)
    if np.any(norms == 0):
        raise ValueError("A constraint row cannot be zero.")
    scaled_C = scaled_C/norms[:, None]
    _, singular, vectors = np.linalg.svd(scaled_C, full_matrices=True)
    if len(C) > len(f) or np.count_nonzero(singular > 1e-8) != len(C):
        raise ValueError("Dependent or nearly dependent constraints.")
    Z = vectors[len(C):].T
    scaled_K = S[:, None]*K*S[None, :]
    reduced = Z.T @ scaled_K @ Z
    rhs = Z.T @ (S*f)
    if len(reduced):
        diagonal = np.diag(reduced)
        if np.any(diagonal <= 0):
            raise ValueError("Unstable: no positive stiffness on a free mode.")
        scale = 1/np.sqrt(diagonal)
        normalized = scale[:, None]*reduced*scale[None, :]
        eigenvalues = np.linalg.eigvalsh(normalized)
        # Projection can cancel large entries of the original matrix. Scaling
        # only the reduced diagonal would then amplify roundoff and can make a
        # nearly rigid mode appear well resolved. Bound both matrix products
        # before cancellation, then carry that bound through diagonal scaling.
        projected_bound = abs(Z).T @ abs(scaled_K) @ abs(Z)
        error = 10*np.finfo(float).eps*len(f)*scale[:, None]*projected_bound*scale[None, :]
        limit = max(float(error.sum(axis=1).max()),
                    10*np.finfo(float).eps*len(reduced)*max(1., abs(eigenvalues[-1])))
        if eigenvalues[0] <= limit:
            raise ValueError("Unstable or ill-conditioned physical mechanism.")
        q = scale*np.linalg.solve(normalized, scale*rhs)
        x = Z @ q
        minimum_eigenvalue = float(eigenvalues[0])
    else:
        x = np.zeros_like(f)
        minimum_eigenvalue = None
        limit = None
    d = S*x
    reaction = K @ d-f
    free_error = Z.T @ (S*reaction)
    free_scale = abs(Z.T) @ (S*(abs(K) @ abs(d)+abs(f)))
    constraint_error = scaled_C @ x
    if (not np.isfinite(d).all() or not np.isfinite(reaction).all()
            or np.any(abs(free_error) > 1e-10*np.maximum(free_scale, 1e-12))
            or np.any(abs(constraint_error) > 1e-10*max(1., np.linalg.norm(x)))):
        raise ValueError("Constraint or free-equation residual failed.")
    # These are algebraic identities for the equivalent nodal system. With
    # member loads, total physical strain energy additionally includes the
    # member's fixed-end deformation; this is not an energy-recovery benchmark.
    return dict(displacement=d, rigid_reaction=reaction,
        quadratic_energy=float(d @ K @ d/2), equivalent_nodal_work=float(f @ d),
        minimum_scaled_eigenvalue=minimum_eigenvalue,
        stability_roundoff_bound=limit,
        max_constraint_residual=float(abs(constraint_error).max(initial=0.)),
        max_free_residual=float(abs(free_error).max(initial=0.)))
