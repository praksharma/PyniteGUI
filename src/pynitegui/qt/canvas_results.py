"""Main-canvas presentation and exact probes of the current static snapshot."""
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from .theme import colors, theme_name


PLANAR = (("Axial N", "axial"), ("Shear Fy", "shear"), ("Moment Mz", "moment"))


def signed_palette():
    return ("#79bdf1", "#a1aab2", "#ffb36b") if theme_name() == "dark" else ("#2469ad", "#69777e", "#c35d0a")


def signed_color(value, bound):
    negative, zero, positive = map(QColor, signed_palette())
    amount = min(1., abs(value)/bound) if bound else 0.
    end = positive if value >= 0 else negative
    return QColor.fromRgbF(*(zero.getRgbF()[i]+amount*(end.getRgbF()[i]-zero.getRgbF()[i]) for i in range(3)))


def signed_spans(points, values):
    """Skip duplicate load-jump stations and split sign crossings at zero."""
    for a, b, left, right in zip(points, points[1:], values, values[1:]):
        if np.linalg.norm(b-a) < 1e-10:
            continue
        if left*right < 0:
            zero = a+(b-a)*left/(left-right)
            yield a, zero, left/2
            yield zero, b, right/2
        else:
            yield a, b, (left+right)/2


def member_samples(project, result, kind):
    spatial = getattr(project, "dimension", "2D") == "3D"
    from .diagrams import sample_member
    from .spatial_results import QUANTITIES, sampled_member
    rows = {}
    for name, member in project.members.items():
        if spatial:
            xs, samples, _ = sampled_member(project, result, name)
            values = samples[:, QUANTITIES.index(kind)]
            a, b = (np.array(project.nodes[n].coords) for n in (member.start, member.end))
        else:
            samples = sample_member(project, result, name)
            xs, values = samples["x"], samples[kind]
            a, b = (np.array((project.nodes[n].x, project.nodes[n].y)) for n in (member.start, member.end))
        rows[name] = (a+xs[:, None]/np.linalg.norm(b-a)*(b-a), values)
    return rows


