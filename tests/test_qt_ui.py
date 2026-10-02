"""Offscreen integration tests for Qt editing and analysis lifecycle."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import unittest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsLineItem
from pynitegui.qt.app import MainWindow


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.application.processEvents()
        self.window.view.fit()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()

    def test_canvas_drawing_and_undo(self):
        self.window.set_mode("draw")
        for point in (QPointF(0, 0), QPointF(240, 0)):
            QTest.mouseClick(self.window.view.viewport(), Qt.MouseButton.LeftButton, pos=self.window.view.mapFromScene(point))
        self.assertEqual(len(self.window.project.members), 1)
        self.window.undo.undo()
        self.assertFalse(self.window.project.members)
        self.window.undo.redo()
        self.assertEqual(len(self.window.project.members), 1)

    def test_analysis_and_invalidated_results(self):
        self.window.example()
        self.window.run_analysis()
        deadline = time.monotonic() + 15
        while self.window.thread is not None and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.01)
        self.assertIsNone(self.window.thread)
        self.assertIsNotNone(self.window.result)
        self.assertEqual(self.window.results_table.rowCount(), 2)
        self.window.deformed_action.setChecked(True)
        self.window.view.redraw()
        self.window.edit("Move node", lambda project: setattr(project.nodes["N2"], "x", 432))
        self.assertIsNone(self.window.result)
        self.assertFalse(self.window.deformed_action.isEnabled())
        self.window.undo.undo()
        self.assertEqual(self.window.project.nodes["N2"].x, 420)

    def test_selection_uses_screen_distance(self):
        self.window.example()
        self.window.view.fit()
        origin = self.window.view.mapFromScene(QPointF(0, 0))
        for factor in (0.5, 2):
            self.window.view.scale(factor, factor)
            origin = self.window.view.mapFromScene(QPointF(0, 0))
            point = self.window.view.mapToScene(origin + type(origin)(5, 0))
            self.assertEqual(self.window.view.hit(point), ("nodes", "N1"))

    def test_reversed_member_deforms_in_global_load_direction(self):
        self.window.example()
        def reverse(project):
            member = project.members["M1"]
            member.start, member.end = member.end, member.start
        self.window.edit("Reverse member", reverse)
        self.window.run_analysis()
        deadline = time.monotonic() + 15
        while self.window.thread is not None and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.01)
        self.assertIsNone(self.window.thread)
        self.assertIsNotNone(self.window.result)
        self.window.deformed_action.setChecked(True)
        self.window.view.redraw()
        lines = [item.line() for item in self.window.view.scene().items()
                 if isinstance(item, QGraphicsLineItem) and item.pen().color().name() == "#bd3549"]
        self.assertEqual(len(lines), 40)
        self.assertGreater(max(line.y2() for line in lines), 0)
        self.assertGreaterEqual(min(line.y2() for line in lines), -1e-7)


if __name__ == "__main__":
    unittest.main()
