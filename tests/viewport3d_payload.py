"""Emit an actual analyzed example for the standalone browser rendering checks."""
import contextlib
import io
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.analysis import analyze
from pynitegui.qt.examples import example_project
from pynitegui.qt.spatial_view import viewport_payload


if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.load_project(example_project("3d_space_frame"))
    window.project.members["M1"].roll = 27
    with contextlib.redirect_stdout(io.StringIO()):
        window.result = analyze(window.project).for_combination("Combined")
    window.deformed_action.setChecked(True)
    payload = viewport_payload(window)
    payload.update(plane="XY", offset=0, labels=True, localAxes=True)
    payload["qaDiagrams"] = {}
    for kind in ("axial", "shear_y", "shear_z", "torque", "moment_y", "moment_z"):
        window.view.diagram.setCurrentIndex(window.view.diagram.findData(kind))
        diagram = viewport_payload(window)
        diagram.update(plane="XY", offset=0, labels=True, localAxes=True, deformed=False)
        payload["qaDiagrams"][kind] = diagram
    print(json.dumps(payload, allow_nan=False))
    window.saved = window.project.to_dict()
    window.close()
