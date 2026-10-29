"""Explicit, atomic property changes for heterogeneous selections."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton

from .app import number, unit_number, unit_value


def populate_bulk_inspector(window):
    selections = list(window.selections)
    fields = {}
    springs = {}
    movements = {}
    spatial = getattr(window.project, "dimension", "2D") == "3D"
    restraint_fields = ("restraint_x", "restraint_y", "restraint_rz")
    spring_fields = ("spring_x", "spring_y", "spring_rz")
    dofs = ("DX", "DY", "RZ")
    if spatial:
        from .spatial_model import DOFS, RESTRAINT_FIELDS, SPRING_FIELDS
        from .spatial_releases import RELEASE_FIELDS, release_axis
        dofs, restraint_fields, spring_fields = DOFS, RESTRAINT_FIELDS, SPRING_FIELDS
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
        support = choice("support", "Support", ("free", "pin", "roller", "fixed", "custom", "inclined"))
        angles = {}
        for key, label, limit in (("support_angle", "normal azimuth" if spatial else "roller tangent", 180),
                                  *((("support_elevation", "normal elevation", 90),) if spatial else ())):
            enabled = QCheckBox(f"Set {label} (deg)")
            enabled.setObjectName("bulk_change_"+key)
            widget = number(0., -limit, limit, 8)
            widget.setObjectName("bulk_"+key)
            widget.setEnabled(False)
            enabled.toggled.connect(widget.setEnabled)
            widget.setToolTip("Spatial normal: azimuth +X toward +Z, elevation toward +Y." if spatial else "Tangent CCW from global +X.")
            window.form.addRow(enabled, widget)
            angles[key] = enabled, widget
        restraints = [boolean(key, "Restrain " + dof) for key, dof in zip(restraint_fields, dofs)]
        def update_support():
            for widget in restraints:
                widget.setEnabled(support.currentData() in (("custom", "inclined") if spatial else ("custom",)))
        support.currentIndexChanged.connect(update_support)
        update_support()
        for key, dof in zip(spring_fields, dofs):
            label, quantity = "Spring " + dof, "rotational_stiffness" if dof.startswith("R") else "stiffness"
            enabled = QCheckBox(f"{label} ({getattr(window.project.units, quantity)})")
            enabled.setObjectName("bulk_change_" + key)
            value = unit_number(0, window.project.units, quantity, 0)
            value.setObjectName("bulk_" + key)
            value.setEnabled(False)
            enabled.toggled.connect(value.setEnabled)
            window.form.addRow(enabled, value)
            springs[key] = enabled, value
        from .support_movements import movement_fields, movement_label
        template = next(window.project.nodes[name] for kind, name in selections if kind == "nodes")
        for key in movement_fields(template):
            rotation = key.startswith("settlement_r")
            label = movement_label(key)
            enabled = QCheckBox(f"Set imposed {label} ({'rad' if rotation else window.project.units.length})")
            enabled.setObjectName("bulk_change_"+key)
            value = unit_number(0., window.project.units, "rotation" if rotation else "length", decimals=9)
            value.setObjectName("bulk_"+key)
            value.setEnabled(False)
            value.setToolTip("Same signed prescribed motion in every combination. Requires the corresponding rigid restraint.")
            enabled.toggled.connect(value.setEnabled)
            window.form.addRow(enabled, value)
            movements[key] = enabled, value
    if "members" in kinds:
        window.form.addRow(QLabel(f"Members ({sum(kind == 'members' for kind, name in selections)})"))
        choice("material", "Material", window.project.materials)
        choice("section", "Section", window.project.sections)
        if spatial:
            choice("kind", "Type", ("frame", "truss"))
            roll_enabled = QCheckBox("Set roll (deg)")
            roll_enabled.setObjectName("bulk_change_roll")
            roll = number(0, -360, 360, 6)
            roll.setObjectName("bulk_roll")
            roll.setEnabled(False)
            roll_enabled.toggled.connect(roll.setEnabled)
            window.form.addRow(roll_enabled, roll)
            for key in RELEASE_FIELDS:
                boolean(key, ("Start" if "start" in key else "End")+" "+release_axis(key)+" (local release)")
        else:
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
        for key, (enabled, widget) in {**springs, **movements}.items():
            if enabled.isChecked():
                values[key] = unit_value(widget, window.project.units)
        if spatial and "members" in kinds and roll_enabled.isChecked():
            values["roll"] = roll.value()
        if "nodes" in kinds:
            for key, (enabled, widget) in angles.items():
                if enabled.isChecked():
                    values[key] = widget.value()
        def mutate(project):
            for kind, name in selections:
                entity = getattr(project, kind)[name]
                if kind == "nodes" and any(key in values for key in ("support_angle", "support_elevation")) and values.get("support", entity.support) != "inclined":
                    raise ValueError("Choose Support inclined before applying a roller tangent angle to these nodes.")
                if kind == "nodes" and values.get("support") == "custom":
                    for key, fixed in zip(restraint_fields, entity.restraints):
                        setattr(entity, key, fixed)
                if spatial and kind == "nodes" and values.get("support") == "inclined" and entity.support != "inclined":
                    for key in restraint_fields:
                        setattr(entity, key, False)
                keys = {"nodes": ("support", "support_angle", "support_elevation", *restraint_fields, *spring_fields),
                        "members": ("material", "section", "roll", "kind", *RELEASE_FIELDS) if spatial else ("material", "section", "kind", "release_start", "release_end",
                                    "release_start_x", "release_end_x", "release_start_y", "release_end_y"),
                        "loads": ("case",)}[kind]
                for key in keys:
                    if key in values:
                        setattr(entity, key, values[key])
                if kind == "nodes" and entity.support != "inclined":
                    entity.support_angle = 0.
                    if spatial:
                        entity.support_elevation = 0.
                if kind == "nodes":
                    from .support_movements import clear_inapplicable_movements
                    clear_inapplicable_movements(entity)
                    for key in movements:
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
