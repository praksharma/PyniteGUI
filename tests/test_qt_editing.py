"""Snapped drags and visibility filters must preserve model ownership."""
import os
import unittest
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from pynitegui.qt.app import MainWindow, EngineeringSymbol
from pynitegui.qt.model import Load


class EditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.window.example()
        self.app.processEvents()
        self.window.view.fit()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def press_move(self, target):
        view = self.window.view
        start = view.mapFromScene(QPointF(420, 0))
        end = view.mapFromScene(QPointF(*target))
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        return end

    def test_drag_is_one_snapped_undoable_edit(self):
        count = self.window.undo.count()
        end = self.press_move((449, -29))
        self.assertEqual(self.window.project.nodes["N2"].x, 420)
        self.assertTrue(self.window.view.drag_items)
        QTest.mouseRelease(self.window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual((self.window.project.nodes["N2"].x, self.window.project.nodes["N2"].y), (444, 24))
        self.assertEqual(self.window.undo.count(), count + 1)
        self.window.undo.undo()
        self.assertEqual(self.window.project.nodes["N2"].x, 420)
        self.window.undo.redo()
        self.assertEqual(self.window.project.nodes["N2"].x, 444)

    def test_cancel_drag_and_plain_click_do_not_edit(self):
        before = self.window.project.to_dict()
        end = self.press_move((444, -24))
        self.window.set_mode("select")
        QTest.mouseRelease(self.window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(self.window.project.to_dict(), before)
        position = self.window.view.mapFromScene(QPointF(420, 0))
        QTest.mouseClick(self.window.view.viewport(), Qt.MouseButton.LeftButton, pos=position)
        self.assertEqual(self.window.project.to_dict(), before)

    def test_collision_is_rejected(self):
        before = self.window.project.to_dict()
        end = self.press_move((0, 0))
        with patch.object(QMessageBox, "warning") as warning:
            QTest.mouseRelease(self.window.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
            warning.assert_called_once()
        self.assertEqual(self.window.project.to_dict(), before)

    def test_filter_only_changes_visible_loads(self):
        self.window.edit("Add case", lambda p: p.set_load_case("Wind"))
        self.window.edit("Add wind", lambda p: p.loads.update({"L2": Load("L2", "N2", "FX", 3, case="Wind")}))
        before, revision = self.window.project.to_dict(), self.window.revision
        def glyphs():
            return [item for item in self.window.view.scene().items() if isinstance(item, EngineeringSymbol) and item.kind == "load"]
        self.window.load_filter.setCurrentText("Wind")
        self.assertEqual(len(glyphs()), 1)
        self.assertEqual(glyphs()[0].value, ("FX", 3))
        self.window.load_filter.setCurrentText("Hide loads")
        self.assertFalse(glyphs())
        self.window.load_filter.setCurrentText("All load cases")
        self.assertEqual(len(glyphs()), 2)
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertEqual(self.window.revision, revision)


if __name__ == "__main__":
    unittest.main()
