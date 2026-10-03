"""Numerical editing transactions, units, references, and history."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Load, Material, Project, Section
from pynitegui.qt.model_tables import FIELDS, ModelTablesDialog
from pynitegui.qt.units import UNIT_SYSTEMS


class ModelTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.project = example_project("simple_beam")
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        self.app.processEvents()

    def dialog(self, project=None):
        dialog = ModelTablesDialog(None, project or self.project)
        self.dialogs.append(dialog)
        return dialog

    def cell(self, dialog, kind, key, row=0):
        table = dialog.tables[kind]
        column = FIELDS[kind].index(key)
        return table.cellWidget(row, column) or table.item(row, column)

    def test_no_op_preserves_all_units_and_full_precision(self):
        self.project.nodes["N2"].x = 420.1234567890123
        self.project.loads["L1"].magnitude = -10.1234567890123
        self.project.loads["L1"].angle = 12.1234567890123
        for key in UNIT_SYSTEMS:
            self.project.unit_system = key
            dialog = self.dialog()
            self.assertEqual(dialog.preview().to_dict(), self.project.to_dict())
            self.assertFalse(self.cell(dialog, "nodes", "name").flags() & Qt.ItemFlag.ItemIsEditable)

    def test_coordinates_and_point_force_use_selected_units(self):
        for key, units in UNIT_SYSTEMS.items():
            self.project.unit_system = key
            dialog = self.dialog()
            self.cell(dialog, "nodes", "x", 1).setText(str(units.to_display(600, "length")))
            self.cell(dialog, "loads", "magnitude").setText(str(units.to_display(-25, "force")))
            candidate = dialog.preview()
            self.assertAlmostEqual(candidate.nodes["N2"].x, 600)
            self.assertAlmostEqual(candidate.loads["L1"].magnitude, -25)

    def test_moment_distributed_and_local_angle_quantities(self):
        self.project.unit_system = "si"
        self.project.loads["L1"].direction = "MZ"
        dialog = self.dialog()
        self.cell(dialog, "loads", "magnitude").setText("-2.5e1")
        self.assertAlmostEqual(dialog.preview().loads["L1"].magnitude, self.project.units.from_display(-25, "moment"))
        self.cell(dialog, "loads", "kind").setCurrentText("distributed")
        self.cell(dialog, "loads", "direction").setCurrentText("Local angle")
        self.cell(dialog, "loads", "magnitude").setText("-1.5")
        self.cell(dialog, "loads", "end_magnitude").setText("-3")
        self.cell(dialog, "loads", "position").setText("0.2")
        self.cell(dialog, "loads", "end_position").setText("0.8")
        self.cell(dialog, "loads", "angle").setText("-45")
        load = dialog.preview().loads["L1"]
        self.assertAlmostEqual(load.magnitude, self.project.units.from_display(-1.5, "intensity"))
        self.assertAlmostEqual(load.end_magnitude, self.project.units.from_display(-3, "intensity"))
        self.assertEqual((load.position, load.end_position, load.angle), (0.2, 0.8, -45))
        self.assertEqual(self.cell(dialog, "loads", "units").text(), "kN/m")

    def test_custom_support_and_member_assignments(self):
        self.project.set_material(Material("Other"))
        self.project.set_section(Section("Other"))
        self.project.set_load_case("Wind")
        dialog = self.dialog()
        self.assertEqual(self.cell(dialog, "nodes", "restraint_x").checkState(), Qt.CheckState.Checked)
        self.cell(dialog, "nodes", "support").setCurrentText("custom")
        self.cell(dialog, "nodes", "restraint_rz").setCheckState(Qt.CheckState.Checked)
        self.cell(dialog, "members", "release_end").setCheckState(Qt.CheckState.Checked)
        self.cell(dialog, "members", "material").setCurrentText("Other")
        self.cell(dialog, "members", "section").setCurrentText("Other")
        self.cell(dialog, "loads", "case").setCurrentText("Wind")
        candidate = dialog.preview()
        self.assertEqual(candidate.nodes["N1"].restraints, (True, True, True))
        self.assertTrue(candidate.members["M1"].release_end)
        self.assertEqual(candidate.members["M1"].material, "Other")
        self.assertEqual(candidate.members["M1"].section, "Other")
        self.assertEqual(candidate.loads["L1"].case, "Wind")

    def test_add_rows_from_empty_project_and_new_references(self):
        dialog = self.dialog(Project())
        dialog.add_row("nodes")
        dialog.add_row("nodes")
        dialog.add_row("members")
        dialog.add_row("loads")
        candidate = dialog.preview()
        self.assertEqual(len(candidate.nodes), 2)
        self.assertEqual(len(candidate.members), 1)
        self.assertEqual(candidate.loads["L1"].target, "M1")
        self.assertEqual(candidate.members["M1"].start, "N1")

    def test_deleting_reference_requires_explicit_dependent_removal(self):
        dialog = self.dialog()
        dialog.tables["nodes"].selectRow(0)
        dialog.remove_rows("nodes")
        with self.assertRaisesRegex(ValueError, "reference"):
            dialog.preview()
        self.assertEqual(self.cell(dialog, "members", "start").currentText(), "N1")
        for kind in ("members", "loads"):
            dialog.tables[kind].selectRow(0)
            dialog.remove_rows(kind)
        self.assertEqual(len(dialog.preview().nodes), 1)
        self.assertEqual(len(self.project.nodes), 2)

    def test_invalid_numbers_rejected_without_mutation(self):
        before = self.project.to_dict()
        for value in ("", "-", "bad", "nan", "inf", "1e999"):
            dialog = self.dialog()
            self.cell(dialog, "nodes", "x").setText(value)
            with self.assertRaisesRegex(ValueError, "finite number"):
                dialog.preview()
        self.assertEqual(self.project.to_dict(), before)

    def test_invalid_geometry_and_loads_rejected(self):
        dialog = self.dialog()
        self.cell(dialog, "nodes", "x", 1).setText("0")
        with self.assertRaisesRegex(ValueError, "coordinates"):
            dialog.preview()
        self.cell(dialog, "nodes", "x", 1).setText("420")
        self.cell(dialog, "loads", "target").setCurrentText("N1")
        self.cell(dialog, "loads", "kind").setCurrentText("distributed")
        with self.assertRaisesRegex(ValueError, "member"):
            dialog.preview()
        self.cell(dialog, "loads", "target").setCurrentText("M1")
        self.cell(dialog, "loads", "position").setText("1")
        with self.assertRaisesRegex(ValueError, "start < end"):
            dialog.preview()

    def test_accept_validation_and_cancel(self):
        dialog = self.dialog()
        self.cell(dialog, "loads", "magnitude").setText("-")
        with patch.object(QMessageBox, "warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.definition)
        dialog.reject()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)

    def test_active_numeric_editor_commits_on_accept(self):
        dialog = self.dialog()
        dialog.show()
        self.app.processEvents()
        table = dialog.tables["nodes"]
        item = self.cell(dialog, "nodes", "x", 1)
        table.setCurrentItem(item)
        table.editItem(item)
        self.app.processEvents()
        QTest.keyClick(self.app.focusWidget(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(self.app.focusWidget(), "-1.25e3")
        dialog.accept()
        self.assertEqual(dialog.definition.nodes["N2"].x, -1250)

    def test_main_window_transaction_undo_redo_and_cancel(self):
        window = MainWindow()
        window.load_project(self.project)
        before, revision = window.project.to_dict(), window.revision
        try:
            def accept(dialog):
                self.cell(dialog, "nodes", "x", 1).setText("600")
                self.cell(dialog, "loads", "magnitude").setText("-20")
                dialog.accept()
                return QDialog.DialogCode.Accepted
            with patch.object(ModelTablesDialog, "exec", accept):
                window.manage_model_tables()
            self.assertEqual(window.undo.count(), 1)
            self.assertGreater(window.revision, revision)
            self.assertEqual(window.project.loads["L1"].magnitude, -20)
            window.undo.undo()
            self.assertEqual(window.project.to_dict(), before)
            window.undo.redo()
            self.assertEqual(window.project.nodes["N2"].x, 600)
            current = window.project.to_dict()
            with patch.object(ModelTablesDialog, "exec", return_value=QDialog.DialogCode.Rejected):
                window.manage_model_tables()
            self.assertEqual(window.project.to_dict(), current)
        finally:
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()

    def test_self_weight_not_duplicated_in_manual_table(self):
        project = example_project("self_weight")
        dialog = self.dialog(project)
        self.assertEqual(dialog.tables["loads"].rowCount(), 0)
        self.assertEqual(dialog.preview().to_dict(), project.to_dict())

    def test_multi_row_deletion_and_no_op_history(self):
        self.project.loads["L2"] = Load("L2", "N1")
        dialog = self.dialog()
        dialog.tables["loads"].selectAll()
        dialog.remove_rows("loads")
        self.assertEqual(dialog.preview().loads, {})
        window = MainWindow()
        window.load_project(self.project)
        try:
            def accept(dialog):
                dialog.accept()
                return QDialog.DialogCode.Accepted
            with patch.object(ModelTablesDialog, "exec", accept):
                window.manage_model_tables()
            self.assertEqual(window.undo.count(), 0)
        finally:
            window.close()
            window.deleteLater()
