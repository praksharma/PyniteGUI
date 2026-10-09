"""Native property controls for spatial models."""
import math
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QPushButton

from .spatial_model import DOFS, FORCES, MEMBER_DIRECTIONS, RESTRAINT_FIELDS, SPRING_FIELDS, SpatialLoad


def choices(values, selected, name=None):
    widget = QComboBox()
    widget.addItems(list(values))
    widget.setCurrentText(selected)
    if name:
        widget.setObjectName(name)
    return widget


def load_fields(form, project, load):
    from .app import number, unit_number, unit_value
    fields = {}
    fields["target"] = choices(list(project.members) if load.kind == "distributed" else [*project.nodes, *project.members], load.target, "spatial_load_target")
    fields["case"] = choices(project.load_cases, load.case, "spatial_load_case")
    fields["direction"] = QComboBox()
    fields["direction"].setObjectName("spatial_load_direction")
    quantity = "intensity" if load.kind == "distributed" else "moment" if load.is_moment else "force"
    fields["magnitude"] = unit_number(load.magnitude, project.units, quantity)
    fields["magnitude"].setObjectName("spatial_load_magnitude")
    fields["position"] = number(load.position, 0, 1, 8)
    fields["end_magnitude"] = unit_number(load.end_magnitude, project.units, "intensity")
    fields["end_position"] = number(load.end_position, 0, 1, 8)
    azimuth, elevation = load.angle, load.elevation
    if load.direction != "Angle" and not load.is_moment:
        import numpy as np
        vector = np.eye(3)["XYZ".index(load.direction[-1].upper())]
        if not load.direction.isupper():
            from .spatial_results import member_axes
            vector = member_axes(project, load.target)["XYZ".index(load.direction[-1].upper())]
        azimuth = math.degrees(math.atan2(vector[2], vector[0]))
        elevation = math.degrees(math.asin(max(-1., min(1., vector[1]))))
    fields["angle"] = number(azimuth, -360, 360, 6)
    fields["elevation"] = number(elevation, -90, 90, 6)
    fields["angle"].setObjectName("spatial_load_azimuth")
    fields["elevation"].setObjectName("spatial_load_elevation")
    fields["angle"].setToolTip("Global XZ-plane angle: 0 = +X, 90 = +Z")
    fields["elevation"].setToolTip("Angle above the XZ plane: 90 = +Y, -90 = -Y")
    for key, label in (("target", "Target"), ("case", "Case"), ("direction", "Direction"), ("magnitude", getattr(project.units, quantity)),
                       ("position", "Start fraction"), ("end_magnitude", f"End ({project.units.intensity})"), ("end_position", "End fraction")):
        form.addRow(label, fields[key])
    form.addRow("Azimuth (deg)", fields["angle"])
    form.addRow("Elevation (deg)", fields["elevation"])
    preview = QLabel()
    preview.setObjectName("spatial_load_components")
    preview.setWordWrap(True)
    preview.setMinimumWidth(130)
    preview.setTextFormat(Qt.TextFormat.PlainText)
    form.addRow("Components", preview)
    def update_preview():
        angular = fields["direction"].currentData() == "Angle"
        for key in ("angle", "elevation"):
            form.setRowVisible(fields[key], angular)
        form.setRowVisible(preview, angular)
        if not angular:
            return
        draft = SpatialLoad("preview", fields["target"].currentText(), "Angle", fields["magnitude"].value(),
                            kind=load.kind, end_magnitude=fields["end_magnitude"].value(),
                            angle=fields["angle"].value(), elevation=fields["elevation"].value())
        start, end = dict(draft.components()), dict(draft.components(magnitude=draft.end_magnitude))
        unit = project.units.intensity if load.kind == "distributed" else project.units.force
        preview.setText("\n".join(f"{direction} {value:.5g}" + (f" to {end[direction]:.5g}" if load.kind == "distributed" else "") + f" {unit}"
                                  for direction, value in start.items()))
    def update_direction():
        quantity = "intensity" if load.kind == "distributed" else "moment" if fields["direction"].currentData().upper().startswith("M") else "force"
        form.labelForField(fields["magnitude"]).setText(getattr(project.units, quantity))
        form.setRowVisible(fields["position"], fields["target"].currentText() in project.members)
        update_preview()
    def update_target():
        selected = fields["direction"].currentData() or load.direction
        directions = MEMBER_DIRECTIONS if fields["target"].currentText() in project.members else FORCES
        if load.kind == "distributed":
            directions = tuple(d for d in directions if not d.upper().startswith("M"))
        fields["direction"].blockSignals(True)
        fields["direction"].clear()
        for direction in directions:
            fields["direction"].addItem(("Global " if direction.isupper() else "Local ") + direction, direction)
        fields["direction"].addItem("Global angle", "Angle")
        fields["direction"].setCurrentIndex(max(0, fields["direction"].findData(selected)))
        fields["direction"].blockSignals(False)
        update_direction()
    fields["target"].currentTextChanged.connect(update_target)
    fields["direction"].currentIndexChanged.connect(update_direction)
    for key in ("magnitude", "end_magnitude", "angle", "elevation"):
        fields[key].valueChanged.connect(update_preview)
    for key in ("end_magnitude", "end_position"):
        form.setRowVisible(fields[key], load.kind == "distributed")
    update_target()
    def values():
        direction = fields["direction"].currentData()
        quantity = "intensity" if load.kind == "distributed" else "moment" if direction.upper().startswith("M") else "force"
        return {"target": fields["target"].currentText(), "case": fields["case"].currentText(), "direction": direction,
                "magnitude": unit_value(fields["magnitude"], project.units, quantity), "position": fields["position"].value(),
                "end_magnitude": unit_value(fields["end_magnitude"], project.units), "end_position": fields["end_position"].value(),
                "angle": load.angle if direction != "Angle" or (load.direction == "Angle" and fields["angle"].value() == round(azimuth, 6)) else fields["angle"].value(),
                "elevation": load.elevation if direction != "Angle" or (load.direction == "Angle" and fields["elevation"].value() == round(elevation, 6)) else fields["elevation"].value()}
    return fields, values


