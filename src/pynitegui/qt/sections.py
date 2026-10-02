"""Reusable section definitions and per-member assignments."""
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .app import number
from .model import Section


class SectionEditor(QDialog):
    def __init__(self, parent, project, section, previous=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Section" if previous else "Add Section")
        self.project, self.previous = project, previous
        self.definition = None
        self.original = section
        form = QFormLayout(self)
        self.name = QLineEdit(section.name)
        self.name.setMaxLength(80)
        form.addRow("Name", self.name)
        self.fields = {}
        for key, label in (("A", "Area (in2)"), ("Iy", "Iy (in4)"), ("Iz", "Iz (in4)"), ("J", "J (in4)")):
            self.fields[key] = number(getattr(section, key), 0, 1e12, 8)
            form.addRow(label, self.fields[key])
        self.initial_values = {key: widget.value() for key, widget in self.fields.items()}
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        values = {key: getattr(self.original, key) if widget.value() == self.initial_values[key] else widget.value()
                  for key, widget in self.fields.items()}
        section = Section(self.name.text().strip(), **values)
        try:
            section.validate()
            if section.name in self.project.sections and section.name != self.previous:
                raise ValueError(f"Section {section.name} already exists.")
        except ValueError as error:
            QMessageBox.warning(self, "Section", str(error))
            return
        self.definition = section
        super().accept()


class SectionDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Sections")
        self.resize(760, 400)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Section", "Area (in2)", "Iy (in4)", "Iz (in4)", "J (in4)", "Members", "Default"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add...")
        self.edit_button = QPushButton("Edit...")
        self.delete_button = QPushButton("Delete")
        self.default_button = QPushButton("Set Default")
        self.add_button.clicked.connect(self.add_section)
        self.edit_button.clicked.connect(self.edit_section)
        self.delete_button.clicked.connect(self.delete_section)
        self.default_button.clicked.connect(self.set_default)
        for button in (self.add_button, self.edit_button, self.delete_button, self.default_button):
            buttons.addWidget(button)
        buttons.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    def selected_name(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.text() if item is not None else None

    def refresh(self, selected=None):
        selected = selected or self.selected_name() or self.window.project.default_section
        project = self.window.project
        if selected not in project.sections:
            selected = project.default_section
        self.table.blockSignals(True)
        self.table.setRowCount(len(project.sections))
        for row, section in enumerate(project.sections.values()):
            count = sum(member.section == section.name for member in project.members.values())
            values = (section.name, f"{section.A:g}", f"{section.Iy:g}", f"{section.Iz:g}", f"{section.J:g}", str(count), "Yes" if section.name == project.default_section else "")
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
            if section.name == selected:
                self.table.selectRow(row)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.blockSignals(False)
        self.update_buttons()

    def update_buttons(self):
        name = self.selected_name()
        project = self.window.project
        exists = name in project.sections
        used = any(member.section == name for member in project.members.values())
        self.edit_button.setEnabled(exists)
        self.default_button.setEnabled(exists and name != project.default_section)
        self.delete_button.setEnabled(exists and not used and name != project.default_section)
        self.delete_button.setToolTip("Reassign members and choose a different default before deleting an assigned section." if used or name == project.default_section else "Delete section")

    def add_section(self):
        project = self.window.project
        name = project.next_name("Section", project.sections)
        source = project.sections[project.default_section]
        editor = SectionEditor(self, project, Section(name, source.A, source.Iy, source.Iz, source.J))
        if editor.exec():
            self.window.edit(f"Add section {editor.definition.name}", lambda p: p.set_section(editor.definition))
            self.refresh(editor.definition.name)

    def edit_section(self):
        name = self.selected_name()
        if name is None:
            return
        editor = SectionEditor(self, self.window.project, self.window.project.sections[name], name)
        if editor.exec():
            self.window.edit(f"Edit section {name}", lambda p: p.set_section(editor.definition, name))
            self.refresh(editor.definition.name)

    def delete_section(self):
        name = self.selected_name()
        if name is not None:
            self.window.edit(f"Delete section {name}", lambda p: p.delete_section(name))
            self.refresh()

    def set_default(self):
        name = self.selected_name()
        if name is not None:
            self.window.edit("Set default section", lambda p: setattr(p, "default_section", name))
            self.refresh(name)
