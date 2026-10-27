"""One temporary native modelling panel; preview uses the existing canvas."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
                              QVBoxLayout, QWidget)
from .geometry_tools import plan_generator, plan_merge, plan_transform, spacing_list, spatial
from .theme import colors


class GeometryPanel(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window, self.plan, self.baseline = window, None, None
        self.context = (window.project_session, window.project.unit_system, spatial(window.project))
        self.controls = {}
        layout = QVBoxLayout(self)
        self.tool = QComboBox()
        self.tool.addItems(["Transform selection", "Beam / Frame generator", "Merge two nodes"])
        layout.addWidget(self.tool)
        self.pages = QStackedWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.pages)
        layout.addWidget(scroll, 1)
        self.transform_form()
        self.generator_form()
        self.merge_form()
        self.note = QLabel("Preview shows dashed candidate geometry on the main canvas. Apply is one undoable edit. Existing results remain unchanged until Apply.")
        self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.note)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        row = QHBoxLayout()
        self.preview_button, self.apply_button, self.cancel_button = (QPushButton(text) for text in ("Preview", "Apply", "Cancel"))
        self.apply_button.setEnabled(False)
        for button in (self.preview_button, self.apply_button, self.cancel_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.preview_button.clicked.connect(self.preview)
        self.apply_button.clicked.connect(self.apply)
        self.cancel_button.clicked.connect(self.cancel)
        self.tool.currentIndexChanged.connect(self.pages.setCurrentIndex)
        self.tool.currentIndexChanged.connect(self.clear_preview)
        for control in self.controls.values():
            if isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self.clear_preview)
            elif isinstance(control, QCheckBox):
                control.toggled.connect(self.clear_preview)
            elif isinstance(control, QLineEdit):
                control.textChanged.connect(self.clear_preview)
            else:
                control.valueChanged.connect(self.clear_preview)
        self.operation_changed()

    def page(self):
        widget = QWidget()
        form = QFormLayout(widget)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.pages.addWidget(widget)
        return form

    def choice(self, form, key, label, items):
        control = QComboBox()
        for text, value in items:
            control.addItem(text, value)
        self.controls[key] = control
        form.addRow(label, control)
        return control

    def length(self, form, key, label, value=0., minimum=-1e9):
        from .app import unit_number
        control = unit_number(value, self.window.project.units, "length", minimum=minimum)
        self.controls[key] = control
        form.addRow(f"{label} ({self.window.project.units.length})", control)
        return control

    def check(self, form, key, text):
        control = QCheckBox(text)
        self.controls[key] = control
        form.addRow(control)
        return control

    def transform_form(self):
        from .app import number
        form = self.page()
        note = QLabel("Preview captures the current node/member selection, including selected members' end nodes. Use Repeat for a linear array of additional copies.")
        note.setWordWrap(True)
        form.addRow(note)
        operation = self.choice(form, "operation", "Operation", [("Move", "move"), ("Repeat / linear array", "repeat"), ("Rotate", "rotate"), ("Mirror", "mirror")])
        dims = "XYZ" if spatial(self.window.project) else "XY"
        for axis in dims:
            self.length(form, "offset_"+axis, "Step / offset "+axis, self.window.project.grid if axis == "X" else 0.)
        for axis in dims:
            self.length(form, "origin_"+axis, "Reference point "+axis)
        self.choice(form, "axis", "Rotation axis / mirror normal", [(axis, axis) for axis in dims+("Z" if dims == "XY" else "")])
        self.controls["axis"].setCurrentText("Z")
        self.controls["angle"] = number(90., -360., 360., 6)
        form.addRow("Rotation (degrees)", self.controls["angle"])
        copies = QSpinBox()
        copies.setRange(1, 50)
        copies.setValue(3)
        self.controls["copies"] = copies
        form.addRow("Additional copies", copies)
        self.check(form, "copy", "Keep original (copy rotated / mirrored selection)")
        self.check(form, "copy_loads", "Copy manual loads on included nodes/members")
        self.check(form, "copy_supports", "Copy global supports and springs")
        self.check(form, "reuse_transform", "Reuse coincident joints (loads can add at reused joints)")
        operation.currentIndexChanged.connect(self.operation_changed)
        self.controls["copy"].toggled.connect(self.operation_changed)

    def operation_changed(self):
        c = self.controls
        op = c["operation"].currentData()
        for axis in "XYZ":
            if "offset_"+axis in c:
                c["offset_"+axis].setEnabled(op in ("move", "repeat"))
                c["origin_"+axis].setEnabled(op in ("rotate", "mirror"))
        c["axis"].setEnabled(op in ("rotate", "mirror"))
        if not spatial(self.window.project):
            allowed = ("Z",) if op == "rotate" else ("X", "Y") if op == "mirror" else ("X", "Y", "Z")
            for index in range(c["axis"].count()):
                c["axis"].model().item(index).setEnabled(c["axis"].itemData(index) in allowed)
            if c["axis"].currentData() not in allowed:
                c["axis"].setCurrentIndex(c["axis"].findData(allowed[0]))
        c["angle"].setEnabled(op == "rotate")
        c["copies"].setEnabled(op == "repeat")
        c["copy"].setEnabled(op in ("rotate", "mirror"))
        copying = op == "repeat" or (op in ("rotate", "mirror") and c["copy"].isChecked())
        for key in ("copy_loads", "copy_supports", "reuse_transform"):
            c[key].setEnabled(copying)

    def generator_form(self):
        p, form = self.window.project, self.page()
        note = QLabel("Planar XY geometry with explicit connected joints. A frame has columns at every bay boundary and beams at every storey. No manual loads are generated.")
        note.setWordWrap(True)
        form.addRow(note)
        self.choice(form, "generator", "Layout", [("Multi-bay / multi-storey frame", "frame"), ("Continuous beam", "beam")])
        for key, label, defaults in (("bays", "Bay / span widths", [240., 240.]), ("heights", "Storey heights", [144., 144.])):
            control = QLineEdit(", ".join(f"{p.units.to_display(value, 'length'):.6g}" for value in defaults))
            control.setToolTip("Comma-separated positive spacings; each value defines one bay/span or storey.")
            self.controls[key] = control
            form.addRow(f"{label} ({p.units.length})", control)
        self.length(form, "insert_X", "Insertion X")
        self.length(form, "insert_Y", "Insertion Y")
        for key, label, entries, default in (("material", "Material", p.materials, p.default_material),
                                            ("beam_section", "Beam section", p.sections, p.default_section),
                                            ("column_section", "Column section", p.sections, p.default_section)):
            control = self.choice(form, key, label, [(name, name) for name in entries])
            control.setCurrentText(default)
        self.choice(form, "base", "Frame base supports", [("Fixed", "fixed"), ("Pin", "pin"), ("Free", "free")])
        self.check(form, "reuse_generator", "Reuse coincident joints (supports must match)")
        def layout_changed():
            frame = self.controls["generator"].currentData() == "frame"
            for key in ("heights", "column_section", "base"):
                self.controls[key].setEnabled(frame)
        self.controls["generator"].currentIndexChanged.connect(layout_changed)

    def merge_form(self):
        p, form = self.window.project, self.page()
        note = QLabel("Retain one node's coordinates and redirect the other node's references. Preview all affected geometry. Zero-length/duplicate members and new overlaps are blocked.")
        note.setWordWrap(True)
        form.addRow(note)
        selected = [n for k, n in self.window.selections if k == "nodes"]
        names = list(dict.fromkeys(selected+list(p.nodes)))
        self.choice(form, "target", "Retain node", [(name, name) for name in names])
        source = self.choice(form, "source", "Remove node", [(name, name) for name in names])
        if len(names) > 1:
            source.setCurrentIndex(1)
        self.length(form, "tolerance", "Maximum merge distance", p.grid*.01, minimum=0.)
        self.choice(form, "supports", "Support / spring conflicts", [("Reject differences", "reject"), ("Keep retained node supports", "target"), ("Use removed node supports", "source")])
        self.check(form, "combine", "Keep both nodal load sets at the retained joint (additive)")

    def current_context(self):
        w = self.window
        return w.project_session, w.project.unit_system, spatial(w.project)

    def clear_preview(self, *_):
        self.plan, self.baseline = None, None
        if hasattr(self, "apply_button"):
            self.apply_button.setEnabled(False)
        if getattr(self.window, "geometry_preview", None) is not None:
            self.window.geometry_preview = None
            self.window.view.redraw()

    def model_changed(self):
        self.clear_preview()
        stale = self.current_context() != self.context
        self.preview_button.setEnabled(not stale)
        self.summary.setText("Project changed. Reopen the modelling tool for this project/units." if stale else "Model changed. Create a new preview before Apply.")

    def preview(self):
        if self.window.mcp_mode:
            return
        self.clear_preview()
        if self.current_context() != self.context:
            self.model_changed()
            return
        from .app import unit_value
        p, c = self.window.project, self.controls
        def vector(prefix):
            return tuple(unit_value(c[prefix+axis], p.units) if prefix+axis in c else 0. for axis in "XYZ")
        try:
            if self.tool.currentIndex() == 0:
                op = c["operation"].currentData()
                self.plan = plan_transform(p, self.window.selections, op,
                    offset=vector("offset_") if op in ("move", "repeat") else (0., 0., 0.),
                    origin=vector("origin_") if op in ("rotate", "mirror") else (0., 0., 0.),
                    angle=c["angle"].value(), axis=c["axis"].currentData(), copies=c["copies"].value(),
                    copy=c["copy"].isChecked() and op in ("rotate", "mirror"),
                    copy_loads=c["copy_loads"].isChecked(), copy_supports=c["copy_supports"].isChecked(), reuse=c["reuse_transform"].isChecked())
            elif self.tool.currentIndex() == 1:
                kind = c["generator"].currentData()
                self.plan = plan_generator(p, kind, spacing_list(c["bays"].text(), p.units),
                    spacing_list(c["heights"].text(), p.units) if kind == "frame" else (),
                    origin=vector("insert_")[:2], material=c["material"].currentData(),
                    beam_section=c["beam_section"].currentData(), column_section=c["column_section"].currentData(),
                    support=c["base"].currentData(), reuse=c["reuse_generator"].isChecked())
            else:
                self.plan = plan_merge(p, c["target"].currentData(), c["source"].currentData(), unit_value(c["tolerance"], p.units),
                    support_policy=c["supports"].currentData(), combine_loads=c["combine"].isChecked())
        except (ValueError, KeyError) as error:
            self.summary.setText(str(error))
            return
        self.baseline = p.to_dict()
        self.window.set_mode("select")
        self.window.geometry_preview = self.plan
        self.window.view.redraw()
        self.summary.setText(self.plan.summary+"\nDashed geometry is a preview. Use Fit to include it; Apply commits the candidate.")
        self.apply_button.setEnabled(True)

    def apply(self):
        w = self.window
        if w.mcp_mode or self.plan is None:
            return
        if self.baseline != w.project.to_dict() or self.current_context() != self.context:
            self.model_changed()
            return
        from .app import Edit
        plan = self.plan
        self.clear_preview()
        w.undo.push(Edit(w, self.tool.currentText(), w.project.clone(), plan.definition.clone()))
        from .organization import show_all
        show_all(w)
        w.select_many(plan.selections)
        w.view.fit()
        self.summary.setText("Applied as one undoable edit. Analyze again to update results.")

    def cancel(self):
        self.clear_preview()
        self.window.geometry_dock.hide()


def open_geometry_tool(window, index=0):
    if window.mcp_mode:
        return
    window.set_mode("select")
    if not hasattr(window, "geometry_dock"):
        window.geometry_panel = GeometryPanel(window)
        window.geometry_dock = window.dock("Modelling Tools", window.geometry_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        window.geometry_dock.visibilityChanged.connect(lambda visible: window.geometry_panel.clear_preview() if not visible else None)
    elif window.geometry_panel.context != window.geometry_panel.current_context():
        old = window.geometry_panel
        old.clear_preview()
        window.geometry_panel = GeometryPanel(window)
        window.geometry_dock.setWidget(window.geometry_panel)
        old.deleteLater()
    if index == 2:
        chosen = [n for k, n in window.selections if k == "nodes" and n in window.project.nodes]
        names = list(dict.fromkeys(chosen+list(window.project.nodes)))
        for key in ("target", "source"):
            control = window.geometry_panel.controls[key]
            control.clear()
            for name in names:
                control.addItem(name, name)
        if len(names) > 1:
            window.geometry_panel.controls["source"].setCurrentIndex(1)
    window.geometry_panel.tool.setCurrentIndex(index)
    window.geometry_dock.show()
    window.geometry_dock.raise_()


def draw_planar_preview(view):
    from .geometry_tools import preview_geometry
    geometry = preview_geometry(view.window.project, getattr(view.window, "geometry_preview", None))
    pen = QPen(QColor(colors()["accent"]), 3, Qt.PenStyle.DashLine)
    pen.setCosmetic(True)
    for (x, y), (xx, yy) in geometry["lines"]:
        item = view.scene().addLine(x, -y, xx, -yy, pen)
        item.setZValue(15)
    for x, y in geometry["nodes"]:
        item = view.scene().addEllipse(-4, -4, 8, 8, pen)
        item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations)
        item.setPos(x, -y)
        item.setZValue(15)
