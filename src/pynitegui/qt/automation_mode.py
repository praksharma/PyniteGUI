"""Per-window manual input lock with an always-available native release button."""
from PySide6.QtCore import QObject, QEvent, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDialog, QDockWidget, QToolBar


class AutomationMode(QObject):
    changed = Signal()
    INPUT_EVENTS = {QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.Shortcut,
                    QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                    QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseMove, QEvent.Type.Wheel,
                    QEvent.Type.ContextMenu, QEvent.Type.InputMethod, QEvent.Type.TouchBegin,
                    QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd, QEvent.Type.DragEnter,
                    QEvent.Type.DragMove, QEvent.Type.Drop, QEvent.Type.TabletPress,
                    QEvent.Type.TabletMove, QEvent.Type.TabletRelease}

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.locked = []
        self.action = QAction("MCP mode", self)
        self.action.setCheckable(True)
        self.action.setEnabled(False)
        self.action.setToolTip("Only while the automation server runs: lock manual controls. Entering cancels drawing and discards unapplied inspector inputs. Click again to unlock.")
        self.action.toggled.connect(self.set_enabled)
        QApplication.instance().installEventFilter(self)

    def sync_server(self):
        server = self.window.automation_server
        running = server is not None and server.state == "Running" and server.bridge.active
        if not running and self.window.mcp_mode:
            self.set_enabled(False)
        self.action.setEnabled(running)

    def set_enabled(self, enabled):
        window = self.window
        server = window.automation_server
        if enabled and (server is None or server.state != "Running" or not server.bridge.active):
            enabled = False
        if enabled == window.mcp_mode:
            self.action.setChecked(enabled)
            return
        if enabled:
            modal = QApplication.activeModalWidget()
            if self.owns(modal):
                self.action.setChecked(False)
                window.statusBar().showMessage("Finish the open dialog before entering MCP mode.")
                return
            window.set_mode("select")
            window.refresh()  # Explicit handover discards unapplied inspector drafts.
            window.mcp_mode = True
            controls = [window.menuBar(), window.centralWidget(), window.unit_selector,
                        window.analysis_cancel_button, *window.findChildren(QToolBar),
                        *window.findChildren(QDockWidget), *window.findChildren(QDialog)]
            self.locked = [(control, control.isEnabled()) for control in dict.fromkeys(controls)
                           if control is not window.automation_panel]
            for control, _ in self.locked:
                control.setEnabled(False)
            self.action.setText("Leave MCP mode")
            window.statusBar().showMessage("MCP mode | Manual controls locked; automation server controls this project")
        else:
            window.mcp_mode = False
            for control, previously_enabled in self.locked:
                try:
                    control.setEnabled(previously_enabled)
                except RuntimeError:  # A nonmodal results window may have been destroyed.
                    pass
            self.locked.clear()
            self.action.setText("MCP mode")
            window.statusBar().showMessage("Manual controls unlocked")
        self.action.setChecked(enabled)
        self.changed.emit()

    def owns(self, target):
        while target is not None:
            if target is self.window:
                return True
            target = target.parent()
        return False

    def eventFilter(self, target, event):
        if self.window.mcp_mode and event.type() in self.INPUT_EVENTS and self.owns(target):
            current = target
            while current is not None and current is not self.window:
                if current.property("pynitegui_non_model_controls"):
                    return False
                current = current.parent()
            return True
        return False
