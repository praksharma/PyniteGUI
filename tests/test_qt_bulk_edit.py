"""Multiple selection, explicit bulk changes, atomic validation, and history."""
import os
import contextlib
import io
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QMessageBox, QPushButton

from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow, EngineeringSymbol
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Material, Project, Section


class BulkEditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("portal"))
        self.window.show()
        self.app.processEvents()
        self.window.view.fit()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def field(self, key, cls):
        return self.window.inspector.findChild(cls, "bulk_" + key)

    def apply(self):
        self.field("apply", QPushButton).click()

    def test_selection_sync_dedup_and_single_compatibility(self):
        before, revision = self.window.project.to_dict(), self.window.revision
        self.window.select_many([("nodes", "N1"), ("members", "M1"), ("nodes", "N1")])
        self.assertEqual(len(self.window.selections), 2)
        self.assertIsNone(self.window.selected)
        self.assertEqual(len(self.window.tree.selectedItems()), 2)
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertEqual(self.window.revision, revision)
        self.window.select(("members", "M1"))
        self.assertEqual(self.window.selected, ("members", "M1"))
        self.assertEqual(len(self.window.tree.selectedItems()), 1)

    def test_canvas_ctrl_click_toggle_and_plain_click(self):
        view = self.window.view
        nodes = list(self.window.project.nodes.values())[:2]
        for index, node in enumerate(nodes):
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.ControlModifier if index else Qt.KeyboardModifier.NoModifier,
                             view.mapFromScene(QPointF(node.x, -node.y)))
        self.assertEqual(set(self.window.selections), {("nodes", node.name) for node in nodes})
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                         view.mapFromScene(QPointF(nodes[0].x, -nodes[0].y)))
        self.assertEqual(self.window.selected, ("nodes", nodes[1].name))

    def test_tree_ctrl_and_shift_preserve_native_range_selection(self):
        tree = self.window.tree
        parent = tree.topLevelItem(0)
        for row, modifier in ((0, Qt.KeyboardModifier.NoModifier), (2, Qt.KeyboardModifier.ShiftModifier)):
            position = tree.visualItemRect(parent.child(row)).center()
            QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, modifier, position)
        self.assertEqual(set(self.window.selections), {("nodes", parent.child(row).text(0)) for row in range(3)})
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                         tree.visualItemRect(parent.child(1)).center())
        self.assertEqual(len(self.window.selections), 2)

    def test_rectangle_intersections_and_cancel(self):
        project = Project()
        project.add_member((0, 0), (100, 100))
        self.window.load_project(project)
        self.assertEqual(self.window.view.in_rectangle(QRectF(0, -100, 20, 20)), [])
        self.assertIn(("members", "M1"), self.window.view.in_rectangle(QRectF(40, -60, 20, 20)))
        self.window.select(("members", "M1"))
        view = self.window.view
        self.window.view.fit()
        start = view.mapFromScene(QPointF(-20, 20))
        end = view.mapFromScene(QPointF(120, -120))
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        view.cancel()
        self.assertEqual(self.window.selected, ("members", "M1"))
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(set(self.window.selections), {("nodes", "N1"), ("nodes", "N2"), ("members", "M1")})

    def test_member_bulk_assignments_keep_other_properties_and_undo(self):
        project = self.window.project.clone()
        project.set_material(Material("Other"))
        project.set_section(Section("Other"))
        project.members["M1"].release_start = True
        self.window.load_project(project)
        before = project.to_dict()
        self.window.select_many([("members", "M1"), ("members", "M2")])
        self.field("material", QComboBox).setCurrentText("Other")
        self.field("section", QComboBox).setCurrentText("Other")
        self.field("release_end", QCheckBox).setCheckState(Qt.CheckState.Checked)
        self.apply()
        for name in ("M1", "M2"):
            self.assertEqual(self.window.project.members[name].material, "Other")
            self.assertTrue(self.window.project.members[name].release_end)
        self.assertTrue(self.window.project.members["M1"].release_start)
        self.assertFalse(self.window.project.members["M2"].release_start)
        self.assertEqual(self.window.project.members["M3"].material, project.default_material)
        self.assertEqual(self.window.undo.count(), 1)
        self.assertEqual(len(self.window.selections), 2)
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), before)
        self.window.undo.redo()
        self.assertEqual(self.window.project.members["M2"].section, "Other")

    def test_node_support_custom_preserves_preset_restraints(self):
        self.window.select_many([("nodes", "N1"), ("nodes", "N2")])
        self.field("support", QComboBox).setCurrentText("custom")
        self.field("restraint_x", QCheckBox).setCheckState(Qt.CheckState.Unchecked)
        self.apply()
        self.assertEqual(self.window.project.nodes["N1"].restraints, (False, True, True))
        self.assertEqual(self.window.project.nodes["N2"].restraints, (False, False, False))
        self.assertEqual(self.window.project.nodes["N1"].support, "custom")

    def test_load_case_and_scaling_all_quantities(self):
        project = example_project("cantilever", "si")
        project.set_load_case("Wind")
        self.window.load_project(project)
        self.window.select_many([("loads", name) for name in project.loads])
        self.field("case", QComboBox).setCurrentText("Wind")
        self.field("scale", QCheckBox).setChecked(True)
        self.field("factor", QDoubleSpinBox).setValue(-2)
        self.apply()
        for name, original in project.loads.items():
            load = self.window.project.loads[name]
            self.assertEqual(load.case, "Wind")
            self.assertEqual(load.magnitude, original.magnitude * -2)
            self.assertEqual(load.end_magnitude, original.end_magnitude * -2 if load.kind == "distributed" else original.end_magnitude)
            self.assertEqual(load.angle, original.angle)
            self.assertEqual(load.direction, original.direction)

    def test_mixed_selection_applies_only_relevant_fields(self):
        magnitude = self.window.project.loads["L1"].magnitude
        self.window.select_many([("nodes", "N1"), ("members", "M1"), ("loads", "L1")])
        self.field("support", QComboBox).setCurrentText("pin")
        self.field("release_end", QCheckBox).setCheckState(Qt.CheckState.Checked)
        self.apply()
        self.assertEqual(self.window.project.nodes["N1"].support, "pin")
        self.assertTrue(self.window.project.members["M1"].release_end)
        self.assertEqual(self.window.project.loads["L1"].magnitude, magnitude)

    def test_invalid_bulk_edit_rejected_atomically(self):
        self.window.select_many([("nodes", "N1"), ("members", "M1")])
        before = self.window.project.to_dict()
        self.field("support", QComboBox).setCurrentText("pin")
        material = self.field("material", QComboBox)
        material.addItem("Missing", "Missing")
        material.setCurrentText("Missing")
        with patch.object(QMessageBox, "warning") as warning:
            self.apply()
        warning.assert_called_once()
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertEqual(self.window.undo.count(), 0)

    def test_delete_cascade_one_transaction_and_prune_selection(self):
        before = self.window.project.to_dict()
        self.window.select_many([("nodes", "N2"), ("members", "M2"), ("loads", "L1")])
        self.window.delete_selected()
        self.assertNotIn("N2", self.window.project.nodes)
        self.assertNotIn("M2", self.window.project.members)
        self.assertEqual(self.window.selections, [])
        self.assertEqual(self.window.undo.count(), 1)
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), before)

    def test_filter_keeps_geometry_and_noop_bulk_edit_keeps_revision(self):
        self.window.select_many([("members", "M1"), ("loads", "L1")])
        before, revision = self.window.project.to_dict(), self.window.revision
        self.apply()
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertEqual(self.window.revision, revision)
        self.assertEqual(self.window.undo.count(), 0)
        self.window.load_filter.setCurrentIndex(self.window.load_filter.findData(False))
        self.assertEqual(self.window.selected, ("members", "M1"))

    def test_new_project_clears_selection(self):
        self.window.select_many([("members", "M1"), ("nodes", "N1")])
        self.window.load_project(Project())
        self.assertEqual(self.window.selections, [])

    def test_selection_noop_and_units_preserve_results_real_edit_invalidates(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(self.window.project)
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(result, "")
        displayed = self.window.result
        self.window.select_many([("members", "M1"), ("members", "M2")])
        self.assertIs(self.window.result, displayed)
        self.apply()
        self.assertIs(self.window.result, displayed)
        self.window.set_units("si")
        self.assertIsNotNone(self.window.result)
        self.assertEqual(len(self.window.selections), 2)
        self.field("release_end", QCheckBox).setCheckState(Qt.CheckState.Checked)
        self.apply()
        self.assertIsNone(self.window.result)

    def test_select_all_filters_loads_and_highlights_selected_arrows(self):
        self.window.select_many([("loads", "L1"), ("loads", "L2")])
        symbols = [item for item in self.window.view.scene().items()
                   if isinstance(item, EngineeringSymbol) and item.kind == "load"]
        self.assertTrue(symbols)
        self.assertTrue(all(item.highlighted for item in symbols))
        self.window.load_filter.setCurrentIndex(self.window.load_filter.findData(False))
        self.window.select_all()
        self.assertEqual(len(self.window.selections), len(self.window.project.nodes) + len(self.window.project.members))

    def test_bulk_case_reassignment_prunes_newly_hidden_loads(self):
        project = self.window.project.clone()
        project.set_load_case("Wind")
        self.window.load_project(project)
        self.window.load_filter.setCurrentIndex(self.window.load_filter.findData("Case 1"))
        self.window.select_many([("members", "M1"), ("loads", "L1"), ("loads", "L2")])
        self.field("case", QComboBox).setCurrentText("Wind")
        self.apply()
        self.assertEqual(self.window.selected, ("members", "M1"))
        self.assertEqual(self.window.project.loads["L1"].case, "Wind")
