"""Independent result bounds over explicit combinations of an analyzed snapshot."""
import csv
import json
import os
from pathlib import Path
import tempfile

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QStyle, QTabWidget,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from .analysis import model_signature
from .theme import colors, style_axes


def selected_results(project, result, combinations):
    names = tuple(combinations)
    if not names or len(set(names)) != len(names):
        raise ValueError("Select at least one distinct analyzed combination.")
    if any(name not in result.solver.load_combos for name in names):
        raise ValueError("Unknown analyzed combination.")
    if model_signature(project) != result.model_signature:
        raise ValueError("The model does not match this analyzed snapshot.")
    return [result.for_combination(name) for name in names]


def bounds(values):
    available = [(value, name) for value, name in values if value is not None]
    if not available:
        return None, "", None, ""
    low = min(available, key=lambda pair: pair[0])
    high = max(available, key=lambda pair: pair[0])
    return *low, *high


def envelope_rows(project, result, combinations):
    """Exact solver member extrema; node bounds at fixed nodes. First tie wins."""
    from .diagrams import member_result_rows
    results = selected_results(project, result, combinations)
    rows = []
    for name in project.nodes:
        for index, (label, quantity) in enumerate((("DX", "length"), ("DY", "length"), ("RZ", "rotation"),
                                                  ("FX", "force"), ("FY", "force"), ("MZ", "moment"))):
            values = [((r.displacements if index < 3 else r.reactions)[name][index % 3], r.combination) for r in results]
            rows.append(("Node", name, label, quantity, *bounds(values)))
    extrema = {r.combination: {(row[0], row[1]): row for row in member_result_rows(project, r)
                              if row[1] in ("Minimum", "Maximum")} for r in results}
    for name in project.members:
        for index, (label, quantity) in enumerate((("N", "force"), ("Fy", "force"), ("Mz", "moment"), ("dy", "length")), 3):
            low = bounds([(extrema[r.combination][name, "Minimum"][index], r.combination) for r in results])[:2]
            high = bounds([(extrema[r.combination][name, "Maximum"][index], r.combination) for r in results])[2:]
            rows.append(("Member", name, label, quantity, *low, *high))
    return rows


def member_envelope(project, result, combinations, member, quantity):
    from .diagrams import sample_member
    if member not in project.members or quantity not in ("axial", "shear", "moment", "deflection"):
        raise ValueError("Unknown envelope member or quantity.")
    results = selected_results(project, result, combinations)
    samples = [sample_member(project, r, member) for r in results]
    values = np.stack([sample[quantity] for sample in samples])
    names = np.array([r.combination for r in results], dtype=object)
    return {"x": samples[0]["x"], "minimum": values.min(axis=0), "maximum": values.max(axis=0),
            "minimum_combination": names[values.argmin(axis=0)], "maximum_combination": names[values.argmax(axis=0)]}


def display_rows(project, rows):
    for kind, name, label, quantity, low, low_combo, high, high_combo in rows:
        unit = {"length": project.units.length, "force": project.units.force,
                "moment": project.units.moment, "rotation": "rad"}[quantity]
        yield (kind, name, f"{label} ({unit})", "n/a" if low is None else project.units.to_display(low, quantity),
               low_combo, "n/a" if high is None else project.units.to_display(high, quantity), high_combo)


HEADERS = ("Entity", "ID", "Result", "Minimum", "Minimum combination", "Maximum", "Maximum combination")


