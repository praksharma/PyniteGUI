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
from pynitegui.qt.spatial_model import SpatialLoad, SPRING_FIELDS
from pynitegui.qt.spatial_conversion import to_spatial


if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.load_project(example_project("3d_space_frame"))
    window.project.members["M1"].roll = 27
    window.project.loads["L7"] = SpatialLoad("L7","N4","Angle",2,case="Wind",angle=40,elevation=30)
    window.project.loads["L8"] = SpatialLoad("L8","M1","Angle",-.003,.2,"distributed",.006,.8,"Wind",angle=25,elevation=-20)
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
    # Unsolved mixed supports exercise rendering independently of solver stability.
    window.result = None
    window.view.diagram.setCurrentIndex(0)
    spring = window.project.nodes["N1"]
    spring.support = "free"
    for index, key in enumerate(SPRING_FIELDS):
        setattr(spring, key, 10. * (index + 1))
    window.project.nodes["N3"].support = "pin"
    window.project.nodes["N5"].support = "roller"
    custom = window.project.nodes["N7"]
    custom.support = "custom"
    custom.restraint_x = custom.restraint_rz = True
    window.project.validate()
    payload["qaSupports"] = viewport_payload(window)
    payload["qaSupports"].update(plane="XY", offset=0, labels=True)
    window.project.unit_system = "si"
    payload["qaSupportsSI"] = viewport_payload(window)
    payload["qaSupportsSI"].update(plane="XY", offset=0, labels=True)
    window.load_project(example_project("3d_cantilever"))
    window.project.nodes["N2"].y, window.project.nodes["N2"].z = 60, -30
    window.project.members["M1"].roll = 27
    window.project.loads["L5"] = SpatialLoad("L5", "M1", "Angle", -.5, .37, angle=23, elevation=-17)
    window.project.split_member("M1", .37)
    with contextlib.redirect_stdout(io.StringIO()):
        window.result = analyze(window.project)
    window.view.diagram.setCurrentIndex(window.view.diagram.findData("moment_z"))
    payload["qaSplit"] = viewport_payload(window)
    payload["qaSplit"].update(plane="XY", offset=0, labels=True)
    window.load_project(example_project("3d_tripod"))
    with contextlib.redirect_stdout(io.StringIO()):
        window.result = analyze(window.project)
    window.deformed_action.setChecked(True)
    window.view.diagram.setCurrentIndex(window.view.diagram.findData("axial"))
    payload["qaTruss"] = viewport_payload(window)
    payload["qaTruss"].update(plane="XZ", offset=0, labels=True)
    window.load_project(to_spatial(example_project("cantilever"), offset=24))
    with contextlib.redirect_stdout(io.StringIO()):
        window.result = analyze(window.project)
    window.deformed_action.setChecked(True)
    window.view.diagram.setCurrentIndex(window.view.diagram.findData("moment_z"))
    payload["qaConversion"] = viewport_payload(window)
    payload["qaConversion"].update(plane="XY", offset=24, labels=True)
    print(json.dumps(payload, allow_nan=False))
    window.saved = window.project.to_dict()
    window.close()
