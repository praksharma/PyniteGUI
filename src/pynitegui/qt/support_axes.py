"""Physical support directions, shared by definitions, solvers and views."""
import math

import numpy as np


def support_normal(node):
    """Planar tangent CCW from +X; spatial normal azimuth +X toward +Z."""
    angle = math.radians(node.support_angle)
    if hasattr(node, "z"):
        elevation = math.radians(node.support_elevation)
        vector = np.array((math.cos(elevation)*math.cos(angle), math.sin(elevation),
                           math.cos(elevation)*math.sin(angle)))
    else:
        vector = np.array((-math.sin(angle), math.cos(angle)))
    vector[abs(vector) < 1e-14] = 0.
    return vector / np.linalg.norm(vector)


def translation_spaces(fixed, normal=None):
    """Orthonormal free and constrained columns, deduplicating exact restraints.

    Only translations enter this tiny SVD. Nearly dependent constraints are
    rejected rather than turning an imprecise orientation into a rigid clamp.
    """
    rows = [axis for axis, restrained in zip(np.eye(len(fixed)), fixed) if restrained]
    if normal is not None:
        rows.append(normal)
    _, values, vectors = np.linalg.svd(np.array(rows).reshape(-1, len(fixed)), full_matrices=True)
    zero = 50*np.finfo(float).eps*max(len(rows), len(fixed))
    if np.any((values > zero) & (values < 1e-8)):
        raise ValueError("Nearly dependent inclined support constraints; revise the normal or additional restraints.")
    rank = int(np.count_nonzero(values > zero))
    return vectors[rank:].T, vectors[:rank].T
