"""Observed WebGL information, kept separate from requested startup settings."""
import json
import os

from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFormLayout, QLabel, QPushButton, QStyle

from .graphics import GRAPHICS_OVERRIDES, graphics_mode


class GraphicsDiagnostics(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.serial = 0
        self.setWindowTitle("3D Graphics Diagnostics")
        self.resize(660, 440)
        form = QFormLayout(self)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.values = {}
        for key, title in (("mode", "Startup preference"), ("saved", "Next-launch preference"),
                           ("qt", "Qt / platform"), ("surface", "Observed window surface"),
                           ("environment", "Requested backend / overrides"), ("status", "3D viewport"),
                           ("renderer", "Observed WebGL renderer"), ("vendor", "Observed WebGL vendor"),
                           ("version", "WebGL / shader version"), ("source", "Renderer information source")):
            label = QLabel()
            label.setWordWrap(True)
            label.setMinimumWidth(240)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.values[key] = label
            form.addRow(title, label)
        refresh = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Refresh")
        refresh.clicked.connect(self.refresh)
        form.addRow(refresh)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        form.addRow(buttons)
        self.refresh()

    def refresh(self):
        self.serial += 1
        serial = self.serial
        app = QApplication.instance()
        self.values["mode"].setText(graphics_mode(app.property("pynitegui_graphics")))
        settings = self.window.settings_store
        self.values["saved"].setText(graphics_mode(settings.value("graphics", "auto")) if settings else "Not persisted")
        self.values["qt"].setText(f"{qVersion()} / {app.platformName()}")
        handle = self.window.windowHandle()
        self.values["surface"].setText(handle.surfaceType().name if handle else "Not created")
        self.values["environment"].setText("\n".join(f"{key}={os.environ[key]}" for key in GRAPHICS_OVERRIDES if os.environ.get(key)) or "Platform defaults")
        for key in ("renderer", "vendor", "version", "source"):
            self.values[key].setText("Unavailable")
        view = self.window.spatial_view
        if view is None or self.window.view is not view:
            self.values["status"].setText("No active 3D viewport")
        elif not view.ready or not view.web:
            self.values["status"].setText(view.failure_message.text() or "Not ready")
        else:
            self.values["status"].setText("Querying renderer")
            view.web.page().runJavaScript("JSON.stringify(window.pyniteViewer.diagnostics());",
                                         lambda data: self.received(data, serial))

    def received(self, data, serial):
        try:
            if serial != self.serial:
                return
            info = json.loads(data) if isinstance(data, str) else None
            if not isinstance(info, dict):
                self.values["status"].setText("Renderer information unavailable")
                return
            self.values["status"].setText("Context lost" if info.get("lost") else "Ready")
            for key in ("renderer", "vendor", "source"):
                self.values[key].setText(str(info.get(key) or "Unavailable"))
            self.values["version"].setText(" / ".join(str(info.get(key) or "Unavailable") for key in ("version", "shader")))
        except ValueError:
            try:
                self.values["status"].setText("Renderer information unavailable")
            except RuntimeError:
                pass
        except RuntimeError:
            # A pending WebEngine reply may arrive after this dialog is closed.
            pass


def show_graphics_diagnostics(window):
    dialog = getattr(window, "graphics_diagnostics", None)
    if dialog is None:
        dialog = GraphicsDiagnostics(window)
        window.graphics_diagnostics = dialog
    else:
        dialog.refresh()
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
