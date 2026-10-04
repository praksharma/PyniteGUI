"""Explicit, atomic property changes for heterogeneous selections."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton

from .app import number, unit_number, unit_value


def populate_bulk_inspector(window):
    selections = list(window.selections)
    fields = {}
    springs = {}
    window.form.addRow("Selection", QLabel(f"{len(selections)} items"))

    def choice(key, label, options):
        widget = QComboBox()
        widget.addItem("Keep existing", None)
        for value in options:
            widget.addItem(value, value)
        widget.setObjectName("bulk_" + key)
        window.form.addRow(label, widget)
        fields[key] = widget
        return widget

    def boolean(key, label):
        widget = QCheckBox()
        widget.setTristate(True)
        widget.setCheckState(Qt.CheckState.PartiallyChecked)
        widget.setToolTip("Partial: keep existing; checked: on; unchecked: off.")
        widget.setObjectName("bulk_" + key)
        window.form.addRow(label, widget)
        fields[key] = widget
        return widget

    kinds = {kind for kind, name in selections}
    if "nodes" in kinds:
        window.form.addRow(QLabel(f"Nodes ({sum(kind == 'nodes' for kind, name in selections)})"))
        support = choice("support", "Support", ("free", "pin", "roller", "fixed", "custom"))
        restraints = [boolean(key, label) for key, label in
                      (("restraint_x", "Restrain DX"), ("restraint_y", "Restrain DY"), ("restraint_rz", "Restrain RZ"))]
        def update_support():
            for widget in restraints:
                widget.setEnabled(support.currentData() == "custom")
        support.currentIndexChanged.connect(update_support)
        update_support()
        for key, label, quantity in (("spring_x", "Spring DX", "stiffness"), ("spring_y", "Spring DY", "stiffness"),
                                     ("spring_rz", "Spring RZ", "rotational_stiffness")):
            enabled = QCheckBox(f"{label} ({getattr(window.project.units, quantity)})")
            enabled.setObjectName("bulk_change_" + key)
            value = unit_number(0, window.project.units, quantity, 0)
            value.setObjectName("bulk_" + key)
            value.setEnabled(False)
            enabled.toggled.connect(value.setEnabled)
            window.form.addRow(enabled, value)
            springs[key] = enabled, value
    if "members" in kinds:
        window.form.addRow(QLabel(f"Members ({sum(kind == 'members' for kind, name in selections)})"))
        choice("material", "Material", window.project.materials)
        choice("section", "Section", window.project.sections)
        choice("kind", "Type", ("frame", "truss"))
        boolean("release_start", "Start hinge")
        boolean("release_end", "End hinge")
        for key, label in (("release_start_x", "Start axial DX"), ("release_end_x", "End axial DX"),
                           ("release_start_y", "Start shear DY"), ("release_end_y", "End shear DY")):
            boolean(key, label + " (local)")
    if "loads" in kinds:
        window.form.addRow(QLabel(f"Loads ({sum(kind == 'loads' for kind, name in selections)})"))
        choice("case", "Load case", window.project.load_cases)
        scale = QCheckBox("Scale magnitudes")
        scale.setObjectName("bulk_scale")
        factor = number(1, -1e6, 1e6, 8)
        factor.setObjectName("bulk_factor")
        factor.setEnabled(False)
        scale.toggled.connect(factor.setEnabled)
        window.form.addRow(scale)
        window.form.addRow("Factor", factor)
        fields["scale"], fields["factor"] = scale, factor

    def apply():
        values = {}
        for key, widget in fields.items():
            if isinstance(widget, QComboBox):
                if widget.currentData() is not None:
                    values[key] = widget.currentData()
            elif isinstance(widget, QCheckBox) and key != "scale" and widget.isEnabled():
                if widget.checkState() != Qt.CheckState.PartiallyChecked:
                    values[key] = widget.isChecked()
        factor = fields["factor"].value() if "scale" in fields and fields["scale"].isChecked() else None
        for key, (enabled, widget) in springs.items():
            if enabled.isChecked():
                values[key] = unit_value(widget, window.project.units)
        def mutate(project):
            for kind, name in selections:
                entity = getattr(project, kind)[name]
                if kind == "nodes" and values.get("support") == "custom":
                    entity.restraint_x, entity.restraint_y, entity.restraint_rz = entity.restraints
                keys = {"nodes": ("support", "restraint_x", "restraint_y", "restraint_rz", "spring_x", "spring_y", "spring_rz"),
                        "members": ("material", "section", "kind", "release_start", "release_end",
                                    "release_start_x", "release_end_x", "release_start_y", "release_end_y"),
                        "loads": ("case",)}[kind]
                for key in keys:
                    if key in values:
                        setattr(entity, key, values[key])
                if kind == "loads" and factor is not None:
                    entity.magnitude *= factor
                    if entity.kind == "distributed":
                        entity.end_magnitude *= factor
        window.edit("Edit selected properties", mutate)
    button = QPushButton("Apply")
    button.setObjectName("bulk_apply")
    button.clicked.connect(apply)
    window.form.addRow(button)
    delete = QPushButton("Delete Selection")
    delete.clicked.connect(window.delete_selected)
    window.form.addRow(delete)
