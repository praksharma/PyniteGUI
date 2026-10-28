"""Staged outer-edge restraint editing; accepting creates one project edit."""
from copy import deepcopy
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.collections import PolyCollection
from matplotlib.figure import Figure
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                              QGridLayout, QLabel, QVBoxLayout)

from .spatial_surfaces import surface_geometry
from .surface_supports import DOFS, EDGES, PLANE_AXES, support_segments
from .theme import colors, style_axes


class SurfaceSupportDialog(QDialog):
    def __init__(self, parent, project, name):
        super().__init__(parent)
        self.project, self.name = project.clone(), name
        self.definition = None
        self.setWindowTitle(f"Slab Edge Supports — {name}")
        self.resize(780, 650)
        layout = QVBoxLayout(self)
        mesh = project.surfaces[name]
        u, v, normal = PLANE_AXES[mesh.plane]
        self.axes = (u, v)
        note = QLabel(f"Outer rectangle edges: left/right follow global {'XYZ'[u]}; bottom/top follow global {'XYZ'[v]}. "
                      "Checked DOFs are rigid global restraints. Corners and coincident frame/adjacent-slab joints use the union of all assignments. "
                      "Opening rims are excluded. Assignments follow the recipe when moved, resized or remeshed; a spring on a fixed DOF causes analysis to fail.")
        note.setWordWrap(True)
        layout.addWidget(note)
        grid = QGridLayout()
        for column, text in enumerate(("Edge", "Preset", *DOFS)):
            grid.addWidget(QLabel(text), 0, column)
        normal_dof = DOFS[normal]
        self.presets = {"Free": [], "Normal roller": [normal_dof],
                        "Bending clamp": [normal_dof, *(DOFS[i+3] for i in range(3) if i != normal)],
                        "Translations fixed": list(DOFS[:3]), "Fixed (six DOFs)": list(DOFS), "Custom": None}
        self.checks, self.choices = {}, {}
        for row, edge in enumerate(EDGES, 1):
            grid.addWidget(QLabel(edge.title()), row, 0)
            choice = QComboBox()
            choice.setObjectName(f"surface_support_{edge}_preset")
            choice.addItems(list(self.presets))
            self.choices[edge] = choice
            grid.addWidget(choice, row, 1)
            flags = self.checks[edge] = {}
            selected = project.surface_supports.get(name, {}).get(edge, [])
            choice.setCurrentText(next((key for key, value in self.presets.items() if value is not None and set(value) == set(selected)), "Custom"))
            for column, dof in enumerate(DOFS, 2):
                check = QCheckBox()
                check.setObjectName(f"surface_support_{edge}_{dof}")
                check.setAccessibleName(f"{edge} {dof}")
                check.setChecked(dof in selected)
                grid.addWidget(check, row, column)
                flags[dof] = check
                check.toggled.connect(lambda _, edge=edge: self.custom(edge))
            choice.currentTextChanged.connect(lambda text, edge=edge: self.preset(edge, text))
        layout.addLayout(grid)
        self.figure = Figure(figsize=(6, 3), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def values(self):
        return {edge: [dof for dof, check in flags.items() if check.isChecked()]
                for edge, flags in self.checks.items() if any(check.isChecked() for check in flags.values())}

    def custom(self, edge):
        self.choices[edge].blockSignals(True)
        self.choices[edge].setCurrentText("Custom")
        self.choices[edge].blockSignals(False)
        self.refresh()

    def preset(self, edge, text):
        if self.presets[text] is not None:
            for dof, check in self.checks[edge].items():
                check.blockSignals(True)
                check.setChecked(dof in self.presets[text])
                check.blockSignals(False)
        self.refresh()

    def refresh(self):
        self.project.surface_supports[self.name] = self.values()
        u, v = self.axes
        units = self.project.units
        _, _, points, cells = surface_geometry(self.project.surfaces[self.name])
        xy = np.asarray(points)[:, [u, v]]*units.length_factor
        self.figure.clear()
        ax = self.figure.add_subplot()
        ax.add_collection(PolyCollection([xy[list(cell)] for cell in cells], facecolor=colors()["selection"],
                                         edgecolor=colors()["muted"], linewidth=.5))
        for support in support_segments(self.project, self.name):
            for segment in support["segments"]:
                line = np.asarray(segment)[:, [u, v]]*units.length_factor
                ax.plot(line[:, 0], line[:, 1], color=colors()["support"], linewidth=3)
            segment = support["segments"][len(support["segments"])//2] if support["segments"] else None
            if segment:
                centre = np.asarray(segment).mean(axis=0)[[u, v]]*units.length_factor
                ax.annotate(support["edge"]+": "+", ".join(support["dofs"]), centre, xytext=(5, 5),
                            textcoords="offset points", fontsize=8, color=colors()["text"])
        ax.autoscale_view()
        ax.margins(.16)
        ax.set_aspect("equal")
        ax.set_xlabel(f"Global {'XYZ'[u]} ({units.length})")
        ax.set_ylabel(f"Global {'XYZ'[v]} ({units.length})")
        ax.set_title("Staged edge restraints — frame-joint supports remain additional")
        style_axes(ax)
        self.figure.set_facecolor(colors()["canvas"])
        self.canvas.draw_idle()

    def accept(self):
        self.definition = deepcopy(self.values())
        super().accept()

    def apply_theme(self):
        if hasattr(self, "canvas"):
            self.refresh()


def edit_surface_supports(window, name):
    dialog = SurfaceSupportDialog(window, window.project, name)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        def mutate(project):
            if dialog.definition:
                project.surface_supports[name] = dialog.definition
            else:
                project.surface_supports.pop(name, None)
        window.edit("Set slab edge supports", mutate)