def export_envelope_csv(path, project, result, combinations, source="Untitled"):
    from .reports import csv_text
    combinations = tuple(combinations)
    rows = envelope_rows(project, result, combinations)
    metadata = (source, result.snapshot_id, result.analyzed_at, result.model_signature,
                json.dumps(list(combinations), ensure_ascii=True), project.units.label,
                json.dumps({name: result.solver.load_combos[name].factors for name in combinations}, ensure_ascii=True),
                project.self_weight_case or "", project.self_weight_factor if project.self_weight_case is not None else "",
                "Independent extrema; local member axes; N positive compression; first selected combination wins ties")
    path, temporary = Path(path), None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream)
            writer.writerow(("Source", "Analysis ID", "Analyzed (UTC)", "Model signature", "Selected combinations",
                             "Unit system", "Combination factors", "Self-weight case", "Self-weight factor", "Convention", *HEADERS))
            writer.writerows([csv_text(value) for value in (*metadata, *row)] for row in display_rows(project, rows))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class EnvelopeWidget(QWidget):
    def __init__(self, parent, project, result, source, selected=None):
        super().__init__(parent)
        self.project, self.result, self.source = project, result, source
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Combinations"))
        self.combinations = QListWidget()
        self.combinations.setMaximumHeight(90)
        self.combinations.setToolTip("Envelope combinations, independent of the single-combination selector. First checked combination wins ties.")
        for name in result.solver.load_combos:
            item = QListWidgetItem(name, self.combinations)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
        controls.addWidget(self.combinations, 1)
        self.export_button = QToolButton()
        self.export_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.export_button.setToolTip("Export envelope summary (CSV)")
        controls.addWidget(self.export_button)
        layout.addLayout(controls)
        self.views = QTabWidget()
        layout.addWidget(self.views)
        self.tables = {}
        for kind, label in (("Node", "Nodes"), ("Member", "Members")):
            table = QTableWidget(0, len(HEADERS))
            table.setHorizontalHeaderLabels(HEADERS)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setAlternatingRowColors(True)
            self.tables[kind] = table
            self.views.addTab(table, label)
        plot = QWidget()
        plot_layout = QVBoxLayout(plot)
        plot_controls = QHBoxLayout()
        self.member = QComboBox()
        self.member.addItems(list(project.members))
        if selected in project.members:
            self.member.setCurrentText(selected)
        self.quantity = QComboBox()
        for label, key in (("Axial N", "axial"), ("Shear Fy", "shear"), ("Moment Mz", "moment"), ("Deflection dy", "deflection")):
            self.quantity.addItem(label, key)
        plot_controls.addWidget(self.member)
        plot_controls.addWidget(self.quantity)
        plot_controls.addStretch()
        self.distance = QDoubleSpinBox()
        self.distance.setDecimals(8)
        self.distance.setKeyboardTracking(False)
        self.distance.setToolTip("Inspection distance from member start")
        self.inspection_x = 0.0
        self.inspection_member = self.member.currentText()
        self.side = QComboBox()
        self.side.addItem("Right side", "right")
        self.side.addItem("Left side", "left")
        plot_controls.addWidget(self.distance)
        plot_controls.addWidget(self.side)
        plot_layout.addLayout(plot_controls)
        self.inspection = QTableWidget(1, 4)
        self.inspection.setHorizontalHeaderLabels(("Minimum", "Minimum combination", "Maximum", "Maximum combination"))
        self.inspection.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.inspection.verticalHeader().hide()
        self.inspection.setMaximumHeight(70)
        plot_layout.addWidget(self.inspection)
        self.figure = Figure(figsize=(9, 5), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        plot_layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        plot_layout.addWidget(self.canvas)
        self.views.addTab(plot, "Member Curves")
        self.combinations.itemChanged.connect(self.refresh)
        self.member.currentTextChanged.connect(self.update_plot)
        self.quantity.currentIndexChanged.connect(self.update_plot)
        self.distance.valueChanged.connect(self.inspect_distance)
        self.side.currentIndexChanged.connect(self.update_plot)
        self.canvas.mpl_connect("button_press_event", self.inspect_click)
        self.export_button.clicked.connect(self.export)
        self.refresh()

    def selected_combinations(self):
        return tuple(self.combinations.item(i).text() for i in range(self.combinations.count())
                     if self.combinations.item(i).checkState() == Qt.CheckState.Checked)

    def refresh(self):
        names = self.selected_combinations()
        self.export_button.setEnabled(bool(names))
        rows = list(display_rows(self.project, envelope_rows(self.project, self.result, names))) if names else []
        for kind, table in self.tables.items():
            subset = [row for row in rows if row[0] == kind]
            table.setRowCount(len(subset))
            for i, row in enumerate(subset):
                for j, value in enumerate(row):
                    item = QTableWidgetItem(value if isinstance(value, str) else f"{value:.6g}")
                    item.setToolTip("Independent extrema, not one simultaneous load state. Local member axes; N positive compression. First checked combination wins ties.")
                    table.setItem(i, j, item)
            table.resizeColumnsToContents()
        self.update_plot()

    def update_plot(self):
        from .diagrams import member_breaks, member_values
        self.figure.clear()
        ax = self.figure.add_subplot()
        names, member, quantity = self.selected_combinations(), self.member.currentText(), self.quantity.currentData()
        units, palette = self.project.units, colors()
        if member != self.inspection_member:
            self.inspection_x = 0.0
            self.inspection_member = member
        length = member_breaks(self.project, member)[0] if member else 0
        self.distance.blockSignals(True)
        self.distance.setRange(0, units.to_display(length, "length"))
        self.distance.setSuffix(f" {units.length}")
        self.distance.setValue(units.to_display(self.inspection_x, "length"))
        self.distance.blockSignals(False)
        self.inspection.clearContents()
        if names and member:
            data = member_envelope(self.project, self.result, names, member, quantity)
            value_quantity = "length" if quantity == "deflection" else "moment" if quantity == "moment" else "force"
            value_unit = getattr(units, value_quantity)
            self.inspection.setHorizontalHeaderLabels((f"Minimum ({value_unit})", "Minimum combination",
                                                       f"Maximum ({value_unit})", "Maximum combination"))
            x = units.to_display(data["x"], "length")
            low, high = (units.to_display(data[key], value_quantity) for key in ("minimum", "maximum"))
            ax.plot(x, low, color=palette["shear"], label="Minimum")
            ax.plot(x, high, color=palette["moment"], label="Maximum")
            ax.fill_between(x, low, high, color=palette["shear"], alpha=0.12)
            ax.set_ylabel(f"{self.quantity.currentText()} ({getattr(units, value_quantity)})")
            ax.set_xlabel(f"Distance from start ({units.length})")
            legend = ax.legend(facecolor=palette["canvas"], edgecolor=palette["axis"])
            for text in legend.get_texts():
                text.set_color(palette["text"])
            ax.set_title(f"{member} | {len(names)} combination(s) | Local axes" + (" | + compression" if quantity == "axial" else ""))
            index = ("axial", "shear", "moment", "deflection").index(quantity)
            values = bounds([(member_values(self.project, self.result.for_combination(name), member, self.inspection_x,
                                            self.side.currentData())[index], name) for name in names])
            for col, value in enumerate(values):
                text = value if isinstance(value, str) else f"{units.to_display(value, value_quantity):.6g}"
                self.inspection.setItem(0, col, QTableWidgetItem(text))
            self.inspection.resizeColumnsToContents()
            ax.axvline(units.to_display(self.inspection_x, "length"), color=palette["label"], linestyle="--", linewidth=0.8)
        else:
            ax.set_title("No combinations selected")
        ax.axhline(0, color=palette["axis"], linewidth=0.6)
        style_axes(ax)
        self.canvas.setPalette(self.palette())
        self.canvas.draw_idle()

    def inspect_distance(self):
        from .diagrams import member_breaks
        length = member_breaks(self.project, self.member.currentText())[0]
        self.inspection_x = min(length, max(0, self.project.units.from_display(self.distance.value(), "length")))
        self.update_plot()

    def inspect_click(self, event):
        if event.button != 1 or event.inaxes not in self.figure.axes or event.xdata is None:
            return
        if self.canvas.toolbar and self.canvas.toolbar.mode:
            return
        self.distance.setValue(min(self.distance.maximum(), max(0, event.xdata)))

    def apply_theme(self):
        if hasattr(self, "canvas"):
            self.update_plot()

    def export(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Export Envelope", f"envelope-{self.result.snapshot_id}.csv", "CSV (*.csv)")
        if filename:
            try:
                export_envelope_csv(filename, self.project, self.result, self.selected_combinations(), self.source)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Export failed", str(exc))
