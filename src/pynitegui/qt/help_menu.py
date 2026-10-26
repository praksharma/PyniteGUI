"""Native help, shortcuts and application information; links open on request."""
from importlib.metadata import PackageNotFoundError, version
import platform

from PySide6.QtCore import Qt, QUrl, qVersion
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QApplication, QAbstractItemView, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from pynitegui import __version__

DOCS_URL = "https://praksharma.github.io/PyniteGUI/"
SOURCE_URL = "https://github.com/praksharma/PyniteGUI"
LINKS = {"documentation": DOCS_URL, "getting_started": DOCS_URL + "start/first-model/",
         "source": SOURCE_URL, "issues": SOURCE_URL + "/issues"}


def open_link(window, name):
    url = LINKS[name]
    try:
        opened = QDesktopServices.openUrl(QUrl(url))
    except (OSError, RuntimeError):
        opened = False
    if not opened:
        QMessageBox.warning(window, "Could Not Open Browser", "Open this address in your browser:\n\n" + url)
    return opened


def support_information():
    lines = [f"PyniteGUI {__version__}", f"System: {platform.system()} {platform.release()} ({platform.machine()})",
             f"Python: {platform.python_version()}", f"Qt: {qVersion()}"]
    for package in ("PySide6", "PyniteFEA", "numpy", "scipy"):
        try:
            value = version(package)
        except PackageNotFoundError:
            value = "Unavailable"
        lines.append(f"{package}: {value}")
    return "\n".join(lines)


def copy_support_information(window):
    QApplication.clipboard().setText(support_information())
    window.statusBar().showMessage("Application version details copied", 5000)


def shortcut_rows(window):
    rows = set()
    # Main-window commands only: child plot/dialog shortcuts belong to their
    # own windows and must not leak into this reference.
    for action in window.findChildren(QAction):
        if action.parent() is not window:
            continue
        keys = [key.toString(QKeySequence.SequenceFormat.NativeText) for key in action.shortcuts() if not key.isEmpty()]
        if keys:
            label = action.property("command_label") or action.text().replace("&", "")
            rows.add((label, ", ".join(keys)))
    return sorted(rows, key=lambda row: row[0].casefold())


class ShortcutsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("keyboard_shortcuts")
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(560, 500)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a command or shortcut…")
        self.search.setAccessibleName("Find keyboard shortcut")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Command", "Shortcut"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)
        note = QLabel("Single-letter tools work when the model view has focus. "
                      "Escape cancels the current drawing or selection gesture. "
                      "Use the mouse wheel to zoom.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.empty = QLabel("No matching shortcuts.")
        layout.addWidget(self.empty)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self.filter_rows)
        self.refresh()

    def refresh(self):
        rows = shortcut_rows(self.parentWidget())
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, value in enumerate(row):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self.filter_rows()

    def filter_rows(self, *_):
        query = self.search.text().casefold().strip()
        visible = 0
        for row in range(self.table.rowCount()):
            match = any(query in self.table.item(row, column).text().casefold() for column in range(2))
            self.table.setRowHidden(row, not match)
            visible += match
        self.empty.setVisible(not visible)


class AboutDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("about_pynitegui")
        self.setWindowTitle("About PyniteGUI")
        self.setMinimumWidth(440)
        self.resize(500, 310)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)
        title = QLabel("PyniteGUI")
        title_font = title.font()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        self.version_label = QLabel(f"Version {__version__}")
        self.version_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.version_label)
        description = QLabel("Desktop structural modelling for 2D and 3D frames and trusses.\nPowered by PyNite and Qt.")
        description.setWordWrap(True)
        layout.addWidget(description)
        credits = QLabel("By Prakhar and contributors\nGNU Affero General Public License v3.0")
        credits.setWordWrap(True)
        layout.addWidget(credits)
        links = QHBoxLayout()
        for label, target in (("Documentation", "documentation"), ("Source Code", "source"), ("Report an Issue", "issues")):
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False, target=target: open_link(window, target))
            links.addWidget(button)
        layout.addLayout(links)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy = buttons.addButton("Copy Version Details", QDialogButtonBox.ButtonRole.ActionRole)
        copy.setAutoDefault(False)
        buttons.button(QDialogButtonBox.StandardButton.Close).setDefault(True)
        copy.clicked.connect(lambda: copy_support_information(window))
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)


def show_dialog(window, attribute, constructor):
    dialog = getattr(window, attribute, None)
    if dialog is None:
        dialog = constructor(window)
        setattr(window, attribute, dialog)
    elif hasattr(dialog, "refresh"):
        dialog.refresh()
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog


def build_help_menu(window):
    window.help_menu = window.menuBar().addMenu("&Help")
    window.help_action = window.action("Documentation", lambda: open_link(window, "documentation"), "F1")
    window.help_action.setStatusTip("Open the PyniteGUI documentation website in your browser")
    window.help_menu.addAction(window.help_action)
    window.help_menu.addAction(window.action("Getting Started", lambda: open_link(window, "getting_started")))
    window.help_menu.addAction(window.action("Keyboard Shortcuts…", lambda: show_dialog(window, "shortcuts_dialog", ShortcutsDialog)))
    window.help_menu.addSeparator()
    window.help_menu.addAction(window.action("Report an Issue", lambda: open_link(window, "issues")))
    window.help_menu.addAction(window.action("Copy Version Details", lambda: copy_support_information(window)))
    window.help_menu.addSeparator()
    about = window.action("About PyniteGUI…", lambda: show_dialog(window, "about_dialog", AboutDialog))
    about.setMenuRole(QAction.MenuRole.AboutRole)
    window.help_menu.addAction(about)
