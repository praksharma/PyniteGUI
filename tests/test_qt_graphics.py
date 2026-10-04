"""Launch-time renderer choice and actionable native failure recovery."""
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.graphics import configure_graphics, graphics_mode, launch_options
from pynitegui.qt.spatial_view import Bridge


class GraphicsLaunchTests(unittest.TestCase):
    def test_default_preserves_hardware_backend_and_environment(self):
        environment = {"QTWEBENGINE_CHROMIUM_FLAGS": "--use-angle=vulkan", "QT_OPENGL": "desktop"}
        original = environment.copy()
        self.assertEqual(configure_graphics("auto", environment), "auto")
        self.assertEqual(environment, original)

    def test_software_selects_driver_without_disabling_security(self):
        environment = {}
        self.assertEqual(configure_graphics("software", environment), "software")
        self.assertEqual(shlex.split(environment["QTWEBENGINE_CHROMIUM_FLAGS"]),
                         ["--use-gl=angle", "--use-angle=swiftshader", "--disable-gpu-compositing"])
        self.assertEqual(environment["QT_OPENGL"], "software")
        self.assertNotIn("QT_QUICK_BACKEND", environment)
        self.assertNotIn("QTWEBENGINE_DISABLE_SANDBOX", environment)
        self.assertNotIn("--enable-unsafe-swiftshader", environment["QTWEBENGINE_CHROMIUM_FLAGS"])

    def test_explicit_software_mode_replaces_conflicting_gpu_flags(self):
        environment = {"QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --disable-gpu-compositing --use-gl=egl --use-angle=vulkan --use-vulkan=native --disable-software-rasterizer --disable-webgl --disable-webgl2 --lang=en-GB"}
        configure_graphics("software", environment)
        self.assertEqual(shlex.split(environment["QTWEBENGINE_CHROMIUM_FLAGS"]),
                         ["--lang=en-GB", "--use-gl=angle", "--use-angle=swiftshader", "--disable-gpu-compositing"])

    def test_keeps_user_flags_and_is_idempotent(self):
        environment = {"QTWEBENGINE_CHROMIUM_FLAGS": '--lang=en-GB --user-agent="Test Agent"'}
        configure_graphics("software", environment)
        once = environment.copy()
        configure_graphics("software", environment)
        self.assertEqual(once, environment)
        self.assertIn("--user-agent=Test Agent", shlex.split(environment["QTWEBENGINE_CHROMIUM_FLAGS"]))

    def test_invalid_flag_quoting_is_reported(self):
        with self.assertRaises(ValueError):
            configure_graphics("software", {"QTWEBENGINE_CHROMIUM_FLAGS": '"unclosed'})

    def test_bad_saved_preferences_use_automatic(self):
        for value in (None, [], "bad", 1):
            self.assertEqual(graphics_mode(value), "auto")
            self.assertEqual(launch_options(["pynitegui"], value), ("auto", ["pynitegui"]))

    def test_saved_software_used_on_normal_launch(self):
        self.assertEqual(launch_options(["pynitegui"], "software"), ("software", ["pynitegui"]))

    def test_cli_software_option_and_shortcut(self):
        for arguments in (("--software-rendering",), ("--graphics", "software"), ("--graphics=software",)):
            self.assertEqual(launch_options(["pynitegui", *arguments]), ("software", ["pynitegui"]))

    def test_cli_automatic_overrides_saved_software(self):
        self.assertEqual(launch_options(["pynitegui", "--graphics=auto"], "software"), ("auto", ["pynitegui"]))

    def test_qt_arguments_preserved_and_engine_arguments_not_consumed(self):
        arguments = ["pynitegui", "--software-rendering", "-platform", "offscreen", "--webEngineArgs", "--graphics=auto"]
        self.assertEqual(launch_options(arguments), ("software", ["pynitegui", "-platform", "offscreen", "--webEngineArgs", "--graphics=auto"]))
        self.assertEqual(arguments[1], "--software-rendering")

    def test_invalid_cli_option_rejected(self):
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            launch_options(["pynitegui", "--graphics=missing"])


class GraphicsRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.directory.name)/"settings.ini"), QSettings.Format.IniFormat)
        self.window = MainWindow(settings=self.settings)
        self.window.load_project(example_project("3d_cantilever"))

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_failure_is_visible_and_does_not_change_project(self):
        before = self.window.project.to_dict()
        Bridge(self.window.view).failed("WebGL2 blocklisted")
        self.assertFalse(self.window.view.ready)
        self.assertFalse(self.window.view.failure_panel.isHidden())
        self.assertIn("WebGL2 blocklisted", self.window.view.failure_message.text())
        self.assertEqual(self.window.project.to_dict(), before)

    def test_recovery_button_saves_software_preference_without_closing(self):
        view = self.window.view
        view.render_failure("Failed context")
        before = self.window.project.to_dict()
        with patch.object(QMessageBox, "information") as message:
            view.findChild(QPushButton, "spatial_software_restart").click()
        self.assertEqual(self.settings.value("graphics"), "software")
        self.assertTrue(self.window.graphics_actions["software"].isChecked())
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertIn("restarting", message.call_args.args[2])

    def test_saved_mode_reflected_by_view_menu(self):
        self.settings.setValue("graphics", "software")
        other = MainWindow(settings=self.settings)
        self.assertTrue(other.graphics_actions["software"].isChecked())
        other.close()
        other.deleteLater()

    def test_switch_back_to_automatic_is_saved(self):
        with patch.object(QMessageBox, "information"):
            self.window.set_graphics_mode("software")
            self.window.set_graphics_mode("auto")
        self.assertEqual(self.settings.value("graphics"), "auto")
        self.assertTrue(self.window.graphics_actions["auto"].isChecked())

    def test_failure_text_is_plain_and_bounded(self):
        view = self.window.view
        view.render_failure("<img src=bad>" + "x"*1000)
        self.assertLess(len(view.failure_message.text()), 700)
        self.assertEqual(view.failure_message.textFormat().name, "PlainText")


if __name__ == "__main__":
    unittest.main()
