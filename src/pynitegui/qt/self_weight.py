"""Opt-in gravity loading from member weight density and section area."""
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox

from .app import number


class SelfWeightDialog(QDialog):
    def __init__(self, parent, project):
        super().__init__(parent)
        self.project = project
        self.definition = None
        self.setWindowTitle("Self-Weight")
        self.resize(440, 220)
        form = QFormLayout(self)
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(project.self_weight_case is not None)
        self.enabled.setToolTip("Generate downward global FY member loads from weight density and section area. Existing manual loads remain unchanged.")
        form.addRow("Self-weight", self.enabled)
        self.case = QComboBox()
        self.case.addItems(project.load_cases)
        self.case.setCurrentText(project.self_weight_case or project.default_load_case)
        self.case.setToolTip("The selected case must be included in a combination to apply self-weight.")
        form.addRow("Load case", self.case)
        self.factor = number(project.self_weight_factor, 1e-12, 1e6, 12)
        self.initial_factor = self.factor.value()
        self.factor.setToolTip("Positive multiplier on rho times area; rho is weight density, not mass density.")
        form.addRow("Factor", self.factor)
        self.total = QLabel()
        form.addRow(f"Total weight ({project.units.force})", self.total)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.enabled.toggled.connect(self.update_preview)
        self.case.currentTextChanged.connect(self.update_preview)
        self.factor.valueChanged.connect(self.update_preview)
        self.update_preview()

    def values(self):
        factor = self.project.self_weight_factor if self.factor.value() == self.initial_factor else self.factor.value()
        return self.case.currentText() if self.enabled.isChecked() else None, factor

    def preview(self):
        project = self.project.clone()
        project.self_weight_case, project.self_weight_factor = self.values()
        project.validate()
        return project

    def update_preview(self):
        self.case.setEnabled(self.enabled.isChecked())
        self.factor.setEnabled(self.enabled.isChecked())
        try:
            project = self.preview()
            self.total.setText(f"{project.units.to_display(project.self_weight_total(), 'force'):.6g}")
        except ValueError:
            self.total.setText("n/a")

    def accept(self):
        try:
            self.preview()
        except ValueError as error:
            QMessageBox.warning(self, "Self-Weight", str(error))
            return
        self.definition = self.values()
        super().accept()
