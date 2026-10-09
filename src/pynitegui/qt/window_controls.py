"""Client controls for GNOME Wayland Vulkan windows without Qt decorations."""
import os

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QSurface
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QFormLayout, QHBoxLayout, QLabel, QMainWindow,
    QSizePolicy, QStyle, QToolButton, QVBoxLayout, QWidget,
)


def needs_window_controls(window):
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
    handle = window.windowHandle()
    return ("GNOME" in desktop and QApplication.platformName().startswith("wayland")
            and handle is not None and handle.surfaceType() == QSurface.SurfaceType.VulkanSurface
            and not window.windowFlags() & Qt.WindowType.FramelessWindowHint)


def resize_edges(point, size, width=5):
    edges = Qt.Edge(0)
    if point.x() < width:
        edges |= Qt.Edge.LeftEdge
    elif point.x() >= size.width() - width:
        edges |= Qt.Edge.RightEdge
    if point.y() < width:
        edges |= Qt.Edge.TopEdge
    elif point.y() >= size.height() - width:
        edges |= Qt.Edge.BottomEdge
    return edges


class WindowTitle(QLabel):
    def __init__(self, window):
        super().__init__()
        self.full_title = window.windowTitle()
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        window.windowTitleChanged.connect(self.set_title)

    def set_title(self, text):
        self.full_title = text
        self.setText(self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, self.width()))

    def resizeEvent(self, event):
        self.set_title(self.full_title)
        super().resizeEvent(event)


class WindowControls(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.target = window
        self.setObjectName("client_window_controls")
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 4, 2)
        layout.setSpacing(2)
        self.title = WindowTitle(window)
        layout.addWidget(self.title, 1)
        self.minimize = self.button("Minimize", QStyle.StandardPixmap.SP_TitleBarMinButton, window.showMinimized)
        self.maximize = self.button("Maximize", QStyle.StandardPixmap.SP_TitleBarMaxButton, self.toggle_maximized)
        self.close_button = self.button("Close", QStyle.StandardPixmap.SP_TitleBarCloseButton, window.close)
        self.close_button.setObjectName("client_window_close")
        flags = window.windowFlags()
        self.minimize.setVisible(bool(flags & Qt.WindowType.WindowMinimizeButtonHint))
        self.maximize.setVisible(bool(flags & Qt.WindowType.WindowMaximizeButtonHint))
        window.installEventFilter(self)

    def button(self, name, icon, callback):
        button = QToolButton(self)
        button.setAccessibleName(name)
        button.setToolTip(name)
        button.setIcon(self.style().standardIcon(icon))
        button.setFixedSize(32, 30)
        button.clicked.connect(callback)
        self.layout().addWidget(button)
        return button

    def toggle_maximized(self):
        self.target.showNormal() if self.target.isMaximized() else self.target.showMaximized()

    def eventFilter(self, target, event):
        if event.type() == QEvent.Type.WindowStateChange:
            maximized = self.target.isMaximized()
            self.maximize.setToolTip("Restore" if maximized else "Maximize")
            self.maximize.setAccessibleName(self.maximize.toolTip())
            icon = QStyle.StandardPixmap.SP_TitleBarNormalButton if maximized else QStyle.StandardPixmap.SP_TitleBarMaxButton
            self.maximize.setIcon(self.style().standardIcon(icon))
            self.setVisible(not self.target.isFullScreen())
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.target.windowHandle():
            point = self.target.mapFromGlobal(event.globalPosition().toPoint())
            edges = resize_edges(point, self.target.size())
            if edges and not self.target.isMaximized():
                self.target.windowHandle().startSystemResize(edges)
            else:
                self.target.windowHandle().startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.maximize.isHidden():
            self.toggle_maximized()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


def attach_window_controls(window):
    if hasattr(window, "client_controls"):
        return window.client_controls
    if isinstance(window, QMainWindow):
        menu = window.menuWidget()
        if menu:
            menu.setParent(None)
        container = QWidget(window)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        controls = WindowControls(window)
        layout.addWidget(controls)
        if menu:
            layout.addWidget(menu)
        window.setMenuWidget(container)
    elif isinstance(window.layout(), (QBoxLayout, QFormLayout)):
        controls = WindowControls(window)
        layout = window.layout()
        if isinstance(layout, QBoxLayout):
            layout.insertWidget(0, controls)
        else:
            layout.insertRow(0, controls)
    else:
        return None
    window.client_controls = controls
    window.setMouseTracking(True)
    return controls


class WindowControlsController(QObject):
    def __init__(self, application):
        super().__init__(application)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.scan)
        self.timer.start()

    def scan(self):
        # A global Python event filter can crash on WebEngine's internal QObjects.
        # Inspect only top-level widgets, including windows promoted to Vulkan later.
        for window in QApplication.topLevelWidgets():
            if not hasattr(window, "client_controls") and window.windowType() in (
                    Qt.WindowType.Window, Qt.WindowType.Dialog, Qt.WindowType.Tool):
                self.decorate(window)

    def decorate(self, window):
        try:
            if needs_window_controls(window):
                if attach_window_controls(window):
                    window.installEventFilter(self)
        except RuntimeError:
            pass  # A transient window may have closed before the deferred check.

    def eventFilter(self, target, event):
        if isinstance(target, QWidget):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                window = target.window()
                if hasattr(window, "client_controls") and not (window.isMaximized() or window.isFullScreen()):
                    edges = resize_edges(window.mapFromGlobal(event.globalPosition().toPoint()), window.size())
                    if edges and window.windowHandle().startSystemResize(edges):
                        return True
        return False


def install_window_controls(application):
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
    if (not hasattr(application, "window_controls_controller") and "GNOME" in desktop
            and application.platformName().startswith("wayland")
            and os.environ.get("QSG_RHI_BACKEND") == "vulkan"):
        controller = WindowControlsController(application)
        application.window_controls_controller = controller
