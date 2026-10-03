"""Reusable section definitions and per-member assignments."""
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QComboBox, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .app import unit_number, unit_value
from .model import Section
from .section_library import CATALOG, SOURCE


class SectionLibraryDialog(QDialog):
    def __init__(self, parent, project):
        super().__init__(parent)
        self.project = project
        self.definition = None
        self.setWindowTitle("Section Library | " + SOURCE)
        self.resize(820, 520)
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sections")
        self.family = QComboBox()
        self.family.addItems(["All families", *dict.fromkeys(item.family for item in CATALOG)])
        filters.addWidget(self.search, 1)
        filters.addWidget(self.family)
        layout.addLayout(filters)
        self.table = QTableWidget(0, 6)
        units = project.units
        self.table.setHorizontalHeaderLabels(["Section", "Family", f"Area ({units.area})",
                                             f"Iy ({units.inertia})", f"Iz ({units.inertia})", f"J ({units.inertia})"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        form = QFormLayout()
        self.axis = QComboBox()
        self.axis.addItems(["Strong axis (Iz = catalog Ix)", "Weak axis (Iz = catalog Iy)"])
        self.name = QLineEdit()
        self.name.setMaxLength(80)
        form.addRow("In-plane bending", self.axis)
        form.addRow("Project name", self.name)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add to Project")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.search.textChanged.connect(self.refresh)
        self.family.currentIndexChanged.connect(self.refresh)
        self.axis.currentIndexChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.refresh()

    def refresh(self, *_):
        previous = self.table.currentRow()
        selected = self.rows[previous].designation if hasattr(self, "rows") and 0 <= previous < len(self.rows) else None
        query = self.search.text().strip().upper().replace(" ", "")
        self.rows = [item for item in CATALOG if query in item.designation and
                     (self.family.currentIndex() == 0 or self.family.currentText() == item.family)]
        self.table.blockSignals(True)
        self.table.clearContents()
        self.table.setRowCount(len(self.rows))
        selected_row = 0
        for row, item in enumerate(self.rows):
            properties = item.properties(self.axis.currentIndex() == 1)
            values = [item.designation, item.family, *(
                f"{self.project.units.to_display(properties[key], 'area' if key == 'A' else 'inertia'):.10g}"
                for key in ("A", "Iy", "Iz", "J"))]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
            if item.designation == selected:
                selected_row = row
        if self.rows:
            self.table.selectRow(selected_row)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.blockSignals(False)
        self.selection_changed()

    def selection_changed(self):
        row = self.table.currentRow()
        exists = 0 <= row < len(self.rows)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(exists)
        if exists:
            base = self.rows[row].designation + (" (weak)" if self.axis.currentIndex() else "")
            name, suffix = base, 2
            while name in self.project.sections:
                name = f"{base} ({suffix})"
                suffix += 1
            self.name.setText(name)
        else:
            self.name.clear()

    def accept(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.rows):
            return
        item = self.rows[row]
        weak = self.axis.currentIndex() == 1
        definition = Section(self.name.text().strip(), **item.properties(weak),
                             catalog=SOURCE, designation=item.designation, weak_axis=weak)
        try:
            definition.validate()
            if definition.name in self.project.sections:
                raise ValueError(f"Section {definition.name} already exists.")
        except ValueError as error:
            QMessageBox.warning(self, "Section Library", str(error))
            return
        self.definition = definition
        super().accept()


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
        self.source = QLabel(section.source_label)
        self.source.setWordWrap(True)
        form.addRow("Source", self.source)
        self.fields = {}
        for key, label in (("A", f"Area ({project.units.area})"), ("Iy", f"Iy ({project.units.inertia})"),
                           ("Iz", f"Iz ({project.units.inertia})"), ("J", f"J ({project.units.inertia})")):
            self.fields[key] = unit_number(getattr(section, key), project.units, "area" if key == "A" else "inertia", 0, 1e12, 8)
            form.addRow(label, self.fields[key])
        self.initial_values = {key: widget.value() for key, widget in self.fields.items()}
        for widget in self.fields.values():
            widget.valueChanged.connect(self.update_source)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def update_source(self, *_):
        modified = any(widget.value() != self.initial_values[key] for key, widget in self.fields.items())
        self.source.setText("Custom" if modified else self.original.source_label)

    def accept(self):
        values = {key: getattr(self.original, key) if widget.value() == self.initial_values[key] else unit_value(widget, self.project.units)
                  for key, widget in self.fields.items()}
        section = Section(self.name.text().strip(), **values)
        if all(getattr(self.original, key) == value for key, value in values.items()):
            section.catalog, section.designation, section.weak_axis = self.original.catalog, self.original.designation, self.original.weak_axis
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
        self.resize(960, 440)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 8)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add...")
        self.library_button = QPushButton("Library...")
        self.edit_button = QPushButton("Edit...")
        self.delete_button = QPushButton("Delete")
        self.default_button = QPushButton("Set Default")
        self.add_button.clicked.connect(self.add_section)
        self.library_button.clicked.connect(self.add_library_section)
        self.edit_button.clicked.connect(self.edit_section)
        self.delete_button.clicked.connect(self.delete_section)
        self.default_button.clicked.connect(self.set_default)
        for button in (self.library_button, self.add_button, self.edit_button, self.delete_button, self.default_button):
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
        units = project.units
        self.table.setHorizontalHeaderLabels(["Section", f"Area ({units.area})", f"Iy ({units.inertia})", f"Iz ({units.inertia})", f"J ({units.inertia})", "Members", "Default", "Source"])
        if selected not in project.sections:
            selected = project.default_section
        self.table.blockSignals(True)
        self.table.setRowCount(len(project.sections))
        for row, section in enumerate(project.sections.values()):
            count = sum(member.section == section.name for member in project.members.values())
            source = "Custom" if section.catalog is None else f"{section.catalog} ({'weak' if section.weak_axis else 'strong'})"
            values = (section.name, f"{units.to_display(section.A, 'area'):g}", f"{units.to_display(section.Iy, 'inertia'):g}", f"{units.to_display(section.Iz, 'inertia'):g}", f"{units.to_display(section.J, 'inertia'):g}", str(count), "Yes" if section.name == project.default_section else "", source)
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
            self.table.item(row, 7).setToolTip(section.source_label)
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

    def add_library_section(self):
        dialog = SectionLibraryDialog(self, self.window.project)
        if dialog.exec():
            self.window.edit(f"Import section {dialog.definition.name}", lambda p: p.set_section(dialog.definition))
            self.refresh(dialog.definition.name)

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
