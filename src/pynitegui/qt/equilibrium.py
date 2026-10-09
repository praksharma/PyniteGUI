"""Independent global load resultants compared with the solved reactions."""
from dataclasses import dataclass
import math
import numpy as np

from .analysis import model_signature
from .annotations import combination_loads


RELATIVE_TOLERANCE = 1e-7
FORCE_TOLERANCE = 1e-8  # Canonical kip.
MOMENT_TOLERANCE = 1e-6  # Canonical kip-inch.


@dataclass(frozen=True)
class EquilibriumRow:
    component: str
    quantity: str
    applied: float
    reaction: float
    residual: float
    tolerance: float

    @property
    def passed(self):
        return abs(self.residual) <= self.tolerance


@dataclass(frozen=True)
class EquilibriumCheck:
    origin_node: str
    origin: tuple[float, float, float]
    rows: tuple[EquilibriumRow, ...]

    @property
    def passed(self):
        return all(row.passed for row in self.rows)


def check_equilibrium(project, result):
    if result.model_signature != model_signature(project):
        raise ValueError("The model does not match this analyzed snapshot.")
    spatial = getattr(project, "dimension", "2D") == "3D"

    def coordinates(node):
        return np.array(node.coords if spatial else (node.x, node.y, 0.), dtype=float)

    # Refer moments to a real node, keeping large global coordinate offsets
    # out of moment arms. The UI explicitly identifies this reference point.
    reference = next(iter(project.nodes.values()))
    origin = coordinates(reference)
    applied, reactions = [[] for _ in range(6)], [[] for _ in range(6)]
    axes = {}

    def add(target, force, moment):
        for values, value in zip(target, (*force, *moment)):
            if not math.isfinite(value):
                raise ValueError("Equilibrium requires finite loads and reactions.")
            values.append(float(value))

    def direction_vector(direction, member):
        index = "XYZ".index(direction[1].upper())
        if direction != direction.upper():
            if member not in axes:
                axes[member] = result.solver.members[member].T()[:3, :3]
            return axes[member][index]
        return np.eye(3)[index]

    for load in combination_loads(project, result):
        nodal = load.target in project.nodes
        if nodal:
            point = coordinates(project.nodes[load.target]) - origin
        else:
            member = project.members[load.target]
            start = coordinates(project.nodes[member.start]) - origin
            delta = coordinates(project.nodes[member.end]) - coordinates(project.nodes[member.start])
            length = float(np.linalg.norm(delta))
            point = start + delta * load.position
        ends = dict(load.components(project, load.end_magnitude))
        for direction, magnitude in load.components(project):
            vector = direction_vector(direction, None if nodal else load.target)
            if direction.upper().startswith("M"):
                add(applied, np.zeros(3), vector * magnitude)
            elif load.kind == "distributed":
                interval = length * (load.end_position - load.position)
                left, right = vector * magnitude, vector * ends[direction]
                force = (left + right) * interval / 2
                # Integrate s*w(s) directly: a sign-changing load can have
                # zero resultant force and a nonzero moment, with no centroid.
                first_moment = (left + 2 * right) * interval**2 / 6
                moment = np.cross(point, force) + np.cross(delta / length, first_moment)
                add(applied, force, moment)
            else:
                force = vector * magnitude
                add(applied, force, np.cross(point, force))

    for name, values in result.reactions.items():
        force = np.array(values[:3] if spatial else (values[0], values[1], 0.), dtype=float)
        couple = np.array(values[3:] if spatial else (0., 0., values[2]), dtype=float)
        add(reactions, force, couple + np.cross(coordinates(project.nodes[name]) - origin, force))

    rows = []
    for index in (range(6) if spatial else (0, 1, 5)):
        load_sum, reaction_sum = math.fsum(applied[index]), math.fsum(reactions[index])
        residual = math.fsum((load_sum, reaction_sum))
        scale = math.fsum(abs(value) for value in (*applied[index], *reactions[index]))
        quantity = "force" if index < 3 else "moment"
        absolute = FORCE_TOLERANCE if index < 3 else MOMENT_TOLERANCE
        tolerance = absolute + RELATIVE_TOLERANCE * scale
        if not all(math.isfinite(value) for value in (load_sum, reaction_sum, residual, tolerance)):
            raise ValueError("Equilibrium totals exceed the finite numerical range.")
        rows.append(EquilibriumRow(("FX", "FY", "FZ", "MX", "MY", "MZ")[index], quantity,
                                   load_sum, reaction_sum, residual, tolerance))
    return EquilibriumCheck(reference.name, tuple(float(value) for value in origin), tuple(rows))
