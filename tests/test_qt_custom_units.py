"""Independent length/force choices preserve engineering and result identity."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.analysis import model_signature
from pynitegui.qt.model import Project
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.units import UNIT_SYSTEMS, unit_key, units_dialog


class CustomUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_independent_mixed_units_and_derived_dimensions(self):
        # A one-foot member under one kip: force/length and torque must use
        # geometry units, while section properties use their stated dimensions.
        units = UNIT_SYSTEMS[unit_key("cm", "lbf")]
        self.assertAlmostEqual(units.to_display(12, "length"), 30.48)
        self.assertEqual(units.to_display(1, "force"), 1000)
        self.assertAlmostEqual(units.to_display(12, "moment"), 30480)
        self.assertAlmostEqual(units.to_display(1, "stiffness"), 1000 / 2.54)
        self.assertAlmostEqual(units.to_display(1, "density"), 1000 / 2.54**3)
        self.assertEqual(units.to_display(1, "area"), 25.4**2)
        self.assertAlmostEqual(units.to_display(1, "stress"), 6.894757293168361)
        imperial = UNIT_SYSTEMS[unit_key("ft", "N")]
        self.assertEqual(imperial.stress, "psi")
        self.assertEqual(imperial.to_display(1, "stress"), 1000)
        self.assertEqual(imperial.to_display(1, "inertia"), 1)
        for system in UNIT_SYSTEMS.values():
            for quantity in ("length", "force", "moment", "intensity", "stress", "density",
                             "area", "inertia", "rotation", "stiffness", "rotational_stiffness"):
                self.assertAlmostEqual(system.from_display(system.to_display(-3.125, quantity), quantity), -3.125)

    def test_preset_identity_and_unknown_choices(self):
        for length, force, key in (("in", "kip", "imperial"), ("m", "kN", "si"),
                                   ("mm", "N", "si_mm"), ("ft", "kip", "imperial_ft")):
            self.assertEqual(unit_key(length, force), key)
        with self.assertRaises(ValueError):
            unit_key("unknown", "N")

    def test_planar_spatial_persistence_conversion_and_signature(self):
        project = example_project("simple_beam")
        original = model_signature(project)
        for key in UNIT_SYSTEMS:
            project.unit_system = key
            self.assertEqual(model_signature(project), original)
            spatial = to_spatial(project)
            with tempfile.TemporaryDirectory() as folder:
                for item in (project, spatial):
                    path = Path(folder) / "project.json"
                    item.save(path)
                    reopened = Project.open(path)
                    self.assertEqual(reopened.to_dict(), item.to_dict())
                    self.assertEqual(reopened.units, UNIT_SYSTEMS[key])

    def test_dialog_preview_apply_cancel_and_undo(self):
        window = MainWindow()
        dialog = units_dialog(window, window.project.units)
        dialog.length.setCurrentText("cm")
        dialog.force.setCurrentText("lbf")
        self.assertIn("lbf-cm", dialog.findChild(QLabel, "unit_derived").text())
        try:
            with patch("pynitegui.qt.units.units_dialog", return_value=dialog), patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Rejected):
                window.choose_units()
            self.assertEqual(window.project.unit_system, "imperial")
            with patch("pynitegui.qt.units.units_dialog", return_value=dialog), patch.object(QDialog, "exec", return_value=QDialog.DialogCode.Accepted):
                window.choose_units()
            self.assertEqual(window.project.unit_system, unit_key("cm", "lbf"))
            window.undo.undo()
            self.assertEqual(window.project.unit_system, "imperial")
            window.undo.redo()
            self.assertEqual(window.project.unit_system, unit_key("cm", "lbf"))
        finally:
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()
            self.app.processEvents()
