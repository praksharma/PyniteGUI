"""Member sampling and whole-frame force diagrams for analyzed 2D models."""
import math

import numpy as np
from matplotlib.figure import Figure
from matplotlib.offsetbox import AnnotationBbox, DrawingArea
from matplotlib.patches import Circle
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QStyle, QTabWidget, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget

from .analysis import model_signature
from .theme import colors, restyle_figure, style_axes


def member_breaks(project, name):
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
    return length, sorted(breaks)


def member_values(project, result, name, distance, side="right"):
    length, boundaries = member_breaks(project, name)
    if not math.isfinite(distance) or not 0 <= distance <= length:
        raise ValueError("Inspection distance must be within the member.")
    if side not in ("left", "right"):
        raise ValueError("Unknown inspection side.")
    query = distance
    for index, boundary in enumerate(boundaries[1:-1], 1):
        if abs(distance - boundary) <= max(length * 1e-10, 1e-10):
            gap = min(boundary - boundaries[index - 1], boundaries[index + 1] - boundary)
            epsilon = min(gap * 1e-5, max(length * 1e-8, 1e-8))
            query = boundary + (epsilon if side == "right" else -epsilon)
            break
    solver, combo = result.solver.members[name], result.combination
    if project.members[name].kind == "truss":
        return (solver.axial(query, combo), 0.0, 0.0, solver.deflection("dy", query, combo))
    return (solver.axial(query, combo), solver.shear("Fy", query, combo),
            solver.moment("Mz", query, combo), solver.deflection("dy", query, combo))


def member_result_rows(project, result):
    rows = []
    combo = result.combination
    for name in project.members:
        length, _ = member_breaks(project, name)
        solver = result.solver.members[name]
        for label, distance in (("Start", 0), ("End", length)):
            rows.append((name, label, distance, *member_values(project, result, name, distance)))
        for label, prefix in (("Minimum", "min"), ("Maximum", "max")):
            truss = project.members[name].kind == "truss"
            rows.append((name, label, None, getattr(solver, prefix + "_axial")(combo),
                         0.0 if truss else getattr(solver, prefix + "_shear")("Fy", combo),
                         0.0 if truss else getattr(solver, prefix + "_moment")("Mz", combo),
                         getattr(solver, prefix + "_deflection")("dy", combo)))
    return rows


