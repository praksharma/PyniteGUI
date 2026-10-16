"""Terminal SIGINT closes through Qt instead of interrupting arbitrary slots."""
import contextlib
import io
import os
import signal
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.shutdown import TerminalShutdown


class TerminalShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.previous = signal.getsignal(signal.SIGINT)
        self.controller = TerminalShutdown(self.app)
        self.controller.timer.stop()

    def tearDown(self):
        self.controller.restore()
        signal.signal(signal.SIGINT, self.previous)
        self.controller.deleteLater()

    def test_signal_is_deferred_and_repeated_interrupts_coalesce(self):
        with patch.object(QApplication, 'activeModalWidget', return_value=None), patch.object(self.app, 'closeAllWindows') as close:
            handler = signal.getsignal(signal.SIGINT)
            handler(signal.SIGINT, None)
            handler(signal.SIGINT, None)
            close.assert_not_called()
            self.controller.poll()
            close.assert_called_once()
            self.controller.poll()
            close.assert_called_once()

    def test_interrupt_during_close_prompt_cannot_reopen_or_bypass_cancel(self):
        def closing():
            self.controller.request()
            self.controller.poll()
        with patch.object(QApplication, 'activeModalWidget', return_value=None), patch.object(self.app, 'closeAllWindows', side_effect=closing) as close:
            self.controller.request()
            self.controller.poll()
            self.controller.poll()
            close.assert_called_once()
            self.assertFalse(self.controller.pending)

    def test_modal_editor_is_preserved_and_user_is_told_what_to_do(self):
        modal, output = Mock(), io.StringIO()
        with patch.object(QApplication, 'activeModalWidget', return_value=modal), patch.object(self.app, 'closeAllWindows') as close, contextlib.redirect_stderr(output):
            self.controller.request()
            self.controller.poll()
        close.assert_not_called()
        modal.raise_.assert_called_once()
        modal.activateWindow.assert_called_once()
        self.assertIn('finish or cancel', output.getvalue())

    def test_unsaved_project_cancel_remains_open_and_second_request_can_close(self):
        window = MainWindow()
        window.show()
        window.project.add_member((0, 0), (120, 0))
        before = window.project.to_dict()
        try:
            with patch.object(QApplication, 'activeModalWidget', return_value=None), patch.object(self.app, 'closeAllWindows', side_effect=window.close):
                with patch.object(window, 'confirm_discard', return_value=False):
                    self.controller.request()
                    self.controller.poll()
                self.assertTrue(window.isVisible())
                self.assertEqual(window.project.to_dict(), before)
                with patch.object(window, 'confirm_discard', return_value=True):
                    self.controller.request()
                    self.controller.poll()
                self.assertFalse(window.isVisible())
        finally:
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()

    def test_restore_restores_own_handler_without_overwriting_new_owner(self):
        self.controller.restore()
        self.assertEqual(signal.getsignal(signal.SIGINT), self.previous)
        replacement = lambda *args: None
        signal.signal(signal.SIGINT, replacement)
        self.controller.restore()
        self.assertIs(signal.getsignal(signal.SIGINT), replacement)

    def test_real_sigint_exits_offscreen_desktop_without_traceback(self):
        source = '''
import os, signal
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.shutdown import TerminalShutdown
app = QApplication([])
window = MainWindow()
window.show()
controller = TerminalShutdown(app)
QTimer.singleShot(100, lambda: os.kill(os.getpid(), signal.SIGINT))
code = app.exec()
controller.restore()
print("clean-terminal-exit", code)
'''
        completed = subprocess.run([sys.executable, '-B', '-c', source], capture_output=True, text=True,
                                   env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYNITEGUI_NO_WEBENGINE': '1'}, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('clean-terminal-exit 0', completed.stdout)
        self.assertNotIn('KeyboardInterrupt', completed.stderr)


if __name__ == '__main__':
    unittest.main()
