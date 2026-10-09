"""Previewed, explicit construction connections using load-preserving splits."""
from dataclasses import dataclass
import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QGraphicsScene,
                             QGraphicsView, QLabel, QVBoxLayout)
from .theme import colors


TOLERANCE = 1e-8


def coordinates(project, node):
    value = project.nodes[node]
    return value.coords if getattr(project, "dimension", "2D") == "3D" else (value.x, value.y)


@dataclass
class ConnectionPlan:
    definition: object
    connector: str
    splits: dict
    endpoints: tuple


def plan_connection(project, operation, selections):
    """Build a validated candidate without mutating the source project."""
    project.validate()
    identities = list(dict.fromkeys(tuple(selection) for selection in selections))
    if any(kind not in ("nodes", "members") or name not in getattr(project, kind) for kind, name in identities):
        raise ValueError("Select only the nodes/members required by this connection.")
    members = [name for kind, name in identities if kind == "members"]
    nodes = [name for kind, name in identities if kind == "nodes"]
    targets = []
    if operation == "perpendicular":
        if len(members) != 1 or len(nodes) != 1:
            raise ValueError("Select exactly one node and one member for a perpendicular connection.")
        member = project.members[members[0]]
        a, b, point = (coordinates(project, name) for name in (member.start, member.end, nodes[0]))
        delta = tuple(end-start for start, end in zip(a, b))
        length = math.dist(a, b)
        fraction = math.fsum((value-start)*direction for value, start, direction in zip(point, a, delta)) / length**2
        if not -TOLERANCE/length <= fraction <= 1+TOLERANCE/length:
            raise ValueError("The perpendicular foot lies outside the selected member. Choose another member or change the geometry.")
        fraction = 0. if fraction*length <= TOLERANCE else 1. if (1-fraction)*length <= TOLERANCE else fraction
        foot = tuple(start+fraction*direction for start, direction in zip(a, delta))
        endpoints = (point, foot)
        targets.append((members[0], fraction))
    elif operation == "midpoints":
        if len(members) != 2 or nodes:
            raise ValueError("Select exactly two members for a midpoint connection.")
        endpoints = tuple(tuple((start+end)/2 for start, end in zip(
            coordinates(project, project.members[name].start), coordinates(project, project.members[name].end)))
                          for name in members)
        targets.extend((name, .5) for name in members)
    else:
        raise ValueError("Unknown construction connection.")
    if math.dist(*endpoints) <= TOLERANCE:
        raise ValueError("The connection endpoints coincide. Use Connect Intersections to create a shared joint instead.")
    candidate = project.clone()
    splits = {}
    for name, fraction in targets:
        splits[name] = candidate._split_member(name, [fraction]) if 0 < fraction < 1 else [name]
    connector = candidate.add_member(*endpoints)
    candidate.validate()
    connection = candidate.members[connector]
    # Reject overlaps and unintended connections on the new connector. The
    # operation only splits the selected members, never unrelated geometry.
    for name in candidate.members:
        if name == connector:
            continue
        intersection = candidate.member_intersection(connector, name)
        if intersection and any(0 < value < 1 for value in intersection):
            raise ValueError(f"The new connection crosses or meets {name} without a shared endpoint. Split/connect that geometry explicitly first.")
    for name in candidate.nodes:
        if name not in (connection.start, connection.end):
            fraction = candidate.member_position(connector, *coordinates(candidate, name))
            if fraction is not None and 0 < fraction < 1:
                raise ValueError(f"Node {name} lies inside the new connection. Split/connect that geometry explicitly first.")
    endpoints = tuple(coordinates(candidate, name) for name in (connection.start, connection.end))
    return ConnectionPlan(candidate, connector, splits, endpoints)


class ConnectionPreview(QDialog):
    def __init__(self, parent, original, plan, title):
        super().__init__(parent)
        self.original, self.plan = original.clone(), plan
        self.setWindowTitle(title)
        self.resize(700, 560)
        layout = QVBoxLayout(self)
        model = plan.definition
        connector = model.members[plan.connector]
        units = original.units
        additions = len(model.nodes)-len(original.nodes)
        split_count = sum(len(values)-1 for values in plan.splits.values())
        summary = QLabel(f"Add {plan.connector}: frame | {connector.material} | {connector.section}"
                         f"\n{additions} new node(s), {split_count} split(s), 1 connecting member"
                         f"\nLength {units.to_display(math.dist(*plan.endpoints), 'length'):.6g} {units.length}")
        summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.setWordWrap(True)
        layout.addWidget(summary)
        points = " → ".join("("+", ".join(f"{units.to_display(value, 'length'):.6g}" for value in point)+")" for point in plan.endpoints)
        coordinates_label = QLabel(f"{'XYZ' if len(plan.endpoints[0]) == 3 else 'XY'} endpoints ({units.length}): {points}")
        coordinates_label.setTextFormat(Qt.TextFormat.PlainText)
        coordinates_label.setWordWrap(True)
        layout.addWidget(coordinates_label)
        self.projection = QComboBox()
        self.projection.addItems(["Isometric schematic", "XY", "XZ", "YZ"] if len(plan.endpoints[0]) == 3 else ["XY"])
        self.projection.currentTextChanged.connect(self.draw_preview)
        layout.addWidget(self.projection)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_preview)
        layout.addWidget(self.view)
        note = QLabel("Solid: existing geometry. Dashed: new connection. Markers: connection endpoints."
                      "\nSplits retain original assignments, releases and loads; existing joints keep their supports."
                      " The new frame uses project defaults, with no releases or manual loads (3D roll: 0°)."
                      " Enabled self-weight includes its added length. Apply changes stiffness; analyze again.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.draw_preview()

    def projected(self, point):
        if len(point) == 2:
            return point[0], -point[1]
        x, y, z = point
        return {"XY": (x, -y), "XZ": (x, -z), "YZ": (z, -y)}.get(
            self.projection.currentText(), ((x-z)/math.sqrt(2), (x+z-2*y)/math.sqrt(6)))

    def draw_preview(self):
        if not hasattr(self, "scene"):
            return
        self.scene.clear()
        c = colors()
        self.view.setBackgroundBrush(QColor(c["canvas"]))
        base = QPen(QColor(c["muted"]), 2)
        base.setCosmetic(True)
        for member in self.original.members.values():
            a, b = (self.projected(coordinates(self.original, name)) for name in (member.start, member.end))
            self.scene.addLine(*a, *b, base)
        pen = QPen(QColor(c["accent"]), 3, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        a, b = (self.projected(point) for point in self.plan.endpoints)
        self.scene.addLine(*a, *b, pen)
        member = self.plan.definition.members[self.plan.connector]
        for name, position in zip((member.start, member.end), (a, b)):
            item = self.scene.addEllipse(-4, -4, 8, 8, base, QColor(c["accent"]))
            item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations)
            item.setPos(*position)
            label = self.scene.addSimpleText(name)
            label.setBrush(QColor(c["text"]))
            label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations)
            label.setPos(*position)
        self.fit_preview()
        self.fit_timer.start(0)

    def fit_preview(self):
        rect = self.scene.itemsBoundingRect()
        margin = max(rect.width(), rect.height(), 1)*.12
        rect = rect.adjusted(-margin, -margin, margin, margin)
        self.view.setSceneRect(rect)
        self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "fit_timer"):
            self.fit_timer.start(0)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_timer.start(0)