class CanvasResults(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.kind, self.dimension, self.inspected = None, None, None
        self.station = 0.
        self.solver = None
        self.cache_key, self.cache = None, None
        self.bounds = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.mode, self.style = QComboBox(), QComboBox()
        self.mode.setAccessibleName("Main canvas result")
        self.style.addItem("Offset diagrams", "offset")
        self.style.addItem("Signed colour map", "colour")
        self.style.setToolTip("Colour maps share a symmetric scale across this snapshot's combinations. Negative dashed; positive solid; zero dotted.")
        self.scale = QDoubleSpinBox()
        self.scale.setRange(.05, 10.)
        self.scale.setDecimals(2)
        self.scale.setValue(1.)
        self.scale.setSuffix("x")
        self.scale.setKeyboardTracking(False)
        for label, control in (("Canvas", self.mode), ("Style", self.style), ("Diagram scale", self.scale)):
            row.addWidget(QLabel(label))
            row.addWidget(control)
        row.addStretch()
        layout.addLayout(row)
        self.legend = QLabel("Run analysis to show canvas results.")
        self.legend.setWordWrap(True)
        self.legend.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.legend)
        row = QHBoxLayout()
        self.member = QComboBox()
        self.member.setAccessibleName("Inspected member")
        self.distance = QDoubleSpinBox()
        self.distance.setDecimals(8)
        self.distance.setKeyboardTracking(False)
        self.side = QComboBox()
        self.side.addItem("Right side", "right")
        self.side.addItem("Left side", "left")
        self.side.setToolTip("One-sided solver value at a load jump or internal member boundary")
        for label, control in (("Inspect", self.member), ("From start", self.distance)):
            row.addWidget(QLabel(label))
            row.addWidget(control, 1)
        row.addWidget(self.side)
        layout.addLayout(row)
        self.values = QLabel("Select a member to inspect its undeformed length.")
        self.values.setWordWrap(True)
        self.values.setTextFormat(Qt.TextFormat.PlainText)
        self.values.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.values)
        self.mode.currentIndexChanged.connect(self.choose_mode)
        self.style.currentIndexChanged.connect(lambda: window.view.redraw())
        self.scale.valueChanged.connect(self.change_scale)
        self.member.currentIndexChanged.connect(self.choose_member)
        self.distance.valueChanged.connect(self.change_distance)
        self.side.currentIndexChanged.connect(lambda: window.view.redraw())

    def choose_mode(self):
        key = self.mode.currentData()
        self.kind = None if key in (None, "model", "deformation") else key
        self.window.deformed_action.setChecked(key == "deformation")
        if self.spatial:
            control = self.window.view.diagram
            control.blockSignals(True)
            control.setCurrentIndex(max(0, control.findData(self.kind)))
            control.blockSignals(False)
        self.window.view.redraw()

    @property
    def spatial(self):
        return getattr(self.window.project, "dimension", "2D") == "3D"

    def change_scale(self):
        if self.spatial:
            control = self.window.view.diagram_scale
            control.blockSignals(True)
            control.setValue(self.scale.value())
            control.blockSignals(False)
        self.window.view.redraw()

    def choose_member(self):
        name = self.member.currentData()
        self.inspected, self.station = name, 0.
        if name is not None:
            self.window.select(("members", name))
        else:
            self.window.select(None)

    def change_distance(self):
        self.station = self.window.project.units.from_display(self.distance.value(), "length")
        self.window.view.redraw()

    def inspect_at(self, name, point, redraw=True):
        if self.window.result is None or name not in self.window.project.members:
            return
        p, m = self.window.project, self.window.project.members[name]
        a, b = (np.array(p.nodes[n].coords if self.spatial else (p.nodes[n].x, p.nodes[n].y)) for n in (m.start, m.end))
        delta = b-a
        self.inspected = name
        self.station = float(np.clip(np.dot(np.array(point)-a, delta)/np.linalg.norm(delta), 0., np.linalg.norm(delta)))
        if redraw:
            self.window.view.redraw()

    def sync(self):
        w, p, r = self.window, self.window.project, self.window.result
        dimension = "3D" if self.spatial else "2D"
        if self.solver is not (r.solver if r else None):
            self.solver = r.solver if r else None
            self.cache_key, self.cache, self.bounds = None, None, {}
        if dimension != self.dimension:
            self.dimension, self.kind, self.inspected, self.station = dimension, None, None, 0.
            self.mode.blockSignals(True)
            self.mode.clear()
            self.mode.addItem("Model", "model")
            self.mode.addItem("Deformation", "deformation")
            if self.spatial:
                from .spatial_results import LABELS, QUANTITIES
                choices = zip(LABELS[:6], QUANTITIES[:6])
            else:
                choices = PLANAR
            for label, key in choices:
                self.mode.addItem(label, key)
            self.mode.blockSignals(False)
        if self.spatial:
            self.kind = w.view.diagram.currentData()
            self.scale.blockSignals(True)
            self.scale.setValue(w.view.diagram_scale.value())
            self.scale.blockSignals(False)
        if r is None:
            self.kind, self.inspected = None, None
        selected = next((name for kind, name in w.selections if kind == "members"), None)
        if selected is not None and selected != self.inspected:
            self.inspected, self.station = selected, 0.
        if self.inspected not in p.members:
            self.inspected, self.station = None, 0.
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.kind or ("deformation" if w.deformed_action.isChecked() and r else "model"))))
        self.mode.blockSignals(False)
        self.member.blockSignals(True)
        self.member.clear()
        self.member.addItem("Select member…", None)
        for name in p.members:
            self.member.addItem(name, name)
        self.member.setCurrentIndex(max(0, self.member.findData(self.inspected)))
        self.member.blockSignals(False)
        self.mode.setEnabled(r is not None)
        self.style.setEnabled(r is not None and self.kind is not None)
        self.scale.setEnabled(r is not None and self.kind is not None and self.style.currentData() == "offset")
        self.member.setEnabled(r is not None and bool(p.members))
        self.distance.setEnabled(r is not None and self.inspected is not None)
        self.side.setEnabled(self.distance.isEnabled())
        self.update_probe()
        if r is None:
            self.legend.setText("Run analysis to show canvas results.")
        elif self.kind is None:
            self.legend.setText("Deformation uses the toolbar's amplification controls." if w.deformed_action.isChecked() else "Model view | Choose a solved result above. Numerical probes use local member axes; N positive compression.")

    def data(self):
        key = (self.window.result.combination, self.kind)
        if key != self.cache_key:
            self.cache = member_samples(self.window.project, self.window.result, self.kind)
            self.cache_key = key
        return self.cache

    def colour_bound(self):
        if self.kind not in self.bounds:
            p, r = self.window.project, self.window.result
            bound = 0.
            for name in r.solver.load_combos:
                for _, values in member_samples(p, r.for_combination(name), self.kind).values():
                    bound = max(bound, float(np.abs(values).max()))
            self.bounds[self.kind] = bound
        return self.bounds[self.kind]

    def set_legend(self, low, high, unit, label):
        p = self.window.project
        quantity = "moment" if self.kind in ("moment", "moment_y", "moment_z", "torque") else "force"
        low, high = (p.units.to_display(v, quantity) for v in (low, high))
        text = f"{label} ({unit}) | {self.window.result.combination} | Sampled range {low:.5g} to {high:.5g} | Local solver signs; N positive compression."
        if self.style.currentData() == "colour":
            bound = p.units.to_display(self.colour_bound(), quantity)
            text += f" Shared colour scale (all analyzed combinations): −{bound:.5g} / 0 / +{bound:.5g}. Negative blue/dashed; zero grey/dotted; positive orange/solid."
        else:
            text += " Offset toward +local y (or the chosen 3D local axis)."
        self.legend.setText(text)

    def update_probe(self):
        self.probe = None
        p, r, name = self.window.project, self.window.result, self.inspected
        if r is None or name is None:
            self.values.setText("Select a member to inspect its undeformed length.")
            return
        from .diagrams import member_breaks, member_values
        keys, dimensions = ("N", "Fy", "Mz", "dy"), ("force", "force", "moment", "length")
        if self.spatial:
            from .spatial_results import member_breaks as spatial_breaks, inspect_member, LABELS, UNITS
            length = spatial_breaks(p, name, r)[0]
            reader, keys, dimensions = inspect_member, LABELS, UNITS
        else:
            length = member_breaks(p, name)[0]
            reader = member_values
        self.station = min(length, max(0., self.station))
        self.distance.blockSignals(True)
        self.distance.setRange(0., p.units.to_display(length, "length"))
        self.distance.setSuffix(f" {p.units.length}")
        self.distance.setValue(p.units.to_display(self.station, "length"))
        self.distance.blockSignals(False)
        values = reader(p, r, name, self.station, self.side.currentData())
        text = " | ".join(f"{key} {p.units.to_display(value, quantity):.6g} {getattr(p.units, quantity)}" for key, quantity, value in zip(keys, dimensions, values))
        self.values.setText(f"{name} @ {p.units.to_display(self.station, 'length'):.6g} {p.units.length} ({self.side.currentData()}) | {text}")
        m = p.members[name]
        a, b = (np.array(p.nodes[n].coords if self.spatial else (p.nodes[n].x, p.nodes[n].y)) for n in (m.start, m.end))
        index = (("axial", "shear_y", "shear_z", "torque", "moment_y", "moment_z", "dy", "dz") if self.spatial else ("axial", "shear", "moment", "deflection")).index(self.kind) if self.kind else 0
        value, quantity = values[index], dimensions[index]
        label = f"{name} @ {p.units.to_display(self.station, 'length'):.5g} {p.units.length} ({self.side.currentData()}) | {keys[index]} {p.units.to_display(value, quantity):.5g} {getattr(p.units, quantity)}"
        self.probe = {"position": (a+(b-a)*self.station/length).tolist(), "label": label}

    def draw_planar(self, view):
        self.sync()
        p, r = self.window.project, self.window.result
        if r is not None and self.kind is not None:
            rows = self.data()
            peak = max((float(np.abs(v).max()) for _, v in rows.values()), default=0.)
            extent = max((float(np.ptp(np.array([(n.x, n.y) for n in p.nodes.values()]), axis=0).max())), 1.)
            factor = .15*extent*self.scale.value()/peak if peak else 0.
            colour = self.style.currentData() == "colour"
            bound = self.colour_bound() if colour else 0.
            for name, (points, values) in rows.items():
                if colour:
                    for a, b, value in signed_spans(points, values):
                        pen = QPen(signed_color(value, bound), 5)
                        pen.setCosmetic(True)
                        pen.setStyle(Qt.PenStyle.DashLine if value < 0 else Qt.PenStyle.DotLine if value == 0 else Qt.PenStyle.SolidLine)
                        item = view.scene().addLine(a[0], -a[1], b[0], -b[1], pen)
                        item.setData(0, ("canvas_result", self.kind))
                        item.setToolTip(f"{name}: signed span colour; use exact station probe for values")
                else:
                    normal = r.solver.members[name].T()[1, :2]
                    offset = points+values[:, None]*factor*normal
                    path = QPainterPath(QPointF(*offset[0]*np.array([1., -1.])))
                    for point in offset[1:]:
                        path.lineTo(point[0], -point[1])
                    for index in (0, -1):
                        path.moveTo(points[index][0], -points[index][1])
                        path.lineTo(offset[index][0], -offset[index][1])
                    pen = QPen(QColor(colors()[self.kind]), 2)
                    pen.setCosmetic(True)
                    item = view.scene().addPath(path, pen)
                    item.setData(0, ("canvas_result", self.kind))
                    item.setToolTip(f"{name}: +local y offset; sampled {self.kind}")
            all_values = np.concatenate([v for _, v in rows.values()]) if rows else np.array([0.])
            self.set_legend(float(all_values.min()), float(all_values.max()), p.units.moment if self.kind == "moment" else p.units.force, dict((key, label) for label, key in PLANAR)[self.kind])
        if self.probe is not None:
            x, y = self.probe["position"]
            item = view.scene().addEllipse(-5, -5, 10, 10, QPen(QColor(colors()["accent"]), 2), QColor(colors()["canvas"]))
            item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations)
            item.setPos(x, -y)
            item.setToolTip(self.probe["label"])
