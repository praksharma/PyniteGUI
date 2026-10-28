"""Staged pressure-case, combination and horizontal self-weight editing."""
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                              QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                              QMessageBox, QPushButton, QTableWidget,
                              QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .plate_model import PlateDefinition


class PlateLoadsDialog(QDialog):
    def __init__(self, parent, definition):
        super().__init__(parent)
        self.definition = PlateDefinition.from_dict(definition.to_dict())
        self.setWindowTitle("Plate Load Cases and Combinations")
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        note = QLabel("Each case is a signed uniform pressure on the net material area. "
                      "The primary case and its factor remain in the main controls; Plate always uses that case alone. "
                      "Add named combinations to combine cases. Self-weight is additional global -Y loading, "
                      "available only for horizontal XZ plates. Its case uses the combination's ordinary factor.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.cases, self.combinations = QTableWidget(), QTableWidget()
        self.buttons = {}
        for kind, table, title in (("cases", self.cases, "Pressure cases"), ("combinations", self.combinations, "Combinations")):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            table.setObjectName("plate_load_"+kind)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            page_layout.addWidget(table)
            row = QHBoxLayout()
            for action, text in (("add", "Add…"), ("edit", "Rename…" if kind == "cases" else "Edit…"), ("delete", "Delete")):
                button = QPushButton(text)
                button.clicked.connect(lambda checked=False, kind=kind, action=action: self.perform(kind, action))
                self.buttons[kind, action] = button
                row.addWidget(button)
            row.addStretch()
            page_layout.addLayout(row)
            self.tabs.addTab(page, title)
            table.itemSelectionChanged.connect(self.update_buttons)
        form = QFormLayout()
        self.weight_case = QComboBox()
        self.weight_case.setObjectName("plate_weight_case")
        from .app import number
        self.weight_factor = number(self.definition.self_weight_factor, 1e-8, 1e6, 8)
        self.weight_factor.setObjectName("plate_weight_factor")
        self.weight_factor.setProperty("canonical", self.definition.self_weight_factor)
        self.weight_factor.setProperty("initial", self.weight_factor.value())
        form.addRow("Self-weight case", self.weight_case)
        form.addRow("Self-weight multiplier", self.weight_factor)
        density = self.definition.units.to_display(self.definition.material.rho, "density")
        form.addRow("Material weight density", QLabel(f"{density:.8g} {self.definition.units.density}"))
        self.weight_case.setEnabled(self.definition.plane == "XZ")
        self.weight_factor.setEnabled(self.definition.plane == "XZ")
        self.weight_case.setToolTip("Choose the horizontal XZ plane and set material weight density in the main plate controls before enabling self-weight.")
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def selected(self, kind):
        table = self.cases if kind == "cases" else self.combinations
        item = table.item(table.currentRow(), 0)
        return item.text() if item else None

    def read_inputs(self):
        from .app import unit_value
        values = {}
        for row in range(self.cases.rowCount()):
            widget = self.cases.cellWidget(row, 1)
            widget.interpretText()
            values[self.cases.item(row, 0).text()] = unit_value(widget, self.definition.units, "pressure")
        self.definition.pressure = values.pop(self.definition.load_case)
        self.definition.additional_pressures = values
        self.definition.self_weight_case = self.weight_case.currentData()
        self.weight_factor.interpretText()
        self.definition.self_weight_factor = (self.weight_factor.property("canonical")
            if self.weight_factor.value() == self.weight_factor.property("initial") else self.weight_factor.value())

    def refresh(self, kind=None, selected=None):
        from .app import unit_number
        selection = selected if kind == "cases" else self.selected("cases")
        self.cases.blockSignals(True)
        self.cases.setColumnCount(3)
        self.cases.setHorizontalHeaderLabels(["Case", f"Uniform pressure ({self.definition.units.pressure})", "Role"])
        self.cases.setRowCount(len(self.definition.load_cases))
        for row, (name, pressure) in enumerate(self.definition.case_pressures.items()):
            self.cases.setItem(row, 0, QTableWidgetItem(name))
            field = unit_number(pressure, self.definition.units, "pressure", decimals=10)
            self.cases.setCellWidget(row, 1, field)
            self.cases.setItem(row, 2, QTableWidgetItem("Primary" if name == self.definition.load_case else "Additional"))
            if name == selection or (selection not in self.definition.load_cases and row == 0):
                self.cases.selectRow(row)
        self.cases.resizeColumnsToContents()
        self.cases.horizontalHeader().setStretchLastSection(True)
        self.cases.blockSignals(False)
        selection = selected if kind == "combinations" else self.selected("combinations")
        self.combinations.blockSignals(True)
        self.combinations.setColumnCount(2)
        self.combinations.setHorizontalHeaderLabels(["Combination", "Case factors"])
        self.combinations.setRowCount(len(self.definition.load_combinations))
        for row, (name, factors) in enumerate(self.definition.load_combinations.items()):
            self.combinations.setItem(row, 0, QTableWidgetItem(name))
            self.combinations.setItem(row, 1, QTableWidgetItem("; ".join(f"{case}: {factor:g}" for case, factor in factors.items())))
            if name == selection or (selection not in self.definition.load_combinations and row == 0):
                self.combinations.selectRow(row)
        self.combinations.resizeColumnsToContents()
        self.combinations.setColumnWidth(0, max(140, self.combinations.columnWidth(0)))
        self.combinations.horizontalHeader().setStretchLastSection(True)
        self.combinations.blockSignals(False)
        self.weight_case.blockSignals(True)
        self.weight_case.clear()
        self.weight_case.addItem("Off", None)
        for name in self.definition.load_cases:
            self.weight_case.addItem(name, name)
        self.weight_case.setCurrentIndex(max(0, self.weight_case.findData(self.definition.self_weight_case)))
        self.weight_case.blockSignals(False)
        self.update_buttons()

    def update_buttons(self):
        if len(self.buttons) < 6:
            return
        case, combination = self.selected("cases"), self.selected("combinations")
        self.buttons["cases", "edit"].setEnabled(case is not None)
        self.buttons["cases", "delete"].setEnabled(case is not None and case != self.definition.load_case)
        for action in ("edit", "delete"):
            self.buttons["combinations", action].setEnabled(combination is not None and combination != "Plate")
        self.buttons["combinations", "edit"].setToolTip("Plate uses the primary case/factor from the main controls; named combinations can mix all cases.")

    def perform(self, kind, action):
        from .load_cases import CombinationEditor
        self.read_inputs()
        previous = self.selected(kind)
        if action != "add" and previous is None:
            return
        try:
            if kind == "cases":
                if action == "delete":
                    if previous == self.definition.load_case or previous == self.definition.self_weight_case or any(
                            previous in factors for factors in self.definition.combinations.values()):
                        raise ValueError("Remove combination/self-weight references before deleting an additional case; keep the primary case.")
                    del self.definition.additional_pressures[previous]
                else:
                    name, accepted = QInputDialog.getText(self, "Add Pressure Case" if action == "add" else "Rename Pressure Case", "Name", text="" if action == "add" else previous)
                    if not accepted:
                        return
                    name = name.strip()
                    self.definition.validate_load_name(name)
                    if action == "add":
                        if name in self.definition.load_cases:
                            raise ValueError("A pressure case with that name already exists.")
                        if len(self.definition.load_cases) >= 32:
                            raise ValueError("Use at most 32 pressure cases.")
                        self.definition.additional_pressures[name] = 0.
                    else:
                        self.definition.rename_case(previous, name)
                    self.refresh(kind, name)
                    return
            elif action == "delete":
                if previous == "Plate":
                    raise ValueError("Keep the primary Plate combination.")
                del self.definition.combinations[previous]
            else:
                if action == "add" and len(self.definition.load_combinations) >= 32:
                    raise ValueError("Use at most 32 plate combinations.")
                name = previous if action == "edit" else next(f"Combination {i}" for i in range(1, 33) if f"Combination {i}" not in self.definition.combinations)
                factors = self.definition.combinations[previous] if action == "edit" else {self.definition.load_case: 1.}
                editor = CombinationEditor(self, self.definition, name, factors, previous if action == "edit" else None)
                if editor.exec() != QDialog.DialogCode.Accepted:
                    return
                name, factors = editor.definition
                if action == "edit":
                    del self.definition.combinations[previous]
                self.definition.combinations[name] = factors
                self.refresh(kind, name)
                return
            self.refresh()
        except ValueError as error:
            QMessageBox.warning(self, "Plate Loading", str(error))

    def accept(self):
        self.read_inputs()
        try:
            self.definition.validate()
        except ValueError as error:
            QMessageBox.warning(self, "Plate Loading", str(error))
            return
        super().accept()
