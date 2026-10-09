"""Offline Three.js viewport and validated native editing bridge."""
import json
import base64
import math
import os
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QUrl, Slot, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QStyle, QToolButton, QVBoxLayout, QWidget

from .annotations import combination_loads
from .spatial_results import LABELS, QUANTITIES, diagram_metadata, member_axes, sampled_member
from .theme import colors


def viewport_payload(window):
    project, result = window.project, window.result
    nodes = [{"name": n.name, "position": list(n.coords), "restraints": list(n.restraints), "springs": list(n.springs)}
             for n in project.nodes.values()]
    members, peak, samples = [], 0., []
    kind = window.view.diagram.currentData()
    axes = {}
    for member in project.members.values():
        axes[member.name] = member_axes(project, member.name, result)
        definition = {"name": member.name, "start": member.start, "end": member.end, "axes": axes[member.name].tolist()}
        if result is not None:
            positions, values, displacement = sampled_member(project, result, member.name)
            a, b = np.array(project.nodes[member.start].coords), np.array(project.nodes[member.end].coords)
            points = a + positions[:, None] / math.dist(a, b) * (b - a)
            definition["points"] = points.tolist()
            definition["displacements"] = displacement.tolist()
            if kind in QUANTITIES[:6]:
                definition["diagramValues"] = values[:, QUANTITIES.index(kind)].tolist()
                samples.append(values)
            peak = max(peak, float(np.linalg.norm(displacement, axis=1).max()))
        members.append(definition)
    extent = max((max(n.coords[i] for n in project.nodes.values()) - min(n.coords[i] for n in project.nodes.values())
                  for i in range(3)), default=0) if project.nodes else 0
    mode = window.deformation_mode.currentData()
    visible = result is not None and window.deformed_action.isChecked()
    window.deformation_mode.setEnabled(visible)
    window.deformation_scale.setEnabled(visible and mode == "custom")
    window.deformation_peak.setVisible(visible)
    factor = 0.15 * max(extent, project.grid) / peak if mode == "auto" and peak else 1 if mode != "custom" else window.deformation_scale.value()
    window.deformation_scale_action.setVisible(mode == "custom")
    window.deformation_peak.setText(f"Peak {project.units.to_display(peak, 'length'):.4g} {project.units.length} | {factor:.4g}x" if result else "")
    loads = []
    definitions = combination_loads(project, result) if result else (*project.loads.values(), *project.self_weight_loads())
    for load in definitions:
        if not window.load_visible(load):
            continue
        axis = "XYZ".index(load.direction[-1].upper())
        vector = np.eye(3)[axis] if load.direction.isupper() else axes[load.target][axis]
        quantity = "intensity" if load.kind == "distributed" else "moment" if load.is_moment else "force"
        label = f"{load.name}: {project.units.to_display(load.magnitude, quantity):.4g}"
        if load.kind == "distributed":
            label += f" to {project.units.to_display(load.end_magnitude, quantity):.4g}"
        label += f" {getattr(project.units, quantity)} | {load.direction}"
        loads.append({"name": load.name, "target": load.target, "kind": load.kind, "vector": vector.tolist(),
                      "moment": load.is_moment, "magnitude": load.magnitude, "endMagnitude": load.end_magnitude,
                      "position": load.position, "endPosition": load.end_position, "label": label})
    diagram = diagram_metadata(project, result, kind, window.view.diagram_scale.value(), samples)
    if diagram:
        diagram["values"] = window.view.diagram_values.isChecked()
    return {"nodes": nodes, "members": members, "loads": loads if window.view.show_loads.isChecked() else [], "grid": project.grid, "colors": colors(),
            "diagram": diagram,
            "selection": [list(s) for s in window.selections], "mode": window.mode,
            "deformed": visible, "factor": factor,
            "unit": project.units.length, "displayFactor": project.units.to_display(1, "length")}


class Bridge(QObject):
    def __init__(self, view):
        super().__init__(view)
        self.view = view

    @Slot()
    def ready(self):
        self.view.ready = True
        self.view.failure_panel.hide()
        self.view.web.show()
        self.view.redraw()
        self.view.fit()

    @Slot(str)
    def failed(self, message):
        self.view.render_failure(message)

    @Slot(int)
    def orientation(self, index):
        if 0 <= index <= 7:
            control = self.view.orientation
            previous = control.blockSignals(True)
            control.setCurrentIndex(index)
            control.blockSignals(previous)

    @Slot(str, str, bool)
    def select(self, kind, name, extend):
        window = self.view.window
        if kind not in ("nodes", "members", "loads") or name not in getattr(window.project, kind):
            if not extend:
                window.select(None)
            return
        selection = (kind, name)
        if extend:
            window.select_many([s for s in window.selections if s != selection] if selection in window.selections
                               else [*window.selections, selection])
        else:
            window.select(selection)

    @Slot(str)
    def draw(self, data):
        window = self.view.window
        try:
            points = json.loads(data)
            if (window.mode != "draw" or len(points) != 2 or any(len(p) != 3 for p in points)
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for p in points for v in p)):
                return
        except (ValueError, TypeError):
            return
        window.edit("Draw 3D member", lambda p: p.add_member(*points))

    @Slot(float, float, float)
    def coordinates(self, x, y, z):
        units = self.view.window.project.units
        self.view.window.coordinates.setText("   ".join(f"{axis} {units.to_display(value, 'length'):.5g} {units.length}"
                                                        for axis, value in zip("XYZ", (x, y, z))))


