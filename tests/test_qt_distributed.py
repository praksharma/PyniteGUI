"""Distributed-load mechanics, persistence, splitting, and editor regressions."""
import contextlib
import io
import math
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDoubleSpinBox, QPushButton
from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import EngineeringSymbol, MainWindow
from pynitegui.qt.diagrams import sample_member, structure_data
from pynitegui.qt.model import Load, Project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def beam(w1=-0.1, w2=-0.1, start=0, end=1):
    project = Project()
    project.add_member((0, 0), (120, 0))
    project.nodes["N1"].support = "pin"
    project.nodes["N2"].support = "roller"
    project.loads["L1"] = Load("L1", "M1", "FY", w1, start, "distributed", w2, end)
    return project


class DistributedTests(unittest.TestCase):
    def test_uniform_beam_formulas(self):
        project = beam()
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][1], 6)
        self.assertAlmostEqual(result.reactions["N2"][1], 6)
        member = result.solver.members["M1"]
        self.assertAlmostEqual(member.moment("Mz", 60, "Service"), -180)
        expected = -5 * 0.1 * 120**4 / (384 * project.E * project.Iz)
        self.assertAlmostEqual(member.deflection("dy", 60, "Service"), expected)
        sampled = sample_member(project, result, "M1")
        self.assertAlmostEqual(sampled["shear"][0], 6)
        self.assertAlmostEqual(sampled["shear"][-1], -6)

    def test_triangular_beam_reactions(self):
        result = solve(beam(0, -0.1))
        self.assertAlmostEqual(result.reactions["N1"][1], 2)
        self.assertAlmostEqual(result.reactions["N2"][1], 4)

    def test_partial_span_and_diagram_boundaries(self):
        project = beam(-0.1, -0.3, 0.2, 0.7)
        result = solve(project)
        total = 0.2 * 60
        centroid = 24 + 60 * (0.1 + 2 * 0.3) / (3 * (0.1 + 0.3))
        self.assertAlmostEqual(result.reactions["N2"][1], total * centroid / 120)
        self.assertAlmostEqual(result.reactions["N1"][1], total * (1 - centroid / 120))
        sampled = sample_member(project, result, "M1")
        self.assertIn(24, sampled["x"])
        self.assertIn(84, sampled["x"])

    def test_split_interpolates_and_preserves_results(self):
        project = beam(-0.1, -0.3, 0.2, 0.8)
        before = solve(project)
        project.split_member("M1", 0.5)
        self.assertEqual(len(project.loads), 2)
        a, b = project.loads.values()
        self.assertEqual((a.target, b.target), ("M1", "M2"))
        self.assertAlmostEqual(a.position, 0.4)
        self.assertAlmostEqual(a.end_position, 1)
        self.assertAlmostEqual(a.end_magnitude, -0.2)
        self.assertAlmostEqual(b.magnitude, -0.2)
        self.assertAlmostEqual(b.end_position, 0.6)
        after = solve(project)
        for node in ("N1", "N2"):
            for old, new in zip(before.reactions[node], after.reactions[node]):
                self.assertAlmostEqual(old, new)
            for old, new in zip(before.displacements[node], after.displacements[node]):
                self.assertAlmostEqual(old, new)

    def test_multiple_cuts_and_load_name_collisions(self):
        project = beam(0, -0.3, 0.25, 0.75)
        project.loads["L2"] = Load("L2", "M1", "FY", -1, 0.5)
        project._split_member("M1", [0.25, 0.5, 0.75])
        project.validate()
        distributed = [load for load in project.loads.values() if load.kind == "distributed"]
        self.assertEqual(len(distributed), 2)
        self.assertEqual(project.loads["L2"].target, "N4")
        total = 0
        for load in distributed:
            member = project.members[load.target]
            a, b = project.nodes[member.start], project.nodes[member.end]
            length = math.hypot(b.x - a.x, b.y - a.y)
            total += length * (load.end_position - load.position) * (load.magnitude + load.end_magnitude) / 2
        self.assertAlmostEqual(total, -9)

    def test_global_load_on_inclined_cantilever(self):
        for direction, expected in (("FY", (0, 10, 300)), ("FX", (10, 0, -400))):
            project = Project()
            project.add_member((0, 0), (60, 80))
            project.nodes["N1"].support = "fixed"
            project.loads["L1"] = Load("L1", "M1", direction, -0.1, 0, "distributed", -0.1, 1)
            result = solve(project)
            for actual, value in zip(result.reactions["N1"], expected):
                self.assertAlmostEqual(actual, value)

    def test_split_outside_loaded_region(self):
        project = beam(-0.1, -0.2, 0.6, 0.9)
        project.split_member("M1", 0.5)
        self.assertEqual(len(project.loads), 1)
        load = project.loads["L1"]
        self.assertEqual(load.target, "M2")
        self.assertAlmostEqual(load.position, 0.2)
        self.assertAlmostEqual(load.end_position, 0.8)
        self.assertAlmostEqual(load.magnitude, -0.1)
        self.assertAlmostEqual(load.end_magnitude, -0.2)

    def test_reversed_uniform_diagram_geometry(self):
        project = beam()
        normal = structure_data(project, solve(project), "moment")["M1"]
        member = project.members["M1"]
        member.start, member.end = member.end, member.start
        reversed_data = structure_data(project, solve(project), "moment")["M1"]
        import numpy as np
        np.testing.assert_allclose(normal["values"], reversed_data["values"][::-1], atol=1e-8)

    def test_sign_changing_load_preserved_on_split(self):
        project = beam(-0.1, 0.1)
        before = solve(project)
        project.split_member("M1", 0.5)
        after = solve(project)
        self.assertAlmostEqual(project.loads["L1"].end_magnitude, 0)
        self.assertAlmostEqual(project.loads["L2"].magnitude, 0)
        for node in ("N1", "N2"):
            self.assertAlmostEqual(before.reactions[node][1], after.reactions[node][1])

    def test_round_trip_and_version_three_point_loads(self):
        project = beam()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "beam.pynite.json"
            project.save(path)
            self.assertEqual(Project.open(path).to_dict(), project.to_dict())
        data = project.to_dict()
        data["version"] = 3
        data["loads"]["L1"] = {"name": "L1", "target": "M1", "direction": "FY", "magnitude": -5, "position": 0.5}
        self.assertEqual(Project.from_dict(data).loads["L1"].kind, "point")

    def test_reject_invalid_distributions(self):
        for kwargs in ({"target": "N1"}, {"direction": "MZ"}, {"position": 1},
                       {"end_position": 0}, {"end_position": 1.1},
                       {"end_position": float("nan")}, {"end_magnitude": float("inf")}, {"kind": "unknown"}):
            with self.subTest(kwargs=kwargs):
                project = beam()
                project.loads["L1"] = replace(project.loads["L1"], **kwargs)
                with self.assertRaises(ValueError):
                    project.validate()


class DistributedEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(beam())

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def test_create_distributed_load_dialog(self):
        self.window.selected = ("members", "M1")
        def accept(dialog):
            combos = dialog.findChildren(QComboBox)
            combos[0].setCurrentText("Distributed")
            self.assertEqual(combos[1].count(), 2)
            numbers = dialog.findChildren(QDoubleSpinBox)
            self.assertEqual([n.value() for n in numbers], [-0.1, 0, -0.1, 1])
            return QDialog.DialogCode.Accepted
        with patch.object(QDialog, "exec", accept):
            self.window.add_load()
        load = self.window.project.loads["L2"]
        self.assertEqual(load.kind, "distributed")
        self.assertEqual(load.position, 0)
        self.window.undo.undo()
        self.assertNotIn("L2", self.window.project.loads)

    def test_inspector_and_split_undo(self):
        self.window.selected = ("loads", "L1")
        self.window.refresh()
        combos = self.window.inspector.findChildren(QComboBox)
        self.assertEqual(self.window.inspector.findChild(QComboBox, "load_case").count(), 1)
        self.assertEqual(self.window.inspector.findChild(QComboBox, "load_direction").count(), 2)
        numbers = self.window.inspector.findChildren(QDoubleSpinBox)
        numbers[2].setValue(-0.2)
        buttons = self.window.inspector.findChildren(QPushButton)
        next(b for b in buttons if b.text() == "Apply").click()
        self.assertAlmostEqual(self.window.project.loads["L1"].end_magnitude, -0.2)
        self.window.edit("Split member", lambda p: p.split_member("M1", 0.5))
        self.assertEqual(len(self.window.project.loads), 2)
        self.window.undo.undo()
        self.assertEqual(len(self.window.project.loads), 1)
        self.window.undo.redo()
        self.assertEqual(len(self.window.project.loads), 2)
        glyphs = [item for item in self.window.view.scene().items() if isinstance(item, EngineeringSymbol) and item.kind == "load"]
        self.assertEqual(len(glyphs), 18)
