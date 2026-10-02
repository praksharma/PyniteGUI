"""Reusable material definitions and member assignment management."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from .app import number, unit_number, unit_value
from .model import Material


class MaterialEditor(QDialog):
    def __init__(self, parent, project, material, previous=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Material" if previous else "Add Material")
        self.project, self.previous = project, previous
        self.definition = None
        form = QFormLayout(self)
        self.name = QLineEdit(material.name)
        self.name.setMaxLength(80)
        self.E = unit_number(material.E, project.units, "stress", 0.000001, 1e12, 6)
        self.nu = number(material.nu, -0.999999, 0.499999, 6)
        self.rho = unit_number(material.rho, project.units, "density", 0, 1e9, 10)
        self.original = material
        self.initial_values = (self.E.value(), self.nu.value(), self.rho.value())
        self.G = QLabel()
        for label, widget in (("Name", self.name), (f"E ({project.units.stress})", self.E), ("Poisson ratio", self.nu), (f"Weight density ({project.units.density})", self.rho), (f"G ({project.units.stress})", self.G)):
            form.addRow(label, widget)
        self.E.valueChanged.connect(self.update_G)
        self.nu.valueChanged.connect(self.update_G)
        self.update_G()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def update_G(self):
        self.G.setText(f"{self.E.value() / (2 * (1 + self.nu.value())):.6g}")

    def accept(self):
        values = tuple(original if widget.value() == initial else widget.value()
                       for widget, initial, original in zip(
                           (self.E, self.nu, self.rho), self.initial_values,
                           (self.original.E, self.original.nu, self.original.rho)))
        material = Material(self.name.text().strip(), unit_value(self.E, self.project.units), values[1], unit_value(self.rho, self.project.units))
        try:
            material.validate()
            if material.name in self.project.materials and material.name != self.previous:
                raise ValueError(f"Material {material.name} already exists.")
        except ValueError as error:
            QMessageBox.warning(self, "Material", str(error))
            return
        self.definition = material
        super().accept()


class MaterialDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Materials")
        self.resize(760, 400)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 6)

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
        self.add_button.clicked.connect(self.add_material)
        self.edit_button.clicked.connect(self.edit_material)
        self.delete_button.clicked.connect(self.delete_material)
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
        selected = selected or self.selected_name() or self.window.project.default_material
        project = self.window.project
        units = project.units
        self.table.setHorizontalHeaderLabels(["Material", f"E ({units.stress})", "Poisson ratio", f"Weight density ({units.density})", "Members", "Default"])
        if selected not in project.materials:
            selected = project.default_material
        self.table.blockSignals(True)
        self.table.setRowCount(len(project.materials))
        for row, material in enumerate(project.materials.values()):
            count = sum(member.material == material.name for member in project.members.values())
            values = (material.name, f"{units.to_display(material.E, 'stress'):g}", f"{material.nu:g}", f"{units.to_display(material.rho, 'density'):.8g}", str(count), "Yes" if material.name == project.default_material else "")
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
            if material.name == selected:
                self.table.selectRow(row)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.blockSignals(False)
        self.update_buttons()

    def update_buttons(self):
        name = self.selected_name()
        project = self.window.project
        exists = name in project.materials
        used = any(member.material == name for member in project.members.values())
        self.edit_button.setEnabled(exists)
        self.default_button.setEnabled(exists and name != project.default_material)
        self.delete_button.setEnabled(exists and not used and name != project.default_material)
        self.delete_button.setToolTip("Reassign members and choose a different default before deleting an assigned material." if used or name == project.default_material else "Delete material")

    def add_material(self):
        project = self.window.project
        name = project.next_name("Material", project.materials)
        source = project.materials[project.default_material]
        editor = MaterialEditor(self, project, Material(name, source.E, source.nu, source.rho))
        if editor.exec():
            self.window.edit(f"Add material {editor.definition.name}", lambda p: p.set_material(editor.definition))
            self.refresh(editor.definition.name)

    def edit_material(self):
        name = self.selected_name()
        if name is None:
            return
        editor = MaterialEditor(self, self.window.project, self.window.project.materials[name], name)
        if editor.exec():
            self.window.edit(f"Edit material {name}", lambda p: p.set_material(editor.definition, name))
            self.refresh(editor.definition.name)

    def delete_material(self):
        name = self.selected_name()
        if name is not None:
            self.window.edit(f"Delete material {name}", lambda p: p.delete_material(name))
            self.refresh()

    def set_default(self):
        name = self.selected_name()
        if name is not None:
            self.window.edit("Set default material", lambda p: setattr(p, "default_material", name))
            self.refresh(name)
