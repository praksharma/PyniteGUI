"""Retained spatial member diagrams in both bending planes and torsion."""
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QToolButton, QVBoxLayout

from .analysis import model_signature
from .spatial_results import LABELS, UNITS, sampled_member
from .theme import colors, style_axes


class SpatialDiagramDialog(QDialog):
    def __init__(self, parent, project, result, selected=None):
        super().__init__(parent)
        self.project, self.result = project.clone(), result
        self.source = str(parent.path or "Untitled")
        self.resize(1000, 850)
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
        button.setText("Export")
        button.setMenu(self.export_menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.snapshot_status = QLabel()
        layout.addWidget(self.snapshot_status)
        self.figure = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        layout.addWidget(self.canvas)
        self.member.currentTextChanged.connect(self.redraw)
        self.combination.currentTextChanged.connect(self.select_combination)
        self.redraw()
        self.update_snapshot_status()

    def select_combination(self, name):
        self.result = self.result.for_combination(name)
        self.redraw()

    def set_unit_system(self, key):
        if self.project.unit_system != key:
            self.project.unit_system = key
            self.redraw()

    def update_snapshot_status(self):
        parent = self.parent()
        current = model_signature(parent.project) == self.result.model_signature and parent.result is not None and parent.result.snapshot_id == self.result.snapshot_id
        self.snapshot_status.setText(f"Analysis {self.result.snapshot_id} | {'Current model' if current else 'Retained snapshot'}")

    def redraw(self, *unused):
        self.figure.clear()
        name, units = self.member.currentText(), self.project.units
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
        self.canvas.draw_idle()

    def apply_theme(self):
        self.redraw()
