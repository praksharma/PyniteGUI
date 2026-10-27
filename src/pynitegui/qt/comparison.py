"""Two combination curves and an exact probe from one retained solver snapshot."""
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .envelopes import selected_results
from .plot_export import SnapshotPlotToolbar, snapshot_metadata
from .theme import colors, style_axes


class ComparisonWidget(QWidget):
    def __init__(self, parent, project, result, source, selected=None):
        super().__init__(parent)
        self.project, self.result, self.source = project, result, source
        self.spatial = getattr(project, "dimension", "2D") == "3D"
        self.inspection_x = 0.
        self.inspection_member = ""
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.first, self.second = QComboBox(), QComboBox()
        names = list(result.solver.load_combos)
        for label, control in (("A", self.first), ("B", self.second)):
            controls.addWidget(QLabel(label))
            control.addItems(names)
            controls.addWidget(control, 1)
        self.first.setCurrentText(result.combination)
        self.second.setCurrentText(next((n for n in names if n != result.combination), result.combination))
        layout.addLayout(controls)
        controls = QHBoxLayout()
        self.member, self.quantity = QComboBox(), QComboBox()
        self.member.addItems(list(project.members))
        if selected in project.members:
            self.member.setCurrentText(selected)
        if self.spatial:
            from .spatial_results import LABELS, QUANTITIES
            choices = zip(LABELS, QUANTITIES)
        else:
            choices = zip(("Axial N", "Shear Fy", "Moment Mz", "Deflection dy"),
                          ("axial", "shear", "moment", "deflection"))
        for label, key in choices:
            self.quantity.addItem(label, key)
        self.distance = QDoubleSpinBox()
        self.distance.setDecimals(8)
        self.distance.setKeyboardTracking(False)
        self.distance.setToolTip("Distance from member start; click the curve to inspect")
        self.side = QComboBox()
        self.side.addItem("Right side", "right")
        self.side.addItem("Left side", "left")
        for control in (self.member, self.quantity, self.distance, self.side):
            controls.addWidget(control)
        layout.addLayout(controls)
        note = QLabel("Same analysis snapshot and method • Local member axes • N positive compression • "
                      "Governing = largest absolute value at the probe; A wins ties")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.inspection = QTableWidget(1, 4)
        self.inspection.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.inspection.verticalHeader().hide()
        self.inspection.setMaximumHeight(76)
        layout.addWidget(self.inspection)
        self.figure = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(SnapshotPlotToolbar(self.canvas, self, self.metadata))
        layout.addWidget(self.canvas)
        for control in (self.first, self.second, self.member, self.quantity, self.side):
            control.currentIndexChanged.connect(self.refresh)
        self.distance.valueChanged.connect(self.inspect_distance)
        self.canvas.mpl_connect("button_press_event", self.inspect_click)
        self.refresh()

    def metadata(self):
        return snapshot_metadata(self, "Combination comparison", combinations=(self.first.currentText(), self.second.currentText()),
                                 member=self.member.currentText(), quantity=self.quantity.currentData(),
                                 inspection_distance=self.distance.value(), inspection_side=self.side.currentData(),
                                 governing="Largest absolute probe value; A wins ties")

    def refresh(self, *unused):
        from .diagrams import member_breaks, member_values, sample_member
        quantities = ("axial", "shear", "moment", "deflection")
        units_by_quantity = ("force", "force", "moment", "length")
        if self.spatial:
            from .spatial_results import member_breaks, inspect_member as member_values, sampled_member, QUANTITIES, UNITS
            quantities, units_by_quantity = QUANTITIES, UNITS
        member, quantity = self.member.currentText(), self.quantity.currentData()
        names = (self.first.currentText(), self.second.currentText())
        # Validate against the retained model, never against the mutable editor.
        results = selected_results(self.project, self.result, tuple(dict.fromkeys(names)))
        results = {r.combination: r for r in results}
        self.figure.clear()
        ax = self.figure.add_subplot()
        self.inspection.clearContents()
        units, palette = self.project.units, colors()
        if member != self.inspection_member:
            self.inspection_x, self.inspection_member = 0., member
        length = member_breaks(self.project, member)[0] if member else 0.
        self.distance.blockSignals(True)
        self.distance.setRange(0, units.to_display(length, "length"))
        self.distance.setSuffix(f" {units.length}")
        self.distance.setValue(units.to_display(self.inspection_x, "length"))
        self.distance.blockSignals(False)
        if member:
            index = quantities.index(quantity)
            dimension = units_by_quantity[index]
            unit = getattr(units, dimension)
            values = []
            for name, role, color, linestyle in zip(names, ("A", "B"), (palette["shear"], palette["moment"]), ("-", "--")):
                result = results[name]
                if self.spatial:
                    xs, samples, _ = sampled_member(self.project, result, member)
                    ys = samples[:, index]
                else:
                    data = sample_member(self.project, result, member)
                    xs, ys = data["x"], data[quantity]
                ax.plot(units.to_display(xs, "length"), units.to_display(ys, dimension),
                        color=color, linestyle=linestyle, label=f"{role}: {name}")
                values.append(member_values(self.project, result, member, self.inspection_x, self.side.currentData())[index])
            governing = 0 if abs(values[0]) >= abs(values[1]) else 1
            self.inspection.setHorizontalHeaderLabels((f"A ({unit})", f"B ({unit})", "Governing combination", f"Governing ({unit})"))
            for col, value in enumerate((*(f"{units.to_display(v, dimension):.6g}" for v in values),
                                         f"{'A' if governing == 0 else 'B'}: {names[governing]}",
                                         f"{units.to_display(values[governing], dimension):.6g}")):
                self.inspection.setItem(0, col, QTableWidgetItem(value))
            self.inspection.resizeColumnsToContents()
            ax.axvline(units.to_display(self.inspection_x, "length"), color=palette["label"], linestyle=":")
            ax.set_xlabel(f"Distance from start ({units.length})")
            ax.set_ylabel(f"{self.quantity.currentText()} ({unit})")
            ax.set_title(f"{member} | Analysis {self.result.snapshot_id} | {self.result.method_label}")
            legend = ax.legend(facecolor=palette["canvas"], edgecolor=palette["axis"])
            for text in legend.get_texts():
                text.set_color(palette["text"])
        else:
            ax.set_title("No members in this snapshot")
        ax.axhline(0, color=palette["axis"], linewidth=.6)
        style_axes(ax)
        self.canvas.draw_idle()

    def inspect_distance(self):
        self.inspection_x = self.project.units.from_display(self.distance.value(), "length")
        self.refresh()

    def inspect_click(self, event):
        if event.button == 1 and event.inaxes in self.figure.axes and event.xdata is not None:
            if not self.canvas.toolbar or not self.canvas.toolbar.mode:
                self.distance.setValue(min(self.distance.maximum(), max(0., event.xdata)))

    def apply_theme(self):
        self.refresh()
