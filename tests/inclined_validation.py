"""Assemble real planar frame stiffness/load vectors for test-only feasibility.

The supported production adapter prepares the physical member matrices on an
all-clamped copy. Its displacements are not used; the original project and its
result state remain untouched. Inclined solutions never become AnalysisResults.
"""
import contextlib
import io

import numpy as np

from inclined_reference import normal, rotation
from pynitegui.qt.analysis import analyze
from pynitegui.qt.model import Project, Material, Section, Load


def beam(fractions=(0., 1.), angle=0., origin=(17., -31.), nodal=(3., -2., 7.), distributed=(.002, -.005)):
    p = Project(combinations={"Service": {"Case 1": 1.}, "Reverse": {"Case 1": -1.7}, "Zero": {"Case 1": 0.}})
    p.materials = {"Test": Material("Test", E=30000., nu=.25, rho=0.)}
    p.sections = {"Test": Section("Test", A=8., Iy=20., Iz=80., J=5.)}
    p.default_material = p.default_section = "Test"
    Q = rotation(angle)
    points = [tuple(np.asarray(origin)+(Q @ (120.*x, 0., 0.))[:2]) for x in fractions]
    for a, b in zip(points, points[1:]):
        p.add_member(a, b)
    tip = next(reversed(p.nodes))
    for dof, magnitude in zip(("FX", "FY", "MZ"), Q @ nodal):
        if magnitude:
            name = f"Tip_{dof}"
            p.loads[name] = Load(name, tip, dof, float(magnitude))
    for member in p.members:
        for dof, magnitude in zip(("FX", "FY"), (Q @ (*distributed, 0.))[:2]):
            if magnitude:
                name = f"{member}_{dof}"
                p.loads[name] = Load(name, member, dof, float(magnitude), 0., "distributed", float(magnitude))
    p.validate()
    return p


def assemble(project):
    if getattr(project, 'dimension', None) == '3D':
        raise ValueError("Feasibility fixture accepts unreleased planar linear frames only.")
    candidate = Project.from_dict(project.to_dict())
    if candidate.analysis_method != "linear" or any(member.kind != "frame" or any(any(end) for end in member.end_releases)
            for member in candidate.members.values()):
        raise ValueError("Feasibility fixture accepts unreleased planar linear frames only.")
    for node in candidate.nodes.values():
        node.support = "fixed"
        node.spring_x = node.spring_y = node.spring_rz = 0.
    with contextlib.redirect_stdout(io.StringIO()):
        prepared = analyze(candidate).solver
    names = list(prepared.nodes)
    indices = [6*prepared.nodes[name].ID+offset for name in names for offset in (0, 1, 5)]
    matrices, forces = {}, {}
    for combination in project.combinations:
        K = prepared.Ke(combination, check_stability=False, sparse=True).tocsr()
        springs = [value for name in names for value in project.nodes[name].springs]
        matrices[combination] = K[indices, :][:, indices].toarray()+np.diag(springs)
        forces[combination] = (prepared.P(combination)-prepared.FER(combination))[indices, 0]
    return names, matrices, forces


def constraints(names, fixed=(), pinned=(), rollers=()):
    rows = []
    for name, vector in [(name, axis) for name in fixed for axis in np.eye(3)] + [
            (name, axis) for name in pinned for axis in np.eye(3)[:2]] + [
            (name, normal(angle)) for name, angle in rollers]:
        row = np.zeros(3*len(names))
        start = 3*names.index(name)
        row[start:start+3] = vector
        rows.append(row)
    return np.asarray(rows).reshape(-1, 3*len(names))


def balance(project, names, reactions, combination):
    """Independent global force/moment sum, using actual applied physical loads."""
    total = np.zeros(3)
    origin = np.array((project.nodes[names[0]].x, project.nodes[names[0]].y))
    def add(xy, force):
        x, y = np.asarray(xy)-origin
        total[:] += (force[0], force[1], force[2]+x*force[1]-y*force[0])
    for name, reaction in zip(names, np.asarray(reactions).reshape(-1, 3)):
        add((project.nodes[name].x, project.nodes[name].y), reaction)
    factors = project.combinations[combination]
    for load in project.loads.values():
        force = np.zeros(3)
        for dof, value in load.components(project):
            force[("FX", "FY", "MZ").index(dof)] += value*factors[load.case]
        if load.target in project.nodes:
            node = project.nodes[load.target]
            xy = (node.x, node.y)
        else:
            member = project.members[load.target]
            a, b = (np.array((project.nodes[name].x, project.nodes[name].y)) for name in (member.start, member.end))
            # This diagnostic fixture only generates uniform full-span loads.
            if load.kind != "distributed" or load.position != 0. or load.end_position != 1. or load.end_magnitude != load.magnitude:
                raise ValueError("Balance fixture requires uniform full-span member loading.")
            xy = (a+b)/2
            force *= np.linalg.norm(b-a)
        add(xy, force)
    return total
