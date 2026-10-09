"""Native recipes/options for all concrete PyNite mesh generators."""
import json

from PySide6.QtCore import QIODevice, QSaveFile
from PySide6.QtGui import QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QStyle, QTableWidget, QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget)

from .mesh_model import (COUNT_KEYS, GENERATORS, RECT_FAMILIES, MeshDefinition,
                         generate_mesh, mesh_export, mesh_quality)
from .mesh_preview import MeshPreview
from .units import UNIT_SYSTEMS


class MeshEdit(QUndoCommand):
    def __init__(self, window, before, after):
        super().__init__("Change mesh recipe")
        self.window, self.before, self.after = window, before, after

    def undo(self):
        self.window.install(self.before)

    def redo(self):
        self.window.install(self.after)


class MeshWorkspace(QDialog):
    def __init__(self, parent=None, unit_system="imperial", definition=None, selection_only=False):
        super().__init__(parent)
        self.setWindowTitle("PyNite Surface Meshing (Experimental)")
        self.resize(1180, 820)
        self.loading, self.pending, self.path = False, False, None
        self.definition = MeshDefinition.from_dict(definition.to_dict()) if definition else MeshDefinition(unit_system=unit_system)
        self.saved = self.definition.to_dict()
        self.selection_only = selection_only
        self.undo = QUndoStack(self)
        root = QVBoxLayout(self)
        toolbar = QToolBar()
        root.addWidget(toolbar)
        for label, icon, callback in (("Open recipe", QStyle.StandardPixmap.SP_DialogOpenButton, self.open_file),
                                      ("Save recipe", QStyle.StandardPixmap.SP_DialogSaveButton, self.save_file),
                                      ("Export generated mesh", QStyle.StandardPixmap.SP_ArrowDown, self.export_mesh)):
            action = toolbar.addAction(self.style().standardIcon(icon), label)
            action.setToolTip(label)
            action.triggered.connect(callback)
        for text, icon, action in (("Undo", QStyle.StandardPixmap.SP_ArrowBack, self.undo.createUndoAction(self, "Undo")),
                                  ("Redo", QStyle.StandardPixmap.SP_ArrowForward, self.undo.createRedoAction(self, "Redo"))):
            action.setIcon(self.style().standardIcon(icon))
            action.setToolTip(text)
            toolbar.addAction(action)
        self.analyze_action = toolbar.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
                                               "Analyze rectangular plate", self.analyze_rectangle)
        self.analyze_action.setVisible(not selection_only)
        splitter = QSplitter()
        root.addWidget(splitter, 1)
        controls = QWidget()
        controls.setMinimumWidth(460)
        controls_layout = QVBoxLayout(controls)
        self.generator = QComboBox()
        for key, (label, _) in GENERATORS.items():
            if not selection_only or key == "rectangle":
                self.generator.addItem(label, key)
        controls_layout.addWidget(self.generator)
        self.tabs = QTabWidget()
        controls_layout.addWidget(self.tabs, 1)
        self.geometry_form, self.mesh_form = QFormLayout(), QFormLayout()
        for label, form in (("Geometry", self.geometry_form), ("Mesh / Material", self.mesh_form)):
            body = QWidget()
            body.setLayout(form)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(body)
            self.tabs.addTab(scroll, label)
        self.units = QComboBox()
        for key in ("imperial", "si", "si_mm", "imperial_ft"):
            self.units.addItem(UNIT_SYSTEMS[key].label, key)
        self.mesh_form.addRow("Units", self.units)
        self.mesh_name = QLineEdit()
        self.mesh_form.addRow("Mesh name", self.mesh_name)
        self.mesh_name.textChanged.connect(self.mark_pending)
        self.material_name = QLineEdit()
        self.mesh_form.addRow("Material", self.material_name)
        self.material_name.textChanged.connect(self.mark_pending)
        self.common_fields = {}
        for key in ("mesh_size", "thickness", "E", "nu", "rho", "kx_mod", "ky_mod", "node_start", "element_start"):
            self.common_fields[key] = self.numeric(key)
            self.mesh_form.addRow(key, self.common_fields[key])
        self.element_type = QComboBox()
        self.element_type.addItems(["Quad", "Rect"])
        self.element_type.currentTextChanged.connect(self.mark_pending)
        self.mesh_form.addRow("Element family", self.element_type)
        self.plane, self.axis = QComboBox(), QComboBox()
        self.plane.addItems(["XY", "XZ", "YZ"])
        self.axis.addItems(["X", "Y", "Z"])
        self.plane.currentTextChanged.connect(self.mark_pending)
        self.axis.currentTextChanged.connect(self.mark_pending)
        self.origin_fields = [self.numeric("origin_" + axis) for axis in "XYZ"]
        self.parameter_fields = {}
        self.line_table = QTableWidget(0, 2)
        self.opening_table = QTableWidget(0, 5)
        for title, table, callback in (("Control Lines", self.line_table, self.add_control),
                                       ("Openings", self.opening_table, self.add_opening)):
            panel = QWidget()
            layout = QVBoxLayout(panel)
            actions = QHBoxLayout()
            for text, icon, handler in (("Add", QStyle.StandardPixmap.SP_FileDialogNewFolder, callback),
                                       ("Remove selected", QStyle.StandardPixmap.SP_TrashIcon, lambda checked=False, table=table: self.remove_row(table))):
                button = QToolButton()
                button.setIcon(self.style().standardIcon(icon))
                button.setToolTip(text)
                button.clicked.connect(handler)
                actions.addWidget(button)
            actions.addStretch()
            layout.addLayout(actions)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            layout.addWidget(table)
            self.tabs.addTab(panel, title)
        self.apply_button = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Apply / Generate Mesh")
        self.apply_button.clicked.connect(self.apply)
        controls_layout.addWidget(self.apply_button)
        if selection_only:
            use = QPushButton("Use Mesh")
            use.clicked.connect(lambda: self.accept() if self.apply() else None)
            controls_layout.addWidget(use)
        splitter.addWidget(controls)
        self.preview = MeshPreview(self)
        splitter.addWidget(self.preview)
        splitter.setSizes([480, 700])
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.generator.currentIndexChanged.connect(self.change_generator)
        self.units.currentIndexChanged.connect(self.change_units)
        self.install(self.definition.to_dict())

    def numeric(self, key):
        if key in COUNT_KEYS or key in ("node_start", "element_start"):
            widget = QSpinBox()
            automatic = key == "num_elements" and self.definition.generator == "cylinder"
            widget.setRange(0 if automatic else 3 if key in COUNT_KEYS else 1, 1024 if key in COUNT_KEYS else 100000000)
            if automatic:
                widget.setSpecialValueText("Automatic")
        else:
            from .app import number
            widget = number(0, -1e12, 1e12, 8)
        widget.setKeyboardTracking(False)
        widget.setObjectName("mesh_" + key)
        widget.valueChanged.connect(self.mark_pending)
        return widget

    @staticmethod
    def quantity(key, units):
        if key in COUNT_KEYS or key in ("node_start", "element_start", "nu", "kx_mod", "ky_mod"):
            return 1, ""
        if key == "E":
            return units.factor("stress"), units.stress
        if key == "rho":
            return units.factor("density"), units.density
        return units.length_factor, units.length

    def set_number(self, widget, key, value):
        factor, _ = self.quantity(key, self.definition.units)
        widget.setValue(value*factor)
        widget.setProperty("canonical", value)
        widget.setProperty("initial", widget.value())

    def get_number(self, widget, key):
        widget.interpretText()
        if widget.value() == widget.property("initial"):
            return widget.property("canonical")
        factor, _ = self.quantity(key, self.definition.units)
        return widget.value()/factor if not isinstance(widget, QSpinBox) else widget.value()

    def install(self, data):
        definition = MeshDefinition.from_dict(data)
        model = generate_mesh(definition)
        self.definition, self.model, self.loading = definition, model, True
        units = definition.units
        if self.units.findData(units.key) < 0:
            self.units.addItem(units.label, units.key)
        self.units.setCurrentIndex(self.units.findData(units.key))
        self.generator.setCurrentIndex(self.generator.findData(definition.generator))
        # takeRow preserves reusable plane/axis/origin widgets.
        while self.geometry_form.rowCount():
            row = self.geometry_form.takeRow(0)
            if row.labelItem:
                row.labelItem.widget().deleteLater()
            if row.fieldItem and row.fieldItem.widget() not in (self.plane, self.axis, *self.origin_fields):
                row.fieldItem.widget().deleteLater()
        self.plane.hide()
        self.axis.hide()
        self.parameter_fields = {}
        for key, value in definition.parameters.items():
            widget = self.numeric(key)
            self.set_number(widget, key, value)
            _, label = self.quantity(key, units)
            name = {"num_elements": "Circumferential divisions", "num_quads": "Circumferential divisions",
                    "num_inner_quads": "Inner circumferential divisions"}.get(key, key.replace("_", " ").capitalize())
            self.geometry_form.addRow(name + (f" ({label})" if label else ""), widget)
            self.parameter_fields[key] = widget
        self.geometry_form.addRow("Plane" if definition.generator == "rectangle" else "Axis",
                                  self.plane if definition.generator == "rectangle" else self.axis)
        (self.plane if definition.generator == "rectangle" else self.axis).show()
        self.plane.setCurrentText(definition.plane)
        self.axis.setCurrentText(definition.axis)
        for coordinate, widget, value in zip("XYZ", self.origin_fields, definition.origin):
            self.set_number(widget, "origin", value)
            self.geometry_form.addRow(f"Origin {coordinate} ({units.length})", widget)
            widget.show()
        labels = {"mesh_size": "Target size", "thickness": "Thickness", "E": "Elastic modulus",
                  "nu": "Poisson ratio", "rho": "Weight density", "kx_mod": "Local x stiffness modifier",
                  "ky_mod": "Local y stiffness modifier", "node_start": "First node number", "element_start": "First element number"}
        for key, widget in self.common_fields.items():
            value = getattr(definition.material, key) if key in ("E", "nu", "rho") else getattr(definition, key)
            self.set_number(widget, key, value)
            _, label = self.quantity(key, units)
            self.mesh_form.labelForField(widget).setText(labels[key] + (f" ({label})" if label else ""))
        self.common_fields["mesh_size"].setEnabled(definition.generator not in ("annulus_ring", "annulus_transition", "cylinder_ring"))
        self.material_name.setText(definition.material.name)
        self.mesh_name.setText(definition.name)
        self.element_type.setCurrentText(definition.element_type)
        self.element_type.setEnabled(definition.generator in RECT_FAMILIES)
        rectangle = definition.generator == "rectangle"
        self.tabs.setTabEnabled(2, rectangle)
        self.tabs.setTabEnabled(3, rectangle)
        self.line_table.setHorizontalHeaderLabels(["Axis", f"Coordinate ({units.length})"])
        self.opening_table.setHorizontalHeaderLabels(["Name", f"Left ({units.length})", f"Bottom ({units.length})", f"Width ({units.length})", f"Height ({units.length})"])
        self.line_table.setRowCount(0)
        self.opening_table.setRowCount(0)
        for axis, coordinates in (("x", definition.x_control), ("y", definition.y_control)):
            for coordinate in coordinates:
                self.add_control(axis=axis, coordinate=coordinate)
        for opening in definition.openings:
            self.add_opening(opening=opening)
        self.loading, self.pending = False, False
        self.analyze_action.setEnabled(rectangle)
        self.preview.set_mesh(definition, model)
        quality = mesh_quality(model)
        self.status.setText(f"Geometry only | {quality['nodes']} nodes | {quality['elements']} {definition.element_type} elements | "
                            f"Max edge ratio {quality['max_edge_ratio']:.3g}")

    def mark_pending(self, *_):
        if not self.loading:
            self.pending = True
            self.status.setText("Unapplied mesh changes")

    def add_control(self, checked=False, *, axis="x", coordinate=0.):
        row = self.line_table.rowCount()
        if row >= 64:
            return
        self.line_table.insertRow(row)
        box = QComboBox()
        box.addItems(["x", "y"])
        box.setCurrentText(axis)
        box.currentTextChanged.connect(self.mark_pending)
        number = self.numeric("control")
        self.set_number(number, "control", coordinate)
        self.line_table.setCellWidget(row, 0, box)
        self.line_table.setCellWidget(row, 1, number)
        self.mark_pending()

    def add_opening(self, checked=False, *, opening=None):
        row = self.opening_table.rowCount()
        if row >= 16:
            return
        opening = opening or {"name": f"Opening {row+1}", "x_left": 30., "y_bott": 30., "width": 15., "height": 15.}
        self.opening_table.insertRow(row)
        name = QLineEdit(opening["name"])
        name.textChanged.connect(self.mark_pending)
        self.opening_table.setCellWidget(row, 0, name)
        for column, key in enumerate(("x_left", "y_bott", "width", "height"), 1):
            number = self.numeric(key)
            self.set_number(number, key, opening[key])
            self.opening_table.setCellWidget(row, column, number)
        self.mark_pending()

    def remove_row(self, table):
        for row in sorted({index.row() for index in table.selectedIndexes()}, reverse=True):
            table.removeRow(row)
        self.mark_pending()

    def candidate(self):
        definition = MeshDefinition.from_dict(self.definition.to_dict())
        for key, widget in self.common_fields.items():
            owner = definition.material if key in ("E", "nu", "rho") else definition
            value = self.get_number(widget, key)
            if owner is definition.material and value != getattr(owner, key):
                owner.preset = None
            setattr(owner, key, value)
        definition.parameters = {key: self.get_number(widget, key) for key, widget in self.parameter_fields.items()}
        definition.material.name = self.material_name.text()
        definition.name = self.mesh_name.text()
        definition.origin = [self.get_number(widget, "origin") for widget in self.origin_fields]
        definition.element_type = self.element_type.currentText()
        definition.plane, definition.axis = self.plane.currentText(), self.axis.currentText()
        definition.x_control, definition.y_control = [], []
        for row in range(self.line_table.rowCount()):
            axis = self.line_table.cellWidget(row, 0).currentText()
            getattr(definition, axis+"_control").append(self.get_number(self.line_table.cellWidget(row, 1), "control"))
        definition.openings = []
        for row in range(self.opening_table.rowCount()):
            opening = {"name": self.opening_table.cellWidget(row, 0).text()}
            for column, key in enumerate(("x_left", "y_bott", "width", "height"), 1):
                opening[key] = self.get_number(self.opening_table.cellWidget(row, column), key)
            definition.openings.append(opening)
        definition.validate()
        return definition

    def apply(self):
        try:
            candidate = self.candidate()
            generate_mesh(candidate)
            before, after = self.definition.to_dict(), candidate.to_dict()
            if before != after:
                self.undo.push(MeshEdit(self, before, after))
            else:
                self.install(after)
            return True
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Mesh", str(error))
            return False

    def change_generator(self, *_):
        if self.loading:
            return
        key = self.generator.currentData()
        try:
            candidate = self.candidate()
            candidate.generator, candidate.parameters = key, dict(GENERATORS[key][1])
            candidate.x_control, candidate.y_control, candidate.openings = [], [], []
            candidate.mesh_size = 15.
            if key not in RECT_FAMILIES:
                candidate.element_type = "Quad"
            generate_mesh(candidate)
            self.undo.push(MeshEdit(self, self.definition.to_dict(), candidate.to_dict()))
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Mesh", str(error))
            self.loading = True
            self.generator.setCurrentIndex(self.generator.findData(self.definition.generator))
            self.loading = False

    def change_units(self, *_):
        if self.loading:
            return
        key = self.units.currentData()
        if self.apply():
            before = self.definition.to_dict()
            self.undo.push(MeshEdit(self, before, {**before, "unit_system": key}))
        else:
            self.loading = True
            self.units.setCurrentIndex(self.units.findData(self.definition.unit_system))
            self.loading = False

    def confirm_discard(self):
        if self.pending or self.definition.to_dict() != self.saved:
            return QMessageBox.question(self, "Unsaved Mesh", "Discard unsaved mesh recipe changes?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Discard
        return True

    def open_file(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Mesh Recipe", "", "Mesh recipe (*.pynitemesh)")
        if path:
            try:
                definition = MeshDefinition.open(path)
                if self.selection_only and definition.generator != "rectangle":
                    raise ValueError("The rectangular plate workspace accepts Rectangle recipes only.")
                self.install(definition.to_dict())
                self.undo.clear()
                self.path, self.saved = path, definition.to_dict()
            except (ValueError, OSError) as error:
                QMessageBox.warning(self, "Open Mesh", str(error))

    def write_json(self, path, data):
        encoded = json.dumps(data, indent=2, allow_nan=False).encode()
        file = QSaveFile(path)
        if not file.open(QIODevice.OpenModeFlag.WriteOnly) or file.write(encoded) != len(encoded) or not file.commit():
            QMessageBox.warning(self, "Save Mesh", file.errorString())
            return False
        return True

    def save_file(self):
        if not self.apply():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Mesh Recipe", self.path or "surface.pynitemesh", "Mesh recipe (*.pynitemesh)")
        if path:
            if not path.endswith(".pynitemesh"):
                path += ".pynitemesh"
            if self.write_json(path, self.definition.to_dict()):
                self.path, self.saved = path, self.definition.to_dict()

    def export_mesh(self):
        if not self.apply():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Generated Mesh", "surface-mesh.json", "JSON (*.json)")
        if path:
            self.write_json(path, mesh_export(self.definition, self.model))

    def analyze_rectangle(self):
        if not self.apply() or self.definition.generator != "rectangle":
            return
        from .plate_model import PlateDefinition
        from .plate_workspace import PlateWorkspace
        definition = PlateDefinition()
        transfer_rectangle(self.definition, definition)
        PlateWorkspace(self, definition=definition).exec()

    def reject(self):
        if self.confirm_discard():
            super().reject()

    def closeEvent(self, event):
        event.ignore()
        self.reject()


def transfer_rectangle(mesh, plate):
    if mesh.generator != "rectangle":
        raise ValueError("Only rectangular recipes can be transferred to transverse plate analysis.")
    for key in ("mesh_size", "thickness", "material", "origin", "plane", "element_type", "x_control", "y_control",
                "openings", "kx_mod", "ky_mod", "node_start", "element_start", "unit_system"):
        setattr(plate, key, getattr(mesh, key))
    plate.width, plate.height = mesh.parameters["width"], mesh.parameters["height"]
    plate.mesh_name = mesh.name
    plate.validate()
