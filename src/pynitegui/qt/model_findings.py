"""Conservative navigation for the application's known diagnostic formats."""
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


def finding_entities(project, message):
    entities = []
    def add(kind, name):
        identity = (kind, name)
        if identity not in entities:
            entities.append(identity)

    # Explicit entity prefixes, not incidental mentions in arbitrary errors.
    for kind, prefix in (("nodes", "Node"), ("members", "Member"), ("loads", "Load")):
        for name in getattr(project, kind):
            if message.startswith(f"{prefix} {name}:"):
                add(kind, name)
    if " lies inside " in message:
        for node in project.nodes:
            if message.startswith(f"{node} lies inside "):
                for member in project.members:
                    if message.startswith(f"{node} lies inside {member}."):
                        add("nodes", node)
                        add("members", member)
    if message.startswith("Members "):
        for first in project.members:
            if not message.startswith(f"Members {first} and "):
                continue
            for second in project.members:
                if first != second and (message.startswith(f"Members {first} and {second} overlap.")
                                        or message.startswith(f"Members {first} and {second} cross or meet ")):
                    add("members", first)
                    add("members", second)
    if message.startswith("Disconnected node groups: "):
        # This finding refers to all disconnected components, including isolates.
        for node in project.nodes:
            add("nodes", node)
    prefixes = ("Affected global degrees of freedom: ", "No effective joint stiffness at: ",
                "Possible mechanism or very weak stiffness involves: ")
    names = sorted(project.nodes, key=len, reverse=True)
    for line in message.splitlines():
        for prefix in prefixes:
            if not line.startswith(prefix):
                continue
            remaining = line[len(prefix):]
            while remaining:
                match = None
                for name in names:
                    token = re.match(re.escape(name) + r" (DX|DY|DZ|RX|RY|RZ)(?=, |\.$)", remaining)
                    if token:
                        match = name, token
                        break
                if match is None:
                    break
                name, token = match
                add("nodes", name)
                remaining = remaining[token.end():]
                remaining = remaining[2:] if remaining.startswith(", ") else ""
    return entities


class ModelFindings(QWidget):
    entities_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.summary = QLabel("Run Model Check or Analyze to review findings.")
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        layout.addWidget(self.list)
        self.select_button = QPushButton("Select affected geometry")
        self.select_button.setEnabled(False)
        layout.addWidget(self.select_button)
        self.list.currentRowChanged.connect(self.update_button)
        self.list.itemDoubleClicked.connect(lambda _: self.activate())
        self.select_button.clicked.connect(self.activate)

    def update_button(self, *args):
        item = self.list.currentItem()
        self.select_button.setEnabled(bool(item and item.data(Qt.ItemDataRole.UserRole)))

    def activate(self):
        item = self.list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole):
            self.entities_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def clear(self):
        self.list.clear()
        self.summary.setText("Model changed. Run Model Check or Analyze again.")
        self.update_button()

    def show_findings(self, project, messages, title):
        self.list.clear()
        self.summary.setText(f"{title} | {len(messages)} finding(s). Select a row to inspect its geometry.")
        for message in messages:
            item = QListWidgetItem(message)
            entities = finding_entities(project, message)
            item.setData(Qt.ItemDataRole.UserRole, entities)
            item.setToolTip("Double-click to select affected geometry." if entities else
                            "No specific geometry reference is available for this finding.")
            self.list.addItem(item)
        if messages:
            self.list.setCurrentRow(0)
        self.update_button()
