"""Qt desktop editor for planar and spatial PyNite frames."""
import math
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QThread, QTimer, QStandardPaths, QSettings
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPainterPath, QPen, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView,
    QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QToolButton,
    QRubberBand, QScrollArea, QStyle, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QStackedWidget,
)

from .analysis_jobs import AnalysisWorker, CANCELLED
from .annotations import combination_loads, load_label as annotation_load_label, support_label, support_geometry, spring_geometry, release_geometry, moment_geometry
from .model import Load, Project
from .units import UNIT_SYSTEMS
from .theme import colors, configure_theme, theme_name


def number(value, minimum=-1e9, maximum=1e9, decimals=4):
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


def unit_number(value, units, quantity, minimum=-1e9, maximum=1e9, decimals=6):
    widget = number(units.to_display(value, quantity), units.to_display(minimum, quantity),
                    units.to_display(maximum, quantity), decimals)
    widget.setProperty("quantity", quantity)
    widget.setProperty("original_value", value)
    widget.setProperty("initial_value", widget.value())
    return widget


def unit_value(widget, units, quantity=None):
    quantity = quantity or widget.property("quantity")
    if quantity == widget.property("quantity") and widget.value() == widget.property("initial_value"):
        return widget.property("original_value")
    return units.from_display(widget.value(), quantity)


def load_directions(is_member, kind):
    choices = ["FY", "FX", "Angle"] if kind == "distributed" else ["FY", "FX", "MZ", "Angle"]
    return choices + (["Local x", "Local y", "Local angle"] if is_member else [])


def component_preview(project, load):
    units = project.units
    quantity = "intensity" if load.kind == "distributed" else "force"
    start, end = dict(load.components(project)), dict(load.components(project, load.end_magnitude))
    lines = []
    for direction in ("FX", "FY"):
        value = f"{units.to_display(start.get(direction, 0), quantity):.6g}"
        if load.kind == "distributed":
            value += f" to {units.to_display(end.get(direction, 0), quantity):.6g}"
        lines.append(f"{direction} {value} {getattr(units, quantity)}")
    return "\n".join(lines)


def load_symbol(project, load, magnitude):
    if load.direction == "Angle" or load.direction.startswith("Local"):
        return "Angle", magnitude, load.resolved_angle(project)
    return load.direction, magnitude


def deformation_paths(project, result):
    paths = []
    for member in project.members.values():
        a, b = project.nodes[member.start], project.nodes[member.end]
        length = math.hypot(b.x - a.x, b.y - a.y)
        solver_member = result.solver.members[member.name]
        axes = solver_member.T()[:3, :3]
        points = []
        for index in range(41):
            t = index / 40
            dx = solver_member.deflection("dx", t * length, result.combination)
            dy = solver_member.deflection("dy", t * length, result.combination)
            ux = axes[0, 0] * dx + axes[1, 0] * dy
            uy = axes[0, 1] * dx + axes[1, 1] * dy
            points.append((a.x + t * (b.x - a.x), a.y + t * (b.y - a.y), ux, uy))
        paths.append(points)
    return paths


class Edit(QUndoCommand):
    def __init__(self, window, title, before, after):
        super().__init__(title)
        self.window, self.before, self.after = window, before, after

    def redo(self):
        self.window.replace_project(self.after)

    def undo(self):
        self.window.replace_project(self.before)


class EngineeringSymbol(QGraphicsItem):
    def __init__(self, kind, value=None, length=38, highlighted=False):
        super().__init__()
        self.kind, self.value, self.length = kind, value, length
        self.highlighted = highlighted
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(2)

    def boundingRect(self):
        return QRectF(-46, -46, 92, 92)

    def paint(self, painter, option, widget=None):
        c = colors()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(c["accent"] if self.highlighted else c["support"] if self.kind in ("support", "spring") else c["load"]), 1.8))
        if self.kind == "hinge":
            painter.setPen(QPen(QColor(c["highlight"] if theme_name() == "light" else c["accent"]), 1.8))
            painter.setBrush(QColor(c["canvas"]))
            dx, dy = self.value
            painter.drawEllipse(QPointF(dx * 9, dy * 9), 4, 4)
            return
        if self.kind in ("support", "spring", "release"):
            if self.kind == "support":
                support = self.value[0] if isinstance(self.value, tuple) else self.value
                geometry = support_geometry(support, self.value[1:] if isinstance(self.value, tuple) else ())
            elif self.kind == "spring":
                geometry = spring_geometry(self.value)
            else:
                painter.setPen(QPen(QColor(c["accent"]), 1.8))
                geometry = release_geometry(self.value[:2], *self.value[2:])
            paths, circles = geometry
            for path in paths:
                for start, end in zip(path, path[1:]):
                    painter.drawLine(QPointF(*start), QPointF(*end))
            for x, y, radius in circles:
                painter.drawEllipse(QPointF(x, y), radius, radius)
        else:
            direction, magnitude = self.value[:2]
            sign = 1 if magnitude >= 0 else -1
            if direction == "MZ":
                for path in moment_geometry(magnitude)[0]:
                    for start, end in zip(path, path[1:]):
                        painter.drawLine(QPointF(*start), QPointF(*end))
                return
            dx, dy = (sign, 0) if direction == "FX" else (0, -sign)
            if direction == "Angle":
                angle = math.radians(self.value[2])
                dx, dy = sign * math.cos(angle), -sign * math.sin(angle)
            head = min(9, self.length * 0.5)
            width = head * 4 / 9
            painter.drawLine(QPointF(-dx * self.length, -dy * self.length), QPointF(0, 0))
            painter.drawLine(QPointF(0, 0), QPointF(-dx * head + dy * width, -dy * head - dx * width))
            painter.drawLine(QPointF(0, 0), QPointF(-dx * head - dy * width, -dy * head + dx * width))


