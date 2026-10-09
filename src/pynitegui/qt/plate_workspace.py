"""Separate transverse-plate pilot; no implicit conversion of frame projects."""
import csv
import json

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.collections import PolyCollection
from matplotlib.figure import Figure
from PySide6.QtCore import QSaveFile, QIODevice, QThread
from PySide6.QtGui import QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                              QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
                              QStyle, QToolBar, QVBoxLayout, QWidget)

from .analysis_jobs import AnalysisWorker, AnalysisCancelled, CANCELLED, execute_analysis
from .plate_model import PlateDefinition, EDGES, PLANES, build_plate, plate_geometry, plate_analysis_child
from .units import UNIT_SYSTEMS
from .theme import colors, style_axes


class PlateWorker(AnalysisWorker):
    def run(self):
        try:
            result = execute_analysis(self.project, self.progress.emit, self.cancelled, target=plate_analysis_child)
            self.finished.emit(result, "")
        except AnalysisCancelled:
            self.finished.emit(None, CANCELLED)
        except Exception as error:
            self.finished.emit(None, str(error))


class PlateEdit(QUndoCommand):
    def __init__(self, window, before, after):
        super().__init__("Change plate")
        self.window, self.before, self.after = window, before, after

    def undo(self):
        self.window.install(self.before)

    def redo(self):
        self.window.install(self.after)