def populate_inspector(window):
    from .app import number, unit_number, unit_value
    project, form = window.project, window.form
    if len(window.selections) > 1:
        from .bulk_edit import populate_bulk_inspector
        populate_bulk_inspector(window)
        button = QPushButton("Model Tables...")
        button.clicked.connect(window.manage_model_tables)
        form.addRow(button)
        return
    if not window.selected:
        form.addRow("Model", QLabel("3D frame"))
        form.addRow("Units", QLabel(project.units.label))
        form.addRow("Default material", QLabel(project.default_material))
        form.addRow("Default section", QLabel(project.default_section))
        button = QPushButton("Add Node...")
        button.clicked.connect(window.add_spatial_node)
        form.addRow(button)
        return
    kind, name = window.selected
    entity = getattr(project, kind)[name]
    form.addRow("ID", QLabel(name))
    fields = {}
    custom_values = None
    if kind == "nodes":
        for key in ("x", "y", "z"):
            fields[key] = unit_number(getattr(entity, key), project.units, "length")
            fields[key].setObjectName("spatial_" + key)
            form.addRow(f"{key.upper()} ({project.units.length})", fields[key])
        fields["support"] = choices(("free", "pin", "roller", "fixed", "custom"), entity.support, "spatial_support")
        fields["support"].setToolTip("Pin restrains XYZ translations. Roller restrains global Y only. Custom controls all six global DOFs.")
        form.addRow("Support", fields["support"])
        for key, dof, fixed in zip(RESTRAINT_FIELDS, DOFS, entity.restraints):
            fields[key] = QCheckBox("Restrained")
            fields[key].setChecked(fixed)
            fields[key].setObjectName(key)
            form.addRow(dof, fields[key])
        def update_support():
            custom = fields["support"].currentText() == "custom"
            for index, key in enumerate(RESTRAINT_FIELDS):
                form.setRowVisible(fields[key], custom)
                if not custom:
                    fields[key].setChecked(replace(entity, support=fields["support"].currentText()).restraints[index])
        fields["support"].currentTextChanged.connect(update_support)
        update_support()
        for index, (key, dof) in enumerate(zip(SPRING_FIELDS, DOFS)):
            quantity = "stiffness" if index < 3 else "rotational_stiffness"
            fields[key] = unit_number(getattr(entity, key), project.units, quantity, 0)
            fields[key].setObjectName(key)
            form.addRow(f"Spring {dof} ({getattr(project.units, quantity)})", fields[key])
    elif kind == "members":
        for key, label, values in (("start", "Start", project.nodes), ("end", "End", project.nodes),
                                  ("material", "Material", project.materials), ("section", "Section", project.sections)):
            fields[key] = choices(values, getattr(entity, key), "spatial_" + key)
            form.addRow(label, fields[key])
        form.addRow(f"Length ({project.units.length})", QLabel(f"{project.units.to_display(math.dist(project.nodes[entity.start].coords, project.nodes[entity.end].coords), 'length'):.6g}"))
        fields["roll"] = number(entity.roll, -360, 360, 6)
        fields["roll"].setObjectName("spatial_roll")
        fields["roll"].setProperty("initial", fields["roll"].value())
        form.addRow("Roll (deg)", fields["roll"])
        from .spatial_results import member_axes
        axes = member_axes(project, name)
        label = QLabel("\n".join(f"{axis}: " + ", ".join(f"{value:.3g}" for value in row) for axis, row in zip(("x", "y", "z"), axes)))
        label.setWordWrap(True)
        form.addRow("Local axes (XYZ)", label)
    else:
        form.addRow("Type", QLabel(entity.kind.capitalize()))
        fields, custom_values = load_fields(form, project, entity)
    def apply():
        if custom_values:
            values = custom_values()
        else:
            values = {key: widget.currentText() if isinstance(widget, QComboBox) else widget.isChecked() if isinstance(widget, QCheckBox)
                      else unit_value(widget, project.units) if widget.property("quantity") else widget.value() for key, widget in fields.items()}
            if kind == "nodes" and values["support"] != "custom":
                for key in RESTRAINT_FIELDS:
                    values.pop(key)
            if kind == "members" and fields["roll"].value() == fields["roll"].property("initial"):
                values["roll"] = entity.roll
        def mutate(candidate):
            target = getattr(candidate, kind)[name]
            for key, value in values.items():
                setattr(target, key, value)
        window.edit(f"Edit {name}", mutate)
    button = QPushButton("Apply")
    button.setObjectName("spatial_apply")
    button.clicked.connect(apply)
    form.addRow(button)
    button = QPushButton("Delete")
    button.clicked.connect(window.delete_selected)
    form.addRow(button)
    if kind == "members":
        button = QPushButton("Split...")
        button.setObjectName("spatial_split")
        button.clicked.connect(window.split_selected_member)
        form.addRow(button)


def add_load(window):
    kind, target = window.selected
    dialog = QDialog(window)
    dialog.setWindowTitle(f"3D Load on {target}")
    dialog.setMinimumWidth(420)
    form = QFormLayout(dialog)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    load_type = choices(("point", "distributed") if kind == "members" else ("point",), "point", "spatial_load_type")
    form.addRow("Type", load_type)
    panel = QFormLayout()
    form.addRow(panel)
    state = {}
    def update_type():
        while panel.rowCount():
            panel.removeRow(0)
        distributed = load_type.currentText() == "distributed"
        load = SpatialLoad("draft", target, magnitude=-.01 if distributed else -10,
                           position=0 if distributed else .5, kind=load_type.currentText(), end_magnitude=-.01,
                           case=window.project.default_load_case)
        fields, values = load_fields(panel, window.project, load)
        state["values"] = values
    load_type.currentTextChanged.connect(update_type)
    update_type()
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    if dialog.exec():
        values = state["values"]()
        def mutate(project):
            name = project.next_name("L", project.loads)
            project.loads[name] = SpatialLoad(name=name, kind=load_type.currentText(), **values)
        window.edit("Add spatial load", mutate)