def sample_member(project, result, name):
    length, boundaries = member_breaks(project, name)
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
    truss = project.members[name].kind == "truss"
    return {
        "x": np.array(xs),
        "axial": np.array([solver.axial(x, result.combination) for x in locations]),
        "shear": np.zeros(len(locations)) if truss else np.array([solver.shear("Fy", x, result.combination) for x in locations]),
        "moment": np.zeros(len(locations)) if truss else np.array([solver.moment("Mz", x, result.combination) for x in locations]),
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
        # Axial compression/tension is a scalar and does not change with local
        # axis reversal. Only transverse cut forces need the orientation mapping.
        values = sampled[quantity].copy() if quantity == "axial" else sampled[quantity] * direction * (orientation if quantity == "shear" else 1)
        base = start + np.outer(sampled["x"], tangent)
        data[name] = {"base": base, "normal": normal, "values": values}
    return data


def draw_structure(ax, project, result, quantity, amplitude=20, side=1, sign=1, palette=None):
    if type(side) is not int or side not in (-1, 1) or type(sign) is not int or sign not in (-1, 1):
        raise ValueError("Diagram side and sign must be +1 or -1.")
    data = structure_data(project, result, quantity)
    for row in data.values():
        row["values"] *= sign
    units = project.units
    value_quantity = "moment" if quantity == "moment" else "force"
    maximum = max((float(np.max(np.abs(row["values"]))) for row in data.values()), default=0)
    xs, ys = [n.x for n in project.nodes.values()], [n.y for n in project.nodes.values()]
    extent = max(max(xs) - min(xs), max(ys) - min(ys), 1)
    factor = extent * amplitude / 100 / maximum if maximum > 1e-10 else 0
    c = palette or colors()
    color = c[quantity]
    for name, row in data.items():
        base, values, normal = row["base"], row["values"], row["normal"]
        base = units.to_display(base, "length")
        offset = base + np.outer(units.to_display(values * factor * side, "length"), normal)
        ax.plot(base[:, 0], base[:, 1], color=c["member"], linewidth=2, zorder=3)
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
            if any(np.linalg.norm(point - previous) < units.to_display(extent * 0.025, "length") for previous in used):
                continue
            used.append(point)
            ax.annotate(f"{units.to_display(values[index], value_quantity):.4g}", point, xytext=(5, 5), textcoords="offset points", fontsize=8, color=color,
                        bbox={"facecolor": c["canvas"], "edgecolor": "none", "alpha": 0.8, "pad": 1})
        midpoint = (base[0] + base[-1]) / 2
        ax.annotate(name, midpoint, xytext=(5, -12), textcoords="offset points", fontsize=8, color=c["member"])
    for node in project.nodes.values():
        x, y = units.to_display(node.x, "length"), units.to_display(node.y, "length")
        ax.plot(x, y, "o", color=c["member"], markersize=3, zorder=4)
        if any(node.restraints):
            ax.plot(x, y, marker="^" if node.support != "roller" else "o", color=c["support"], fillstyle="none", markersize=9, zorder=4)
    for name, row in data.items():
        member = project.members[name]
        start, end = row["base"][0], row["base"][-1]
        tangent = (end - start) / np.linalg.norm(end - start)
        release_start, release_end = member.moment_releases
        for released, point, offset_sign in ((release_start, start, 1), (release_end, end, -1)):
            if released:
                marker = DrawingArea(8, 8)
                marker.add_artist(Circle((4, 4), 3, facecolor=c["canvas"], edgecolor=c["accent"], linewidth=1.3))
                ax.add_artist(AnnotationBbox(marker, units.to_display(point, "length"), xybox=tuple(offset_sign * tangent * 9),
                                            boxcoords="offset points", frameon=False, pad=0, zorder=5))
    ax.set_title({"axial": f"Axial Force Diagram N ({units.force}; + {'compression' if sign == 1 else 'tension'})",
                  "shear": f"Shear Force Diagram V ({units.force})",
                  "moment": f"Bending Moment Diagram M ({units.moment})"}[quantity] +
                 (" | reversed display sign" if sign == -1 and quantity != "axial" else ""))
    ax.set_xlabel(f"X ({units.length})")
    ax.set_ylabel(f"Y ({units.length})")
    ax.set_aspect("equal", adjustable="datalim")
    ax.margins(0.2)
    ax.grid(alpha=0.15)
    if palette is None:
        style_axes(ax)
    else:
        ax.figure.set_facecolor(c["window"])
        ax.set_facecolor(c["canvas"])
        ax.tick_params(colors=c["label"])
        for spine in ax.spines.values():
            spine.set_color(c["axis"])
        for text in (ax.title, ax.xaxis.label, ax.yaxis.label):
            text.set_color(c["text"])
        ax.grid(color=c["axis"], alpha=0.3)
    return data


class DiagramDialog(QDialog):
    def __init__(self, parent, project, result, selected=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"Force Diagrams | {result.combination}")
        self.resize(1000, 800)
        self.project, self.result = project.clone(), result
        self.plot_colors = colors()
        self.source = str(getattr(parent, "path", None) or "Untitled")
        self.model_revision = getattr(parent, "revision", None)
        layout = QVBoxLayout(self)
        self.snapshot_label = QLabel()
        self.snapshot_label.setTextFormat(Qt.TextFormat.PlainText)
        self.snapshot_label.setWordWrap(True)
        layout.addWidget(self.snapshot_label)
        top_controls = QHBoxLayout()
        self.combination = QComboBox()
        self.combination.addItems(list(result.solver.load_combos))
        self.combination.setCurrentText(result.combination)
        self.combination.setToolTip("Diagram combination")
        top_controls.addWidget(self.combination, 1)
        from .reports import ResultExportMenu
        self.export_menu = ResultExportMenu(self, lambda: (self.project, self.result, self.source))
        self.export_button = QToolButton()
        self.export_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.export_button.setToolTip("Export or print this analyzed snapshot")
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_button.setMenu(self.export_menu)
        top_controls.addWidget(self.export_button)
        layout.addLayout(top_controls)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        structure = QWidget()
        structure_layout = QVBoxLayout(structure)
        controls = QHBoxLayout()
        self.quantity = QComboBox()
        units = project.units
        for label, key in ((f"Shear Force ({units.force})", "shear"), (f"Bending Moment ({units.moment})", "moment"), (f"Axial Force ({units.force})", "axial")):
            self.quantity.addItem(label, key)
        self.quantity.setToolTip("Axial force: positive compression, negative tension.")
        controls.addWidget(self.quantity)
        controls.addStretch()
        controls.addWidget(QLabel("Amplitude (%)"))
        self.amplitude = QDoubleSpinBox()
        self.amplitude.setRange(2, 60)
        self.amplitude.setValue(20)
        self.amplitude.setKeyboardTracking(False)
        controls.addWidget(self.amplitude)
        structure_layout.addLayout(controls)
        display = QHBoxLayout()
        self.diagram_side = QComboBox()
        self.diagram_side.addItem("Default side", 1)
        self.diagram_side.addItem("Opposite side", -1)
        self.diagram_side.setToolTip("Flip diagram placement; numerical signs remain unchanged.")
        display.addWidget(self.diagram_side)
        self.reverse_sign = QCheckBox("Reverse display signs")
        self.reverse_sign.setToolTip("Whole-structure diagrams only. Member Detail, result tables, and CSV keep solver signs.")
        display.addWidget(self.reverse_sign)
        display.addStretch()
        structure_layout.addLayout(display)
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
        inspection = QHBoxLayout()
        inspection.addWidget(QLabel("Distance"))
        self.distance = QDoubleSpinBox()
        self.distance.setDecimals(8)
        self.distance.setKeyboardTracking(False)
        self.distance.setToolTip("Distance from the member start; click a member plot to inspect")
        inspection.addWidget(self.distance)
        self.inspection_side = QComboBox()
        self.inspection_side.addItem("Right side", "right")
        self.inspection_side.addItem("Left side", "left")
        self.inspection_side.setToolTip("One-sided value at a concentrated load or internal segment boundary")
        inspection.addWidget(self.inspection_side)
        inspection.addStretch()
        detail_layout.addLayout(inspection)
        self.inspection_values = QTableWidget(1, 4)
        self.inspection_values.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.inspection_values.verticalHeader().hide()
        self.inspection_values.setMaximumHeight(72)
        detail_layout.addWidget(self.inspection_values)
        self.inspection_x = 0
        self.inspection_member = self.member.currentText()
        self.probes = []
        self.member_figure = Figure(figsize=(9, 7), layout="constrained")
        self.member_canvas = FigureCanvasQTAgg(self.member_figure)
        detail_layout.addWidget(NavigationToolbar2QT(self.member_canvas, self))
        detail_layout.addWidget(self.member_canvas)
        self.tabs.addTab(detail, "Member Detail")
        self.member_results = QTableWidget(0, 7)
        self.member_results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.member_results.setAlternatingRowColors(True)
        self.tabs.addTab(self.member_results, "Member Results")
        from .envelopes import EnvelopeWidget
        self.envelopes = EnvelopeWidget(self, self.project, result, self.source, selected)
        self.tabs.addTab(self.envelopes, "Envelopes")
        self.combination.currentTextChanged.connect(self.select_combination)
        self.quantity.currentIndexChanged.connect(self.update_structure)
        self.amplitude.valueChanged.connect(self.update_structure)
        self.diagram_side.currentIndexChanged.connect(self.update_structure)
        self.reverse_sign.toggled.connect(self.update_structure)
        self.member.currentTextChanged.connect(self.update_member)
        self.distance.valueChanged.connect(self.inspect_distance)
        self.inspection_side.currentIndexChanged.connect(self.update_inspection)
        self.member_canvas.mpl_connect("button_press_event", self.inspect_click)
        self.update_structure()
        self.update_member()
        self.update_results()
        self.update_snapshot_status()

    def update_snapshot_status(self):
        parent = self.parentWidget()
        status = "Analyzed snapshot"
        if parent is not None and hasattr(parent, "project"):
            if model_signature(parent.project) != self.result.model_signature:
                status = "Different from current editor model"
            elif getattr(parent, "result", None) is not None and parent.result.snapshot_id != self.result.snapshot_id:
                status = "Earlier analysis of current model"
            else:
                status = "Matches current editor model"
        revision = f" | Editor revision {self.model_revision}" if self.model_revision is not None else ""
        self.snapshot_label.setText(f"Analysis {self.result.snapshot_id} | {self.result.analyzed_at} (UTC)\nModel {self.result.model_signature[:12]}{revision} | {status}")
        self.snapshot_label.setToolTip(self.source)
        self.setWindowTitle(f"Force Diagrams | {self.result.combination} | {self.result.snapshot_id}")

    def set_unit_system(self, key):
        if self.project.unit_system == key:
            return
        self.project.unit_system = key
        units = self.project.units
        self.quantity.blockSignals(True)
        for index, label in enumerate((f"Shear Force ({units.force})", f"Bending Moment ({units.moment})", f"Axial Force ({units.force})")):
            self.quantity.setItemText(index, label)
        self.quantity.blockSignals(False)
        self.update_structure()
        self.update_member()
        self.update_results()
        self.envelopes.refresh()

    def select_combination(self, name):
        self.result = self.result.for_combination(name)
        self.update_snapshot_status()
        self.update_structure()
        self.update_member()
        self.update_results()

    def update_structure(self):
        self.structure_canvas.setPalette(self.palette())
        self.structure_figure.clear()
        ax = self.structure_figure.add_subplot(111)
        draw_structure(ax, self.project, self.result, self.quantity.currentData(), self.amplitude.value(),
                       self.diagram_side.currentData(), -1 if self.reverse_sign.isChecked() else 1)
        self.structure_canvas.draw_idle()

    def update_member(self):
        self.member_canvas.setPalette(self.palette())
        self.member_figure.clear()
        name = self.member.currentText()
        if name != self.inspection_member:
            self.inspection_x = 0
            self.inspection_member = name
        data = sample_member(self.project, self.result, name)
        units = self.project.units
        self.distance.blockSignals(True)
        self.distance.setRange(0, units.to_display(float(data["x"][-1]), "length"))
        self.distance.setSuffix(f" {units.length}")
        self.distance.setValue(units.to_display(self.inspection_x, "length"))
        self.distance.blockSignals(False)
        self.probes = []
        c = colors()
        shared = None
        for index, (key, label, color) in enumerate((("axial", f"Axial N ({units.force})\n+ compression", c["axial"]),
                                                     ("shear", f"Shear Fy ({units.force})", c["shear"]),
                                                     ("moment", f"Moment Mz ({units.moment})", c["moment"]),
                                                     ("deflection", f"Deflection dy ({units.length})", c["shear"]))):
            ax = self.member_figure.add_subplot(4, 1, index + 1, sharex=shared)
            if shared is None:
                shared = ax
            ax.plot(units.to_display(data["x"], "length"), units.to_display(data[key], "length" if key == "deflection" else "moment" if key == "moment" else "force"), color=color)
            ax.axhline(0, color=c["axis"], linewidth=0.6)
            ax.set_ylabel(label, fontsize=8, rotation=0, ha="right", va="center", labelpad=12)
            ax.grid(alpha=0.2)
            if index == 0:
                ax.set_title(f"{name} | Local Member Axes")
            ax.tick_params(axis="x", labelbottom=index == 3)
            if index == 3:
                ax.set_xlabel(f"Distance from start ({units.length})")
            style_axes(ax)
        self.update_inspection()

    def apply_theme(self):
        if not hasattr(self, "member_canvas"):
            return
        for figure in (self.structure_figure, self.member_figure):
            restyle_figure(figure, self.plot_colors)
        self.plot_colors = colors()
        self.structure_canvas.setPalette(self.palette())
        self.member_canvas.setPalette(self.palette())
        self.structure_canvas.draw_idle()
        self.member_canvas.draw_idle()
        self.envelopes.apply_theme()

    def inspect_distance(self):
        self.inspection_x = self.project.units.from_display(self.distance.value(), "length")
        length, _ = member_breaks(self.project, self.member.currentText())
        self.inspection_x = min(length, max(0, self.inspection_x))
        self.update_inspection()

    def inspect_click(self, event):
        if event.button != 1 or event.inaxes not in self.member_figure.axes or event.xdata is None:
            return
        if self.member_canvas.toolbar and self.member_canvas.toolbar.mode:
            return
        self.distance.setValue(min(self.distance.maximum(), max(0, event.xdata)))

    def update_inspection(self):
        units = self.project.units
        values = member_values(self.project, self.result, self.member.currentText(), self.inspection_x,
                               self.inspection_side.currentData())
        self.inspection_values.setHorizontalHeaderLabels([f"N ({units.force})", f"Fy ({units.force})",
                                                          f"Mz ({units.moment})", f"dy ({units.length})"])
        for col, (value, quantity) in enumerate(zip(values, ("force", "force", "moment", "length"))):
            self.inspection_values.setItem(0, col, QTableWidgetItem(f"{units.to_display(value, quantity):.6g}"))
        self.inspection_values.resizeColumnsToContents()
        for line in self.probes:
            line.remove()
        self.probes = [ax.axvline(units.to_display(self.inspection_x, "length"), color=colors()["label"], linestyle="--", linewidth=0.8)
                       for ax in self.member_figure.axes]
        self.member_canvas.draw_idle()

    def update_results(self):
        units = self.project.units
        self.member_results.setHorizontalHeaderLabels(["Member", "Station", f"x ({units.length})", f"N ({units.force})",
                                                       f"Fy ({units.force})", f"Mz ({units.moment})", f"dy ({units.length})"])
        rows = member_result_rows(self.project, self.result)
        self.member_results.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                if col >= 2 and value is not None:
                    value = units.to_display(value, ("length", "force", "force", "moment", "length")[col - 2])
                text = "-" if value is None else value if isinstance(value, str) else f"{value:.6g}"
                item = QTableWidgetItem(text)
                item.setToolTip("Local member axes; N positive compression. Min/max are independent extrema of each column, not values at one shared station.")
                self.member_results.setItem(row, col, item)
        self.member_results.resizeColumnsToContents()
