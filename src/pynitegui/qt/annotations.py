"""Shared engineering context and screen-sized support geometry."""
from dataclasses import replace
import math


def combination_loads(project, result):
    factors = result.solver.load_combos[result.combination].factors
    return [replace(load, magnitude=load.magnitude * factors[load.case],
                    end_magnitude=load.end_magnitude * factors[load.case])
            for load in (*project.loads.values(), *project.self_weight_loads())
            if factors.get(load.case, 0) and (load.magnitude or (load.kind == "distributed" and load.end_magnitude))]


def load_label(project, load):
    units = project.units
    quantity = "intensity" if load.kind == "distributed" else "moment" if load.direction == "MZ" else "force"
    value = f"{units.to_display(load.magnitude, quantity):g}"
    if load.kind == "distributed":
        value += f" to {units.to_display(load.end_magnitude, quantity):g}"
    direction = load.direction
    if direction in ("Angle", "Local angle"):
        direction += f" {load.angle:g} deg"
    return f"{load.name}: {value} {getattr(units, quantity)} | {direction}"


def support_label(project, node):
    fixed = ", ".join(label for label, value in zip(("DX", "DY", "RZ"), node.restraints) if value)
    pieces = [f"{node.name}: {node.support}" + (f" ({fixed})" if fixed else "")]
    for label, k, quantity in zip(("DX", "DY", "RZ"), node.springs,
                                  ("stiffness", "stiffness", "rotational_stiffness")):
        if k:
            pieces.append(f"{label} spring {project.units.to_display(k, quantity):g} {getattr(project.units, quantity)}")
    return " | ".join(pieces)


def support_geometry(support, restraints):
    """Polylines/circles in pixels, with screen Y pointing down."""
    paths, circles = [], []
    if support == "custom":
        rx, ry, rz = restraints
        if rx:
            paths.append([(-9, -12), (-9, 12)])
            paths.extend([[(-9, y), (-14, y + 4)] for y in (-10, -4, 2, 8)])
        if ry:
            paths.append([(-12, 9), (12, 9)])
            paths.extend([[(x, 9), (x - 4, 14)] for x in (-10, -4, 2, 8)])
        if rz:
            paths.append([(-4, -4), (4, -4), (4, 4), (-4, 4), (-4, -4)])
    elif support != "free":
        ground = 4
        if support in ("pin", "roller"):
            paths.append([(0, 0), (-9, 15), (9, 15), (0, 0)])
            ground = 18
            if support == "roller":
                circles.extend([(-4.5, 19.5, 2.5), (4.5, 19.5, 2.5)])
                ground = 25
        paths.append([(-12, ground), (12, ground)])
        paths.extend([[(x, ground), (x - 4, ground + 5)] for x in (-10, -4, 2, 8)])
    return paths, circles


def spring_geometry(springs):
    paths = []
    for index, k in enumerate(springs[:2]):
        if not k:
            continue
        coil = [(0, 0), (0, 12), (-4, 15), (4, 19), (-4, 23), (4, 27), (0, 30), (0, 34)]
        ground = [[(-8, 34), (8, 34)], *[[(x, 34), (x - 3, 38)] for x in (-6, 0, 6)]]
        for path in (coil, *ground):
            paths.append([(-y, x) if index == 0 else (x, y) for x, y in path])
    if springs[2]:
        coil = [(0, 0), (14, -14)]
        coil.extend((22 + radius * math.cos(angle), -22 + radius * math.sin(angle))
                    for angle, radius in zip((math.pi + i * math.pi * 3 / 40 for i in range(41)),
                                             (8 - i * 0.1 for i in range(41))))
        paths.append(coil)
        paths.append([(22, -34), (22, -30), (22, -22)])
        paths.append([(14, -34), (30, -34)])
        paths.extend([[(x, -34), (x - 3, -38)] for x in (16, 22, 28)])
    return paths, []


def release_geometry(tangent, axial, shear):
    dx, dy = tangent
    normal = (-dy, dx)
    paths = []
    if axial:
        for distance in (16, 21):
            paths.append([(dx * distance + normal[0] * side, dy * distance + normal[1] * side) for side in (-5, 5)])
    if shear:
        paths.append([(dx * (28 + along) + normal[0] * across, dy * (28 + along) + normal[1] * across)
                      for along, across in ((-4, -4), (4, -4), (4, 4), (-4, 4), (-4, -4))])
    return paths, []


def moment_geometry(magnitude):
    sign = 1 if magnitude >= 0 else -1
    angles = [math.radians(30 + sign * i * 280 / 40) for i in range(41)]
    arc = [(14 * math.cos(angle), -14 * math.sin(angle)) for angle in angles]
    angle = angles[-1]
    dx, dy = -sign * math.sin(angle), -sign * math.cos(angle)
    x, y = arc[-1]
    return [arc, [(x - dx * 7 + dy * 3, y - dy * 7 - dx * 3), (x, y),
                  (x - dx * 7 - dy * 3, y - dy * 7 + dx * 3)]], []
