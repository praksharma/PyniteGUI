"""Read-only PyNite surface-mesh preview using the existing offline renderer."""
import json
import os
from pathlib import Path
import numpy as np

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QStyle, QToolButton, QVBoxLayout, QWidget

from .mesh_model import mesh_geometry
from .theme import colors


def mesh_payload(definition, model):
    names, _, points, cells = mesh_geometry(model)
    plane = definition.plane if definition.generator == "rectangle" else {"X": "YZ", "Y": "XZ", "Z": "XY"}[definition.axis]
    perpendicular = {"XY": 2, "XZ": 1, "YZ": 0}[plane]
    return {"nodes": [{"name": name, "position": point, "restraints": [False]*6, "springs": [0]*6,
                       "supportDetails": []} for name, point in zip(names, points.tolist())],
            "members": [], "loads": [], "surfaces": cells.tolist(), "grid": max(float(np.ptp(points, axis=0).max())/20, 1e-8),
            "colors": colors(), "selection": [], "mode": "preview", "supports": False,
            "labels": False, "showNodes": False, "surfaceFill": True, "plane": plane, "offset": definition.origin[perpendicular],
            "unit": definition.units.length, "displayFactor": definition.units.length_factor}


class MeshBridge(QObject):
    def __init__(self, view):
        super().__init__(view)
        self.view = view

    @Slot()
    def ready(self):
        self.view.ready = True
        self.view.failure.hide()
        self.view.web.show()
        self.view.redraw()

    @Slot(str)
    def failed(self, message):
        self.view.ready = False
        self.view.failure.setText("3D mesh graphics could not start or were interrupted.\n" + message[:600])
        self.view.failure.show()
        self.view.web.hide()

    @Slot(float, float, float)
    def coordinates(self, x, y, z):
        pass

    @Slot(int)
    def orientation(self, index):
        previous = self.view.orientation.blockSignals(True)
        self.view.orientation.setCurrentIndex(index)
        self.view.orientation.blockSignals(previous)


class MeshPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ready, self.web, self.payload = False, None, None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.orientation = QComboBox()
        self.orientation.addItems(["Isometric", "Front XY", "Top XZ", "Right YZ", "Back XY", "Bottom XZ", "Left YZ", "Orbit"])
        self.orientation.model().item(7).setEnabled(False)
        self.orientation.currentIndexChanged.connect(lambda index: self.call("orient", index) if index < 7 else None)
        row.addWidget(self.orientation)
        self.fill, self.nodes = QCheckBox("Faces"), QCheckBox("Nodes")
        self.fill.setChecked(True)
        for control in (self.fill, self.nodes):
            control.toggled.connect(lambda: self.redraw(fit=False))
            row.addWidget(control)
        row.addStretch()
        fit = QToolButton()
        fit.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        fit.setToolTip("Fit mesh")
        fit.clicked.connect(lambda: self.call("fit"))
        row.addWidget(fit)
        layout.addLayout(row)
        self.failure = QLabel()
        self.failure.setWordWrap(True)
        self.failure.hide()
        layout.addWidget(self.failure)
        if os.environ.get("PYNITEGUI_NO_WEBENGINE") == "1":
            layout.addWidget(QLabel("3D viewport disabled for automated widget tests."))
            return
        from .spatial_view import web_view_class
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEngineSettings
        self.web = web_view_class()(self)
        self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.channel = QWebChannel(self.web.page())
        self.bridge = MeshBridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.web.page().renderProcessTerminated.connect(lambda status, code: self.bridge.failed(f"Rendering process exited ({code})."))
        self.web.setUrl(QUrl.fromLocalFile(str(Path(__file__).parent/"viewport3d"/"index.html")))
        layout.addWidget(self.web, 1)

    def set_mesh(self, definition, model):
        self.payload = mesh_payload(definition, model)
        self.redraw()

    def call(self, method, value=None):
        if self.web and self.ready:
            args = "" if value is None else json.dumps(value, allow_nan=False)
            self.web.page().runJavaScript(f"window.pyniteViewer.{method}({args});")

    def redraw(self, fit=True):
        if self.payload:
            self.call("update", {**self.payload, "surfaceFill": self.fill.isChecked(), "showNodes": self.nodes.isChecked()})
            if fit:
                self.call("fit")
