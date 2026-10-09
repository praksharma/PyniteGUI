import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QSurface, QWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QMainWindow, QVBoxLayout
from pynitegui.qt.app import MainWindow
from pynitegui.qt.spatial_view import Bridge
from pynitegui.qt.window_controls import (
    WindowControlsController, attach_window_controls, needs_window_controls, resize_edges,
)


class WindowControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QMainWindow()
        self.window.setWindowTitle("Example | PyniteGUI")
        self.menu = self.window.menuBar()
        self.menu.addMenu("File")
        self.controls = attach_window_controls(self.window)
        self.window.resize(640, 320)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_title_and_menu_survive_attachment_and_title_updates(self):
        self.assertIs(attach_window_controls(self.window), self.controls)
        self.assertEqual(self.menu.actions()[0].text(), "File")
        self.window.setWindowTitle("* Model | PyniteGUI")
        self.assertEqual(self.controls.title.full_title, "* Model | PyniteGUI")
        self.assertIn("Model", self.controls.title.text())

    def test_close_button_closes_window(self):
        self.controls.close_button.click()
        self.assertFalse(self.window.isVisible())

    def test_maximize_and_restore(self):
        self.controls.maximize.click()
        self.assertTrue(self.window.isMaximized())
        self.assertEqual(self.controls.maximize.toolTip(), "Restore")
        self.controls.maximize.click()
        self.assertFalse(self.window.isMaximized())

    def test_minimize(self):
        self.controls.minimize.click()
        self.assertTrue(self.window.isMinimized())

    def test_title_bar_requests_compositor_move(self):
        with patch.object(QWindow, "startSystemMove", return_value=True) as move:
            QTest.mousePress(self.controls, Qt.MouseButton.LeftButton, pos=QPoint(40, 18))
        move.assert_called_once()

    def test_title_double_click_maximizes(self):
        QTest.mouseDClick(self.controls, Qt.MouseButton.LeftButton, pos=QPoint(40, 18))
        self.assertTrue(self.window.isMaximized())

    def test_resize_edges_and_interior(self):
        self.assertEqual(resize_edges(QPoint(1, 1), QSize(640, 320)), Qt.Edge.LeftEdge | Qt.Edge.TopEdge)
        self.assertEqual(resize_edges(QPoint(639, 319), QSize(640, 320)), Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
        self.assertFalse(resize_edges(QPoint(100, 100), QSize(640, 320)))

    def test_owned_box_and_form_dialogs_get_close_controls(self):
        for layout_type in (QVBoxLayout, QFormLayout):
            dialog = QDialog()
            layout_type(dialog)
            controls = attach_window_controls(dialog)
            self.assertIsNotNone(controls)
            dialog.show()
            controls.close_button.click()
            self.assertFalse(dialog.isVisible())
            dialog.deleteLater()

    def test_native_decoration_fallback_is_scoped(self):
        window = MagicMock()
        window.windowHandle.return_value.surfaceType.return_value = QSurface.SurfaceType.VulkanSurface
        window.windowFlags.return_value = Qt.WindowType.Window
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}), patch.object(QApplication, "platformName", return_value="wayland"):
            self.assertTrue(needs_window_controls(window))
            window.windowHandle.return_value.surfaceType.return_value = QSurface.SurfaceType.RasterSurface
            self.assertFalse(needs_window_controls(window))
        with patch.object(QApplication, "platformName", return_value="xcb"):
            self.assertFalse(needs_window_controls(window))

    def test_controller_discovers_promoted_window_only_once(self):
        window = QMainWindow()
        controller = WindowControlsController(self.app)
        controller.timer.stop()
        try:
            with patch.object(QApplication, "topLevelWidgets", return_value=[window]), patch(
                    "pynitegui.qt.window_controls.needs_window_controls", return_value=False):
                controller.scan()
                self.assertFalse(hasattr(window, "client_controls"))
            with patch.object(QApplication, "topLevelWidgets", return_value=[window]), patch(
                    "pynitegui.qt.window_controls.needs_window_controls", return_value=True) as needs:
                controller.scan()
                controls = window.client_controls
                controller.scan()
                self.assertIs(window.client_controls, controls)
                needs.assert_called_once()
        finally:
            window.deleteLater()
            controller.deleteLater()
            self.app.processEvents()

    def test_controls_hide_in_fullscreen_and_return(self):
        self.window.showFullScreen()
        self.app.processEvents()
        self.assertTrue(self.controls.isHidden())
        self.window.showNormal()
        self.app.processEvents()
        self.assertFalse(self.controls.isHidden())

    def test_close_keeps_existing_unsaved_work_confirmation(self):
        window = MainWindow()
        controls = attach_window_controls(window)
        window.show()
        with patch.object(window, "confirm_discard", return_value=False) as confirm:
            controls.close_button.click()
            self.assertTrue(window.isVisible())
            confirm.assert_called_once()
        window.saved = window.project.to_dict()
        window.close()
        window.deleteLater()

    def test_gizmo_orientation_sync_does_not_send_recursive_commands(self):
        window = MainWindow()
        window.new_spatial_project()
        with patch.object(window.view, "call") as call:
            Bridge(window.view).orientation(5)
            self.assertEqual(window.view.orientation.currentText(), "Bottom XZ")
            Bridge(window.view).orientation(7)
            self.assertEqual(window.view.orientation.currentText(), "Orbit")
            Bridge(window.view).orientation(99)
            self.assertEqual(window.view.orientation.currentIndex(), 7)
            call.assert_not_called()
        window.close()
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
