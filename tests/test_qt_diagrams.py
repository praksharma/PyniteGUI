import unittest
import numpy as np
from pynitegui.qt.model import Project, Load
from pynitegui.qt.analysis import analyze
from pynitegui.qt.diagrams import sample_member, structure_data


def portal():
    project = Project()
    project.add_member((60, 0), (60, 132))
    project.add_member((60, 132), (264, 132))
    project.add_member((264, 132), (264, 0))
    project.nodes["N1"].support = "fixed"
    project.nodes["N4"].support = "fixed"
    project.loads["L1"] = Load("L1", "M2", "FY", -10, 0.5)
    return project


class DiagramTests(unittest.TestCase):
    def test_point_load_jump_at_exact_position(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.nodes["N1"].support = "fixed"
        project.loads["L1"] = Load("L1", "M1", "FY", -10, 0.37)
        data = sample_member(project, analyze(project), "M1")
        index = np.where(np.diff(data["x"]) == 0)[0][0]
        self.assertAlmostEqual(data["x"][index], 44.4)
        self.assertAlmostEqual(abs(data["shear"][index + 1] - data["shear"][index]), 10, places=6)
        self.assertAlmostEqual(data["moment"][index + 1], data["moment"][index], places=4)

    def test_concentrated_moment_jump(self):
        project = Project()
        project.add_member((0, 0), (120, 0))
        project.nodes["N1"].support = "fixed"
        project.loads["L1"] = Load("L1", "M1", "MZ", 7, 0.42)
        data = sample_member(project, analyze(project), "M1")
        index = np.where(np.diff(data["x"]) == 0)[0][0]
        self.assertAlmostEqual(abs(data["moment"][index + 1] - data["moment"][index]), 7, places=6)

    def test_portal_includes_columns_and_is_orientation_independent(self):
        project = portal()
        result = analyze(project)
        self.assertAlmostEqual(sum(row[1] for row in result.reactions.values()), 10)
        original = {key: structure_data(project, result, key) for key in ("axial", "shear", "moment")}
        for member in project.members.values():
            member.start, member.end = member.end, member.start
        reversed_result = analyze(project)
        for quantity in original:
            reverse = structure_data(project, reversed_result, quantity)
            self.assertEqual(set(reverse), {"M1", "M2", "M3"})
            for name in reverse:
                self.assertTrue(np.allclose(original[quantity][name]["base"], reverse[name]["base"][::-1]))
                self.assertTrue(np.allclose(original[quantity][name]["values"], reverse[name]["values"][::-1], atol=1e-5))
            self.assertGreater(np.max(np.abs(original[quantity]["M1"]["values"])), 1)

    def test_inclined_member_orientation(self):
        project = Project()
        project.add_member((0, 0), (120, 120))
        project.nodes["N1"].support = "fixed"
        project.loads["L1"] = Load("L1", "N2", "FY", -2)
        result = analyze(project)
        original = {key: structure_data(project, result, key)["M1"] for key in ("axial", "shear", "moment")}
        member = project.members["M1"]
        member.start, member.end = member.end, member.start
        reverse_result = analyze(project)
        for quantity in original:
            reverse = structure_data(project, reverse_result, quantity)["M1"]
            self.assertTrue(np.allclose(original[quantity]["values"], reverse["values"][::-1], atol=1e-5))
            self.assertTrue(np.allclose(original[quantity]["normal"], reverse["normal"]))


if __name__ == "__main__":
    unittest.main()
