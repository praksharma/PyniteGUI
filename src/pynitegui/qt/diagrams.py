"""Member sampling and whole-frame force diagrams for analyzed 2D models."""
import math

import numpy as np
from matplotlib.figure import Figure
from matplotlib.offsetbox import AnnotationBbox, DrawingArea
from matplotlib.patches import Circle
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget


def sample_member(project, result, name):
    member = project.members[name]
    a, b = project.nodes[member.start], project.nodes[member.end]
    length = math.hypot(b.x - a.x, b.y - a.y)
    breaks = {0.0, length}
    for load in project.loads.values():
        if load.target == name:
            breaks.add(load.position * length)
            if load.kind == "distributed":
                breaks.add(load.end_position * length)
    # Physical members can also be segmented at intermediate model nodes.
    for node in project.nodes.values():
        distance = ((node.x - a.x) * (b.x - a.x) + (node.y - a.y) * (b.y - a.y)) / length
        cross = (node.x - a.x) * (b.y - a.y) - (node.y - a.y) * (b.x - a.x)
        if 0 < distance < length and abs(cross) < length * 1e-8:
            breaks.add(distance)
    boundaries = sorted(breaks)
    solver = result.solver.members[name]
    xs, locations = [], []
    for left, right in zip(boundaries, boundaries[1:]):
        points = np.linspace(left, right, max(3, math.ceil(80 * (right - left) / length) + 1))
        epsilon = min((right - left) * 1e-5, max(length * 1e-8, 1e-8))
        queries = points.copy()
        if left > 0:
            queries[0] += epsilon
        if right < length:
            queries[-1] -= epsilon
        xs.extend(points)
        locations.extend(queries)
    return {
        "x": np.array(xs),
        "shear": np.array([solver.shear("Fy", x, result.combination) for x in locations]),
        "moment": np.array([solver.moment("Mz", x, result.combination) for x in locations]),
        "deflection": np.array([solver.deflection("dy", x, result.combination) for x in locations]),
    }


def structure_data(project, result, quantity):
    data = {}
    for name, member in project.members.items():
        sampled = sample_member(project, result, name)
        a, b = project.nodes[member.start], project.nodes[member.end]
        start, end = np.array([a.x, a.y]), np.array([b.x, b.y])
        tangent = (end - start) / np.linalg.norm(end - start)
        orientation = 1 if (a.x, a.y) < (b.x, b.y) else -1
        canonical_tangent = tangent * orientation
        normal = np.array([-canonical_tangent[1], canonical_tangent[0]])
        local_y = result.solver.members[name].T()[1, :2]
        direction = float(np.dot(local_y, normal))
        # Express cut forces using a consistent endpoint orientation, regardless
        # of the order in which a user originally drew each member.
        values = sampled[quantity] * direction * (orientation if quantity == "shear" else 1)
        base = start + np.outer(sampled["x"], tangent)
        data[name] = {"base": base, "normal": normal, "values": values}
    return data


