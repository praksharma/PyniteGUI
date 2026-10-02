"""Focused regression checks for project editing and the solver contract."""
import tempfile
import unittest
from pathlib import Path

from pynitegui.qt.analysis import analyze
from pynitegui.qt.model import Load, Project


def beam():
    project = Project()
    project.add_member((0, 0), (420, 0))
    project.nodes["N1"].support = "pin"
    project.nodes["N2"].support = "roller"
    project.loads["L1"] = Load("L1", "M1", "FY", -10, 0.5)
    return project


class ProjectTests(unittest.TestCase):
    def test_round_trip(self):
        project = beam()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "beam.pynite.json"
            project.save(path)
            self.assertEqual(project.to_dict(), Project.open(path).to_dict())

    def test_delete_node_removes_attached_members_and_loads(self):
        project = beam()
        project.loads["L2"] = Load("L2", "N1")
        project.delete("nodes", "N1")
        self.assertEqual(project.members, {})
        self.assertEqual(project.loads, {})
        self.assertEqual(set(project.nodes), {"N2"})

    def test_invalid_edits_and_files(self):
        project = beam()
        with self.assertRaises(ValueError):
            project.add_member((420, 0), (0, 0))
        project.nodes["N2"].x = 0
        with self.assertRaises(ValueError):
            project.validate()
        data = beam().to_dict()
        data["loads"]["L1"]["target"] = "missing"
        with self.assertRaises(ValueError):
            Project.from_dict(data)

    def test_clone_does_not_share_entities(self):
        project = beam()
        other = project.clone()
        other.nodes["N1"].x = -10
        self.assertEqual(project.nodes["N1"].x, 0)

    def test_simply_supported_member_load(self):
        project = beam()
        result = analyze(project)
        self.assertAlmostEqual(result.reactions["N1"][1], 5, places=7)
        self.assertAlmostEqual(result.reactions["N2"][1], 5, places=7)
        expected = -10 * 420**3 / (48 * project.E * project.Iz)
        actual = result.solver.members["M1"].deflection("dy", 210, "Service")
        self.assertAlmostEqual(actual, expected, places=7)

    def test_nodal_load_and_fixed_support(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.nodes["N1"].support = "fixed"
        project.loads["L1"] = Load("L1", "N2", "FY", -2)
        result = analyze(project)
        self.assertAlmostEqual(result.reactions["N1"][1], 2, places=7)
        self.assertAlmostEqual(result.reactions["N1"][2], 240, places=7)
        expected = -2 * 120**3 / (3 * project.E * project.Iz)
        self.assertAlmostEqual(result.displacements["N2"][1], expected, places=7)


if __name__ == "__main__":
    unittest.main()
