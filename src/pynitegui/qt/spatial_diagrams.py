"""Retained spatial member diagrams in both bending planes and torsion."""
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QStyle, QTabWidget, QTableWidget, QTableWidgetItem,
                               QToolButton, QVBoxLayout, QWidget)

from .analysis import model_signature
from .spatial_results import LABELS, UNITS, inspect_member, member_breaks, sampled_member
from .theme import colors, style_axes


class SpatialDiagramDialog(QDialog):
    def __init__(self, parent, project, result, selected=None):
        super().__init__(parent)
        self.project, self.result = project.clone(), result
        self.source = str(getattr(parent, "path", None) or "Untitled")
        self.resize(1100, 900)
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.member = QComboBox()
        self.member.addItems(list(project.members))
        if selected:
            self.member.setCurrentText(selected)
        self.combination = QComboBox()
        self.combination.addItems(list(result.solver.load_combos))
        self.combination.setCurrentText(result.combination)
        toolbar.addWidget(self.member)
        toolbar.addWidget(self.combination)
        toolbar.addStretch()
        from .reports import ResultExportMenu
        self.export_menu = ResultExportMenu(self, lambda: (self.project, self.result, self.source))
        button = QToolButton()
        button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        button.setToolTip("Export or print analysis results")
        button.setMenu(self.export_menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.snapshot_status = QLabel()
        layout.addWidget(self.snapshot_status)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.tabs.addTab(detail, "Member Detail")
        inspection = QHBoxLayout()
        inspection.addWidget(QLabel("Distance"))
        self.distance = QDoubleSpinBox()
        self.distance.setDecimals(8)
        self.distance.setKeyboardTracking(False)
        self.distance.setToolTip("Distance from member start; click a plot to inspect")
        inspection.addWidget(self.distance)
        self.inspection_side = QComboBox()
        self.inspection_side.addItem("Right side", "right")
        self.inspection_side.addItem("Left side", "left")
        self.inspection_side.setToolTip("One-sided solver value at an interior load boundary")
        inspection.addWidget(self.inspection_side)
        inspection.addStretch()
        detail_layout.addLayout(inspection)
        self.inspection_values = QTableWidget(1, len(LABELS))
        self.inspection_values.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.inspection_values.verticalHeader().hide()
        self.inspection_values.setMaximumHeight(75)
        detail_layout.addWidget(self.inspection_values)
        self.inspection_x = 0.
        self.inspection_member = self.member.currentText()
        self.probes = []
        self.figure = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        detail_layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        detail_layout.addWidget(self.canvas)
        from .envelopes import EnvelopeWidget
        self.envelopes = EnvelopeWidget(self, self.project, self.result, self.source, selected)
        self.tabs.addTab(self.envelopes, "Combination Envelopes")
        self.member.currentTextChanged.connect(self.redraw)
        self.combination.currentTextChanged.connect(self.select_combination)
        self.distance.valueChanged.connect(self.inspect_distance)
        self.inspection_side.currentIndexChanged.connect(self.update_inspection)
        self.canvas.mpl_connect("button_press_event", self.inspect_click)
        self.redraw()
        self.update_snapshot_status()

    def select_combination(self, name):
        self.result = self.result.for_combination(name)
        self.redraw()

    def set_unit_system(self, key):
        if self.project.unit_system != key:
            self.project.unit_system = key
            self.redraw()
            self.envelopes.refresh()

    def update_snapshot_status(self):
        parent = self.parent()
        current = (parent is not None and model_signature(parent.project) == self.result.model_signature
                   and parent.result is not None and parent.result.snapshot_id == self.result.snapshot_id)
        self.snapshot_status.setText(f"Analysis {self.result.snapshot_id} | {'Current model' if current else 'Retained snapshot'}")

    def redraw(self, *unused):
        self.figure.clear()
        name, units = self.member.currentText(), self.project.units
        if name != self.inspection_member:
            self.inspection_x = 0.
            self.inspection_member = name
        length, _ = member_breaks(self.project, name)
        self.distance.blockSignals(True)
        self.distance.setRange(0, units.to_display(length, "length"))
        self.distance.setSuffix(f" {units.length}")
        self.distance.setValue(units.to_display(self.inspection_x, "length"))
        self.distance.blockSignals(False)
        self.probes = []
        xs, values, _ = sampled_member(self.project, self.result, name)
        for index, (label, quantity) in enumerate(zip(LABELS, UNITS)):
            ax = self.figure.add_subplot(4, 2, index + 1)
            ax.plot(xs * units.factor("length"), values[:, index] * units.factor(quantity), color=colors()["accent"])
            ax.axhline(0, color=colors()["axis"], linewidth=.7)
            ax.set_ylabel(f"{label} ({getattr(units, quantity)})")
            if index >= 6:
                ax.set_xlabel(f"Distance from start ({units.length})")
            style_axes(ax)
        self.setWindowTitle(f"{name} | {self.result.combination} | Local 3D member axes")
        self.update_inspection()
        self.canvas.draw_idle()

    def inspect_distance(self):
        length, _ = member_breaks(self.project, self.member.currentText())
        self.inspection_x = min(length, max(0., self.project.units.from_display(self.distance.value(), "length")))
        self.update_inspection()

    def inspect_click(self, event):
        if event.button != 1 or event.inaxes not in self.figure.axes or event.xdata is None:
            return
        if self.canvas.toolbar and self.canvas.toolbar.mode:
            return
        self.distance.setValue(min(self.distance.maximum(), max(0., event.xdata)))

    def update_inspection(self):
        units = self.project.units
        values = inspect_member(self.project, self.result, self.member.currentText(), self.inspection_x,
                                self.inspection_side.currentData())
        self.inspection_values.setHorizontalHeaderLabels([f"{label} ({getattr(units, quantity)})"
                                                          for label, quantity in zip(LABELS, UNITS)])
        for col, (value, quantity) in enumerate(zip(values, UNITS)):
            item = QTableWidgetItem(f"{units.to_display(value, quantity):.6g}")
            item.setToolTip("Local rolled member axes; N positive compression. Numerical solver signs, without display amplification.")
            self.inspection_values.setItem(0, col, item)
        self.inspection_values.resizeColumnsToContents()
        for line in self.probes:
            line.remove()
        self.probes = [ax.axvline(units.to_display(self.inspection_x, "length"), color=colors()["label"],
                                  linestyle="--", linewidth=.8) for ax in self.figure.axes]
        self.canvas.draw_idle()

    def apply_theme(self):
        self.redraw()
        self.envelopes.apply_theme()