def draw_structure(ax, project, result, quantity, amplitude=20):
    data = structure_data(project, result, quantity)
    maximum = max((float(np.max(np.abs(row["values"]))) for row in data.values()), default=0)
    xs, ys = [n.x for n in project.nodes.values()], [n.y for n in project.nodes.values()]
    extent = max(max(xs) - min(xs), max(ys) - min(ys), 1)
    factor = extent * amplitude / 100 / maximum if maximum > 1e-10 else 0
    color = "#168b8b" if quantity == "shear" else "#b53c5b"
    for name, row in data.items():
        base, values, normal = row["base"], row["values"], row["normal"]
        offset = base + np.outer(values * factor, normal)
        ax.plot(base[:, 0], base[:, 1], color="#32464d", linewidth=2, zorder=3)
        ax.plot(offset[:, 0], offset[:, 1], color=color, linewidth=1.7)
        polygon = np.vstack((base[0], offset, base[-1]))
        ax.fill(polygon[:, 0], polygon[:, 1], color=color, alpha=0.12)
        for index in (0, len(values) - 1):
            ax.plot([base[index, 0], offset[index, 0]], [base[index, 1], offset[index, 1]], color=color, linewidth=0.8)
        labels = sorted({0, len(values) - 1, int(np.argmax(values)), int(np.argmin(values))})
        # Coincident endpoint/extreme labels need only one annotation.
        used = []
        for index in labels:
            point = offset[index]
            if any(np.linalg.norm(point - previous) < extent * 0.025 for previous in used):
                continue
            used.append(point)
            ax.annotate(f"{values[index]:.4g}", point, xytext=(5, 5), textcoords="offset points", fontsize=8, color=color,
                        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 1})
        midpoint = (base[0] + base[-1]) / 2
        ax.annotate(name, midpoint, xytext=(5, -12), textcoords="offset points", fontsize=8, color="#32464d")
    for node in project.nodes.values():
        ax.plot(node.x, node.y, "o", color="#32464d", markersize=3, zorder=4)
        if node.support != "free":
            ax.plot(node.x, node.y, marker="^" if node.support != "roller" else "o", color="#258451", fillstyle="none", markersize=9, zorder=4)
    for name, row in data.items():
        member = project.members[name]
        start, end = row["base"][0], row["base"][-1]
        tangent = (end - start) / np.linalg.norm(end - start)
        for released, point, sign in ((member.release_start, start, 1), (member.release_end, end, -1)):
            if released:
                marker = DrawingArea(8, 8)
                marker.add_artist(Circle((4, 4), 3, facecolor="white", edgecolor="#176b73", linewidth=1.3))
                ax.add_artist(AnnotationBbox(marker, point, xybox=tuple(sign * tangent * 9),
                                            boxcoords="offset points", frameon=False, pad=0, zorder=5))
    ax.set_title("Shear Force Diagram V (kip)" if quantity == "shear" else "Bending Moment Diagram M (kip-in)")
    ax.set_xlabel("X (in)")
    ax.set_ylabel("Y (in)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.margins(0.2)
    ax.grid(alpha=0.15)
    return data


class DiagramDialog(QDialog):
    def __init__(self, parent, project, result, selected=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"Force Diagrams | {result.combination}")
        self.resize(1000, 800)
        self.project, self.result = project.clone(), result
        layout = QVBoxLayout(self)
        self.combination = QComboBox()
        self.combination.addItems(list(result.solver.load_combos))
        self.combination.setCurrentText(result.combination)
        self.combination.setToolTip("Diagram combination")
        layout.addWidget(self.combination)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        structure = QWidget()
        structure_layout = QVBoxLayout(structure)
        controls = QHBoxLayout()
        self.quantity = QComboBox()
        self.quantity.addItems(["Shear Force (kip)", "Bending Moment (kip-in)"])
        controls.addWidget(self.quantity)
        controls.addStretch()
        controls.addWidget(QLabel("Amplitude (%)"))
        self.amplitude = QDoubleSpinBox()
        self.amplitude.setRange(2, 60)
        self.amplitude.setValue(20)
        self.amplitude.setKeyboardTracking(False)
        controls.addWidget(self.amplitude)
        structure_layout.addLayout(controls)
        self.structure_figure = Figure(figsize=(9, 7), layout="constrained")
        self.structure_canvas = FigureCanvasQTAgg(self.structure_figure)
        structure_layout.addWidget(NavigationToolbar2QT(self.structure_canvas, self))
        structure_layout.addWidget(self.structure_canvas)
        self.tabs.addTab(structure, "Whole Structure")
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.member = QComboBox()
        self.member.addItems(list(project.members))
        if selected in project.members:
            self.member.setCurrentText(selected)
        detail_layout.addWidget(self.member)
        self.member_figure = Figure(figsize=(9, 7), layout="constrained")
        self.member_canvas = FigureCanvasQTAgg(self.member_figure)
        detail_layout.addWidget(NavigationToolbar2QT(self.member_canvas, self))
        detail_layout.addWidget(self.member_canvas)
        self.tabs.addTab(detail, "Member Detail")
        self.combination.currentTextChanged.connect(self.select_combination)
        self.quantity.currentIndexChanged.connect(self.update_structure)
        self.amplitude.valueChanged.connect(self.update_structure)
        self.member.currentTextChanged.connect(self.update_member)
        self.update_structure()
        self.update_member()

    def select_combination(self, name):
        self.result = self.result.for_combination(name)
        self.setWindowTitle(f"Force Diagrams | {name}")
        self.update_structure()
        self.update_member()

    def update_structure(self):
        self.structure_figure.clear()
        ax = self.structure_figure.add_subplot(111)
        draw_structure(ax, self.project, self.result, "shear" if self.quantity.currentIndex() == 0 else "moment", self.amplitude.value())
        self.structure_canvas.draw_idle()

    def update_member(self):
        self.member_figure.clear()
        name = self.member.currentText()
        data = sample_member(self.project, self.result, name)
        for index, (key, label) in enumerate((("shear", "Shear Fy (kip)"), ("moment", "Moment Mz (kip-in)"), ("deflection", "Deflection dy (in)"))):
            ax = self.member_figure.add_subplot(3, 1, index + 1)
            ax.plot(data["x"], data[key], color="#168b8b")
            ax.axhline(0, color="#869395", linewidth=0.6)
            ax.set_ylabel(label)
            ax.grid(alpha=0.2)
            if index == 0:
                ax.set_title(f"{name} | Local Member Axes")
            if index == 2:
                ax.set_xlabel("Distance from start (in)")
        self.member_canvas.draw_idle()
