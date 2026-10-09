"""Snapshot-based orthographic spatial diagrams, independent of WebGL."""
import io
import math

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.collections import PolyCollection

from .annotations import combination_loads
from .diagram_labels import add_diagram_label, reserve_annotation
from .spatial_model import DOFS
from .spatial_results import DIAGRAM_AXES, LABELS, QUANTITIES, UNITS, member_axes, sampled_member
from .theme import LIGHT


VIEWS = {"isometric": "Isometric", "front": "Front XY", "top": "Top XZ", "right": "Right YZ"}
TITLES = {"axial": "Axial-Force Diagram", "shear_y": "Shear Vy Diagram", "shear_z": "Shear Vz Diagram",
          "torque": "Torsion Diagram", "moment_y": "Bending My Diagram", "moment_z": "Bending Mz Diagram"}


def projection(view):
    if view == "isometric":
        return np.array(((1 / math.sqrt(2), 0, -1 / math.sqrt(2)),
                         (-1 / math.sqrt(6), 2 / math.sqrt(6), -1 / math.sqrt(6))))
    if view == "front":
        return np.array(((1, 0, 0), (0, 1, 0)))
    if view == "top":
        return np.array(((1, 0, 0), (0, 0, -1)))
    if view == "right":
        return np.array(((0, 0, -1), (0, 1, 0)))
    raise ValueError("Unknown spatial report view.")


def samples(project, result):
    rows = []
    for member in project.members.values():
        stations, values, _ = sampled_member(project, result, member.name)
        a, b = (np.array(project.nodes[name].coords) for name in (member.start, member.end))
        points = a + stations[:, None] / math.dist(a, b) * (b - a)
        rows.append((member.name, points, values, member_axes(project, member.name, result)))
    return rows


def diagram_geometry(rows, kind, amplitude, span, side=1, sign=1):
    index = QUANTITIES.index(kind)
    low = min(float(values[:, index].min()) for _, _, values, _ in rows)
    high = max(float(values[:, index].max()) for _, _, values, _ in rows)
    peak = max(abs(low), abs(high))
    factor = amplitude / 100 * span / peak if peak else 0.
    return [(name, points, points + values[:, index, None] * axes[DIAGRAM_AXES[index]] * factor * side * sign,
             values[:, index]) for name, points, values, axes in rows], (low, high)


def ribbon_polygons(points, offsets, values):
    polygons = []
    for index in range(1, len(points)):
        a, b = points[index - 1], points[index]
        if np.linalg.norm(a - b) < 1e-10:
            continue
        left, right = values[index - 1], values[index]
        if left * right < 0:
            zero = a + left / (left - right) * (b - a)
            polygons.extend(([a, zero, offsets[index - 1]], [zero, b, offsets[index]]))
        else:
            polygons.append([a, b, offsets[index], offsets[index - 1]])
    return polygons