def web_view_class():
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as error:
        # Some Conda hosts preload an older Brotli common library than Qt's decoder.
        if not sys.platform.startswith("linux") or "BrotliSharedDictionaryDestroyInstance" not in str(error):
            raise
        import ctypes
        library = Path("/lib/x86_64-linux-gnu/libbrotlicommon.so.1")
        if not library.exists():
            raise
        ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)
        from PySide6.QtWebEngineWidgets import QWebEngineView
    return QWebEngineView


class SpatialView(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window, self.ready = window, False
        self.pending_fit = True
        self.setObjectName("spatial_view")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 4, 6, 4)
        self.plane = QComboBox()
        self.plane.addItems(["XY", "XZ", "YZ"])
        self.plane.setToolTip("Member drawing work plane")
        from .app import unit_number
        self.offset = unit_number(0, window.project.units, "length")
        self.offset.setToolTip("Work plane offset along its perpendicular global axis")
        self.offset.setMaximumWidth(125)
        self.orientation = QComboBox()
        self.orientation.addItems(["Isometric", "Front XY", "Top XZ", "Right YZ", "Back XY", "Bottom XZ", "Left YZ", "Orbit"])
        self.orientation.model().item(7).setEnabled(False)
        self.orientation.setToolTip("Camera orientation")
        self.labels = QCheckBox("Labels")
        self.labels.setChecked(True)
        self.axes = QCheckBox("Local axes")
        toolbar.addWidget(QLabel("Plane"))
        toolbar.addWidget(self.plane)
        self.offset_label = QLabel(window.project.units.length)
        toolbar.addWidget(self.offset_label)
        toolbar.addWidget(self.offset)
        toolbar.addWidget(self.orientation)
        toolbar.addWidget(self.labels)
        toolbar.addWidget(self.axes)
        toolbar.addStretch()
        add = QToolButton()
        add.setIcon(window.standard_icon(window.style().StandardPixmap.SP_FileDialogNewFolder))
        add.setToolTip("Add node by XYZ coordinates")
        add.clicked.connect(window.add_spatial_node)
        toolbar.addWidget(add)
        layout.addLayout(toolbar)
        results = QHBoxLayout()
        results.setContentsMargins(6, 4, 6, 4)
        results.addWidget(QLabel("Result"))
        self.diagram = QComboBox()
        self.diagram.addItem("None", None)
        for label, kind in zip(LABELS[:6], QUANTITIES[:6]):
            self.diagram.addItem(label, kind)
        self.diagram.setToolTip("Whole-frame member results in local solver axes")
        results.addWidget(self.diagram)
        from .app import number
        self.diagram_scale = number(1., .05, 10., 2)
        self.diagram_scale.setSingleStep(.1)
        self.diagram_scale.setSuffix("x")
        self.diagram_scale.setMaximumWidth(100)
        self.diagram_scale.setToolTip("Diagram height relative to automatic scaling")
        results.addWidget(QLabel("Scale"))
        results.addWidget(self.diagram_scale)
        self.diagram_values = QCheckBox("Values")
        self.diagram_values.setChecked(True)
        results.addWidget(self.diagram_values)
        self.show_loads = QCheckBox("Loads")
        self.show_loads.setChecked(True)
        results.addWidget(self.show_loads)
        results.addStretch()
        self.export_button = QToolButton()
        self.export_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.export_button.setToolTip("Export current 3D view as PNG")
        self.export_button.clicked.connect(self.export_image)
        results.addWidget(self.export_button)
        layout.addLayout(results)
        self.diagram.currentIndexChanged.connect(self.redraw)
        self.diagram_scale.valueChanged.connect(self.redraw)
        self.diagram_values.toggled.connect(self.redraw)
        self.show_loads.toggled.connect(self.redraw)
        self.diagram.setEnabled(False)
        self.diagram_scale.setEnabled(False)
        self.diagram_values.setEnabled(False)
        self.export_button.setEnabled(False)
        self.web = None
        self.failure_panel = QWidget()
        self.failure_panel.setObjectName("spatial_render_failure")
        failure_layout = QVBoxLayout(self.failure_panel)
        failure_layout.addStretch()
        self.failure_message = QLabel()
        self.failure_message.setTextFormat(Qt.TextFormat.PlainText)
        self.failure_message.setWordWrap(True)
        failure_layout.addWidget(self.failure_message)
        recovery = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Use Software Rendering on Restart")
        recovery.setObjectName("spatial_software_restart")
        recovery.clicked.connect(lambda: window.set_graphics_mode("software"))
        failure_layout.addWidget(recovery)
        failure_layout.addStretch()
        self.failure_panel.hide()
        layout.addWidget(self.failure_panel)
        if os.environ.get("PYNITEGUI_NO_WEBENGINE") == "1":
            layout.addWidget(QLabel("3D viewport disabled for automated widget tests."))
            return
        try:
            self.web = web_view_class()(self)
            from PySide6.QtWebChannel import QWebChannel
            from PySide6.QtWebEngineCore import QWebEngineSettings
            self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            self.channel = QWebChannel(self.web.page())
            self.bridge = Bridge(self)
            self.channel.registerObject("bridge", self.bridge)
            self.web.page().setWebChannel(self.channel)
            self.web.page().renderProcessTerminated.connect(lambda status, code: self.render_failure(f"The 3D rendering process stopped (code {code})."))
            self.web.setUrl(QUrl.fromLocalFile(str(Path(__file__).parent / "viewport3d" / "index.html")))
            layout.addWidget(self.web)
        except ImportError as error:
            label = QLabel("3D rendering requires the Qt WebEngine component.\n" + str(error))
            label.setWordWrap(True)
            layout.addWidget(label)
        self.plane.currentTextChanged.connect(self.redraw)
        self.offset.valueChanged.connect(self.redraw)
        self.orientation.currentIndexChanged.connect(lambda: self.call("orient", self.orientation.currentIndex()))
        self.labels.toggled.connect(self.redraw)
        self.axes.toggled.connect(self.redraw)

    def render_failure(self, message):
        self.ready = False
        self.export_button.setEnabled(False)
        self.failure_message.setText("3D graphics could not start or were interrupted.\n\n" + str(message)[:600])
        self.failure_panel.show()
        if self.web:
            self.web.hide()

    def call(self, method, value=None):
        if self.web and self.ready:
            arguments = "" if value is None else json.dumps(value, allow_nan=False)
            self.web.page().runJavaScript(f"window.pyniteViewer.{method}({arguments});")

    def redraw(self, *unused):
        if getattr(self.window.project, "dimension", "2D") != "3D":
            return
        payload = viewport_payload(self.window)
        self.diagram.setEnabled(self.window.result is not None)
        self.diagram_scale.setEnabled(payload["diagram"] is not None)
        self.diagram_values.setEnabled(payload["diagram"] is not None)
        self.export_button.setEnabled(self.ready and self.web is not None)
        from .app import unit_value
        units = self.window.project.units
        previous = self.offset.property("unit_system")
        if previous is not None and previous != units.key:
            from .units import UNIT_SYSTEMS
            canonical = unit_value(self.offset, UNIT_SYSTEMS[previous])
            self.offset.blockSignals(True)
            self.offset.setValue(units.to_display(canonical, "length"))
            self.offset.setProperty("original_value", canonical)
            self.offset.setProperty("initial_value", self.offset.value())
            self.offset.blockSignals(False)
        self.offset.setProperty("unit_system", units.key)
        self.offset_label.setText(units.length)
        payload.update(plane=self.plane.currentText(), offset=unit_value(self.offset, units), labels=self.labels.isChecked(), localAxes=self.axes.isChecked())
        self.call("update", payload)
        if self.pending_fit and self.ready:
            self.pending_fit = False
            self.call("fit")

    def export_image(self):
        if not self.ready or not self.web:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export 3D View", "frame-3d.png", "PNG Image (*.png)")
        if not filename:
            return
        if not filename.lower().endswith(".png"):
            filename += ".png"
        self.web.page().runJavaScript("window.pyniteViewer.exportImage();", lambda data: self.save_image(filename, data))

    def save_image(self, filename, data):
        try:
            if not isinstance(data, str) or not data.startswith("data:image/png;base64,"):
                raise ValueError("The 3D renderer did not return an image.")
            image = QImage.fromData(base64.b64decode(data.split(",", 1)[1], validate=True), "PNG")
            if image.isNull() or not image.save(filename, "PNG"):
                raise ValueError("Could not save the PNG image to the selected location.")
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Image Export", str(error))

    def fit(self):
        self.pending_fit = True
        self.redraw()

    def cancel(self):
        self.call("cancel")

    def setDragMode(self, mode):
        self.redraw()

    def setBackgroundBrush(self, brush):
        pass

    def viewport(self):
        return self.web or self
