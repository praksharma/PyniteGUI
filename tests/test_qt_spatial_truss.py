"""Axial spatial elements: independent benchmarks, mechanisms and editing."""
import contextlib
import io
import os
import pickle
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox, QPushButton

from pynitegui.qt.analysis import analyze
from pynitegui.qt.app import MainWindow
from pynitegui.qt.envelopes import envelope_rows
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Project
from pynitegui.qt.model_tables import ModelTablesDialog
from pynitegui.qt.reports import report_html, result_table
from pynitegui.qt.spatial_model import SpatialLoad, SpatialProject
from pynitegui.qt.spatial_results import member_extrema, member_values, sampled_member


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def bar():
    project = SpatialProject()
    project.add_member((0, 0, 0), (120, 0, 0))
    project.members["M1"].kind = "truss"
    project.nodes["N1"].support = "pin"
    node = project.nodes["N2"]
    node.support = "custom"
    node.restraint_y = node.restraint_z = True
    project.loads["L1"] = SpatialLoad("L1", "N2", "FX", 10)
    return project


class SpatialTrussTests(unittest.TestCase):
    def test_bar_axial_stiffness_and_unused_rotations(self):
        project = bar()
        result = solve(project)
        E = project.materials[project.default_material].E
        A = project.sections[project.default_section].A
        self.assertAlmostEqual(result.displacements["N2"][0], 10 * 120 / (E * A), places=10)
        self.assertEqual(result.displacements["N2"][3:], (None, None, None))
        self.assertEqual(result.reactions["N2"][3:], (0., 0., 0.))
        self.assertAlmostEqual(result.reactions["N1"][0], -10)
        values = member_values(result, "M1", 60)
        self.assertAlmostEqual(values[0], -10)
        self.assertEqual(values[1:6], (0.,) * 5)
        np.testing.assert_allclose(sampled_member(project, result, "M1")[2][-1], result.displacements["N2"][:3])
        np.testing.assert_allclose(sampled_member(project, result, "M1")[2][30], np.array(result.displacements["N2"][:3]) / 2)
        result = pickle.loads(pickle.dumps(result)).for_combination("Service")
        self.assertEqual(result.displacements["N2"][3:], (None,) * 3)
        self.assertEqual(member_extrema(result, "M1", "min")[1:6], (0.,) * 5)

    def test_tripod_closed_form_force_and_displacement(self):
        project = example_project("3d_tripod")
        result = solve(project)
        joint = project.node_at(0, 80, 0)
        E = project.materials[project.default_material].E
        A = project.sections[project.default_section].A
        self.assertAlmostEqual(result.displacements[joint][1], -3 * 100**3 / (3 * E * A * 80**2), places=10)
        for name in project.members:
            self.assertAlmostEqual(member_values(result, name, 50)[0], 1.25, places=8)
        self.assertAlmostEqual(sum(reaction[1] for reaction in result.reactions.values()), 3)
        self.assertTrue(all(reaction[3:] == (0., 0., 0.) for reaction in result.reactions.values()))
        modified = project.clone()
        for section in modified.sections.values():
            section.Iy *= 1000
            section.Iz *= .001
            section.J *= 10
        for member in modified.members.values():
            member.roll = 63
        other = solve(modified)
        np.testing.assert_allclose(other.displacements[joint][:3], result.displacements[joint][:3], atol=1e-10)

    def test_real_internal_mechanism_not_stabilized_by_unused_rotations(self):
        project = example_project("3d_tripod")
        last = project.members.pop("M3")
        name = project.add_member(project.nodes["N1"].coords, project.nodes[last.start].coords)
        project.members[name].kind = "truss"
        with self.assertRaisesRegex(ValueError, "unstable|Insufficient|singular"):
            solve(project)

    def test_mixed_frame_truss_joint_retains_rotational_stiffness(self):
        project = SpatialProject()
        project.add_member((0, 0, 0), (0, 100, 0))
        project.nodes["N1"].support = "fixed"
        project.add_member((0, 100, 0), (100, 100, 60))
        project.members["M2"].kind = "truss"
        project.nodes["N3"].support = "pin"
        project.loads["L1"] = SpatialLoad("L1", "N2", "FX", 3)
        project.loads["L2"] = SpatialLoad("L2", "N2", "MZ", 5)
        result = solve(project)
        self.assertTrue(all(value is not None for value in result.displacements["N2"]))
        self.assertNotEqual(result.displacements["N2"][5], 0)
        self.assertEqual(result.displacements["N3"][3:], (None,) * 3)
        self.assertEqual(member_values(result, "M2", 50)[1:6], (0.,) * 5)

    def test_joint_load_validation_and_moments_with_support_springs(self):
        project = bar()
        for kind in ("point", "distributed"):
            project.loads["bad"] = SpatialLoad("bad", "M1", "FY", -1, kind=kind, end_magnitude=-1)
            with self.assertRaisesRegex(ValueError, "joint loads"):
                project.validate()
        del project.loads["bad"]
        project.loads["L2"] = SpatialLoad("L2", "N2", "MX", 2)
        with self.assertRaisesRegex(ValueError, "rotational stiffness"):
            solve(project)
        project.nodes["N2"].spring_rx = 4
        result = solve(project)
        self.assertAlmostEqual(result.displacements["N2"][3], .5)
        self.assertAlmostEqual(result.reactions["N2"][3], -2)

    def test_lumped_weight_and_split_mechanism(self):
        project = example_project("3d_tripod")
        project.self_weight_case = "Case 1"
        original = solve(project)
        weight = project.self_weight_total()
        self.assertEqual(len(project.self_weight_loads()), 6)
        self.assertTrue(all(load.target in project.nodes for load in project.self_weight_loads()))
        self.assertAlmostEqual(sum(reaction[1] for reaction in original.reactions.values()), 3 + weight)
        project.split_member("M1", .5)
        self.assertAlmostEqual(project.self_weight_total(), weight)
        with self.assertRaisesRegex(ValueError, "unstable|singular"):
            solve(project)

    def test_version_migration_and_result_exports(self):
        project = bar()
        data = project.to_dict()
        self.assertEqual(data["version"], 18)
        self.assertEqual(Project.from_dict(data).to_dict(), data)
        for version in (16, 17):
            data["version"] = version
            with self.assertRaisesRegex(ValueError, "version 18"):
                Project.from_dict(data)
        result = solve(project)
        headers, rows = result_table(project, result, "nodes")
        self.assertEqual(rows[1][4:7], ["n/a"] * 3)
        self.assertIn("axial", report_html(project, result).lower())
        rotation = next(row for row in envelope_rows(project, result, ("Service",)) if row[:3] == ("Node", "N2", "RX"))
        self.assertEqual(rotation[4:], (None, "", None, ""))


class SpatialTrussEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_inspector_tables_bulk_and_invalid_conversion_are_atomic(self):
        window = MainWindow()
        try:
            project = bar()
            project.members["M1"].kind = "frame"
            window.load_project(project)
            window.select(("members", "M1"))
            window.findChild(QComboBox, "spatial_member_kind").setCurrentText("truss")
            window.findChild(QPushButton, "spatial_apply").click()
            self.assertEqual(window.project.members["M1"].kind, "truss")
            window.undo.undo()
            self.assertEqual(window.project.members["M1"].kind, "frame")
            table = ModelTablesDialog(window, window.project)
            column = table.fields["members"].index("kind")
            table.tables["members"].cellWidget(0, column).setCurrentText("truss")
            table.accept()
            self.assertEqual(table.definition.members["M1"].kind, "truss")
            table.close()
            window.project.loads["bad"] = SpatialLoad("bad", "M1", "FY", -1)
            before = window.project.to_dict()
            window.select(("members", "M1"))
            window.findChild(QComboBox, "spatial_member_kind").setCurrentText("truss")
            with patch.object(QMessageBox, "warning") as warning:
                window.findChild(QPushButton, "spatial_apply").click()
            warning.assert_called_once()
            self.assertEqual(window.project.to_dict(), before)
            window.load_project(example_project("3d_tripod"))
            window.select_many([("members", "M1"), ("members", "M2")])
            window.findChild(QComboBox, "bulk_kind").setCurrentText("frame")
            window.findChild(QPushButton, "bulk_apply").click()
            self.assertEqual([member.kind for member in window.project.members.values()], ["frame", "frame", "truss"])
            window.undo.undo()
            self.assertTrue(all(member.kind == "truss" for member in window.project.members.values()))
            window.select(("members", "M1"))
            with patch.object(QMessageBox, "information") as information:
                window.add_load()
            information.assert_called_once()
        finally:
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