class StructureView(QGraphicsView):
    def __init__(self, window):
        super().__init__(QGraphicsScene(window), window)
        self.window = window
        self.start = None
        self.preview = None
        self.drag_node = None
        self.drag_items = []
        self.box_origin = None
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(colors()["canvas"]))
        self.setSceneRect(-120, -360, 720, 600)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        spacing = self.window.project.grid
        while spacing * abs(self.transform().m11()) < 15:
            spacing *= 2
        painter.setPen(QPen(QColor(colors()["grid"]), 0))
        x = math.floor(rect.left() / spacing) * spacing
        while x <= rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += spacing
        y = math.floor(rect.top() / spacing) * spacing
        while y <= rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += spacing
        painter.setPen(QPen(QColor(colors()["axis"]), 0))
        painter.drawLine(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
        painter.drawLine(QPointF(rect.left(), 0), QPointF(rect.right(), 0))

    def hit(self, point):
        tolerance = 10 / max(abs(self.transform().m11()), 1e-6)
        project = self.window.project
        nodes = [(math.hypot(n.x - point.x(), -n.y - point.y()), name) for name, n in project.nodes.items()]
        if nodes:
            distance, name = min(nodes)
            if distance < tolerance:
                return "nodes", name
        best = (tolerance, None)
        for name, member in project.members.items():
            a, b = project.nodes[member.start], project.nodes[member.end]
            dx, dy = b.x - a.x, b.y - a.y
            t = max(0, min(1, ((point.x() - a.x) * dx + (-point.y() - a.y) * dy) / (dx * dx + dy * dy)))
            distance = math.hypot(point.x() - a.x - t * dx, -point.y() - a.y - t * dy)
            if distance < best[0]:
                best = distance, name
        return ("members", best[1]) if best[1] else None

    def snapped(self, point):
        hit = self.hit(point)
        if hit and hit[0] == "nodes":
            node = self.window.project.nodes[hit[1]]
            return node.x, node.y
        grid = self.window.project.grid
        return round(point.x() / grid) * grid, round(-point.y() / grid) * grid

    def cancel(self):
        self.box_origin = None
        self.rubber_band.hide()
        self.start = None
        self.drag_node = None
        for item in self.drag_items:
            self.scene().removeItem(item)
        self.drag_items.clear()
        if self.preview is not None:
            self.scene().removeItem(self.preview)
            self.preview = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.cancel()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        if self.window.mode == "pan":
            super().mousePressEvent(event)
        elif self.window.mode == "draw":
            xy = self.snapped(point)
            if self.start is None:
                self.start = xy
                self.preview = self.scene().addLine(xy[0], -xy[1], xy[0], -xy[1], QPen(QColor(colors()["accent"]), 0, Qt.PenStyle.DashLine))
            else:
                start = self.start
                self.cancel()
                self.window.edit("Add member", lambda project: project.add_member(start, xy))
        else:
            hit = self.hit(point)
            additive = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            if hit:
                if additive:
                    selections = list(self.window.selections)
                    if hit in selections:
                        selections.remove(hit)
                    else:
                        selections.append(hit)
                    self.window.select_many(selections)
                else:
                    self.window.select(hit)
            if not hit:
                self.box_origin = event.position().toPoint()
                self.box_previous = list(self.window.selections) if additive else []
                self.rubber_band.setGeometry(QRect(self.box_origin, self.box_origin))
                self.rubber_band.show()
            elif hit[0] == "nodes" and not additive:
                self.drag_node = hit[1]
                self.drag_origin = event.position().toPoint()
                self.drag_target = None

    def mouseMoveEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        x, y = self.snapped(point)
        units = self.window.project.units
        self.window.coordinates.setText(f"X {units.to_display(x, 'length'):g} {units.length}   Y {units.to_display(y, 'length'):g} {units.length}")
        if self.box_origin is not None:
            self.rubber_band.setGeometry(QRect(self.box_origin, event.position().toPoint()).normalized())
            return
        if self.preview is not None:
            self.preview.setLine(self.start[0], -self.start[1], x, -y)
        if self.drag_node and (event.position().toPoint() - self.drag_origin).manhattanLength() >= QApplication.startDragDistance():
            self.drag_target = x, y
            for item in self.drag_items:
                self.scene().removeItem(item)
            self.drag_items.clear()
            pen = QPen(QColor(colors()["accent"]), 0, Qt.PenStyle.DashLine)
            for member in self.window.project.members.values():
                if self.drag_node in (member.start, member.end):
                    other = self.window.project.nodes[member.end if member.start == self.drag_node else member.start]
                    self.drag_items.append(self.scene().addLine(other.x, -other.y, x, -y, pen))
            dot = self.scene().addEllipse(-4, -4, 8, 8, QPen(QColor(colors()["accent"])), QColor(colors()["canvas"]))
            dot.setFlag(dot.GraphicsItemFlag.ItemIgnoresTransformations)
            dot.setPos(x, -y)
            self.drag_items.append(dot)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.box_origin is not None:
            rectangle = QRect(self.box_origin, event.position().toPoint()).normalized()
            previous = self.box_previous
            self.cancel()
            if rectangle.width() + rectangle.height() >= QApplication.startDragDistance():
                area = self.mapToScene(rectangle).boundingRect()
                self.window.select_many([*previous, *self.in_rectangle(area)])
            else:
                self.window.select_many(previous)
            return
        if event.button() == Qt.MouseButton.LeftButton and self.drag_node:
            name, target = self.drag_node, self.drag_target
            self.cancel()
            if target is not None:
                def move(project):
                    project.nodes[name].x, project.nodes[name].y = target
                self.window.edit(f"Move {name}", move)
            return
        super().mouseReleaseEvent(event)

    def in_rectangle(self, area):
        project = self.window.project
        selections = [("nodes", name) for name, node in project.nodes.items()
                      if area.contains(QPointF(node.x, -node.y))]
        boundary = QPainterPath()
        boundary.addRect(area)
        for name, member in project.members.items():
            a, b = project.nodes[member.start], project.nodes[member.end]
            start, end = QPointF(a.x, -a.y), QPointF(b.x, -b.y)
            segment = QPainterPath(start)
            segment.lineTo(end)
            if area.contains(start) or area.contains(end) or boundary.intersects(segment):
                selections.append(("members", name))
        return selections

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        scale = abs(self.transform().m11()) * factor
        if 0.02 <= scale <= 100:
            self.scale(factor, factor)

    def fit(self):
        self.cancel()
        rect = self.scene().itemsBoundingRect() if self.window.project.nodes else QRectF(-24, -180, 480, 360)
        rect = rect.adjusted(-48, -48, 48, 48)
        self.setSceneRect(rect.adjusted(-rect.width(), -rect.height(), rect.width(), rect.height()))
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.redraw()

    def label(self, text, x, y, color=None, offset=(7, 7)):
        item = self.scene().addSimpleText(text)
        item.setBrush(QColor(color or colors()["label"]))
        item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations)
        item.setPos(x, -y)
        item.setTransformOriginPoint(0, 0)
        # Offset is in screen units because the item ignores the view transform.
        from PySide6.QtGui import QTransform
        item.setTransform(QTransform.fromTranslate(*offset))
        return item

    def redraw(self):
        self.cancel()
        scene, project = self.scene(), self.window.project
        c = colors()
        units = project.units
        scene.clear()
        selected = set(self.window.selections)
        for name, member in project.members.items():
            a, b = project.nodes[member.start], project.nodes[member.end]
            pen = QPen(QColor(c["accent"] if ("members", name) in selected else c["member"]), 3)
            pen.setCosmetic(True)
            if member.kind == "truss":
                pen.setStyle(Qt.PenStyle.DashLine)
            scene.addLine(a.x, -a.y, b.x, -b.y, pen)
            length = math.hypot(b.x - a.x, b.y - a.y)
            release_start, release_end = member.moment_releases
            for released, node, sign in ((release_start, a, 1), (release_end, b, -1)):
                if released:
                    symbol = EngineeringSymbol("hinge", (sign * (b.x - a.x) / length, -sign * (b.y - a.y) / length))
                    symbol.setToolTip(f"{name}: local RZ moment released")
                    scene.addItem(symbol)
                    symbol.setPos(node.x, -node.y)
            for flags, node, sign in zip(member.end_releases, (a, b), (1, -1)):
                if any(flags[:2]):
                    symbol = EngineeringSymbol("release", (sign * (b.x - a.x) / length, -sign * (b.y - a.y) / length, *flags[:2]))
                    symbol.setToolTip(f"{name}: local " + ", ".join(label for label, released in zip(("DX", "DY", "RZ"), flags) if released) + " released")
                    scene.addItem(symbol)
                    symbol.setPos(node.x, -node.y)
            self.label(name, (a.x + b.x) / 2, (a.y + b.y) / 2, offset=(4, 8))
        for name, node in project.nodes.items():
            color = QColor(c["accent"] if ("nodes", name) in selected else c["member"])
            dot = scene.addEllipse(-4, -4, 8, 8, QPen(QColor(c["base"])), color)
            dot.setFlag(dot.GraphicsItemFlag.ItemIgnoresTransformations)
            dot.setPos(node.x, -node.y)
            self.label(name, node.x, node.y, offset=(-30, -25) if node.spring_rz else (8, -22))
            if any(node.restraints):
                symbol = EngineeringSymbol("support", ("custom", *node.restraints) if node.support == "custom" else node.support)
                symbol.setToolTip(support_label(project, node))
                scene.addItem(symbol)
                symbol.setPos(node.x, -node.y)
            if any(node.springs):
                symbol = EngineeringSymbol("spring", node.springs)
                symbol.setToolTip(support_label(project, node))
                scene.addItem(symbol)
                symbol.setPos(node.x, -node.y)
        occupied = [item.deviceTransform(self.viewportTransform()).mapRect(item.boundingRect())
                    for item in scene.items() if isinstance(item, QGraphicsSimpleTextItem)]
        def load_label(text, x, y, highlighted=False):
            from PySide6.QtGui import QTransform
            item = self.label(text, x, y, c["accent"] if highlighted else c["load"], (8, -52))
            offset = -52
            obstacles = occupied + [symbol.deviceTransform(self.viewportTransform()).mapRect(symbol.boundingRect())
                                    for symbol in scene.items() if isinstance(symbol, EngineeringSymbol) and symbol.kind == "load"]
            while True:
                rect = item.deviceTransform(self.viewportTransform()).mapRect(item.boundingRect()).adjusted(-2, -2, 2, 2)
                if not any(rect.intersects(previous) for previous in obstacles):
                    occupied.append(rect)
                    break
                offset -= item.boundingRect().height() + 4
                item.setTransform(QTransform.fromTranslate(8, offset))
        loads = combination_loads(project, self.window.result) if self.window.result is not None else (*project.loads.values(), *project.self_weight_loads())
        for definition in loads:
            if not self.window.load_visible(definition):
                continue
            load = definition
            highlighted = definition.name in project.loads and ("loads", definition.name) in selected
            if load.target in project.nodes:
                node = project.nodes[load.target]
                x, y = node.x, node.y
            else:
                member = project.members[load.target]
                a, b = project.nodes[member.start], project.nodes[member.end]
                x, y = a.x + (b.x - a.x) * load.position, a.y + (b.y - a.y) * load.position
            if load.kind == "distributed":
                maximum = max(abs(load.magnitude), abs(load.end_magnitude), 1e-12)
                for index in range(9):
                    ratio = index / 8
                    fraction = load.position + ratio * (load.end_position - load.position)
                    intensity = load.magnitude + ratio * (load.end_magnitude - load.magnitude)
                    if abs(intensity) < maximum * 1e-8:
                        continue
                    symbol = EngineeringSymbol("load", load_symbol(project, load, intensity), 38 * abs(intensity) / maximum, highlighted=highlighted)
                    scene.addItem(symbol)
                    symbol.setPos(a.x + (b.x - a.x) * fraction, -a.y - (b.y - a.y) * fraction)
                midpoint = (load.position + load.end_position) / 2
                x, y = a.x + (b.x - a.x) * midpoint, a.y + (b.y - a.y) * midpoint
                load_label(annotation_load_label(project, load), x, y, highlighted)
                continue
            symbol = EngineeringSymbol("load", load_symbol(project, load, load.magnitude), highlighted=highlighted)
            scene.addItem(symbol)
            symbol.setPos(x, -y)
            load_label(annotation_load_label(project, load), x, y, highlighted)
        visible = bool(self.window.result and self.window.deformed_action.isChecked())
        self.window.deformation_mode.setEnabled(visible)
        self.window.deformation_scale.setEnabled(visible and self.window.deformation_mode.currentData() == "custom")
        self.window.deformation_scale_action.setVisible(self.window.deformation_mode.currentData() == "custom")
        self.window.deformation_peak.setVisible(visible)
        if visible:
            paths = deformation_paths(project, self.window.result)
            peak = max((math.hypot(ux, uy) for path in paths for _, _, ux, uy in path), default=0)
            mode = self.window.deformation_mode.currentData()
            scale = self.window.deformation_scale.value()
            if mode == "auto":
                xs = [node.x for node in project.nodes.values()]
                ys = [node.y for node in project.nodes.values()]
                span = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) if xs else 0
                scale = 0.15 * span / peak if peak > 1e-12 else 1.0
            elif mode == "true":
                scale = 1.0
            self.window.deformation_peak.setText(f"Factor {scale:.6g}x | Max {units.to_display(peak, 'length'):.6g} {units.length}")
            pen = QPen(QColor(c["load"]), 2)
            pen.setCosmetic(True)
            for path in paths:
                previous = None
                for x, y, ux, uy in path:
                    point = QPointF(x + scale * ux, -(y + scale * uy))
                    if previous is not None:
                        scene.addLine(previous.x(), previous.y(), point.x(), point.y(), pen)
                    previous = point


