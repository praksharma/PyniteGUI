"""Transactional, unit-aware numerical model editing."""
import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QMessageBox, QPushButton, QStyle, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from .model import Load, Member, Node


FIELDS = {
    "nodes": ("name", "x", "y", "support", "restraint_x", "restraint_y", "restraint_rz", "spring_x", "spring_y", "spring_rz"),
    "members": ("name", "start", "end", "material", "section", "release_start", "release_end", "kind",
                "release_start_x", "release_end_x", "release_start_y", "release_end_y"),
    "loads": ("name", "target", "case", "kind", "direction", "magnitude", "position",
              "end_magnitude", "end_position", "angle", "units"),
}
BOOLEAN_FIELDS = {"restraint_x", "restraint_y", "restraint_rz", "release_start", "release_end",
                  "release_start_x", "release_end_x", "release_start_y", "release_end_y"}
NUMERIC_FIELDS = {"x", "y", "magnitude", "position", "end_magnitude", "end_position", "angle", "spring_x", "spring_y", "spring_rz"}


class ModelTablesDialog(QDialog):
    def __init__(self, parent, project):
        super().__init__(parent)
        self.spatial = getattr(project, "dimension", None) == "3D"
        self.fields = FIELDS
        self.boolean_fields = BOOLEAN_FIELDS
        self.numeric_fields = NUMERIC_FIELDS
        self.constructors = {"nodes": Node, "members": Member, "loads": Load}
        if self.spatial:
            from .spatial_model import SpatialNode, SpatialMember, SpatialLoad, RESTRAINT_FIELDS, SPRING_FIELDS
            self.fields = {"nodes": ("name", "x", "y", "z", "support", *RESTRAINT_FIELDS, *SPRING_FIELDS),
                           "members": ("name", "start", "end", "material", "section", "roll", "kind"),
                           "loads": (*FIELDS["loads"][:-1], "elevation", "units")}
            self.boolean_fields = set(RESTRAINT_FIELDS)
            self.numeric_fields = NUMERIC_FIELDS | {"z", "roll", "elevation", *SPRING_FIELDS}
            self.constructors = {"nodes": SpatialNode, "members": SpatialMember, "loads": SpatialLoad}
        self.original = project.clone()
        self.definition = None
        self.setWindowTitle("Model Tables")
        self.resize(1050, 520)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tables = {}
        headers = {
            "nodes": ["ID", f"X ({project.units.length})", f"Y ({project.units.length})",
                      "Support", "Restrain DX", "Restrain DY", "Restrain RZ",
                      f"Spring DX ({project.units.stiffness})", f"Spring DY ({project.units.stiffness})",
                      f"Spring RZ ({project.units.rotational_stiffness})"],
            "members": ["ID", "Start", "End", "Material", "Section", "Start hinge", "End hinge", "Type",
                        "Start axial DX", "End axial DX", "Start shear DY", "End shear DY"],
            "loads": ["ID", "Target", "Case", "Type", "Direction", "Magnitude / start intensity",
                      "Start fraction", f"End intensity ({project.units.intensity})", "End fraction", "Angle (deg)", "Magnitude units"],
        }
        if self.spatial:
            from .spatial_model import DOFS
            headers["nodes"] = ["ID", *(f"{axis} ({project.units.length})" for axis in ("X", "Y", "Z")), "Support",
                                *("Restrain " + dof for dof in DOFS),
                                *(f"Spring {dof} ({project.units.stiffness if index < 3 else project.units.rotational_stiffness})" for index, dof in enumerate(DOFS))]
            headers["members"] = ["ID", "Start", "End", "Material", "Section", "Roll (deg)", "Type"]
            headers["loads"] = [*headers["loads"][:-2], "Azimuth (deg)", "Elevation (deg)", "Magnitude units"]
        for kind, fields in self.fields.items():
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            table = QTableWidget(0, len(fields))
            table.setObjectName(f"model_table_{kind}")
            table.setHorizontalHeaderLabels(headers[kind])
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            table.setSortingEnabled(False)
            self.tables[kind] = table
            panel_layout.addWidget(table)
            actions = QHBoxLayout()
            for title, icon, callback in (
                ("Add row", QStyle.StandardPixmap.SP_FileIcon, self.add_row),
                ("Remove selected rows", QStyle.StandardPixmap.SP_TrashIcon, self.remove_rows),
            ):
                button = QPushButton(self.style().standardIcon(icon), title)
                button.clicked.connect(lambda checked=False, kind=kind, callback=callback: callback(kind))
                actions.addWidget(button)
            actions.addStretch()
            panel_layout.addLayout(actions)
            self.tabs.addTab(panel, kind.capitalize())
        for kind in self.fields:
            for entity in getattr(project, kind).values():
                self.insert_entity(kind, entity)
        for kind, table in self.tables.items():
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(kind == "loads")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def names(self, kind):
        table = self.tables[kind]
        return [table.item(row, 0).text() for row in range(table.rowCount())]

    def choices(self, kind, key):
        if self.spatial and key == "direction":
            from .spatial_model import MEMBER_DIRECTIONS
            return [*MEMBER_DIRECTIONS, "Angle"]
        if kind == "members" and key == "kind":
            return ["frame", "truss"]
        if key in ("start", "end"):
            return self.names("nodes")
        if key == "target":
            return [*self.names("nodes"), *self.names("members")]
        if key == "material":
            return list(self.original.materials)
        if key == "section":
            return list(self.original.sections)
        if key == "case":
            return self.original.load_cases
        return {"support": ["free", "pin", "roller", "fixed", "custom"],
                "kind": ["point", "distributed"],
                "direction": ["FX", "FY", "MZ", "Angle", "Local x", "Local y", "Local angle"]}.get(key)

    def quantity(self, kind, key, direction="FY", load_kind="point"):
        if key in ("x", "y", "z"):
            return "length"
        if key in ("spring_x", "spring_y", "spring_z"):
            return "stiffness"
        if key in ("spring_rx", "spring_ry", "spring_rz"):
            return "rotational_stiffness"
        if key == "end_magnitude":
            return "intensity"
        if key == "magnitude":
            return "intensity" if load_kind == "distributed" else "moment" if direction.upper().startswith("M") else "force"
        return None

    def insert_entity(self, kind, entity):
        table = self.tables[kind]
        row = table.rowCount()
        table.insertRow(row)
        for column, key in enumerate(self.fields[kind]):
            if key == "units":
                item = QTableWidgetItem()
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, column, item)
                continue
            value = getattr(entity, key)
            choices = self.choices(kind, key)
            if choices is not None:
                widget = QComboBox()
                widget.addItems(choices if value in choices else [*choices, value])
                widget.setCurrentText(value)
                if kind == "loads" and key in ("kind", "direction"):
                    widget.setToolTip("Changing type or direction reinterprets the entered magnitude in the row's displayed units.")
                if self.spatial and key == "direction":
                    widget.setToolTip(widget.toolTip() + "\nUppercase: global XYZ. Mixed case: rolled member xyz. Angle: global azimuth +X toward +Z, elevation toward +Y. Nodes accept global only.")
                table.setCellWidget(row, column, widget)
            else:
                quantity = self.quantity(kind, key, getattr(entity, "direction", "FY"), getattr(entity, "kind", "point"))
                shown = self.original.units.to_display(value, quantity) if quantity else value
                text = f"{shown:.12g}" if key in self.numeric_fields else str(value)
                item = QTableWidgetItem(text)
                if key == "name":
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                elif key in self.boolean_fields:
                    item.setText("")
                    item.setFlags((item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable)
                    item.setCheckState(Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
                    item.setData(Qt.ItemDataRole.UserRole, value)
                elif key in self.numeric_fields:
                    item.setData(Qt.ItemDataRole.UserRole, (value, text, quantity))
                    item.setToolTip("Finite signed number; scientific notation is accepted.")
                table.setItem(row, column, item)
        if kind == "loads":
            for key in ("kind", "direction"):
                widget = table.cellWidget(row, self.fields[kind].index(key))
                widget.currentTextChanged.connect(self.update_load_units)
            self.update_load_units()
        if kind == "nodes":
            widget = table.cellWidget(row, self.fields[kind].index("support"))
            widget.currentTextChanged.connect(self.update_supports)
            self.update_supports()
        if kind == "members" and not self.spatial:
            widget = table.cellWidget(row, self.fields[kind].index("kind"))
            widget.currentTextChanged.connect(self.update_member_types)
            self.update_member_types()

    def update_member_types(self):
        table = self.tables["members"]
        for row in range(table.rowCount()):
            frame = table.cellWidget(row, FIELDS["members"].index("kind")).currentText() == "frame"
            for key in ("release_start", "release_end", "release_start_x", "release_end_x", "release_start_y", "release_end_y"):
                item = table.item(row, FIELDS["members"].index(key))
                flags = item.flags()
                item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled if frame else flags & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip("Member-local frame release. Truss ends are pinned; clear axial/shear releases before changing to truss.")

    def update_load_units(self):
        table = self.tables["loads"]
        for row in range(table.rowCount()):
            direction = table.cellWidget(row, self.fields["loads"].index("direction")).currentText()
            kind = table.cellWidget(row, self.fields["loads"].index("kind")).currentText()
            quantity = self.quantity("loads", "magnitude", direction, kind)
            table.item(row, self.fields["loads"].index("units")).setText(getattr(self.original.units, quantity))
            table.item(row, self.fields["loads"].index("end_magnitude")).setToolTip(f"End intensity ({self.original.units.intensity}); used for distributed loads.")

    def update_supports(self):
        table = self.tables["nodes"]
        for row in range(table.rowCount()):
            support = table.cellWidget(row, self.fields["nodes"].index("support")).currentText()
            keys = tuple(key for key in self.fields["nodes"] if key.startswith("restraint_"))
            for index, key in enumerate(keys):
                item = table.item(row, self.fields["nodes"].index(key))
                flags = item.flags()
                item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled if support == "custom" else flags & ~Qt.ItemFlag.ItemIsEnabled)
                if support != "custom":
                    restrained = self.constructors["nodes"]("", 0, 0, support).restraints[index]
                    item.setCheckState(Qt.CheckState.Checked if restrained else Qt.CheckState.Unchecked)
                item.setToolTip("Used only with a custom support.")

    def refresh_references(self):
        for kind, keys in (("members", ("start", "end")), ("loads", ("target",))):
            table = self.tables[kind]
            for row in range(table.rowCount()):
                for key in keys:
                    widget = table.cellWidget(row, self.fields[kind].index(key))
                    value, choices = widget.currentText(), self.choices(kind, key)
                    widget.clear()
                    widget.addItems(choices if value in choices else [*choices, value])
                    widget.setCurrentText(value)

    def add_row(self, kind):
        name = self.original.next_name({"nodes": "N", "members": "M", "loads": "L"}[kind],
                                       {*self.names("nodes"), *self.names("members"), *self.names("loads")})
        if kind == "nodes":
            entity = self.constructors[kind](name, (len(self.names("nodes")) + 1) * self.original.grid, 0)
        elif kind == "members":
            nodes = self.names("nodes")
            if len(nodes) < 2:
                QMessageBox.warning(self, "Model Tables", "Add at least two nodes first.")
                return
            entity = self.constructors[kind](name, nodes[0], nodes[-1], self.original.default_material, self.original.default_section)
        else:
            targets = [*self.names("members"), *self.names("nodes")]
            if not targets:
                QMessageBox.warning(self, "Model Tables", "Add a node or member first.")
                return
            entity = self.constructors[kind](name, targets[0], case=self.original.default_load_case)
        self.insert_entity(kind, entity)
        self.refresh_references()
        self.tables[kind].resizeColumnsToContents()
        self.tables[kind].selectRow(self.tables[kind].rowCount() - 1)

    def remove_rows(self, kind):
        table = self.tables[kind]
        for row in sorted({index.row() for index in table.selectedIndexes()}, reverse=True):
            table.removeRow(row)
        self.refresh_references()

    def preview(self):
        candidate = self.original.clone()
        for kind, constructor in self.constructors.items():
            table, entities = self.tables[kind], {}
            for row in range(table.rowCount()):
                values = {}
                for column, key in enumerate(self.fields[kind]):
                    if key == "units":
                        continue
                    widget, item = table.cellWidget(row, column), table.item(row, column)
                    if widget is not None:
                        value = widget.currentText()
                    elif key in self.boolean_fields:
                        value = item.checkState() == Qt.CheckState.Checked
                        if kind == "nodes" and values["support"] != "custom":
                            value = item.data(Qt.ItemDataRole.UserRole)
                    elif key in self.numeric_fields:
                        quantity = self.quantity(kind, key, values.get("direction", "FY"), values.get("kind", "point"))
                        original, shown, original_quantity = item.data(Qt.ItemDataRole.UserRole)
                        if item.text() == shown and quantity == original_quantity:
                            value = original
                        else:
                            try:
                                value = float(item.text())
                                if quantity:
                                    value = candidate.units.from_display(value, quantity)
                                if not math.isfinite(value):
                                    raise ValueError()
                            except (ValueError, OverflowError):
                                raise ValueError(f"{kind.capitalize()} row {row + 1}, {table.horizontalHeaderItem(column).text()}: enter a finite number.") from None
                    else:
                        value = item.text()
                    values[key] = value
                entities[values["name"]] = constructor(**values)
            setattr(candidate, kind, entities)
        candidate.validate()
        return candidate

    def accept(self):
        # Move focus out of any cell editor so its final text reaches the table.
        self.tabs.setFocus()
        try:
            self.definition = self.preview()
        except ValueError as error:
            QMessageBox.warning(self, "Model Tables", str(error))
            return
        super().accept()