def draw_report(ax, project, result, rows, kind, view, options):
    basis, units = projection(view), project.units
    show = units.to_display
    length_factor = units.factor("length")
    coordinates = np.array([node.coords for node in project.nodes.values()])
    origin = (coordinates.min(axis=0) + coordinates.max(axis=0)) / 2
    span = max(float(np.ptp(coordinates, axis=0).max()), project.grid)
    def project_points(points):
        return (np.asarray(points) - origin) @ basis.T * length_factor
    index = QUANTITIES.index(kind)
    color = LIGHT["axial" if index in (0, 3) else "shear" if index in (1, 2) else "moment"]
    geometry, bounds = diagram_geometry(rows, kind, options.amplitude, span, options.side, options.sign)
    for name, points, offsets, values in geometry:
        baseline, curve = project_points(points), project_points(offsets)
        polygons = ribbon_polygons(points, offsets, values)
        ax.add_collection(PolyCollection([project_points(polygon) for polygon in polygons],
                                        facecolors=color, edgecolors="none", alpha=.18))
        ax.plot(*baseline.T, color=LIGHT["member"], linewidth=1.4, zorder=3)
        ax.plot(*curve.T, color=color, linewidth=1.1)
        for station in (0, -1):
            ax.plot(*np.array((baseline[station], curve[station])).T, color=color, linewidth=.7)
        add_diagram_label(ax, name + (" [truss]" if project.members[name].kind == "truss" else ""),
                          baseline[len(baseline) // 2], LIGHT["member"], "white", member=True)
        for station in sorted({0, len(values) - 1, int(values.argmin()), int(values.argmax())}):
            add_diagram_label(ax, f"{name} {LABELS[index]} {show(values[station] * options.sign, UNITS[index]):.4g}",
                              curve[station], color, "white")
    for node in project.nodes.values():
        point = project_points(node.coords)
        ax.plot(*point, marker=".", color=LIGHT["member"], markersize=5, zorder=4)
        add_diagram_label(ax, node.name, point, LIGHT["label"], "white", member=True)
        if options.supports and (any(node.restraints) or any(node.springs)):
            if any(node.restraints):
                ax.plot(*point, marker="^", markerfacecolor="white", markeredgecolor=LIGHT["support"], markersize=8, zorder=4)
            if any(node.springs):
                ax.plot(*point, marker="s", markerfacecolor="none", markeredgecolor=LIGHT["support"], markersize=11, zorder=4)
            fixed = "/".join(dof for dof, value in zip(DOFS, node.restraints) if value)
            spring = "/".join(dof for dof, value in zip(DOFS, node.springs) if value)
            context = (f"fixed {fixed}" if fixed else "") + (f"; spring {spring}" if spring else "")
            add_diagram_label(ax, f"{node.name}: {context.lstrip('; ')}", point, LIGHT["support"], "white")
    if options.loads:
        for load in combination_loads(project, result):
            if load.target in project.nodes:
                a = b = np.array(project.nodes[load.target].coords)
            else:
                member = project.members[load.target]
                a, b = (np.array(project.nodes[name].coords) for name in (member.start, member.end))
            if load.direction == "Angle":
                vector = np.array([value for _, value in load.components(project, 1.)])
            else:
                axis = "XYZ".index(load.direction[-1].upper())
                vector = np.eye(3)[axis] if load.direction.isupper() else member_axes(project, load.target, result)[axis]
            quantity = "intensity" if load.kind == "distributed" else "moment" if load.is_moment else "force"
            magnitude = f"{show(load.magnitude, quantity):.4g}"
            if load.kind == "distributed":
                magnitude += f" to {show(load.end_magnitude, quantity):.4g}"
            label = f"{load.name}: {magnitude} {getattr(units, quantity)} | {load.direction}"
            fractions = np.linspace(load.position, load.end_position, 7) if load.kind == "distributed" else [load.position]
            peak = max(abs(load.magnitude), abs(load.end_magnitude)) if load.kind == "distributed" else abs(load.magnitude)
            for fraction in fractions:
                magnitude = (load.magnitude + (load.end_magnitude - load.magnitude) *
                             (fraction - load.position) / (load.end_position - load.position) if load.kind == "distributed" else load.magnitude)
                if not magnitude:
                    continue
                head = a + fraction * (b - a)
                tail = head - vector * span * .07 * magnitude / peak
                start, end = project_points(tail), project_points(head)
                if np.linalg.norm(end - start) < span * length_factor * 1e-8:
                    normal = np.cross(*basis)
                    ax.plot(*end, marker="o" if vector @ normal * magnitude > 0 else "x", color=LIGHT["load"],
                            markerfacecolor="white", markersize=6, zorder=5)
                else:
                    ax.update_datalim([start, end])
                    delta = end - start
                    perpendicular = np.array((-delta[1], delta[0])) / np.linalg.norm(delta)
                    for offset in ((0., .009 * span * length_factor) if load.is_moment else (0.,)):
                        shift = perpendicular * offset
                        ax.annotate("", end + shift, start + shift,
                                    arrowprops={"arrowstyle": "->", "color": LIGHT["load"], "linewidth": .9})
            point = a + ((load.position + load.end_position) / 2 if load.kind == "distributed" else load.position) * (b - a)
            add_diagram_label(ax, label, project_points(point), LIGHT["load"], "white")
    ax.autoscale_view()
    ax.margins(.18)
    # Nonzero 2D extents make edge-on and zero-force projections stable.
    for get, set_limit in ((ax.get_xlim, ax.set_xlim), (ax.get_ylim, ax.set_ylim)):
        low, high = get()
        minimum = span * length_factor * .2
        if high - low < minimum:
            center = (low + high) / 2
            set_limit(center - minimum / 2, center + minimum / 2)
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()
    unit = getattr(units, UNITS[index])
    bounds = sorted(value * options.sign for value in bounds)
    note = f"{LABELS[index]} ({unit}) | Sampled range {show(bounds[0], UNITS[index]):.5g} to {show(bounds[1], UNITS[index]):.5g}"
    note += "\nOrthographic projection | Offset along " + ("+" if options.side == 1 else "-") + "local " + "xyz"[DIAGRAM_AXES[index]]
    text = ax.text(.01, .98, note, transform=ax.transAxes, va="top", fontsize=8, color=LIGHT["text"])
    reserve_annotation(ax, text)
    axis_origin = np.array((.9, .13))
    for axis, vector, axis_color in zip("XYZ", basis.T, (LIGHT["load"], LIGHT["support"], LIGHT["axial"])):
        end = axis_origin + .07 * vector
        guide = ax.annotate(axis, end, axis_origin, xycoords="axes fraction", textcoords="axes fraction", fontsize=8,
                            color=axis_color, arrowprops={"arrowstyle": "->", "color": axis_color, "linewidth": .8})
        reserve_annotation(ax, guide)


def report_images(project, result, options):
    rows = samples(project, result)
    images = {}
    for kind in options.diagrams:
        for view in options.views:
            figure = Figure(figsize=(9, 4.8), facecolor="white", layout="constrained")
            FigureCanvasAgg(figure)
            draw_report(figure.add_subplot(111), project, result, rows, kind, view, options)
            stream = io.BytesIO()
            figure.savefig(stream, format="png", dpi=160)
            images[f"{kind}:{view}"] = stream.getvalue()
            figure.clear()
    return images
