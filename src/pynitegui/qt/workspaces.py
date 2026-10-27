"""Optional native command workspaces; switching never rebuilds the editor."""
from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QComboBox, QStyle, QToolBar, QToolButton


# File, view and analysis commands remain useful in both focused workspaces.
TOOLBARS = {
    "toolbar_file": "shared", "toolbar_view": "shared", "toolbar_analysis": "shared",
    "toolbar_edit": "model", "toolbar_loads": "model",
    "toolbar_results": "results", "toolbar_deformation": "results",
}
WORKSPACES = {"all": "All tools", "model": "Model", "results": "Results"}


class Workspaces(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.current = "all"
        self.commands_visible = True
        self.toolbar = QToolBar("Workspace", window)
        self.toolbar.setObjectName("toolbar_workspace")
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        window.insertToolBar(window.findChild(QToolBar, "toolbar_file"), self.toolbar)
        self.selector = QComboBox()
        self.selector.setAccessibleName("Command workspace")
        self.selector.setToolTip("Choose Model or Results command groups, or keep All tools. Switching preserves unsaved inputs and selection.")
        for key, label in WORKSPACES.items():
            self.selector.addItem(label, key)
        self.toolbar.addWidget(self.selector)
        self.commands = window.action("Show Command Toolbars", self.set_commands)
        self.commands.setCheckable(True)
        self.commands.setChecked(True)
        pixmap = QStyle.StandardPixmap.SP_TitleBarShadeButton
        self.commands.setProperty("standard_pixmap", pixmap.value)
        self.commands.setIcon(window.standard_icon(pixmap))
        self.commands.setToolTip("Show or hide command toolbars; the workspace selector stays available")
        button = QToolButton()
        button.setDefaultAction(self.commands)
        self.toolbar.addWidget(button)
        menu = window.menuBar_view.addMenu("Workspace")
        self.group = QActionGroup(self)
        self.actions = {}
        for key, label in WORKSPACES.items():
            action = window.action(label, lambda checked=False, key=key: self.choose(key))
            action.setCheckable(True)
            action.setChecked(key == "all")
            self.group.addAction(action)
            self.actions[key] = action
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.commands)
        self.selector.currentIndexChanged.connect(lambda: self.choose(self.selector.currentData()))

    def choose(self, key):
        if self.window.mcp_mode:
            self.sync_controls()
            return
        if key not in WORKSPACES:
            raise ValueError("Unknown command workspace.")
        self.toolbar.show()
        if key == self.current:
            self.sync_controls()
            return
        # No refresh/select/redraw: property widgets, draft values, result
        # windows and pending editor gestures retain their existing objects.
        view = self.window.view
        planar = getattr(self.window.project, "dimension", "2D") == "2D"
        center = view.mapToScene(view.viewport().width()//2, view.viewport().height()//2) if planar else None
        self.current = key
        self.sync_controls()
        self.apply_toolbars()
        self.window.structure_dock.setVisible(key != "results")
        self.window.properties_dock.setVisible(key != "results")
        if key == "results":
            self.window.results_dock.show()
        elif key == "model":
            self.window.results_dock.hide()
        else:
            self.window.results_dock.setVisible(self.window.result is not None)
        self.window.layout().activate()
        if planar:
            view.centerOn(center)
        self.window.statusBar().showMessage(f"{WORKSPACES[key]} workspace | Model and unsaved inputs preserved", 5000)

    def sync_controls(self):
        self.selector.blockSignals(True)
        self.selector.setCurrentIndex(self.selector.findData(self.current))
        self.selector.blockSignals(False)
        self.actions[self.current].setChecked(True)

    def set_commands(self, visible):
        if self.window.mcp_mode:
            self.commands.setChecked(self.commands_visible)
            return
        view = self.window.view
        planar = getattr(self.window.project, "dimension", "2D") == "2D"
        center = view.mapToScene(view.viewport().width()//2, view.viewport().height()//2) if planar else None
        self.commands_visible = bool(visible)
        self.commands.setChecked(visible)
        self.apply_toolbars()
        self.window.layout().activate()
        if planar:
            view.centerOn(center)

    def apply_toolbars(self):
        pixmap = QStyle.StandardPixmap.SP_TitleBarShadeButton if self.commands.isChecked() else QStyle.StandardPixmap.SP_TitleBarUnshadeButton
        self.commands.setProperty("standard_pixmap", pixmap.value)
        self.commands.setIcon(self.window.standard_icon(pixmap))
        self.commands.setToolTip(("Hide" if self.commands.isChecked() else "Show") + " command toolbars; workspace selector stays available")
        for name, role in TOOLBARS.items():
            toolbar = self.window.findChild(QToolBar, name)
            toolbar.setVisible(self.commands.isChecked() and (self.current == "all" or role in ("shared", self.current)))

    def reset(self):
        self.current = "all"
        self.commands_visible = True
        self.commands.setChecked(True)
        self.sync_controls()
        self.toolbar.show()
        self.apply_toolbars()
