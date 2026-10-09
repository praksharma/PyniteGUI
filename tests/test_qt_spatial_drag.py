"""Validated, work-plane-constrained, single-command spatial node moves."""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication, QMessageBox
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.spatial_view import Bridge, viewport_payload


class SpatialDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("3d_cantilever"))
        self.view = self.window.view
        self.view.move_nodes.setChecked(True)
        self.bridge = Bridge(self.view)

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def request(self, **changes):
        return {"node": "N2", "start": list(self.window.project.nodes["N2"].coords),
                "target": [132, 24, 0], "plane": "XY", "revision": self.window.revision, **changes}

    def send(self, **changes):
        self.bridge.move_node(json.dumps(self.request(**changes)))

    def test_each_plane_retains_perpendicular_coordinate_and_undo_redo(self):
        for plane, target in (("XY", [132, 24, 0]), ("XZ", [132, 0, 24]), ("YZ", [120, 24, 24])):
            with self.subTest(plane=plane):
                self.window.load_project(example_project("3d_cantilever"))
                self.view.plane.setCurrentText(plane)
                self.view.offset.setValue(999)
                before = self.window.project.to_dict()
                self.send(plane=plane, target=target)
                after = self.window.project.to_dict()
                self.assertEqual(self.window.project.nodes["N2"].coords, tuple(target))
                self.assertEqual(self.window.undo.count(), 1)
                self.assertEqual(after["members"], before["members"])
                self.assertEqual(after["loads"], before["loads"])
                self.assertEqual(after["nodes"]["N1"], before["nodes"]["N1"])
                self.window.undo.undo()
                self.assertEqual(self.window.project.to_dict(), before)
                self.window.undo.redo()
                self.assertEqual(self.window.project.to_dict(), after)

    def test_supported_node_move_preserves_supports_materials_roll_and_weight(self):
        self.window.project.members["M1"].roll = 31
        self.window.project.self_weight_case = "Case 1"
        before = self.window.project.to_dict()
        weight = self.window.project.self_weight_total()
        self.send(node="N1", start=[0, 0, 0], target=[-12, -24, 0])
        self.assertEqual(self.window.project.nodes["N1"].support, "fixed")
        self.assertEqual(self.window.project.members["M1"].roll, 31)
        self.assertEqual(self.window.project.to_dict()["materials"], before["materials"])
        self.assertGreater(self.window.project.self_weight_total(), weight)
        self.assertEqual(self.window.project.loads.keys(), before["loads"].keys())

    def test_commit_invalidates_results_noop_or_collision_does_not(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.window.result = analyze(self.window.project)
        previous = self.window.result
        before = self.window.project.to_dict()
        self.send(target=[120, 0, 0])
        self.assertIs(self.window.result, previous)
        self.assertEqual(self.window.undo.count(), 0)
        with patch.object(QMessageBox, "warning") as warning:
            self.send(target=[0, 0, 0])
        warning.assert_called_once()
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertIs(self.window.result, previous)
        self.assertEqual(self.window.undo.count(), 0)
        self.send()
        self.assertIsNone(self.window.result)
        self.assertFalse(self.window.export_menu.isEnabled())

    def test_malformed_stale_off_grid_and_out_of_plane_requests_are_rejected(self):
        before = self.window.project.to_dict()
        invalid = [None, [], "text", {}, self.request(extra=1), self.request(node="missing"),
                   self.request(revision=True), self.request(revision=self.window.revision-1),
                   self.request(start=[0, 0, 0]), self.request(start=[120, 0]),
                   self.request(target=[132, True, 0]), self.request(target=[132, 24, float("nan")]),
                   self.request(target=[132, 24, 12]), self.request(target=[131, 24, 0]),
                   self.request(plane="XZ"), self.request(plane="bad"), self.request(target=None)]
        for request in invalid:
            self.bridge.move_node(json.dumps(request))
            self.assertEqual(self.window.project.to_dict(), before)
        self.bridge.move_node("not json")
        self.assertEqual(self.window.undo.count(), 0)

    def test_move_requires_enabled_select_tool_and_active_spatial_view(self):
        before = self.window.project.to_dict()
        self.view.move_nodes.setChecked(False)
        self.send()
        self.view.move_nodes.setChecked(True)
        for mode in ("pan", "draw"):
            self.window.set_mode(mode)
            self.send()
        self.window.set_mode("select")
        self.view.box_select.setChecked(True)
        self.assertFalse(self.view.move_nodes.isChecked())
        self.send()
        self.assertEqual(self.window.project.to_dict(), before)
        self.view.move_nodes.setChecked(True)
        self.assertFalse(self.view.box_select.isChecked())
        stale = self.request()
        self.window.load_project(example_project("cantilever"))
        before = self.window.project.to_dict()
        self.bridge.move_node(json.dumps(stale))
        self.assertEqual(self.window.project.to_dict(), before)

    def test_units_revision_and_native_payload_controls(self):
        revision = self.window.revision
        self.window.set_units("si")
        self.assertEqual(self.window.revision, revision)
        payload = viewport_payload(self.window)
        self.assertEqual(payload["revision"], revision)
        with patch.object(self.view, "call") as call:
            self.view.redraw()
        self.assertTrue(call.call_args.args[1]["moveNodes"])
        self.send()
        self.assertEqual(self.window.project.nodes["N2"].coords, (132, 24, 0))
        self.assertEqual(self.window.project.unit_system, "si")
        self.window.set_mode("pan")
        self.assertFalse(self.view.move_nodes.isEnabled())
        self.window.set_mode("select")
        self.assertTrue(self.view.move_nodes.isEnabled())


if __name__ == "__main__":
    unittest.main()
