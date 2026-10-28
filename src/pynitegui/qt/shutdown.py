"""Translate terminal interrupts into normal Qt window-close requests."""
import signal
import sys

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication


class TerminalShutdown(QObject):
    def __init__(self, application):
        super().__init__(application)
        self.application = application
        self.pending = self.closing = False
        self.previous = signal.getsignal(signal.SIGINT)
        self.handler = self.request
        signal.signal(signal.SIGINT, self.handler)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def request(self, signum=None, frame=None):
        # Signal handlers must not enter Qt or raise through a Qt callback.
        if not self.closing:
            self.pending = True

    def poll(self):
        if not self.pending or self.closing:
            return
        self.pending, self.closing = False, True
        try:
            modal = QApplication.activeModalWidget()
            if modal is not None:
                modal.raise_()
                modal.activateWindow()
                print("Brecon: finish or cancel the open dialog, then press Ctrl+C again to close.", file=sys.stderr)
                return
            # Honors save/cancel prompts and the existing worker/server cleanup.
            self.application.closeAllWindows()
        finally:
            self.closing = False

    def restore(self):
        self.timer.stop()
        self.pending = False
        if signal.getsignal(signal.SIGINT) == self.handler:
            signal.signal(signal.SIGINT, self.previous)
