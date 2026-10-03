"""Load case definitions and editable linear combination factors."""
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QInputDialog, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .app import number


class CombinationEditor(QDialog):
    def __init__(self, parent, project, name, factors, previous=None):
        super().__init__(parent)
        self.project, self.previous = project, previous
        self.definition = None
        self.original = dict(factors)
        self.setWindowTitle("Edit Combination" if previous else "Add Combination")
        self.resize(520, 380)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(name)
        self.name.setMaxLength(80)
        form.addRow("Name", self.name)
        layout.addLayout(form)
        self.table = QTableWidget(len(project.load_cases), 3)
        self.table.setHorizontalHeaderLabels(["Include", "Load case", "Factor"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.fields = {}
        self.initial_values = {}
        for row, case in enumerate(project.load_cases):
            include = QCheckBox()
            include.setChecked(case in factors)
            include.setToolTip(f"Include {case}")
            factor = number(factors.get(case, 1), -1e6, 1e6, 8)
            factor.setEnabled(include.isChecked())
            include.toggled.connect(factor.setEnabled)
            self.table.setCellWidget(row, 0, include)
            self.table.setItem(row, 1, QTableWidgetItem(case))
            self.table.setCellWidget(row, 2, factor)
            self.fields[case] = include, factor
            self.initial_values[case] = factor.value()
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        name = self.name.text().strip()
        factors = {case: self.original.get(case, 1) if factor.value() == self.initial_values[case] else factor.value()
                   for case, (include, factor) in self.fields.items() if include.isChecked()}
        try:
            self.project.validate_combination(name, factors)
            if name in self.project.combinations and name != self.previous:
                raise ValueError(f"Combination {name} already exists.")
        except ValueError as error:
            QMessageBox.warning(self, "Combination", str(error))
            return
        self.definition = name, factors
        super().accept()


class LoadCasesDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Load Cases and Combinations")
        self.resize(760, 430)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tables = {}
        self.buttons = {}
        for kind, title, headers in (
            ("cases", "Load Cases", ["Load case", "Loads", "Self-weight loads", "Default"]),
            ("combinations", "Combinations", ["Combination", "Factors"]),
        ):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            table = QTableWidget(0, len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.itemSelectionChanged.connect(self.update_buttons)
            panel_layout.addWidget(table)
            self.tables[kind] = table
            actions = QHBoxLayout()
            for action, label in (("add", "Add..."), ("edit", "Rename..." if kind == "cases" else "Edit..."), ("delete", "Delete")):
                button = QPushButton(label)
                button.clicked.connect(lambda checked=False, kind=kind, action=action: self.perform(kind, action))
                self.buttons[kind, action] = button
                actions.addWidget(button)
            if kind == "cases":
                button = QPushButton("Set Default")
                button.clicked.connect(self.set_default)
                self.buttons[kind, "default"] = button
                actions.addWidget(button)
            actions.addStretch()
            panel_layout.addLayout(actions)
            self.tabs.addTab(panel, title)
        layout.addWidget(self.tabs)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.accept)
        layout.addWidget(close)
        self.refresh()

    def selected_name(self, kind):
        table = self.tables[kind]
        item = table.item(table.currentRow(), 0)
        return item.text() if item else None

    def refresh(self, kind=None, selected=None):
        project = self.window.project
        for key, table in self.tables.items():
            names = project.load_cases if key == "cases" else list(project.combinations)
            selection = selected if key == kind else self.selected_name(key)
            if selection not in names:
                selection = names[0]
            table.blockSignals(True)
            table.setRowCount(len(names))
            for row, name in enumerate(names):
                values = (name, str(sum(load.case == name for load in project.loads.values())),
                          str(len(project.self_weight_loads())) if name == project.self_weight_case else "0",
                          "Yes" if name == project.default_load_case else "") if key == "cases" else (
                              name, "; ".join(f"{case}: {factor:g}" for case, factor in project.combinations[name].items()))
                for column, value in enumerate(values):
                    table.setItem(row, column, QTableWidgetItem(value))
                if name == selection:
                    table.selectRow(row)
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(True)
            table.blockSignals(False)
        self.update_buttons()

    def update_buttons(self):
        if len(self.tables) < 2:
            return
        project = self.window.project
        case = self.selected_name("cases")
        used = (case == project.self_weight_case or any(load.case == case for load in project.loads.values())
                or any(case in factors for factors in project.combinations.values()))
        self.buttons["cases", "edit"].setEnabled(case is not None)
        self.buttons["cases", "default"].setEnabled(case is not None and case != project.default_load_case)
        self.buttons["cases", "delete"].setEnabled(case is not None and not used and case != project.default_load_case)
        self.buttons["cases", "delete"].setToolTip("Reassign manual loads and self-weight, remove combination references, and change the default before deleting a used case.")
        combination = self.selected_name("combinations")
        self.buttons["combinations", "edit"].setEnabled(combination is not None)
        self.buttons["combinations", "delete"].setEnabled(combination is not None and len(project.combinations) > 1)
        self.buttons["combinations", "delete"].setToolTip("Keep at least one combination.")

    def perform(self, kind, action):
        project = self.window.project
        previous = self.selected_name(kind)
        if action != "add" and previous is None:
            return
        if action == "delete":
            mutate = (lambda p: p.delete_load_case(previous)) if kind == "cases" else (lambda p: p.delete_combination(previous))
            self.window.edit(f"Delete {previous}", mutate)
            self.refresh()
            return
        if kind == "cases":
            name, accepted = QInputDialog.getText(self, "Add Load Case" if action == "add" else "Rename Load Case", "Name", text="" if action == "add" else previous)
            if accepted:
                name = name.strip()
                self.window.edit("Edit load cases", lambda p: p.set_load_case(name, None if action == "add" else previous))
                self.refresh(kind, name)
        else:
            name = project.next_name("Combination", project.combinations) if action == "add" else previous
            factors = {project.default_load_case: 1} if action == "add" else project.combinations[previous]
            editor = CombinationEditor(self, project, name, factors, None if action == "add" else previous)
            if editor.exec():
                name, factors = editor.definition
                self.window.edit("Edit combinations", lambda p: p.set_combination(name, factors, None if action == "add" else previous))
                self.refresh(kind, name)

    def set_default(self):
        name = self.selected_name("cases")
        if name is not None:
            self.window.edit("Set default load case", lambda p: setattr(p, "default_load_case", name))
            self.refresh("cases", name)