class PlateWorkspace(QDialog):
    def __init__(self, parent=None, unit_system="imperial"):
        super().__init__(parent)
        self.setWindowTitle("Rectangular Plate (Experimental)")
        self.resize(1100, 760)
        self.definition = PlateDefinition(unit_system=unit_system)
        self.result, self.thread, self.worker, self.path = None, None, None, None
        self.pending, self.loading = False, False
        self.saved = self.definition.to_dict()
        self.undo = QUndoStack(self)
        root = QVBoxLayout(self)
        toolbar = QToolBar()
        self.toolbar = toolbar
        root.addWidget(toolbar)
        for text, icon, callback in (("Open plate", QStyle.StandardPixmap.SP_DialogOpenButton, self.open_file),
                                     ("Save plate", QStyle.StandardPixmap.SP_DialogSaveButton, self.save_file)):
            action = toolbar.addAction(self.style().standardIcon(icon), text)
            action.setToolTip(text)
            action.triggered.connect(callback)
        for text, icon, action in (("Undo", QStyle.StandardPixmap.SP_ArrowBack, self.undo.createUndoAction(self, "Undo")),
                                  ("Redo", QStyle.StandardPixmap.SP_ArrowForward, self.undo.createRedoAction(self, "Redo"))):
            action.setIcon(self.style().standardIcon(icon))
            action.setToolTip(text)
            toolbar.addAction(action)
        self.export_action = toolbar.addAction("Export CSV", self.export_csv)
        self.export_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.export_action.setEnabled(False)
        splitter = QSplitter()
        root.addWidget(splitter, 1)
        self.controls = QWidget()
        form = QFormLayout(self.controls)
        self.form = form
        self.units_box = QComboBox()
        for key in ("imperial", "si", "si_mm", "imperial_ft"):
            self.units_box.addItem(UNIT_SYSTEMS[key].label, key)
        if unit_system not in ("imperial", "si", "si_mm", "imperial_ft"):
            self.units_box.addItem(UNIT_SYSTEMS[unit_system].label, unit_system)
        form.addRow("Units", self.units_box)
        self.plane = QComboBox()
        self.plane.addItems(list(PLANES))
        form.addRow("Plane", self.plane)
        from .app import number
        self.fields = {}
        for key in ("width", "height", "thickness", "mesh_size", "E", "nu", "pressure", "load_factor"):
            widget = number(0, -1e12, 1e12, 8)
            widget.setObjectName("plate_" + key)
            self.fields[key] = widget
            form.addRow(key, widget)
            widget.valueChanged.connect(self.mark_pending)
        self.case = QLineEdit()
        form.addRow("Load case", self.case)
        self.case.textChanged.connect(self.mark_pending)
        self.supports = {}
        for edge in EDGES:
            box = QComboBox()
            box.addItems(["Free", "Simply supported", "Clamped"])
            form.addRow(edge, box)
            box.currentTextChanged.connect(self.mark_pending)
            self.supports[edge] = box
        self.normal_label = QLabel()
        form.addRow("Positive pressure", self.normal_label)
        self.apply_button = QPushButton("Apply / Preview Mesh")
        self.apply_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.apply_button.clicked.connect(self.apply)
        form.addRow(self.apply_button)
        row = QHBoxLayout()
        self.run_button, self.cancel_button = QPushButton("Analyze"), QPushButton("Cancel")
        self.run_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.cancel_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserStop))
        self.run_button.clicked.connect(self.run_analysis)
        self.cancel_button.clicked.connect(lambda: self.worker.cancel() if self.worker else None)
        self.cancel_button.setEnabled(False)
        row.addWidget(self.run_button)
        form.addRow(row)
        splitter.addWidget(self.controls)
        display = QWidget()
        layout = QVBoxLayout(display)
        self.component = QComboBox()
        self.component.addItems(["Mesh", "Normal displacement", "Mx (element centre)",
                                 "My (element centre)", "Mxy (element centre)",
                                 "Qx (element centre)", "Qy (element centre)"])
        self.component.currentIndexChanged.connect(self.draw)
        layout.addWidget(self.component)
        self.figure = Figure()
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        layout.addWidget(self.canvas, 1)
        splitter.addWidget(display)
        splitter.setSizes([310, 790])
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addWidget(self.cancel_button)
        self.units_box.currentIndexChanged.connect(self.change_units)
        self.plane.currentTextChanged.connect(self.mark_pending)
        self.install(self.definition.to_dict())

    def install(self, data):
        self.definition = PlateDefinition.from_dict(data)
        self.loading = True
        units = self.definition.units
        if self.units_box.findData(units.key) < 0:
            self.units_box.addItem(units.label, units.key)
        self.units_box.setCurrentIndex(self.units_box.findData(units.key))
        self.plane.setCurrentText(self.definition.plane)
        labels = {"width": "Width", "height": "Height", "thickness": "Thickness", "mesh_size": "Mesh size",
                  "E": "Elastic modulus", "nu": "Poisson ratio", "pressure": "Pressure", "load_factor": "Combination factor"}
        for key, widget in self.fields.items():
            value = getattr(self.definition.material, key) if key in ("E", "nu") else getattr(self.definition, key)
            factor, label = self.quantity(key, units)
            widget.setValue(value * factor)
            widget.setProperty("canonical", value)
            widget.setProperty("initial", widget.value())
            self.form.labelForField(widget).setText(labels[key] + (f" ({label})" if label else ""))
        self.case.setText(self.definition.load_case)
        for edge, box in self.supports.items():
            box.setCurrentText(self.definition.edges[edge])
        _, _, axis, sign = PLANES[self.definition.plane]
        self.normal_label.setText(("+" if sign > 0 else "-") + "XYZ"[axis])
        self.pending, self.loading, self.result = False, False, None
        self.export_action.setEnabled(False)
        self.component.setCurrentIndex(0)
        self.draw()

    @staticmethod
    def quantity(key, units):
        if key in ("width", "height", "thickness", "mesh_size"):
            return units.factor("length"), units.length
        if key == "E":
            return units.factor("stress"), units.stress
        if key == "pressure":
            return units.force_factor / units.length_factor**2, units.force + "/" + units.length + "2"
        return 1, ""

    def mark_pending(self, *_):
        if self.loading:
            return
        self.pending, self.result = True, None
        self.export_action.setEnabled(False)
        self.component.setCurrentIndex(0)
        self.draw()
        self.status.setText("Unapplied changes | Results cleared")

    def candidate(self):
        definition = PlateDefinition.from_dict(self.definition.to_dict())
        for key, widget in self.fields.items():
            widget.interpretText()
            factor, _ = self.quantity(key, self.definition.units)
            value = widget.property("canonical") if widget.value() == widget.property("initial") else widget.value() / factor
            if key in ("E", "nu") and value != getattr(definition.material, key):
                definition.material.preset = None
            setattr(definition.material if key in ("E", "nu") else definition, key, value)
        definition.plane = self.plane.currentText()
        definition.load_case = self.case.text()
        definition.edges = {edge: box.currentText() for edge, box in self.supports.items()}
        definition.validate()
        return definition

    def apply(self):
        try:
            candidate = self.candidate()
            before, after = self.definition.to_dict(), candidate.to_dict()
            if before != after:
                self.undo.push(PlateEdit(self, before, after))
            else:
                self.pending = False
                self.draw()
            return True
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Plate", str(error))
            return False

    def change_units(self, *_):
        if self.loading:
            return
        key = self.units_box.currentData()
        if not self.apply():
            self.loading = True
            self.units_box.setCurrentIndex(self.units_box.findData(self.definition.unit_system))
            self.loading = False
            return
        before = self.definition.to_dict()
        after = {**before, "unit_system": key}
        if before != after:
            self.undo.push(PlateEdit(self, before, after))

    def draw(self, *_):
        if not hasattr(self, "canvas"):
            return
        model = build_plate(self.definition)
        _, points, cells = plate_geometry(model, self.definition)
        units = self.definition.units
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        palette = colors()
        polygons = points[cells] * units.length_factor
        index = self.component.currentIndex()
        values, label = None, ""
        if self.result is not None and index:
            if index == 1:
                values = self.result["displacement"] * units.length_factor
                triangles = np.vstack((cells[:, [0, 1, 2]], cells[:, [0, 2, 3]]))
                artist = ax.tripcolor(points[:, 0]*units.length_factor, points[:, 1]*units.length_factor,
                                      triangles, values, shading="gouraud", cmap="coolwarm")
                label = units.length
            else:
                moment = index < 5
                values = self.result["moments" if moment else "shears"][:, index-2 if moment else index-5]
                values = values * units.factor("force" if moment else "intensity")
                artist = PolyCollection(polygons, array=values, cmap="coolwarm")
                ax.add_collection(artist)
                label = units.force if moment else units.intensity
            peak = max(float(np.max(np.abs(values))), 1e-15)
            artist.set_clim(-peak, peak)
            self.figure.colorbar(artist, ax=ax, label=label)
        ax.add_collection(PolyCollection(polygons, facecolors="none" if values is not None else palette["selection"],
                                         edgecolors=palette["muted"], linewidths=0.6))
        width, height = self.definition.width*units.length_factor, self.definition.height*units.length_factor
        edge_points = (((0, 0), (0, height)), ((width, 0), (width, height)),
                       ((0, 0), (width, 0)), ((0, height), (width, height)))
        for edge, endpoints in zip(EDGES, edge_points):
            support = self.definition.edges[edge]
            if support != "Free":
                xy = np.array(endpoints)
                ax.plot(xy[:, 0], xy[:, 1], color=palette["support"], linewidth=3,
                        linestyle="-" if support == "Clamped" else "--")
        u, v, _, _ = PLANES[self.definition.plane]
        ax.set_xlabel(f"Local x / Global {'XYZ'[u]} ({units.length})")
        ax.set_ylabel(f"Local y / Global {'XYZ'[v]} ({units.length})")
        ax.set_title(self.component.currentText() + " | DKMQ quads")
        ax.autoscale()
        ax.set_aspect("equal")
        for axis in self.figure.axes:
            style_axes(axis)
        self.figure.tight_layout()
        self.canvas.draw_idle()
        if self.result is None:
            self.status.setText(f"{len(points)} nodes | {len(cells)} quads | Transverse bending only | In-plane motion restrained")
        else:
            peak = max(abs(self.result["displacement"])) * units.length_factor
            reaction = self.result["reactions"].sum() * units.force_factor
            self.status.setText(f"{len(cells)} quads | Max |normal displacement| {peak:.6g} {units.length} | "
                                f"Normal reaction sum {reaction:.6g} {units.force} | {self.definition.load_case} x {self.definition.load_factor:g}")
            if max(abs(self.result["displacement"])) > self.definition.thickness / 2:
                self.status.setText(self.status.text() + " | Large deflection: linear plate assumptions may be invalid")

    def run_analysis(self):
        if self.thread is not None or not self.apply():
            return
        self.thread = QThread(self)
        self.worker = PlateWorker(PlateDefinition.from_dict(self.definition.to_dict()))
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.analysis_stopped)
        self.controls.setEnabled(False)
        self.toolbar.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.thread.start()

    def analysis_finished(self, result, error):
        self.result = result
        self.export_action.setEnabled(result is not None)
        if error:
            self.status.setText(error)
            if error != CANCELLED:
                QMessageBox.warning(self, "Plate Analysis", error)
        else:
            self.component.setCurrentIndex(1)
            self.draw()

    def analysis_stopped(self):
        self.thread.deleteLater()
        self.thread, self.worker = None, None
        self.controls.setEnabled(True)
        self.toolbar.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def confirm_discard(self):
        if self.pending or self.definition.to_dict() != self.saved:
            return QMessageBox.question(self, "Unsaved Plate", "Discard unsaved plate changes?",
                                        QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                        QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Discard
        return True

    def open_file(self):
        if self.thread is not None or not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Plate", "", "Plate (*.pyniteplate)")
        if not path:
            return
        try:
            definition = PlateDefinition.open(path)
            self.install(definition.to_dict())
            self.undo.clear()
            self.path, self.saved = path, definition.to_dict()
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Open Plate", str(error))

    def save_file(self):
        if self.thread is not None or not self.apply():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Plate", self.path or "plate.pyniteplate", "Plate (*.pyniteplate)")
        if not path:
            return
        if not path.endswith(".pyniteplate"):
            path += ".pyniteplate"
        data = json.dumps(self.definition.to_dict(), indent=2).encode()
        file = QSaveFile(path)
        if not file.open(QIODevice.OpenModeFlag.WriteOnly) or file.write(data) != len(data) or not file.commit():
            QMessageBox.warning(self, "Save Plate", file.errorString())
            return
        self.path, self.saved = path, self.definition.to_dict()

    def export_csv(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Plate Nodes", "plate-nodes.csv", "CSV (*.csv)")
        if not path:
            return
        units = self.definition.units
        try:
            with open(path, "w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Node", f"Local x ({units.length})", f"Local y ({units.length})",
                                 f"Normal displacement ({units.length})", f"Normal reaction ({units.force})",
                                 "Load case", "Factor"])
                for name, point, displacement, reaction in zip(self.result["names"], self.result["points"],
                        self.result["displacement"], self.result["reactions"]):
                    writer.writerow([name, *(point*units.length_factor), displacement*units.length_factor,
                                     reaction*units.force_factor, self.definition.load_case, self.definition.load_factor])
        except OSError as error:
            QMessageBox.warning(self, "Export Plate", str(error))

    def reject(self):
        if self.thread is not None:
            self.worker.cancel()
            self.status.setText("Cancelling plate analysis; close again after it stops")
            return
        if self.confirm_discard():
            super().reject()

    def closeEvent(self, event):
        event.ignore()
        self.reject()
