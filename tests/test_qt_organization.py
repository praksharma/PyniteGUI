"""Native organization controls preserve engineering state and filter both views."""
import contextlib
import io
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.analysis import analyze
from pynitegui.qt.examples import example_project
from pynitegui.qt.organization import set_group, show_group, show_all
from pynitegui.qt.organization_dialog import OrganizationDialog
from pynitegui.qt.spatial_view import Bridge, viewport_payload


class OrganizationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = MainWindow()
        self.w.load_project(example_project("portal"))
        self.dialog = OrganizationDialog(self.w)

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()
        self.w.saved = self.w.project.to_dict()
        self.w.close()
        self.w.deleteLater()
        self.app.processEvents()

    def test_native_save_rename_delete_and_undo_preserve_analysis(self):
        w, d = self.w, self.dialog
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(w.project)
        w.analysis_revision = w.revision
        w.analysis_finished(result, "")
        result = w.result
        revision = w.revision
        w.select(("members", "M1"))
        d.group_name.setText("Column")
        d.save_group()
        self.assertEqual(w.project.groups["Column"]["members"], ["M1"])
        self.assertEqual(w.revision, revision)
        self.assertIs(w.result, result)
        w.undo.undo()
        self.assertEqual(w.project.groups, {})
        self.assertIs(w.result, result)
        w.undo.redo()
        d.reload()
        d.group_name.setText("West")
        d.rename_group()
        self.assertIn("West", w.project.groups)
        d.reload()
        d.delete_group()
        self.assertEqual(w.project.groups, {})
        self.assertIs(w.result, result)

    def test_planar_isolation_filters_scene_hits_box_selection_loads_and_tree(self):
        w = self.w
        w.edit("Group", lambda p: set_group(p, "Column", [("members", "M1")]))
        before, revision = w.project.to_dict(), w.revision
        show_group(w, "Column", True)
        self.assertIn("Isolated: Column", w.windowTitle())
        self.assertTrue(w.show_all_action.isEnabled())
        endpoint = w.project.members["M1"].end
        self.assertTrue(w.entity_visible("nodes", endpoint))
        hidden = next(n for n in w.project.nodes if not w.entity_visible("nodes", n))
        node = w.project.nodes[hidden]
        self.assertNotEqual(w.view.hit(QPointF(node.x, -node.y)), ("nodes", hidden))
        selected = w.view.in_rectangle(QRectF(-1e6, -1e6, 2e6, 2e6))
        self.assertEqual({n for k, n in selected if k == "members"}, {"M1"})
        self.assertEqual(w.project.to_dict(), before)
        self.assertEqual(w.revision, revision)
        show_all(w)
        self.assertFalse(w.show_all_action.isEnabled())
        self.assertEqual(w.view.hit(QPointF(node.x, -node.y)), ("nodes", hidden))

    def test_level_controls_units_snapping_and_global_y_selection(self):
        w, d = self.w, self.dialog
        d.level_name.setText("Roof")
        d.elevation.setValue(150.5)
        d.save_level()
        d.snap.setChecked(True)
        w.view.resetTransform()
        self.assertEqual(w.view.snapped(QPointF(151., -151.)), (156., 150.5))
        w.set_units("si")
        self.assertEqual(w.project.levels["Roof"], 150.5)
        self.assertTrue(w.project.snap_levels)
        w.undo.undo()
        self.assertEqual(w.project.levels["Roof"], 150.5)

    def test_spatial_isolation_and_level_plane_keep_complete_model(self):
        self.w.load_project(example_project("3d_space_frame"))
        w = self.w
        w.edit("Group", lambda p: set_group(p, "Edge", [("members", "M1")]))
        w.edit("Level", lambda p: p.levels.update(Roof=150.5))
        w.edit("Snap", lambda p: setattr(p, "snap_levels", True))
        show_group(w, "Edge", True)
        payload = viewport_payload(w)
        self.assertEqual([m["name"] for m in payload["members"]], ["M1"])
        self.assertEqual({n["name"] for n in payload["nodes"]}, {w.project.members["M1"].start, w.project.members["M1"].end})
        self.assertEqual(payload["levels"], [150.5])
        self.assertGreater(len(w.project.members), 1)
        d = OrganizationDialog(w)
        try:
            d.levels.setCurrentRow(0)
            d.use_plane()
            self.assertEqual(w.view.plane.currentText(), "XZ")
            self.assertEqual(w.view.offset.value(), 150.5)
            show_all(w)
            self.assertEqual(len(viewport_payload(w)["members"]), len(w.project.members))
        finally:
            d.close()
            d.deleteLater()

    def test_spatial_drag_accepts_level_y_but_rejects_arbitrary_off_grid(self):
        w = self.w
        w.load_project(example_project("3d_space_frame"))
        w.edit("Level", lambda p: p.levels.update(Floor=150.5))
        w.edit("Snap", lambda p: setattr(p, "snap_levels", True))
        w.view.move_nodes.setChecked(True)
        w.view.plane.setCurrentText("XY")
        node = next(iter(w.project.nodes))
        start = list(w.project.nodes[node].coords)
        bridge = Bridge(w.view)
        request = {"node": node, "start": start, "target": [start[0], 151.1, start[2]], "plane": "XY", "revision": w.revision}
        bridge.move_node(json.dumps(request))
        self.assertEqual(list(w.project.nodes[node].coords), start)
        request["target"][1] = 150.5
        bridge.move_node(json.dumps(request))
        self.assertEqual(w.project.nodes[node].y, 150.5)
