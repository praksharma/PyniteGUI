"""Member queries and extrema use solved local values, not screen interpolation."""
import contextlib
import io
import os
import unittest
from types import SimpleNamespace
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from pynitegui.qt.analysis import analyze
from pynitegui.qt.diagrams import DiagramDialog, member_values, member_result_rows
from pynitegui.qt.model import Project, Load


def example():
    project = Project()
    project.add_member((0, 0), (240, 0))
    project.nodes["N1"].support = "pin"
    project.nodes["N2"].support = "roller"
    project.loads["L1"] = Load("L1", "M1", "FY", -10)
    project.set_combination("Double", {"Case 1": 2})
    with contextlib.redirect_stdout(io.StringIO()):
        result = analyze(project)
    return project, result


class InspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_jump_sides_and_exact_interior_value(self):
        project, result = example()
        left = member_values(project, result, "M1", 120, "left")
        right = member_values(project, result, "M1", 120, "right")
        self.assertAlmostEqual(left[1], 5)
        self.assertAlmostEqual(right[1], -5)
        self.assertAlmostEqual(left[2], -600, places=4)
        self.assertAlmostEqual(right[2], -600, places=4)
        self.assertAlmostEqual(member_values(project, result, "M1", 60)[2], -300)
        with self.assertRaises(ValueError):
            member_values(project, result, "M1", 241)

    def test_end_and_extrema_rows(self):
        project, result = example()
        rows = member_result_rows(project, result)
        self.assertEqual([row[1] for row in rows], ["Start", "End", "Minimum", "Maximum"])
        self.assertEqual(rows[0][2], 0)
        self.assertEqual(rows[1][2], 240)
        self.assertIsNone(rows[2][2])
        self.assertAlmostEqual(rows[2][5], -600)
        self.assertAlmostEqual(rows[3][4], 5)
        self.assertAlmostEqual(rows[2][4], -5)
        self.assertLess(rows[2][6], 0)

    def test_dialog_query_units_combination_and_click(self):
        project, result = example()
        dialog = DiagramDialog(None, project, result)
        dialog.distance.setValue(120)
        self.assertAlmostEqual(float(dialog.inspection_values.item(0, 1).text()), -5)
        dialog.inspection_side.setCurrentText("Left side")
        self.assertAlmostEqual(float(dialog.inspection_values.item(0, 1).text()), 5)
        dialog.set_unit_system("si")
        self.assertAlmostEqual(dialog.distance.value(), 3.048)
        self.assertAlmostEqual(float(dialog.inspection_values.item(0, 1).text()), 22.2411, places=4)
        self.assertEqual(dialog.member_results.horizontalHeaderItem(5).text(), "Mz (kN-m)")
        self.assertAlmostEqual(float(dialog.member_results.item(2, 5).text()), -600 * 4.4482216152605 * 0.0254, places=3)
        dialog.select_combination("Double")
        self.assertAlmostEqual(float(dialog.inspection_values.item(0, 1).text()), 44.4822, places=4)
        dialog.inspect_click(SimpleNamespace(button=1, inaxes=dialog.member_figure.axes[0], xdata=1.524))
        self.assertAlmostEqual(dialog.inspection_x, 60)
        self.assertEqual(len(dialog.probes), 4)
        dialog.close()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
