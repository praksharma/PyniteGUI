"""Closed-form spring/release responses and transactional editing regressions."""
import contextlib
import io
import itertools
import os
import pickle
import unittest
from unittest.mock import patch
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QDoubleSpinBox, QPushButton, QMessageBox

from pynitegui.qt.analysis import analyze, model_signature
from pynitegui.qt.analysis_jobs import execute_analysis
from pynitegui.qt.app import MainWindow, EngineeringSymbol
from pynitegui.qt.model import Project, Load
from pynitegui.qt.model_tables import ModelTablesDialog, FIELDS
from pynitegui.qt.reports import model_definition_tables
from pynitegui.qt.units import UNIT_SYSTEMS


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def beam():
    project = Project()
    project.add_member((0, 0), (120, 0))
    project.nodes["N1"].support = "fixed"
    return project


class ElasticSupportTests(unittest.TestCase):
    def test_tip_axial_spring_in_parallel_with_bar(self):
        project = beam()
        project.nodes["N2"].spring_x = 30
        project.loads["L1"] = Load("L1", "N2", "FX", 10)
        project.set_combination("Reverse", {"Case 1": -2})
        result = solve(project)
        stiffness = project.materials["Steel_A992"].E * project.sections["W18x35"].A / 120
        displacement = 10 / (stiffness + 30)
        self.assertAlmostEqual(result.displacements["N2"][0], displacement)
        self.assertAlmostEqual(result.reactions["N2"][0], -30 * displacement)
        self.assertAlmostEqual(result.reactions["N1"][0], -stiffness * displacement)
        self.assertAlmostEqual(result.for_combination("Reverse").reactions["N2"][0], 60 * displacement)

    def test_spring_only_cantilever_base(self):
        project = beam()
        node = project.nodes["N1"]
        node.support = "free"
        node.spring_x, node.spring_y, node.spring_rz = 20, 40, 50000
        project.loads["L1"] = Load("L1", "N2", "FY", -10)
        result = solve(project)
        EI = project.materials["Steel_A992"].E * project.sections["W18x35"].Iz
        self.assertAlmostEqual(result.displacements["N1"][1], -10 / 40)
        self.assertAlmostEqual(result.displacements["N1"][2], -10 * 120 / 50000)
        self.assertAlmostEqual(result.displacements["N2"][1], -10 * (1 / 40 + 120**2 / 50000 + 120**3 / (3 * EI)))
        self.assertAlmostEqual(result.reactions["N1"][1], 10)
        self.assertAlmostEqual(result.reactions["N1"][2], 1200)
        self.assertFalse(result.solver.nodes["N1"].support_RZ)

    def test_rotational_spring_at_all_hinged_joint_carries_moment(self):
        project = beam()
        project.nodes["N1"].support = "pin"
        project.nodes["N2"].support = "roller"
        project.members["M1"].release_start = project.members["M1"].release_end = True
        project.nodes["N1"].spring_rz = 800
        project.loads["L1"] = Load("L1", "N1", "MZ", 8)
        result = solve(project)
        self.assertNotIn("N1", result.inactive_rotations)
        self.assertAlmostEqual(result.displacements["N1"][2], 0.01)
        self.assertAlmostEqual(result.reactions["N1"][2], -8)
        self.assertAlmostEqual(result.solver.members["M1"].moment("Mz", 60, "Service"), 0)

    def test_weak_or_incomplete_spring_supports_do_not_hide_motion(self):
        project = beam()
        project.nodes["N1"].support = "free"
        project.nodes["N1"].spring_y = 10
        with self.assertRaisesRegex(ValueError, "rigid body"):
            solve(project)
        project.nodes["N1"].spring_x = 10
        project.nodes["N1"].spring_rz = 1e-20
        with self.assertRaisesRegex(ValueError, "weak stiffness"):
            solve(project)

    def test_invalid_stiffness_and_rigid_spring_conflicts(self):
        for value in (-1, float("nan"), float("inf"), True, "10", None):
            project = beam()
            project.nodes["N2"].spring_y = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "stiffness"):
                project.validate()
        for key in ("spring_x", "spring_y", "spring_rz"):
            project = beam()
            setattr(project.nodes["N1"], key, 10)
            with self.assertRaisesRegex(ValueError, "both a rigid restraint and a spring"):
                project.validate()

    def test_legacy_migration_clone_and_signature(self):
        project = beam()
        data = project.to_dict()
        data["version"] = 14
        for node in data["nodes"].values():
            for key in ("spring_x", "spring_y", "spring_rz"):
                node.pop(key)
        for member in data["members"].values():
            for key in ("release_start_x", "release_end_x", "release_start_y", "release_end_y"):
                member.pop(key)
        restored = Project.from_dict(data)
        self.assertEqual(restored.to_dict(), project.to_dict())
        original = model_signature(project)
        project.nodes["N2"].spring_y = 10.1234567890123
        self.assertNotEqual(model_signature(project), original)
        self.assertEqual(project.clone().to_dict(), project.to_dict())
        signature = model_signature(project)
        project.unit_system = "si"
        self.assertEqual(model_signature(project), signature)

    def test_all_unit_presets_spring_dimensions(self):
        for units in UNIT_SYSTEMS.values():
            self.assertAlmostEqual(units.to_display(3, "stiffness"), 3 * units.force_factor / units.length_factor)
            self.assertAlmostEqual(units.to_display(3, "rotational_stiffness"), 3 * units.force_factor * units.length_factor)
            self.assertAlmostEqual(units.from_display(units.to_display(123.45, "rotational_stiffness"), "rotational_stiffness"), 123.45)

    def test_axial_release_transfers_member_load_to_other_end_only(self):
        for reverse in (False, True):
            project = beam()
            project.nodes["N2"].support = "fixed"
            member = project.members["M1"]
            if reverse:
                member.start, member.end = member.end, member.start
                member.release_start_x = True
            else:
                member.release_end_x = True
            project.loads["L1"] = Load("L1", "M1", "FX", 10)
            result = solve(project)
            self.assertAlmostEqual(result.reactions["N1"][0], -10)
            self.assertAlmostEqual(result.reactions["N2"][0], 0)
            solver = result.solver.members["M1"]
            self.assertAlmostEqual(solver.axial(0 if reverse else 120, "Service"), 0)
            released_position = 0 if reverse else 120
            EA = project.materials["Steel_A992"].E * project.sections["W18x35"].A
            self.assertAlmostEqual(abs(solver.deflection("dx", released_position, "Service")), 10 * 60 / EA)

    def test_shear_release_matches_fixed_guided_beam(self):
        project = beam()
        project.nodes["N2"].support = "fixed"
        project.members["M1"].release_end_y = True
        project.loads["L1"] = Load("L1", "M1", "FY", -10)
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][1], 10)
        self.assertAlmostEqual(result.reactions["N2"][1], 0)
        self.assertAlmostEqual(result.reactions["N1"][2], 450)
        self.assertAlmostEqual(result.reactions["N2"][2], 150)
        self.assertAlmostEqual(result.solver.members["M1"].shear("Fy", 120, "Service"), 0)
        EI = project.materials["Steel_A992"].E * project.sections["W18x35"].Iz
        expected = -10 * 120**3 / (24 * EI)
        self.assertAlmostEqual(result.solver.members["M1"].deflection("dy", 120, "Service"), expected)
        self.assertEqual(result.displacements["N2"][1], 0)
        restored = pickle.loads(pickle.dumps(result))
        self.assertAlmostEqual(restored.solver.members["M1"].deflection("dy", 120, "Service"), expected)

    def test_released_deflections_combinations_and_split_are_consistent(self):
        project = beam()
        project.nodes["N2"].support = "fixed"
        project.members["M1"].release_end_y = True
        project.loads["L1"] = Load("L1", "M1", "FY", -10)
        project.set_combination("Double", {"Case 1": 2})
        result = solve(project)
        expected = result.solver.members["M1"].deflection("dy", 120, "Service")
        self.assertAlmostEqual(result.solver.members["M1"].deflection("dy", 120, "Double"), expected * 2)
        self.assertAlmostEqual(result.solver.members["M1"].min_deflection("dy", "Service"), expected)
        names = project.split_member("M1", 0.25)
        split = solve(project)
        self.assertAlmostEqual(split.solver.members[names[-1]].deflection("dy", 90, "Service"), expected)
        self.assertAlmostEqual(split.reactions["N1"][2], result.reactions["N1"][2])

    def test_released_member_results_survive_isolated_analysis(self):
        project = beam()
        project.nodes["N2"].spring_y = 20
        project.nodes["N2"].spring_rz = 1000
        project.members["M1"].release_end_y = True
        project.loads["L1"] = Load("L1", "M1", "FY", -10)
        result = execute_analysis(project, lambda phase: None, Event())
        expected = solve(project)
        self.assertEqual(result.displacements, expected.displacements)
        self.assertAlmostEqual(result.solver.members["M1"].deflection("dy", 120, "Service"),
                               expected.solver.members["M1"].deflection("dy", 120, "Service"))

    def test_all_release_patterns_validate_condensation(self):
        keys = ("release_start_x", "release_end_x", "release_start_y", "release_end_y", "release_start", "release_end")
        for flags in itertools.product((False, True), repeat=6):
            project = beam()
            project.nodes["N2"].support = "fixed"
            for key, flag in zip(keys, flags):
                setattr(project.members["M1"], key, flag)
            expected = not (flags[0] and flags[1]) and not (flags[2] and flags[3]) and sum(flags[2:]) <= 2
            with self.subTest(flags=flags):
                if expected:
                    solve(project)
                else:
                    with self.assertRaisesRegex(ValueError, "axial DX|internally unstable"):
                        solve(project)

    def test_translation_mechanism_and_truss_conversion_rejected(self):
        project = beam()
        project.members["M1"].release_end_x = True
        with self.assertRaisesRegex(ValueError, "N2 DX"):
            solve(project)
        project.members["M1"].kind = "truss"
        with self.assertRaisesRegex(ValueError, "truss bars cannot"):
            project.validate()
        project.members["M1"].release_end_x = "true"
        with self.assertRaisesRegex(ValueError, "true or false"):
            project.validate()

    def test_splitting_preserves_only_original_end_releases(self):
        project = beam()
        member = project.members["M1"]
        member.release_start_x = member.release_end_y = True
        names = project.split_member("M1", 0.4)
        project.validate()
        self.assertEqual(project.members[names[0]].end_releases, ((True, False, False), (False, False, False)))
        self.assertEqual(project.members[names[1]].end_releases, ((False, False, False), (False, True, False)))


class ElasticEditorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(beam())

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def apply(self):
        next(b for b in self.window.inspector.findChildren(QPushButton) if b.text() == "Apply").click()

    def test_inspector_spring_apply_glyph_invalidation_and_undo(self):
        self.window.result = solve(self.window.project)
        self.window.select(("nodes", "N2"))
        self.window.inspector.findChild(QDoubleSpinBox, "spring_y").setValue(10)
        self.apply()
        self.assertEqual(self.window.project.nodes["N2"].spring_y, 10)
        self.assertIsNone(self.window.result)
        symbols = [i for i in self.window.view.scene().items() if isinstance(i, EngineeringSymbol) and i.kind == "spring"]
        self.assertEqual(len(symbols), 1)
        self.assertIn("DY spring 10 kip/in", symbols[0].toolTip())
        self.window.undo.undo()
        self.assertEqual(self.window.project.nodes["N2"].spring_y, 0)
        self.window.undo.redo()
        self.assertEqual(self.window.project.nodes["N2"].spring_y, 10)

    def test_release_inspector_and_invalid_edit_atomicity(self):
        self.window.select(("members", "M1"))
        self.window.inspector.findChild(QCheckBox, "release_end_y").setChecked(True)
        self.apply()
        self.assertTrue(self.window.project.members["M1"].release_end_y)
        self.assertTrue(any(isinstance(i, EngineeringSymbol) and i.kind == "release" for i in self.window.view.scene().items()))
        before = self.window.project.to_dict()
        self.window.inspector.findChild(QCheckBox, "release_start_y").setChecked(True)
        with patch.object(QMessageBox, "warning") as warning:
            self.apply()
        warning.assert_called_once()
        self.assertEqual(self.window.project.to_dict(), before)

    def test_unit_aware_tables_precision_and_report_definitions(self):
        project = beam()
        project.nodes["N2"].spring_x = 12.1234567890123
        project.nodes["N2"].spring_rz = 56.1234567890123
        for key in UNIT_SYSTEMS:
            project.unit_system = key
            dialog = ModelTablesDialog(None, project)
            try:
                self.assertEqual(dialog.preview().to_dict(), project.to_dict())
                dialog.tables["nodes"].item(1, FIELDS["nodes"].index("spring_y")).setText(str(project.units.to_display(100, "stiffness")))
                dialog.tables["members"].item(0, FIELDS["members"].index("release_end_x")).setCheckState(Qt.CheckState.Checked)
                candidate = dialog.preview()
                self.assertAlmostEqual(candidate.nodes["N2"].spring_y, 100)
                self.assertTrue(candidate.members["M1"].release_end_x)
                tables = {title: (headers, rows) for title, headers, rows in model_definition_tables(candidate)}
                self.assertIn(f"Spring RZ ({project.units.rotational_stiffness})", tables["Nodes and Supports"][0])
                self.assertAlmostEqual(tables["Nodes and Supports"][1][1][-1], project.units.to_display(project.nodes["N2"].spring_rz, "rotational_stiffness"))
                self.assertEqual(tables["Members and Assignments"][1][0][-1], "DX")
            finally:
                dialog.close()
                dialog.deleteLater()

    def test_bulk_springs_and_releases_only_change_checked_properties(self):
        self.window.project.unit_system = "si"
        self.window.select_many([("nodes", "N1"), ("nodes", "N2"), ("members", "M1")])
        self.window.inspector.findChild(QCheckBox, "bulk_change_spring_rz").setChecked(True)
        self.window.inspector.findChild(QDoubleSpinBox, "bulk_spring_rz").setValue(self.window.project.units.to_display(200, "rotational_stiffness"))
        before = self.window.project.to_dict()
        with patch.object(QMessageBox, "warning"):
            self.window.inspector.findChild(QPushButton, "bulk_apply").click()
        self.assertEqual(self.window.project.to_dict(), before)
        self.window.select_many([("nodes", "N2"), ("members", "M1")])
        self.window.inspector.findChild(QCheckBox, "bulk_change_spring_rz").setChecked(True)
        self.window.inspector.findChild(QDoubleSpinBox, "bulk_spring_rz").setValue(self.window.project.units.to_display(200, "rotational_stiffness"))
        self.window.inspector.findChild(QCheckBox, "bulk_release_end_x").setChecked(True)
        self.window.inspector.findChild(QPushButton, "bulk_apply").click()
        self.assertAlmostEqual(self.window.project.nodes["N2"].spring_rz, 200, places=4)
        self.assertTrue(self.window.project.members["M1"].release_end_x)
        self.assertEqual(self.window.project.nodes["N1"].support, "fixed")
        self.assertEqual(self.window.undo.count(), 1)
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), before)