class MainWindow(QMainWindow):
    def __init__(self, recovery_directory=None, settings=None):
        super().__init__()
        self.settings_store = settings
        if settings is not None:
            configure_theme(QApplication.instance(), settings.value("theme", "light"))
        self.recovery = None
        self.recovery_error = None
        self.last_autosave = None
        if recovery_directory is not None:
            from .recovery import RecoveryStore
            try:
                self.recovery = RecoveryStore(recovery_directory)
            except OSError as error:
                self.recovery_error = str(error)
        self.project = Project()
        self.saved = self.project.to_dict()
        self.path = None
        self.selected = None
        self.mode = "select"
        self.result = None
        self.revision = 0
        self.thread = None
        self.worker = None
        self.analysis_cancel_requested = False
        self.close_after_analysis = False
        self.undo = QUndoStack(self)
        self.resize(1280, 820)
        self.setMinimumSize(820, 560)
        self.planar_view = StructureView(self)
        self.spatial_view = None
        self.view = self.planar_view
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.planar_view)
        self.setCentralWidget(self.view_stack)
        self.build_actions()
        self.build_panels()
        self.analysis_phase = QLabel()
        self.analysis_phase.setMaximumWidth(300)
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setRange(0, 0)
        self.analysis_progress.setFixedWidth(100)
        self.analysis_cancel_button = QToolButton()
        self.analysis_cancel_button.setDefaultAction(self.cancel_analysis_action)
        for widget in (self.analysis_phase, self.analysis_progress, self.analysis_cancel_button):
            self.statusBar().addPermanentWidget(widget)
            widget.hide()
        self.coordinates = QLabel()
        self.statusBar().addPermanentWidget(self.coordinates)
        self.unit_selector = QComboBox()
        self.unit_selector.setToolTip("Project display and input units")
        for key, units in UNIT_SYSTEMS.items():
            self.unit_selector.addItem(units.label, key)
        self.unit_selector.currentIndexChanged.connect(lambda: self.set_units(self.unit_selector.currentData()))
        self.statusBar().addPermanentWidget(self.unit_selector)
        self.statusBar().showMessage(f"Ready | 2D frame | {self.project.units.summary}")
        self.undo.indexChanged.connect(self.update_title)
        self.refresh()
        self.view.fit()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30000)
        self.autosave_timer.timeout.connect(self.autosave_now)
        if self.recovery is not None:
            self.autosave_timer.start()
        elif self.recovery_error:
            QMessageBox.warning(self, "Autosave Unavailable", "The recovery directory could not be opened. Autosave is disabled for this session.\n\n" + self.recovery_error)

    def action(self, text, callback, shortcut=None, icon=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
        if icon:
            fallback = {
                "document-new": QStyle.StandardPixmap.SP_FileIcon,
                "document-open": QStyle.StandardPixmap.SP_DialogOpenButton,
                "document-save": QStyle.StandardPixmap.SP_DialogSaveButton,
                "edit-delete": QStyle.StandardPixmap.SP_TrashIcon,
                "zoom-fit-best": QStyle.StandardPixmap.SP_TitleBarMaxButton,
                "media-playback-start": QStyle.StandardPixmap.SP_MediaPlay,
                "media-playback-stop": QStyle.StandardPixmap.SP_MediaStop,
            }
            action.setProperty("standard_pixmap", fallback[icon].value)
            action.setIcon(self.standard_icon(fallback[icon]))
        action.triggered.connect(callback)
        return action

    def standard_icon(self, standard):
        icon = self.style().standardIcon(standard)
        if theme_name() == "dark" and standard in (QStyle.StandardPixmap.SP_MediaPlay, QStyle.StandardPixmap.SP_MediaStop, QStyle.StandardPixmap.SP_TitleBarMaxButton):
            pixmap = icon.pixmap(24, 24)
            painter = QPainter(pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), QColor(colors()["text"]))
            painter.end()
            icon = QIcon(pixmap)
        return icon

    def set_theme(self, name):
        configure_theme(QApplication.instance(), name)
        if self.settings_store is not None:
            self.settings_store.setValue("theme", theme_name())

    def set_graphics_mode(self, name):
        from .graphics import graphics_mode
        name = graphics_mode(name)
        if self.settings_store is not None:
            self.settings_store.setValue("graphics", name)
        for key, action in self.graphics_actions.items():
            action.setChecked(key == name)
        QMessageBox.information(self, "3D Rendering", "Rendering changes take effect after restarting PyniteGUI. Save your project before closing.\n\n"
                                + ("Software mode uses CPU compositing and requests a software graphics backend. Qt may choose a platform-specific WebGL driver." if name == "software" else "Automatic mode uses the default graphics backend."))

    def apply_theme(self):
        if not hasattr(self, "theme_actions"):
            return
        for key, action in self.theme_actions.items():
            action.setChecked(key == theme_name())
        for action in self.findChildren(QAction):
            standard = action.property("standard_pixmap")
            if standard is not None:
                action.setIcon(self.standard_icon(QStyle.StandardPixmap(standard)))
        self.view.setBackgroundBrush(QColor(colors()["canvas"]))
        self.view.redraw()
        self.view.viewport().update()

    def build_actions(self):
        file_menu = self.menuBar().addMenu("&File")
        self.new_action = self.action("New", self.new_project, "Ctrl+N", "document-new")
        self.open_action = self.action("Open...", self.open_project, "Ctrl+O", "document-open")
        self.save_action = self.action("Save", self.save_project, "Ctrl+S", "document-save")
        for action in (self.new_action, self.open_action, self.save_action):
            file_menu.addAction(action)
        file_menu.addAction(self.action("New 3D Frame", self.new_spatial_project))
        file_menu.addAction(self.action("Save As...", lambda: self.save_project(True), "Ctrl+Shift+S"))
        from .reports import ResultExportMenu
        self.export_menu = ResultExportMenu(self, lambda: (self.project, self.result, str(self.path or "Untitled")))
        self.export_menu.setEnabled(False)
        file_menu.addMenu(self.export_menu)
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self.update_recent_menu()
        if self.recovery is not None:
            file_menu.addAction(self.action("Recover Autosave...", self.offer_recovery))
        file_menu.addSeparator()
        from .examples import EXAMPLES
        self.examples_menu = file_menu.addMenu("Examples")
        for key, label in EXAMPLES.items():
            self.examples_menu.addAction(self.action(label, lambda checked=False, key=key: self.example(key)))
        file_menu.addSeparator()
        file_menu.addAction(self.action("Exit", self.close, "Ctrl+Q"))
        edit_menu = self.menuBar().addMenu("&Edit")
        undo = self.undo.createUndoAction(self, "Undo")
        undo.setShortcut("Ctrl+Z")
        redo = self.undo.createRedoAction(self, "Redo")
        redo.setShortcuts(["Ctrl+Shift+Z", "Ctrl+Y"])
        edit_menu.addActions([undo, redo])
        edit_menu.addAction(self.action("Delete Selection", self.delete_selected, "Delete", "edit-delete"))
        edit_menu.addAction(self.action("Select All", self.select_all, "Ctrl+A"))
        edit_menu.addAction(self.action("Model Tables...", self.manage_model_tables))
        edit_menu.addAction(self.action("Materials...", self.manage_materials))
        edit_menu.addAction(self.action("Sections...", self.manage_sections))
        edit_menu.addAction(self.action("Load Cases and Combinations...", self.manage_load_cases))
        edit_menu.addAction(self.action("Self-Weight...", self.manage_self_weight))
        edit_menu.addAction(self.action("Grid...", self.settings))
        edit_menu.addAction(self.action("Units...", self.choose_units))
        edit_menu.addSeparator()
        edit_menu.addAction(self.action("Split Selected Member...", self.split_selected_member))
        edit_menu.addAction(self.action("Connect Intersections", self.connect_intersections))
        edit_menu.addAction(self.action("Check Model", self.check_model))
        toolbar = self.addToolBar("Model")
        toolbar.setMovable(False)
        toolbar.addActions([self.new_action, self.open_action, self.save_action])
        toolbar.addSeparator()
        self.mode_group = QActionGroup(self)
        self.mode_actions = {}
        for mode, text, shortcut in (("select", "Select", "V"), ("draw", "Member", "M"), ("pan", "Pan", "P")):
            action = self.action(text, lambda checked=False, mode=mode: self.set_mode(mode), shortcut)
            action.setCheckable(True)
            action.setChecked(mode == "select")
            self.mode_group.addAction(action)
            self.mode_actions[mode] = action
            toolbar.addAction(action)
        self.addAction(self.action("Cancel", lambda: self.set_mode("select"), "Escape"))
        toolbar.addAction(self.action("Fit", lambda: self.view.fit(), "F", "zoom-fit-best"))
        toolbar.addSeparator()
        toolbar.addAction(self.action("Load...", self.add_load, "L"))
        toolbar.addAction(self.action("Support...", self.assign_support))
        toolbar.addSeparator()
        self.analyze_action = self.action("Analyze", self.run_analysis, "F5", "media-playback-start")
        toolbar.addAction(self.analyze_action)
        self.cancel_analysis_action = self.action("Cancel Analysis", self.cancel_analysis, icon="media-playback-stop")
        self.cancel_analysis_action.setEnabled(False)
        toolbar.addAction(self.action("Diagrams...", self.diagrams))
        self.addToolBarBreak()
        deformation_toolbar = self.addToolBar("Deformation")
        deformation_toolbar.setMovable(False)
        self.deformed_action = self.action("Deformed", lambda: self.view.redraw())
        self.deformed_action.setCheckable(True)
        self.deformed_action.setEnabled(False)
        deformation_toolbar.addAction(self.deformed_action)
        self.deformation_mode = QComboBox()
        for label, key in (("Auto", "auto"), ("True Scale", "true"), ("Custom", "custom")):
            self.deformation_mode.addItem(label, key)
        self.deformation_mode.setToolTip("Auto: fit displacement to 15% of model extent; True Scale: 1x; Custom: chosen factor")
        self.deformation_mode.currentIndexChanged.connect(lambda: self.view.redraw())
        deformation_toolbar.addWidget(self.deformation_mode)
        self.deformation_scale = number(100, 0.001, 1e9, 3)
        self.deformation_scale.setSuffix("x")
        self.deformation_scale.setToolTip("Custom displacement amplification factor")
        self.deformation_scale.setFixedWidth(140)
        self.deformation_scale.valueChanged.connect(lambda: self.view.redraw())
        self.deformation_scale_action = deformation_toolbar.addWidget(self.deformation_scale)
        self.deformation_peak = QLabel()
        self.deformation_peak.setMargin(6)
        self.deformation_peak.setToolTip("Actual maximum displacement magnitude sampled at 41 positions per member; not amplified")
        deformation_toolbar.addWidget(self.deformation_peak)

    def dock(self, title, widget, area):
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.addDockWidget(area, dock)
        self.menuBar_view.addAction(dock.toggleViewAction())
        return dock

    def build_panels(self):
        self.menuBar_view = self.menuBar().addMenu("&View")
        appearance = self.menuBar_view.addMenu("Appearance")
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        for key, label in (("light", "Light"), ("dark", "Dark")):
            action = self.action(label, lambda checked=False, key=key: self.set_theme(key))
            action.setCheckable(True)
            action.setChecked(key == theme_name())
            self.theme_group.addAction(action)
            self.theme_actions[key] = action
            appearance.addAction(action)
        self.menuBar_view.addSeparator()
        rendering = self.menuBar_view.addMenu("3D Rendering")
        self.graphics_group = QActionGroup(self)
        self.graphics_actions = {}
        from .graphics import graphics_mode
        saved_graphics = self.settings_store.value("graphics", "auto") if self.settings_store is not None else "auto"
        active_graphics = graphics_mode(QApplication.instance().property("pynitegui_graphics") or saved_graphics)
        for key, label in (("auto", "Automatic (GPU)"), ("software", "Software (CPU Compositing)")):
            action = self.action(label, lambda checked=False, key=key: self.set_graphics_mode(key))
            action.setCheckable(True)
            action.setChecked(key == active_graphics)
            action.setToolTip("Requires application restart")
            self.graphics_group.addAction(action)
            self.graphics_actions[key] = action
            rendering.addAction(action)
        self.menuBar_view.addSeparator()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Model", "Properties"])
        self.tree.setMinimumWidth(210)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self.tree_selection)
        structure_panel = QWidget()
        structure_layout = QVBoxLayout(structure_panel)
        structure_layout.setContentsMargins(0, 0, 0, 0)
        self.load_filter = QComboBox()
        self.load_filter.setToolTip("Visible load cases; analysis always uses all model loads")
        self.load_filter.currentIndexChanged.connect(self.filter_loads)
        structure_layout.addWidget(self.load_filter)
        structure_layout.addWidget(self.tree)
        self.dock("Structure", structure_panel, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.inspector = QWidget()
        self.form = QFormLayout(self.inspector)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.inspector.setMinimumWidth(240)
        self.inspector_scroll = QScrollArea()
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.inspector_scroll.setMinimumWidth(260)
        self.inspector_scroll.setWidget(self.inspector)
        self.dock("Properties", self.inspector_scroll, Qt.DockWidgetArea.RightDockWidgetArea)
        self.results_table = QTableWidget(0, 7)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setMinimumHeight(120)
        results_panel = QWidget()
        results_layout = QVBoxLayout(results_panel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        self.result_combination = QComboBox()
        self.result_combination.setToolTip("Results combination")
        self.result_combination.setEnabled(False)
        self.result_combination.currentTextChanged.connect(self.select_result_combination)
        results_layout.addWidget(self.result_combination)
        results_layout.addWidget(self.results_table)
        self.results_dock = self.dock("Results", results_panel, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.results_dock.hide()

    def update_title(self):
        dirty = self.project.to_dict() != self.saved
        self.setWindowTitle(f"{'* ' if dirty else ''}{self.path.name if self.path else 'Untitled'} | PyniteGUI")

    def set_mode(self, mode):
        self.view.cancel()
        self.mode = mode
        self.mode_actions[mode].setChecked(True)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if mode == "pan" else QGraphicsView.DragMode.NoDrag)
        self.view.setCursor(Qt.CursorShape.CrossCursor if mode == "draw" else Qt.CursorShape.ArrowCursor)
        self.statusBar().showMessage(f"{mode.capitalize()} | {getattr(self.project, 'dimension', '2D')} frame | {self.project.units.summary}")

    def edit(self, title, mutate):
        before = self.project.clone()
        after = self.project.clone()
        try:
            mutate(after)
            after.validate()
        except Exception as error:
            QMessageBox.warning(self, title, str(error))
            return
        if before.to_dict() != after.to_dict():
            self.undo.push(Edit(self, title, before, after))

    def set_units(self, key):
        if key != self.project.unit_system:
            self.edit("Change units", lambda p: setattr(p, "unit_system", key))

    def choose_units(self):
        from PySide6.QtWidgets import QInputDialog
        keys = list(UNIT_SYSTEMS)
        labels = [UNIT_SYSTEMS[key].label for key in keys]
        selected, accepted = QInputDialog.getItem(self, "Units", "Unit system", labels,
                                                 keys.index(self.project.unit_system), False)
        if accepted:
            self.set_units(keys[labels.index(selected)])

    def replace_project(self, project):
        before, after = self.project.to_dict(), project.to_dict()
        before.pop("unit_system")
        after.pop("unit_system")
        units_only = before == after and self.project.unit_system != project.unit_system
        self.project = project.clone()
        if units_only:
            self.refresh()
            if self.result is not None:
                self.select_result_combination(self.result.combination)
            else:
                self.statusBar().showMessage(f"Units updated | {self.project.units.summary}")
            return
        self.revision += 1
        self.result = None
        self.export_menu.setEnabled(False)
        self.result_combination.setEnabled(False)
        self.result_combination.clear()
        self.results_table.setRowCount(0)
        self.results_dock.setWindowTitle("Results - Outdated")
        self.deformed_action.setEnabled(False)
        self.deformed_action.setChecked(False)
        self.refresh()
        self.statusBar().showMessage(f"Model updated | Results require analysis | {self.project.units.summary}")

    def refresh(self):
        spatial = getattr(self.project, "dimension", "2D") == "3D"
        if spatial and self.spatial_view is None:
            from .spatial_view import SpatialView
            self.spatial_view = SpatialView(self)
            self.view_stack.addWidget(self.spatial_view)
        self.view = self.spatial_view if spatial else self.planar_view
        self.view_stack.setCurrentWidget(self.view)
        self.selections = [selection for selection in self.selections
                           if selection[1] in getattr(self.project, selection[0])]
        units = self.project.units
        visible_case = self.load_filter.currentData()
        self.load_filter.blockSignals(True)
        self.load_filter.clear()
        self.load_filter.addItem("All load cases", None)
        self.load_filter.addItem("Hide loads", False)
        for case in self.project.load_cases:
            self.load_filter.addItem(case, case)
        index = self.load_filter.findData(visible_case)
        self.load_filter.setCurrentIndex(max(0, index))
        self.load_filter.blockSignals(False)
        self.selections = [selection for selection in self.selections if selection[0] != "loads"
                           or self.load_visible(self.project.loads[selection[1]])]
        selected = set(self.selections)
        self.unit_selector.blockSignals(True)
        self.unit_selector.setCurrentIndex(self.unit_selector.findData(self.project.unit_system))
        self.unit_selector.blockSignals(False)
        if spatial:
            from .spatial_model import DOFS, FORCES
            headers = ["Node", *(f"{dof} ({units.length if i < 3 else 'rad'})" for i, dof in enumerate(DOFS)),
                       *(f"{force} ({units.force if i < 3 else units.moment})" for i, force in enumerate(FORCES))]
        else:
            headers = ["Node", f"DX ({units.length})", f"DY ({units.length})", "RZ (rad)",
                       f"FX ({units.force})", f"FY ({units.force})", f"MZ ({units.moment})"]
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.coordinates.setText("   ".join(f"{axis} 0 {units.length}" for axis in ("XYZ" if spatial else "XY")))
        from .diagrams import DiagramDialog
        for dialog in self.findChildren(DiagramDialog):
            dialog.set_unit_system(self.project.unit_system)
            dialog.update_snapshot_status()
        from .spatial_diagrams import SpatialDiagramDialog
        for dialog in self.findChildren(SpatialDiagramDialog):
            dialog.set_unit_system(self.project.unit_system)
            dialog.update_snapshot_status()
        self.tree.blockSignals(True)
        self.tree.clear()
        for kind, title in (("nodes", "Nodes"), ("members", "Members"), ("loads", "Loads")):
            parent = QTreeWidgetItem(self.tree, [f"{title} ({len(getattr(self.project, kind))})"])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for name, entity in getattr(self.project, kind).items():
                if kind == "loads" and not self.load_visible(entity):
                    continue
                if kind == "nodes":
                    coordinates = entity.coords if spatial else (entity.x, entity.y)
                    detail = ", ".join(f"{units.to_display(v, 'length'):g}" for v in coordinates) + f" {units.length} | {entity.support}"
                    dofs = ("DX", "DY", "DZ", "RX", "RY", "RZ") if spatial else ("DX", "DY", "RZ")
                    if entity.support == "custom":
                        detail += " " + ",".join(label for label, fixed in zip(dofs, entity.restraints) if fixed)
                    if any(entity.springs):
                        detail += " | springs: " + ", ".join(label for label, k in zip(dofs, entity.springs) if k)
                elif kind == "members":
                    detail = f"{entity.start} - {entity.end}"
                    if entity.kind == "truss":
                        detail += " | truss (axial only)"
                else:
                    quantity = "intensity" if entity.kind == "distributed" else "moment" if entity.direction.upper().startswith("M") else "force"
                    detail = f"{entity.target} | {entity.direction} {units.to_display(entity.magnitude, quantity):g}"
                    if entity.kind == "distributed":
                        detail += f" to {units.to_display(entity.end_magnitude, quantity):g}"
                    detail += f" {getattr(units, quantity)}"
                    if entity.direction in ("Angle", "Local angle"):
                        detail += f" @ {entity.angle:g} deg"
                if kind == "members" and entity.kind == "frame":
                    for end, label in zip(("start", "end"), entity.release_labels):
                        if label != "None":
                            detail += f" | {end} releases: {label} (local)"
                if kind == "loads":
                    detail += f" | {entity.case}"
                item = QTreeWidgetItem(parent, [name, detail])
                item.setToolTip(1, detail)
                item.setData(0, Qt.ItemDataRole.UserRole, (kind, name))
                if (kind, name) in selected:
                    item.setSelected(True)
            parent.setExpanded(True)
        if self.project.self_weight_case is not None:
            generated = [load for load in self.project.self_weight_loads() if self.load_visible(load)]
            parent = QTreeWidgetItem(self.tree, [f"Self-weight ({len(generated)})", f"{self.project.self_weight_case} | factor {self.project.self_weight_factor:g}"])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for load in generated:
                quantity = "intensity" if load.kind == "distributed" else "force"
                item = QTreeWidgetItem(parent, [load.target, f"FY {units.to_display(load.magnitude, quantity):g} {getattr(units, quantity)}"])
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                item.setToolTip(1, f"{load.name}: generated from material weight density and section area; configure via Edit > Self-Weight.")
            parent.setExpanded(True)
        self.tree.blockSignals(False)
        self.update_inspector()
        self.view.redraw()
        self.update_title()

    def load_visible(self, load):
        case = self.load_filter.currentData()
        return case is None or (case is not False and load.case == case)

    def filter_loads(self):
        self.selections = [selection for selection in self.selections if selection[0] != "loads"
                           or self.load_visible(self.project.loads[selection[1]])]
        self.refresh()

    def tree_selection(self):
        items = self.tree.selectedItems()
        self.select_many([item.data(0, Qt.ItemDataRole.UserRole) for item in items], sync_tree=False)

    @property
    def selected(self):
        return self.selections[0] if len(self.selections) == 1 else None

    @selected.setter
    def selected(self, selection):
        self.selections = [tuple(selection)] if selection else []

    def select(self, selection):
        self.select_many([selection] if selection else [])

    def select_all(self):
        self.select_many([(kind, name) for kind in ("nodes", "members", "loads")
                          for name in getattr(self.project, kind)])

    def select_many(self, selections, sync_tree=True):
        self.selections = list(dict.fromkeys(tuple(selection) for selection in selections if selection
                                           and selection[1] in getattr(self.project, selection[0])
                                           and (selection[0] != "loads" or self.load_visible(self.project.loads[selection[1]]))))
        if sync_tree:
            selected = set(self.selections)
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            for index in range(self.tree.topLevelItemCount()):
                parent = self.tree.topLevelItem(index)
                for row in range(parent.childCount()):
                    item = parent.child(row)
                    identity = item.data(0, Qt.ItemDataRole.UserRole)
                    if identity and tuple(identity) in selected:
                        item.setSelected(True)
            self.tree.blockSignals(False)
        self.update_inspector()
        self.view.redraw()

    def update_inspector(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        if getattr(self.project, "dimension", "2D") == "3D":
            from .spatial_editor import populate_inspector
            populate_inspector(self)
            return
        if len(self.selections) > 1:
            from .bulk_edit import populate_bulk_inspector
            populate_bulk_inspector(self)
            return
        if not self.selected:
            self.form.addRow("Units", QLabel(self.project.units.label))
            self.form.addRow("Default material", QLabel(self.project.default_material))
            self.form.addRow("Default section", QLabel(self.project.default_section))
            grid = unit_number(self.project.grid, self.project.units, "length", 0.001, 1e6)
            self.form.addRow(f"Grid ({self.project.units.length})", grid)
            button = QPushButton("Apply")
            button.clicked.connect(lambda: self.edit("Change grid", lambda p: setattr(p, "grid", unit_value(grid, self.project.units))))
            self.form.addRow(button)
            return
        kind, name = self.selected
        entity = getattr(self.project, kind)[name]
        self.form.addRow("ID", QLabel(name))
        fields = {}
        if kind == "nodes":
            for key in ("x", "y"):
                fields[key] = unit_number(getattr(entity, key), self.project.units, "length")
                self.form.addRow(f"{key.upper()} ({self.project.units.length})", fields[key])
            fields["support"] = QComboBox()
            fields["support"].addItems(["free", "pin", "roller", "fixed", "custom"])
            fields["support"].setCurrentText(entity.support)
            self.form.addRow("Support", fields["support"])
            for key, label, fixed in zip(("restraint_x", "restraint_y", "restraint_rz"),
                                         ("Horizontal DX", "Vertical DY", "Rotation RZ"), entity.restraints):
                fields[key] = QCheckBox("Restrained")
                fields[key].setObjectName(key)
                fields[key].setChecked(fixed)
                self.form.addRow(label, fields[key])
            def update_support():
                custom = fields["support"].currentText() == "custom"
                for index, key in enumerate(("restraint_x", "restraint_y", "restraint_rz")):
                    self.form.setRowVisible(fields[key], custom)
                    if not custom:
                        fields[key].setChecked(replace(entity, support=fields["support"].currentText()).restraints[index])
            fields["support"].currentTextChanged.connect(update_support)
            update_support()
            for key, label, quantity in (("spring_x", "Spring DX", "stiffness"),
                                          ("spring_y", "Spring DY", "stiffness"),
                                          ("spring_rz", "Spring RZ", "rotational_stiffness")):
                fields[key] = unit_number(getattr(entity, key), self.project.units, quantity, 0)
                fields[key].setObjectName(key)
                fields[key].setToolTip("Global bilateral support spring. Zero means no spring; free this direction before assigning a positive stiffness.")
                self.form.addRow(f"{label} ({getattr(self.project.units, quantity)})", fields[key])
        elif kind == "members":
            for key in ("start", "end"):
                fields[key] = QComboBox()
                fields[key].addItems(list(self.project.nodes))
                fields[key].setCurrentText(getattr(entity, key))
                self.form.addRow(key.capitalize(), fields[key])
            a, b = self.project.nodes[entity.start], self.project.nodes[entity.end]
            self.form.addRow(f"Length ({self.project.units.length})", QLabel(f"{self.project.units.to_display(math.hypot(b.x - a.x, b.y - a.y), 'length'):g}"))
            fields["section"] = QComboBox()
            fields["section"].addItems(list(self.project.sections))
            for index, section in enumerate(self.project.sections.values()):
                fields["section"].setItemData(index, section.source_label, Qt.ItemDataRole.ToolTipRole)
            fields["section"].setCurrentText(entity.section)
            self.form.addRow("Section", fields["section"])
            fields["material"] = QComboBox()
            fields["material"].addItems(list(self.project.materials))
            for index, material in enumerate(self.project.materials.values()):
                fields["material"].setItemData(index, material.source_label, Qt.ItemDataRole.ToolTipRole)
            fields["material"].setCurrentText(entity.material)
            self.form.addRow("Material", fields["material"])
            fields["kind"] = QComboBox()
            fields["kind"].setObjectName("member_type")
            fields["kind"].addItems(["frame", "truss"])
            fields["kind"].setCurrentText(entity.kind)
            self.form.addRow("Type", fields["kind"])
            release_fields = (("release_start_x", "Start axial DX"), ("release_start_y", "Start shear DY"),
                              ("release_start", "Start moment RZ"), ("release_end_x", "End axial DX"),
                              ("release_end_y", "End shear DY"), ("release_end", "End moment RZ"))
            for key, label in release_fields:
                fields[key] = QCheckBox("Released")
                fields[key].setObjectName(key)
                fields[key].setChecked(getattr(entity, key))
                fields[key].setToolTip("Member-local end release: DX axial, DY transverse shear, RZ in-plane moment. Does not change the joint support.")
                self.form.addRow(label, fields[key])
            def update_member_type():
                for key, label in release_fields:
                    self.form.setRowVisible(fields[key], fields["kind"].currentText() == "frame")
            fields["kind"].currentTextChanged.connect(update_member_type)
            update_member_type()
        else:
            fields["target"] = QComboBox()
            fields["target"].addItems(list(self.project.members) if entity.kind == "distributed" else [*self.project.nodes, *self.project.members])
            fields["target"].setCurrentText(entity.target)
            fields["direction"] = QComboBox()
            fields["direction"].setObjectName("load_direction")
            fields["direction"].addItems(load_directions(entity.target in self.project.members, entity.kind))
            fields["direction"].setCurrentText(entity.direction)
            quantity = "intensity" if entity.kind == "distributed" else "moment" if entity.direction == "MZ" else "force"
            fields["magnitude"] = unit_number(entity.magnitude, self.project.units, quantity)
            fields["magnitude"].setObjectName("load_magnitude")
            fields["magnitude"].setToolTip("Signed load value; a negative angled force reverses the specified angle")
            fields["position"] = number(entity.position, 0, 1)
            fields["case"] = QComboBox()
            fields["case"].setObjectName("load_case")
            fields["case"].addItems(self.project.load_cases)
            fields["case"].setCurrentText(entity.case)
            self.form.addRow("Case", fields["case"])
            self.form.addRow("Type", QLabel(entity.kind.capitalize()))
            for key, label in (("target", "Target"), ("direction", "Direction"),
                               ("magnitude", f"Start ({self.project.units.intensity})" if entity.kind == "distributed" else getattr(self.project.units, quantity)),
                               ("position", "Start fraction" if entity.kind == "distributed" else "Member fraction")):
                self.form.addRow(label, fields[key])
            if entity.kind == "distributed":
                fields["end_magnitude"] = unit_number(entity.end_magnitude, self.project.units, "intensity")
                fields["end_magnitude"].setObjectName("load_end_magnitude")
                fields["magnitude"].setDecimals(6)
                fields["end_position"] = number(entity.end_position, 0, 1, 6)
                fields["position"].setDecimals(6)
                self.form.addRow(f"End ({self.project.units.intensity})", fields["end_magnitude"])
                self.form.addRow("End fraction", fields["end_position"])
            fields["angle"] = number(entity.angle, -360, 360, 4)
            fields["angle"].setProperty("original_angle", entity.angle)
            fields["angle"].setProperty("initial_angle", fields["angle"].value())
            fields["angle"].setObjectName("load_angle")
            self.form.addRow("Angle (deg)", fields["angle"])
            components = QLabel()
            components.setMinimumHeight(2 * components.fontMetrics().lineSpacing() + 4)
            self.form.addRow("Components", components)
            previous_target = [entity.target]
            def update_force():
                direction = fields["direction"].currentText()
                self.form.setRowVisible(fields["angle"], direction in ("Angle", "Local angle"))
                self.form.setRowVisible(components, direction == "Angle" or direction.startswith("Local"))
                local_angle = direction == "Local angle"
                self.form.labelForField(fields["angle"]).setText("Local angle (deg)" if local_angle else "Angle (deg)")
                fields["angle"].setToolTip("Counterclockwise from member start-to-end (+local x)" if local_angle else "Global angle: 0 deg right, 90 deg up, -90 deg down; counterclockwise positive")
                quantity = "intensity" if entity.kind == "distributed" else "moment" if direction == "MZ" else "force"
                self.form.labelForField(fields["magnitude"]).setText(f"Start ({self.project.units.intensity})" if entity.kind == "distributed" else getattr(self.project.units, quantity))
                preview = replace(entity, target=fields["target"].currentText(), direction=direction,
                                  magnitude=self.project.units.from_display(fields["magnitude"].value(), quantity),
                                  end_magnitude=self.project.units.from_display(fields["end_magnitude"].value(), "intensity") if entity.kind == "distributed" else 0,
                                  angle=fields["angle"].value())
                components.setText(component_preview(self.project, preview))
            def update_target():
                direction = fields["direction"].currentText()
                target = fields["target"].currentText()
                if direction.startswith("Local") and target not in self.project.members:
                    preview = replace(entity, target=previous_target[0], direction=direction, angle=fields["angle"].value())
                    fields["angle"].blockSignals(True)
                    fields["angle"].setValue(preview.resolved_angle(self.project))
                    fields["angle"].setProperty("original_angle", preview.resolved_angle(self.project))
                    fields["angle"].setProperty("initial_angle", fields["angle"].value())
                    fields["angle"].blockSignals(False)
                    direction = "Angle"
                fields["direction"].blockSignals(True)
                fields["direction"].clear()
                fields["direction"].addItems(load_directions(target in self.project.members, entity.kind))
                fields["direction"].setCurrentText(direction)
                fields["direction"].blockSignals(False)
                previous_target[0] = target
                update_force()
            fields["target"].currentTextChanged.connect(update_target)
            fields["direction"].currentTextChanged.connect(update_force)
            fields["angle"].valueChanged.connect(update_force)
            fields["magnitude"].valueChanged.connect(update_force)
            if entity.kind == "distributed":
                fields["end_magnitude"].valueChanged.connect(update_force)
            update_force()
        def apply():
            values = {key: widget.currentText() if isinstance(widget, QComboBox) else widget.isChecked() if isinstance(widget, QCheckBox) else widget.value() for key, widget in fields.items()}
            if kind == "loads" and fields["angle"].value() == fields["angle"].property("initial_angle"):
                values["angle"] = fields["angle"].property("original_angle")
            if kind == "nodes" and values["support"] != "custom":
                for key in ("restraint_x", "restraint_y", "restraint_rz"):
                    values.pop(key)
            for key, widget in fields.items():
                if isinstance(widget, QDoubleSpinBox) and widget.property("quantity"):
                    quantity = widget.property("quantity")
                    if kind == "loads" and key == "magnitude" and entity.kind == "point":
                        quantity = "moment" if values["direction"] == "MZ" else "force"
                    values[key] = unit_value(widget, self.project.units, quantity)
            def mutate(project):
                target = getattr(project, kind)[name]
                for key, value in values.items():
                    setattr(target, key, value)
            self.edit(f"Edit {name}", mutate)
        button = QPushButton("Apply")
        button.clicked.connect(apply)
        self.form.addRow(button)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.delete_selected)
        self.form.addRow(delete)
        if kind == "members":
            split = QPushButton("Split...")
            split.clicked.connect(self.split_selected_member)
            self.form.addRow(split)

    def split_selected_member(self):
        if not self.selected or self.selected[0] != "members":
            QMessageBox.information(self, "Split Member", "Select a member first.")
            return
        from PySide6.QtWidgets import QInputDialog
        name = self.selected[1]
        fraction, accepted = QInputDialog.getDouble(
            self, f"Split {name}", "Fraction from start", 0.5, 0.000001, 0.999999, 6
        )
        if accepted:
            self.edit(f"Split {name}", lambda project: project.split_member(name, fraction))

    def connect_intersections(self):
        before = len(self.project.members)
        self.edit("Connect intersections", lambda project: project.connect_intersections())
        added = len(self.project.members) - before
        if added:
            self.statusBar().showMessage(f"Connected intersections | {added} additional member segments | Results require analysis")

    def check_model(self):
        try:
            self.project.validate()
            issues = self.project.analysis_topology_issues() + self.project.analysis_release_issues()
        except ValueError as error:
            issues = [str(error)]
        if issues:
            QMessageBox.warning(self, "Model Check", "\n\n".join(issues))
        else:
            QMessageBox.information(self, "Model Check", "No geometry, connectivity, or release/load issues found.")

    def delete_selected(self):
        if self.selections:
            selections = list(self.selections)
            def mutate(project):
                for kind, name in selections:
                    if name in getattr(project, kind):
                        project.delete(kind, name)
            self.edit(f"Delete {len(selections)} selected" if len(selections) > 1 else f"Delete {selections[0][1]}", mutate)

    def add_load(self):
        if not self.selected or self.selected[0] not in ("nodes", "members"):
            QMessageBox.information(self, "Load", "Select a node or member first.")
            return
        if getattr(self.project, "dimension", "2D") == "3D":
            from .spatial_editor import add_load
            add_load(self)
            return
        kind, target = self.selected
        if kind == "members" and self.project.members[target].kind == "truss":
            QMessageBox.information(self, "Truss Load", "Truss members accept joint loads only. Select a node at a properly restrained or braced joint.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Load on {target}")
        dialog.setMinimumWidth(360)
        form = QFormLayout(dialog)
        load_type = QComboBox()
        load_type.addItems(["Point", "Distributed"] if kind == "members" else ["Point"])
        form.addRow("Type", load_type)
        direction = QComboBox()
        direction.addItems(load_directions(kind == "members", "point"))
        magnitude = number(-10)
        magnitude.setObjectName("load_magnitude")
        magnitude.setToolTip("Signed load value; a negative angled force reverses the specified angle")
        position = number(0.5, 0, 1)
        end_magnitude = number(-0.1, decimals=6)
        end_magnitude.setObjectName("load_end_magnitude")
        end_position = number(1, 0, 1, 6)
        form.addRow("Direction", direction)
        case = QComboBox()
        case.addItems(self.project.load_cases)
        case.setCurrentText(self.project.default_load_case)
        form.addRow("Case", case)
        form.addRow(self.project.units.force, magnitude)
        angle = number(-90, -360, 360, 4)
        angle.setObjectName("load_angle")
        angle.setToolTip("Global angle: 0 deg right, 90 deg up, -90 deg down; counterclockwise positive")
        form.addRow("Angle (deg)", angle)
        components = QLabel()
        components.setMinimumHeight(2 * components.fontMetrics().lineSpacing() + 4)
        form.addRow("Components", components)
        if kind == "members":
            form.addRow("Fraction from start", position)
        form.addRow(f"End ({self.project.units.intensity})", end_magnitude)
        form.addRow("End fraction", end_position)
        def update_type():
            distributed = load_type.currentText() == "Distributed"
            previous = direction.currentText()
            direction.blockSignals(True)
            direction.clear()
            choices = load_directions(kind == "members", "distributed" if distributed else "point")
            direction.addItems(choices)
            direction.setCurrentText(previous if previous in choices else "FY")
            direction.blockSignals(False)
            magnitude.setDecimals(6 if distributed else 4)
            magnitude.setValue(-0.1 if distributed else -10)
            position.setDecimals(6)
            position.setValue(0 if distributed else 0.5)
            form.labelForField(magnitude).setText(f"Start ({self.project.units.intensity})" if distributed else self.project.units.moment if direction.currentText() == "MZ" else self.project.units.force)
            if kind == "members":
                form.labelForField(position).setText("Start fraction" if distributed else "Fraction from start")
            form.setRowVisible(end_magnitude, distributed)
            form.setRowVisible(end_position, distributed)
            update_direction()
        def update_direction():
            chosen = direction.currentText()
            form.setRowVisible(angle, chosen in ("Angle", "Local angle"))
            form.setRowVisible(components, chosen == "Angle" or chosen.startswith("Local"))
            form.labelForField(angle).setText("Local angle (deg)" if chosen == "Local angle" else "Angle (deg)")
            angle.setToolTip("Counterclockwise from member start-to-end (+local x)" if chosen == "Local angle" else "Global angle: 0 deg right, 90 deg up, -90 deg down; counterclockwise positive")
            quantity = "intensity" if load_type.currentText() == "Distributed" else "moment" if chosen == "MZ" else "force"
            preview = Load("", target, chosen, self.project.units.from_display(magnitude.value(), quantity),
                           kind=load_type.currentText().lower(), angle=angle.value(),
                           end_magnitude=self.project.units.from_display(end_magnitude.value(), "intensity"))
            components.setText(component_preview(self.project, preview))
        direction.currentTextChanged.connect(update_direction)
        angle.valueChanged.connect(update_direction)
        magnitude.valueChanged.connect(update_direction)
        end_magnitude.valueChanged.connect(update_direction)
        direction.currentTextChanged.connect(lambda: form.labelForField(magnitude).setText(
            f"Start ({self.project.units.intensity})" if load_type.currentText() == "Distributed" else
            self.project.units.moment if direction.currentText() == "MZ" else self.project.units.force))
        load_type.currentTextChanged.connect(update_type)
        update_type()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            def mutate(project):
                name = project.next_name("L", project.loads)
                quantity = "intensity" if load_type.currentText() == "Distributed" else "moment" if direction.currentText() == "MZ" else "force"
                project.loads[name] = Load(name, target, direction.currentText(), project.units.from_display(magnitude.value(), quantity), position.value(),
                                           load_type.currentText().lower(), project.units.from_display(end_magnitude.value(), "intensity"), end_position.value(), case.currentText(), angle.value())
            self.edit("Add load", mutate)

    def assign_support(self):
        if not self.selected or self.selected[0] != "nodes":
            QMessageBox.information(self, "Support", "Select a node first.")
            return
        from PySide6.QtWidgets import QInputDialog
        name = self.selected[1]
        current = self.project.nodes[name].support
        choices = ["free", "pin", "roller", "fixed", "custom"]
        value, accepted = QInputDialog.getItem(self, f"Support on {name}", "Type", choices, choices.index(current), False)
        if accepted:
            def assign(project):
                node = project.nodes[name]
                if value == "custom" and node.support != "custom":
                    if getattr(project, "dimension", "2D") == "3D":
                        from .spatial_model import RESTRAINT_FIELDS
                        for key, fixed in zip(RESTRAINT_FIELDS, node.restraints):
                            setattr(node, key, fixed)
                    else:
                        node.restraint_x, node.restraint_y, node.restraint_rz = node.restraints
                node.support = value
            self.edit("Assign support", assign)

    def manage_materials(self):
        from .materials import MaterialDialog
        MaterialDialog(self).exec()

    def manage_load_cases(self):
        from .load_cases import LoadCasesDialog
        LoadCasesDialog(self).exec()

    def manage_sections(self):
        from .sections import SectionDialog
        SectionDialog(self).exec()

    def manage_model_tables(self):
        from .model_tables import ModelTablesDialog
        dialog = ModelTablesDialog(self, self.project)
        if dialog.exec():
            def mutate(project):
                definition = dialog.definition.clone()
                for kind in ("nodes", "members", "loads"):
                    setattr(project, kind, getattr(definition, kind))
            self.edit("Edit model tables", mutate)

    def manage_self_weight(self):
        from .self_weight import SelfWeightDialog
        dialog = SelfWeightDialog(self, self.project)
        if dialog.exec():
            case, factor = dialog.definition
            def mutate(project):
                project.self_weight_case, project.self_weight_factor = case, factor
            self.edit("Edit self-weight", mutate)

    def settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Grid")
        form = QFormLayout(dialog)
        fields = {}
        labels = {"grid": f"Grid ({self.project.units.length})"}
        for key, label in labels.items():
            fields[key] = unit_number(getattr(self.project, key), self.project.units, "length", 0, 1e12, 8)
            form.addRow(label, fields[key])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            def mutate(project):
                for key, widget in fields.items():
                    setattr(project, key, unit_value(widget, self.project.units))
            self.edit("Edit grid", mutate)

    def confirm_discard(self):
        if self.project.to_dict() == self.saved:
            return True
        answer = QMessageBox.question(self, "Unsaved Project", "Save changes before continuing?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return answer == QMessageBox.StandardButton.Discard

    def load_project(self, project, path=None):
        self.selected = None
        self.replace_project(project)
        self.undo.clear()
        self.path = path
        self.saved = project.to_dict()
        self.clear_autosave()
        if path is not None:
            self.record_recent(path)
        self.set_mode("select")
        self.update_title()
        self.view.fit()

    def new_project(self):
        if self.confirm_discard():
            self.load_project(Project(unit_system=self.project.unit_system))

    def new_spatial_project(self):
        if self.confirm_discard():
            from .spatial_model import SpatialProject
            self.load_project(SpatialProject(unit_system=self.project.unit_system))

    def add_spatial_node(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add 3D Node")
        form = QFormLayout(dialog)
        fields = [unit_number(0, self.project.units, "length") for _ in range(3)]
        for axis, field in zip("XYZ", fields):
            form.addRow(f"{axis} ({self.project.units.length})", field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            coordinates = [unit_value(field, self.project.units) for field in fields]
            self.edit("Add 3D node", lambda project: project.node_at(*coordinates))

    def open_project(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "PyniteGUI Project (*.pynite.json);;JSON (*.json)")
        if path:
            try:
                self.load_project(Project.open(path), Path(path))
            except Exception as error:
                QMessageBox.warning(self, "Open Project", str(error))

    def save_project(self, save_as=False):
        path = self.path
        if save_as or path is None:
            filename, _ = QFileDialog.getSaveFileName(self, "Save Project", str(path or "structure.pynite.json"), "PyniteGUI Project (*.pynite.json)")
            if not filename:
                return False
            path = Path(filename)
        try:
            self.project.save(path)
        except Exception as error:
            QMessageBox.warning(self, "Save Project", str(error))
            return False
        self.path, self.saved = path, self.project.to_dict()
        self.clear_autosave()
        self.record_recent(path)
        self.update_title()
        return True

    def example(self, key="simple_beam"):
        if not self.confirm_discard():
            return
        from .examples import EXAMPLES, example_project
        project = example_project(key, self.project.unit_system)
        self.load_project(project)
        self.saved = Project().to_dict()
        self.update_title()
        self.statusBar().showMessage(f"Example: {EXAMPLES[key]} | {project.units.summary}")

    def run_analysis(self):
        if self.thread is not None:
            return
        self.view.cancel()
        self.analysis_revision = self.revision
        self.analysis_cancel_requested = False
        self.analyze_action.setEnabled(False)
        self.cancel_analysis_action.setEnabled(True)
        self.analysis_phase.setText("Starting analysis")
        for widget in (self.analysis_phase, self.analysis_progress, self.analysis_cancel_button):
            widget.show()
        self.statusBar().showMessage("Analyzing | Previous results retained" if self.result is not None else "Analyzing...")
        self.thread = QThread(self)
        self.worker = AnalysisWorker(self.project.clone())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.analysis_progressed)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.analysis_stopped)
        self.thread.start()

    def analysis_progressed(self, phase):
        if self.thread is not None and not self.analysis_cancel_requested:
            self.analysis_phase.setText(phase)
            self.analysis_phase.setToolTip(phase)

    def cancel_analysis(self):
        if self.thread is None or self.worker is None:
            return
        self.analysis_cancel_requested = True
        self.worker.cancel()
        self.cancel_analysis_action.setEnabled(False)
        self.analysis_phase.setText("Cancelling analysis")
        self.statusBar().showMessage("Cancelling analysis...")

    def analysis_stopped(self):
        self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self.analyze_action.setEnabled(True)
        self.cancel_analysis_action.setEnabled(False)
        for widget in (self.analysis_phase, self.analysis_progress, self.analysis_cancel_button):
            widget.hide()
        if self.close_after_analysis:
            self.close_after_analysis = False
            QTimer.singleShot(0, self.close)

    def analysis_finished(self, result, error):
        if self.analysis_cancel_requested or error == CANCELLED:
            self.statusBar().showMessage("Analysis cancelled | Previous results retained" if self.result is not None else "Analysis cancelled")
            return
        if self.analysis_revision != self.revision:
            self.statusBar().showMessage("Model changed during analysis. Run analysis again.")
            return
        if error:
            self.statusBar().showMessage("Analysis failed | Previous results retained" if self.result is not None else "Analysis failed")
            QMessageBox.warning(self, "Analysis", error)
            return
        self.result = result
        self.export_menu.setEnabled(True)
        self.result_combination.blockSignals(True)
        self.result_combination.clear()
        self.result_combination.addItems(list(result.solver.load_combos))
        self.result_combination.setCurrentText(result.combination)
        self.result_combination.blockSignals(False)
        self.result_combination.setEnabled(True)
        self.select_result_combination(result.combination)
        self.results_dock.show()
        self.deformed_action.setEnabled(True)
        from .diagrams import DiagramDialog
        for dialog in self.findChildren(DiagramDialog):
            dialog.update_snapshot_status()
        from .spatial_diagrams import SpatialDiagramDialog
        for dialog in self.findChildren(SpatialDiagramDialog):
            dialog.update_snapshot_status()

    def select_result_combination(self, name):
        if self.result is None or not name:
            return
        self.result = self.result.for_combination(name)
        result = self.result
        self.results_table.setRowCount(len(result.displacements))
        for row, (name, displacement) in enumerate(result.displacements.items()):
            for col, value in enumerate((name, *displacement, *result.reactions[name])):
                if col and value is not None:
                    quantities = (("length",) * 3 + ("rotation",) * 3 + ("force",) * 3 + ("moment",) * 3
                                  if result.spatial else ("length", "length", "rotation", "force", "force", "moment"))
                    value = self.project.units.to_display(value, quantities[col - 1])
                item = QTableWidgetItem("n/a" if value is None else value if isinstance(value, str) else f"{value:.6g}")
                if value is None:
                    item.setToolTip("Released member ends rotate independently; no shared nodal rotation is defined.")
                self.results_table.setItem(row, col, item)
        self.results_table.resizeColumnsToContents()
        self.results_dock.setWindowTitle(f"Results - {result.combination}")
        self.view.redraw()
        self.statusBar().showMessage(f"Analysis complete | {result.combination} | {self.project.units.summary}")

    def diagrams(self):
        if self.result is None:
            QMessageBox.information(self, "Diagrams", "Run analysis on the current model first.")
            return
        if getattr(self.project, "dimension", "2D") == "3D":
            from .spatial_diagrams import SpatialDiagramDialog
            selected = self.selected[1] if self.selected and self.selected[0] == "members" else None
            SpatialDiagramDialog(self, self.project, self.result, selected).show()
            return
        from .diagrams import DiagramDialog
        selected = self.selected[1] if self.selected and self.selected[0] == "members" else None
        dialog = DiagramDialog(self, self.project, self.result, selected)
        dialog.show()

    def clear_autosave(self):
        self.last_autosave = None
        if self.recovery is not None:
            try:
                self.recovery.clear()
            except OSError as error:
                self.statusBar().showMessage(f"Could not clear recovery snapshot: {error}", 6000)

    def autosave_now(self):
        if self.recovery is None:
            return False
        data = self.project.to_dict()
        if data == self.saved:
            self.clear_autosave()
            return True
        signature = (data, self.saved, str(self.path))
        if signature == self.last_autosave and self.recovery.path.exists():
            return True
        try:
            self.recovery.write(self.project, self.saved, self.path)
            self.last_autosave = signature
            return True
        except (OSError, ValueError) as error:
            self.statusBar().showMessage(f"Autosave failed: {error}", 10000)
            return False

    def recover_snapshot(self, path):
        from .recovery import RecoveryStore
        project, original, saved = RecoveryStore.read(path)
        if not self.confirm_discard():
            return False
        self.load_project(project, original if original and original.exists() else None)
        self.saved = saved
        self.update_title()
        if self.autosave_now():
            if self.recovery is not None and Path(path) != self.recovery.path:
                Path(path).unlink(missing_ok=True)
        return True

    def offer_recovery(self):
        if self.recovery is None:
            return
        snapshots = self.recovery.snapshots()
        if self.recovery.errors:
            QMessageBox.warning(self, "Recovery", "Some recovery files could not be read and have been left untouched in:\n" + str(self.recovery.directory))
        if not snapshots:
            self.statusBar().showMessage("No interrupted-session recovery snapshots found", 6000)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Recover Unsaved Projects")
        dialog.resize(700, 320)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(snapshots), 3)
        table.setHorizontalHeaderLabels(["Project", "Snapshot (UTC)", "Original file"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for row, (_, payload) in enumerate(snapshots):
            original = payload.get("original_path")
            for col, text in enumerate((Path(original).name if original else "Untitled", payload["updated_at"], original or "-")):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                table.setItem(row, col, item)
        table.resizeColumnsToContents()
        table.selectRow(0)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        recover = buttons.addButton("Recover", QDialogButtonBox.ButtonRole.ActionRole)
        discard = buttons.addButton("Discard Snapshot", QDialogButtonBox.ButtonRole.ActionRole)
        def recover_selected():
            if table.currentRow() < 0:
                return
            try:
                if self.recover_snapshot(snapshots[table.currentRow()][0]):
                    dialog.accept()
            except (OSError, ValueError, KeyError, TypeError) as error:
                QMessageBox.warning(dialog, "Recovery", str(error))
        def discard_selected():
            row = table.currentRow()
            if row < 0:
                return
            if QMessageBox.question(dialog, "Discard Recovery", "Permanently discard this unsaved snapshot?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                try:
                    snapshots[row][0].unlink(missing_ok=True)
                    snapshots.pop(row)
                    table.removeRow(row)
                    if not snapshots:
                        dialog.reject()
                    else:
                        table.selectRow(min(row, len(snapshots) - 1))
                except OSError as error:
                    QMessageBox.warning(dialog, "Recovery", str(error))
        recover.clicked.connect(recover_selected)
        discard.clicked.connect(discard_selected)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def record_recent(self, path):
        if self.settings_store is None:
            return
        path = str(Path(path).resolve())
        recent = self.settings_store.value("recent_projects", [], type=list)
        self.settings_store.setValue("recent_projects", [path, *(item for item in recent if item != path)][:10])
        self.update_recent_menu()

    def update_recent_menu(self):
        self.recent_menu.clear()
        recent = self.settings_store.value("recent_projects", [], type=list) if self.settings_store else []
        self.recent_menu.setEnabled(bool(recent))
        for filename in recent:
            path = Path(filename)
            action = self.action(f"{path.name} ({path.parent.name})", lambda checked=False, path=path: self.open_recent(path))
            action.setToolTip(str(path))
            self.recent_menu.addAction(action)

    def open_recent(self, path):
        if not self.confirm_discard():
            return
        try:
            self.load_project(Project.open(path), path)
        except (OSError, ValueError, KeyError, TypeError) as error:
            QMessageBox.warning(self, "Open Project", str(error))

    def closeEvent(self, event):
        if self.thread is not None:
            self.close_after_analysis = True
            self.cancel_analysis()
            event.ignore()
        elif self.confirm_discard():
            self.clear_autosave()
            self.autosave_timer.stop()
            event.accept()
        else:
            event.ignore()


def main():
    from multiprocessing import freeze_support
    freeze_support()
    from .graphics import configure_graphics, launch_options
    settings = QSettings("PyniteGUI", "PyniteGUI")
    mode, arguments = launch_options(sys.argv, settings.value("graphics", "auto"))
    try:
        configure_graphics(mode)
    except ValueError as error:
        raise SystemExit("Invalid QTWEBENGINE_CHROMIUM_FLAGS: " + str(error)) from error
    application = QApplication.instance() or QApplication(arguments)
    application.setProperty("pynitegui_graphics", mode)
    application.setApplicationName("PyniteGUI")
    configure_theme(application)
    recovery_directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / "recovery"
    window = MainWindow(recovery_directory, settings)
    window.show()
    QTimer.singleShot(0, window.offer_recovery)
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
