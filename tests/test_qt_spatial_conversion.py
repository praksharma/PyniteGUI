"""Planar-to-spatial conversion: physical equivalence and independent documents."""
import contextlib
from dataclasses import asdict
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import EXAMPLES, example_project
from pynitegui.qt.model import Load, Project
from pynitegui.qt.recovery import RecoveryStore
from pynitegui.qt.spatial_conversion import conversion_dialog, to_spatial
from pynitegui.qt.spatial_results import member_values
from pynitegui.qt.units import UNIT_SYSTEMS


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class SpatialConversionTests(unittest.TestCase):
    def test_metadata_geometry_assignments_and_units_are_independent(self):
        for units in UNIT_SYSTEMS:
            source = example_project("multistorey", units)
            source.self_weight_case, source.self_weight_factor = "Gravity", 1.3
            original = source.to_dict()
            converted = to_spatial(source, offset=18)
            self.assertEqual(converted.unit_system, units)
            self.assertEqual(converted.combinations, source.combinations)
            self.assertEqual(converted.materials, source.materials)
            self.assertEqual(converted.sections, source.sections)
            self.assertEqual(converted.default_load_case, source.default_load_case)
            self.assertEqual(converted.grid, source.grid)
            self.assertAlmostEqual(converted.self_weight_total(), source.self_weight_total())
            for name, node in source.nodes.items():
                self.assertEqual(converted.nodes[name].coords, (node.x, node.y, 18))
            for name, member in source.members.items():
                self.assertEqual(asdict(converted.members[name]), {**asdict(member), "roll": 0})
            self.assertEqual(Project.from_dict(converted.to_dict()).to_dict(), converted.to_dict())
            converted.materials[converted.default_material].E *= 2
            converted.combinations["Combined"]["Wind"] = 10
            converted.nodes["N1"].x = 99
            self.assertEqual(source.to_dict(), original)

    def test_all_unreleased_planar_examples_retain_in_plane_results(self):
        for key in EXAMPLES:
            if key.startswith("3d_") or key == "shear_release":
                continue
            with self.subTest(example=key):
                source = example_project(key)
                converted = to_spatial(source, offset=-54)
                planar, spatial = solve(source), solve(converted)
                for combination in source.combinations:
                    a, b = planar.for_combination(combination), spatial.for_combination(combination)
                    for name in source.nodes:
                        for old_index, new_index in ((0, 0), (1, 1), (2, 5)):
                            expected = a.displacements[name][old_index]
                            if expected is None:
                                self.assertIsNone(b.displacements[name][new_index])
                            else:
                                self.assertAlmostEqual(b.displacements[name][new_index], expected, places=9)
                            self.assertAlmostEqual(b.reactions[name][new_index], a.reactions[name][old_index], places=6)
                        np.testing.assert_allclose(b.displacements[name][2:3], [0], atol=1e-12)
                    for name, member in source.members.items():
                        solver = a.solver.members[name]
                        distance = solver.L() * .37
                        expected = (solver.axial(distance, combination), solver.shear("Fy", distance, combination),
                                    solver.moment("Mz", distance, combination))
                        actual = member_values(b, name, distance)
                        np.testing.assert_allclose([actual[0], actual[1], actual[5]], expected, atol=1e-7)

    def test_planar_supports_preserve_custom_restraints_and_springs(self):
        source = example_project("elastic")
        source.nodes["N2"].support = "custom"
        source.nodes["N2"].restraint_x = True
        converted = to_spatial(source)
        for name, node in source.nodes.items():
            spatial = converted.nodes[name]
            self.assertEqual(spatial.support, "custom")
            self.assertEqual((spatial.restraints[0], spatial.restraints[1], spatial.restraints[5]), node.restraints)
            self.assertEqual((spatial.springs[0], spatial.springs[1], spatial.springs[5]), node.springs)
            self.assertEqual(spatial.restraints[2:5], (True,) * 3)

    def test_spatial_support_presets_and_real_out_of_plane_mechanism(self):
        source = example_project("truss")
        converted = to_spatial(source, "spatial")
        for name, node in source.nodes.items():
            self.assertEqual(converted.nodes[name].support, node.support)
        pin = next(node for node in converted.nodes.values() if node.support == "pin")
        self.assertEqual(pin.restraints, (True, True, True, False, False, False))
        with self.assertRaisesRegex(ValueError, "Insufficient|unstable|singular"):
            solve(converted)
        source = example_project("cantilever")
        converted = to_spatial(source, "spatial")
        self.assertEqual(converted.nodes["N1"].restraints, (True,) * 6)
        self.assertEqual(converted.nodes["N2"].restraints, (False,) * 6)
        np.testing.assert_allclose(solve(converted).displacements["N2"][:2], solve(source).displacements["N2"][:2])

    def test_local_forces_keep_global_components_including_reversal(self):
        for endpoints in (((0, 0), (72, 96)), ((72, 96), (0, 0)), ((0, 96), (0, 0))):
            for direction in ("Local x", "Local y", "Local angle", "Angle", "FY", "FX", "MZ"):
                source = Project()
                source.add_member(*endpoints)
                source.loads["L1"] = Load("L1", "M1", direction, -2, .2, angle=37)
                if direction != "MZ":
                    source.loads["L2"] = Load("L2", "M1", direction, -.1, .15, "distributed", -.3, .8, angle=-63)
                converted = to_spatial(source)
                for name, load in source.loads.items():
                    for magnitude in (load.magnitude, load.end_magnitude):
                        a = dict(load.components(source, magnitude))
                        b = dict(converted.loads[name].components(converted, magnitude))
                        for component in ("FX", "FY", "FZ", "MZ"):
                            self.assertAlmostEqual(a.get(component, 0), b.get(component, 0), places=12)
                    self.assertEqual(converted.loads[name].position, load.position)
                    self.assertEqual(converted.loads[name].end_position, load.end_position)

    def test_validation_does_not_remove_frame_releases(self):
        for release in ("release_start", "release_end", "release_start_x", "release_end_y"):
            source = example_project("cantilever")
            setattr(source.members["M1"], release, True)
            original = source.to_dict()
            with self.assertRaisesRegex(ValueError, "released frame members: M1"):
                to_spatial(source)
            self.assertEqual(source.to_dict(), original)
        source = example_project("truss")
        source.members["M1"].release_start = True
        converted = to_spatial(source)
        self.assertEqual(converted.members["M1"].kind, "truss")
        self.assertFalse(converted.members["M1"].release_start)
        with self.assertRaisesRegex(ValueError, "Only a 2D"):
            to_spatial(converted)
        with self.assertRaises(ValueError):
            to_spatial(source, "unexpected")
        for value in (float("nan"), float("inf"), True, "0"):
            with self.assertRaises(ValueError):
                to_spatial(source, offset=value)


class SpatialConversionEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.source = MainWindow(self.directory.name)
        self.children = []

    def tearDown(self):
        for window in [self.source, *self.children]:
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.assertFalse(any(window in getattr(self.app, "project_windows", set()) for window in self.children))
        self.directory.cleanup()

    def accepted_dialog(self, mode="planar", offset=0):
        dialog = conversion_dialog(self.source, self.source.project)
        dialog.mode.setCurrentIndex(dialog.mode.findData(mode))
        dialog.offset.setValue(offset)
        return dialog

    def test_independent_unsaved_copy_units_save_and_recovery(self):
        self.assertFalse(self.source.convert_spatial_action.isEnabled())
        project = example_project("portal", "si")
        source_path = Path(self.directory.name) / "original.pynite.json"
        project.save(source_path)
        self.source.load_project(project, source_path)
        self.source.edit("Change grid", lambda project: setattr(project, "grid", 6))
        self.source.result = solve(self.source.project)
        before, result = self.source.project.to_dict(), self.source.result
        dialog = self.accepted_dialog(offset=1.5)
        with patch("pynitegui.qt.spatial_conversion.conversion_dialog", return_value=dialog), patch.object(QDialog, "exec", return_value=1):
            child = self.source.convert_spatial_project()
        self.children.append(child)
        self.assertTrue(child.isVisible())
        self.assertIsNone(child.path)
        self.assertNotEqual(child.project.to_dict(), child.saved)
        self.assertIsNone(child.result)
        self.assertFalse(child.convert_spatial_action.isEnabled())
        self.assertEqual(child.project.unit_system, "si")
        self.assertAlmostEqual(child.project.nodes["N1"].z, project.units.from_display(1.5, "length"))
        self.assertEqual(self.source.project.to_dict(), before)
        self.assertIs(self.source.result, result)
        self.assertEqual(self.source.path, source_path)
        self.assertEqual(self.source.undo.count(), 1)
        self.assertIn(child, self.app.project_windows)
        child.autosave_now()
        recovered, path, baseline = RecoveryStore.read(child.recovery.path)
        self.assertIsNone(path)
        self.assertEqual(recovered.to_dict(), child.project.to_dict())
        self.assertNotEqual(recovered.to_dict(), baseline)
        destination = Path(self.directory.name) / "converted.pynite.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(destination), "")):
            self.assertTrue(child.save_project())
        self.assertEqual(Project.open(destination).to_dict(), child.project.to_dict())
        self.assertEqual(Project.open(source_path).to_dict(), project.to_dict())
        child.edit("Move node", lambda project: setattr(project.nodes["N2"], "z", 20))
        child.undo.undo()
        self.assertEqual(child.project.to_dict(), Project.open(destination).to_dict())
        self.source.saved = self.source.project.to_dict()
        self.source.close()
        self.app.processEvents()
        self.assertTrue(child.isVisible())

    def test_cancel_and_unsupported_conversion_leave_source_unchanged(self):
        self.source.load_project(example_project("shear_release"))
        before = self.source.project.to_dict()
        with patch.object(QDialog, "exec", return_value=0):
            self.assertIsNone(self.source.convert_spatial_project())
        with patch.object(QDialog, "exec", return_value=1), patch.object(QMessageBox, "warning") as warning:
            self.assertIsNone(self.source.convert_spatial_project())
        self.assertIn("M1", warning.call_args.args[2])
        self.assertEqual(self.source.project.to_dict(), before)
        self.assertEqual(self.source.undo.count(), 0)


if __name__ == "__main__":
    unittest.main()
