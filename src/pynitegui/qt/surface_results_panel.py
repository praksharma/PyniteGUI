"""Local slab inspection inside the main Results dock."""
import csv
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.collections import PolyCollection
from matplotlib.figure import Figure
from matplotlib.path import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout,
                              QLabel, QMessageBox, QPushButton, QSplitter, QTableWidget,
                              QVBoxLayout, QWidget)

from .spatial_surfaces import surface_geometry
from .surface_supports import PLANE_AXES
from .surface_results import FIELDS, QUAD_SHEAR_LIMITATION, centre_results, field_units, inspect_surface, surface_table
from .theme import colors, style_axes


class SurfaceResultsPanel(QWidget):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel, self.project, self.result = panel, None, None
        self.rows, self.polygons, self.artist = (), [], None
        self.dirty = True
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.surface, self.field, self.element = QComboBox(), QComboBox(), QComboBox()
        self.surface.setObjectName("surface_result_mesh")
        self.field.setObjectName("surface_result_field")
        self.element.setObjectName("surface_result_element")
        for key, (label, _) in FIELDS.items():
            self.field.addItem(label, key)
        for title, control in (("Slab", self.surface), ("Contour", self.field), ("Element", self.element)):
            control.setAccessibleName(title)
            row.addWidget(QLabel(title))
            row.addWidget(control)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.xi, self.eta = QDoubleSpinBox(), QDoubleSpinBox()
        for title, control in (("xi", self.xi), ("eta", self.eta)):
            control.setRange(-1., 1.)
            control.setDecimals(6)
            control.setSingleStep(.1)
            control.setKeyboardTracking(False)
            control.setAccessibleName("Surface probe " + title)
            row.addWidget(QLabel(title))
            row.addWidget(control)
            control.valueChanged.connect(self.update_probe)
        self.export = QPushButton("Export Slab CSV…")
        self.export.clicked.connect(self.export_csv)
        row.addStretch()
        row.addWidget(self.export)
        layout.addLayout(row)
        note = QLabel("Local axes: x from element i→j, y from i→n, z = x×y. Membrane stresses: tension positive. "
                      "Moments are per unit width. Contours use unsmoothed element centres. "
                      "Click a face to probe; xi/eta ±1 are element edges. Corner peaks and design checks are unverified.")
        note.setWordWrap(True)
        layout.addWidget(note)
        limitation = QLabel("Quad transverse shear is unavailable pending independent validation.")
        limitation.setToolTip(QUAD_SHEAR_LIMITATION)
        limitation.setWordWrap(True)
        layout.addWidget(limitation)
        self.probe = QLabel("Run coupled analysis to inspect slab results.")
        self.probe.setWordWrap(True)
        self.probe.setTextFormat(Qt.TextFormat.PlainText)
        self.probe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.probe)
        splitter = QSplitter()
        plot = QWidget()
        plot_layout = QVBoxLayout(plot)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(5, 3), layout="compressed")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumSize(250, 170)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)
        self.table = QTableWidget()
        self.table.setObjectName("surface_result_table")
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        from .results_panel import ResultDelegate
        self.table.setItemDelegate(ResultDelegate(self.table))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        splitter.addWidget(plot)
        splitter.addWidget(self.table)
        layout.addWidget(splitter)
        self.surface.currentIndexChanged.connect(lambda: self.choose_surface(select=True))
        self.field.currentIndexChanged.connect(self.draw)
        self.element.currentIndexChanged.connect(self.update_probe)
        self.table.itemSelectionChanged.connect(self.choose_row)
        self.canvas.mpl_connect("button_press_event", self.click_plot)

    def set_snapshot(self, project, result):
        self.project, self.result, self.dirty = project, result, True
        name = self.surface.currentText()
        self.surface.blockSignals(True)
        self.surface.clear()
        for surface in getattr(result.solver, "_pynitegui_surfaces", {}) if result else ():
            self.surface.addItem(surface)
        self.surface.setCurrentIndex(max(0, self.surface.findText(name)))
        self.surface.blockSignals(False)
        self.setEnabled(result is not None and self.surface.count() > 0)
        # Never leave an old plot/table in a cleared or unrelated snapshot.
        self.clear_view("Run coupled analysis to inspect slab results.")
        if self.isVisible():
            self.ensure_loaded()

    def ensure_loaded(self):
        if self.dirty and self.result is not None and self.surface.count():
            self.choose_surface()

    def clear_view(self, message):
        self.rows, self.polygons, self.artist = (), [], None
        self.figure.clear()
        self.table.setRowCount(0)
        self.element.clear()
        self.probe.setText(message)
        self.export.setEnabled(False)
        self.canvas.draw_idle()

    def choose_surface(self, select=False):
        if self.result is None or not self.surface.currentText():
            return
        name = self.surface.currentText()
        try:
            self.rows = centre_results(self.result, name)
            headers, rows = surface_table(self.project, self.result, name)
            self.panel.populate(self.table, headers, rows)
            self.element.blockSignals(True)
            old = self.element.currentText()
            self.element.clear()
            self.element.addItems([row["element"] for row in self.rows])
            self.element.setCurrentIndex(max(0, self.element.findText(old)))
            self.element.blockSignals(False)
            self.dirty = False
            self.export.setEnabled(True)
            self.draw()
            if select:
                self.panel.entities_selected.emit([("surfaces", name)])
        except Exception as error:
            self.dirty = False
            self.clear_view(f"Slab results unavailable: {error}")

    def draw(self):
        if not self.rows or self.result is None:
            return
        name, key = self.surface.currentText(), self.field.currentData()
        definition, units = self.project.surfaces[name], self.project.units
        u, v, _ = PLANE_AXES[definition.plane]
        _, _, points, cells = surface_geometry(definition)
        points = np.asarray(points)[:, [u, v]] * units.length_factor
        self.polygons = [points[list(cell)] for cell in cells]
        factor, unit = field_units(units, key)
        values = np.array([row[key] * factor for row in self.rows])
        bound = max(float(np.abs(values).max()), 1e-15)
        self.figure.clear()
        ax = self.figure.add_subplot()
        self.artist = PolyCollection(self.polygons, array=values, cmap="coolwarm", clim=(-bound, bound),
                                     edgecolors=colors()["member"], linewidths=.35)
        ax.add_collection(self.artist)
        ax.autoscale_view()
        ax.set_aspect("equal")
        ax.set_xlabel(f"Global {'XYZ'[u]} ({units.length})")
        ax.set_ylabel(f"Global {'XYZ'[v]} ({units.length})")
        ax.set_title(f"{name} | {key} ({unit}) | {self.result.combination}\n"
                     f"Snapshot {self.result.snapshot_id} | element centres, unsmoothed", fontsize=9)
        style_axes(ax)
        self.figure.set_facecolor(colors()["canvas"])
        bar = self.figure.colorbar(self.artist, ax=ax, label=f"{key} ({unit})", shrink=.8)
        style_axes(bar.ax)
        self.ax = ax
        self.marker, = ax.plot([], [], "+", color=colors()["text"], markersize=9)
        self.update_probe()

    def update_probe(self, *_):
        name, element = self.surface.currentText(), self.element.currentText()
        if self.result is None or not element or not self.rows:
            return
        try:
            row = inspect_surface(self.result, name, element, self.xi.value(), self.eta.value())
            units = self.project.units
            position = ", ".join(f"{value*units.length_factor:.6g}" for value in row["position"])
            values = " | ".join(f"{key} {row[key]*field_units(units, key)[0]:.6g} {field_units(units, key)[1]}" for key in FIELDS)
            axes = "; ".join(f"{axis}=({', '.join(f'{value:g}' for value in vector)})" for axis, vector in zip("xyz", row["axes"]))
            self.probe.setText(f"{element} | XYZ ({position}) {units.length} | {values}\nLocal unit axes: {axes}")
            if self.artist is not None:
                u, v, _ = PLANE_AXES[self.project.surfaces[name].plane]
                self.marker.set_data([row["position"][u]*units.length_factor], [row["position"][v]*units.length_factor])
                self.canvas.draw_idle()
        except ValueError as error:
            self.probe.setText(str(error))

    def choose_row(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.xi.blockSignals(True)
            self.eta.blockSignals(True)
            self.xi.setValue(0.)
            self.eta.setValue(0.)
            self.xi.blockSignals(False)
            self.eta.blockSignals(False)
            self.element.setCurrentText(self.table.item(rows[0].row(), 0).text())
            self.update_probe()

    def click_plot(self, event):
        if (self.result is None or event.inaxes is not getattr(self, "ax", None) or event.button != 1
                or self.toolbar.mode or event.xdata is None or event.ydata is None):
            return
        point = np.array((event.xdata, event.ydata))
        for index, polygon in enumerate(self.polygons):
            if Path(polygon).contains_point(point):
                name = self.surface.currentText()
                row = self.rows[index]
                quad = self.result.solver.quads[row["element"]]
                u, v, _ = PLANE_AXES[self.project.surfaces[name].plane]
                origin = np.array((quad.i_node.X, quad.i_node.Y, quad.i_node.Z))
                position = origin.copy()
                position[[u, v]] = point/self.project.units.length_factor
                delta = position-origin
                width = np.linalg.norm(np.array((quad.j_node.X, quad.j_node.Y, quad.j_node.Z))-origin)
                height = np.linalg.norm(np.array((quad.n_node.X, quad.n_node.Y, quad.n_node.Z))-origin)
                self.xi.blockSignals(True)
                self.eta.blockSignals(True)
                self.xi.setValue(float(2*np.dot(delta, row["axes"][0])/width-1))
                self.eta.setValue(float(2*np.dot(delta, row["axes"][1])/height-1))
                self.xi.blockSignals(False)
                self.eta.blockSignals(False)
                self.element.setCurrentText(row["element"])
                self.update_probe()
                break

    def export_csv(self):
        if self.result is None or not self.rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Slab Element Centres", "slab-elements.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            self.write_csv(path)
        except OSError as error:
            QMessageBox.warning(self, "Export Slab Results", str(error))

    def apply_theme(self):
        if hasattr(self, "canvas") and self.rows:
            self.draw()

    def write_csv(self, path):
        name = self.surface.currentText()
        headers, rows = surface_table(self.project, self.result, name)
        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["# Snapshot", self.result.snapshot_id, "Combination", self.result.combination,
                             "Surface", name, "Analyzed UTC", self.result.analyzed_at])
            writer.writerow(["# Model signature", self.result.model_signature])
            writer.writerow(["# Unsmoothed element centres (xi=eta=0); membrane tension positive; no combined face stresses or design checks"])
            writer.writerow([*headers, *(f"local {axis} global {component}" for axis in "xyz" for component in "XYZ")])
            for row, canonical in zip(rows, centre_results(self.result, name)):
                writer.writerow([*row, *np.array(canonical["axes"]).ravel().tolist()])
