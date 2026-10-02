"""Qt desktop editor for planar PyNite frames."""
import math
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QPainter, QPalette, QPen, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView,
    QLabel, QMainWindow, QMessageBox, QPushButton,
    QStyle, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .analysis import analyze
from .model import Load, Project


def number(value, minimum=-1e9, maximum=1e9, decimals=4):
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


class Edit(QUndoCommand):
    def __init__(self, window, title, before, after):
        super().__init__(title)
        self.window, self.before, self.after = window, before, after

    def redo(self):
        self.window.replace_project(self.after)

    def undo(self):
        self.window.replace_project(self.before)


class AnalysisWorker(QObject):
    finished = Signal(object, str)

    def __init__(self, project):
        super().__init__()
        self.project = project

    def run(self):
        try:
            self.finished.emit(analyze(self.project), "")
        except Exception as error:
            self.finished.emit(None, str(error))


class EngineeringSymbol(QGraphicsItem):
    def __init__(self, kind, value=None, length=38):
        super().__init__()
        self.kind, self.value, self.length = kind, value, length
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(2)

    def boundingRect(self):
        return QRectF(-46, -46, 92, 92)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#258451" if self.kind == "support" else "#bd3549"), 1.8))
        if self.kind == "hinge":
            painter.setPen(QPen(QColor("#176b73"), 1.8))
            painter.setBrush(QColor("#ffffff"))
            dx, dy = self.value
            painter.drawEllipse(QPointF(dx * 9, dy * 9), 4, 4)
            return
        if self.kind == "support":
            if self.value in ("pin", "roller"):
                painter.drawLine(QPointF(0, 0), QPointF(-9, 15))
                painter.drawLine(QPointF(-9, 15), QPointF(9, 15))
                painter.drawLine(QPointF(9, 15), QPointF(0, 0))
                ground = 18
                if self.value == "roller":
                    painter.drawEllipse(QRectF(-7, 17, 5, 5))
                    painter.drawEllipse(QRectF(2, 17, 5, 5))
                    ground = 25
            else:
                ground = 4
            painter.drawLine(QPointF(-12, ground), QPointF(12, ground))
            for x in (-10, -4, 2, 8):
                painter.drawLine(QPointF(x, ground), QPointF(x - 4, ground + 5))
        else:
            direction, magnitude = self.value
            sign = 1 if magnitude >= 0 else -1
            if direction == "MZ":
                painter.drawArc(QRectF(-14, -14, 28, 28), 30 * 16, sign * 280 * 16)
                painter.drawLine(QPointF(12, -7), QPointF(7, -8))
                return
            dx, dy = (sign, 0) if direction == "FX" else (0, -sign)
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
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#fafcfc"))
        self.setSceneRect(-120, -360, 720, 600)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        spacing = self.window.project.grid
        while spacing * abs(self.transform().m11()) < 15:
            spacing *= 2
        painter.setPen(QPen(QColor("#e2e7e8"), 0))
        x = math.floor(rect.left() / spacing) * spacing
        while x <= rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += spacing
        y = math.floor(rect.top() / spacing) * spacing
        while y <= rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += spacing
        painter.setPen(QPen(QColor("#a8b5b8"), 0))
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
        self.start = None
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
                self.preview = self.scene().addLine(xy[0], -xy[1], xy[0], -xy[1], QPen(QColor("#168b8b"), 0, Qt.PenStyle.DashLine))
            else:
                start = self.start
                self.cancel()
                self.window.edit("Add member", lambda project: project.add_member(start, xy))
        else:
            self.window.select(self.hit(point))

    def mouseMoveEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        x, y = self.snapped(point)
        self.window.coordinates.setText(f"X {x:g} in   Y {y:g} in")
        if self.preview is not None:
            self.preview.setLine(self.start[0], -self.start[1], x, -y)
        super().mouseMoveEvent(event)

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

    def label(self, text, x, y, color="#47575c", offset=(7, 7)):
        item = self.scene().addSimpleText(text)
        item.setBrush(QColor(color))
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
        scene.clear()
        selected = self.window.selected
        for name, member in project.members.items():
            a, b = project.nodes[member.start], project.nodes[member.end]
            pen = QPen(QColor("#168b8b" if selected == ("members", name) else "#32464d"), 3)
            pen.setCosmetic(True)
            scene.addLine(a.x, -a.y, b.x, -b.y, pen)
            length = math.hypot(b.x - a.x, b.y - a.y)
            for released, node, sign in ((member.release_start, a, 1), (member.release_end, b, -1)):
                if released:
                    symbol = EngineeringSymbol("hinge", (sign * (b.x - a.x) / length, -sign * (b.y - a.y) / length))
                    scene.addItem(symbol)
                    symbol.setPos(node.x, -node.y)
            self.label(name, (a.x + b.x) / 2, (a.y + b.y) / 2, offset=(4, 8))
        for name, node in project.nodes.items():
            color = QColor("#168b8b" if selected == ("nodes", name) else "#32464d")
            dot = scene.addEllipse(-4, -4, 8, 8, QPen(QColor("white")), color)
            dot.setFlag(dot.GraphicsItemFlag.ItemIgnoresTransformations)
            dot.setPos(node.x, -node.y)
            self.label(name, node.x, node.y, offset=(8, -22))
            if node.support != "free":
                symbol = EngineeringSymbol("support", node.support)
                scene.addItem(symbol)
                symbol.setPos(node.x, -node.y)
        occupied = [item.deviceTransform(self.viewportTransform()).mapRect(item.boundingRect())
                    for item in scene.items() if isinstance(item, QGraphicsSimpleTextItem)]
        def load_label(text, x, y):
            from PySide6.QtGui import QTransform
            item = self.label(text, x, y, "#bd3549", (8, -52))
            offset = -52
            while True:
                rect = item.deviceTransform(self.viewportTransform()).mapRect(item.boundingRect()).adjusted(-2, -2, 2, 2)
                if not any(rect.intersects(previous) for previous in occupied):
                    occupied.append(rect)
                    break
                offset -= item.boundingRect().height() + 4
                item.setTransform(QTransform.fromTranslate(8, offset))
        for definition in project.loads.values():
            load = definition
            if self.window.result is not None:
                factor = self.window.result.solver.load_combos[self.window.result.combination].factors.get(load.case, 0)
                if factor == 0:
                    continue
                load = replace(load, magnitude=load.magnitude * factor, end_magnitude=load.end_magnitude * factor)
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
                    symbol = EngineeringSymbol("load", (load.direction, intensity), 38 * abs(intensity) / maximum)
                    scene.addItem(symbol)
                    symbol.setPos(a.x + (b.x - a.x) * fraction, -a.y - (b.y - a.y) * fraction)
                midpoint = (load.position + load.end_position) / 2
                x, y = a.x + (b.x - a.x) * midpoint, a.y + (b.y - a.y) * midpoint
                load_label(f"{load.name}: {load.magnitude:g} to {load.end_magnitude:g} kip/in", x, y)
                continue
            symbol = EngineeringSymbol("load", (load.direction, load.magnitude))
            scene.addItem(symbol)
            symbol.setPos(x, -y)
            units = "kip-in" if load.direction == "MZ" else "kip"
            load_label(f"{load.name}: {load.magnitude:g} {units}", x, y)
        if self.window.result and self.window.deformed_action.isChecked():
            scale = self.window.deformation_scale.value()
            pen = QPen(QColor("#bd3549"), 2)
            pen.setCosmetic(True)
            for member in project.members.values():
                a, b = project.nodes[member.start], project.nodes[member.end]
                length = math.hypot(b.x - a.x, b.y - a.y)
                solver_member = self.window.result.solver.members[member.name]
                axes = solver_member.T()[:3, :3]
                previous = None
                for index in range(41):
                    t = index / 40
                    dx = solver_member.deflection("dx", t * length, self.window.result.combination)
                    dy = solver_member.deflection("dy", t * length, self.window.result.combination)
                    ux = axes[0, 0] * dx + axes[1, 0] * dy
                    uy = axes[0, 1] * dx + axes[1, 1] * dy
                    point = QPointF(a.x + t * (b.x - a.x) + scale * ux, -(a.y + t * (b.y - a.y) + scale * uy))
                    if previous is not None:
                        scene.addLine(previous.x(), previous.y(), point.x(), point.y(), pen)
                    previous = point


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.saved = self.project.to_dict()
        self.path = None
        self.selected = None
        self.mode = "select"
        self.result = None
        self.revision = 0
        self.thread = None
        self.undo = QUndoStack(self)
        self.resize(1280, 820)
        self.setMinimumSize(820, 560)
        self.view = StructureView(self)
        self.setCentralWidget(self.view)
        self.build_actions()
        self.build_panels()
        self.coordinates = QLabel("X 0 in   Y 0 in")
        self.statusBar().addPermanentWidget(self.coordinates)
        self.statusBar().showMessage("Ready | 2D frame | in, kip")
        self.undo.indexChanged.connect(self.update_title)
        self.refresh()
        self.view.fit()

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
            }
            action.setIcon(self.style().standardIcon(fallback[icon]))
        action.triggered.connect(callback)
        return action

    def build_actions(self):
        file_menu = self.menuBar().addMenu("&File")
        self.new_action = self.action("New", self.new_project, "Ctrl+N", "document-new")
        self.open_action = self.action("Open...", self.open_project, "Ctrl+O", "document-open")
        self.save_action = self.action("Save", self.save_project, "Ctrl+S", "document-save")
        for action in (self.new_action, self.open_action, self.save_action):
            file_menu.addAction(action)
        file_menu.addAction(self.action("Save As...", lambda: self.save_project(True), "Ctrl+Shift+S"))
        file_menu.addSeparator()
        file_menu.addAction(self.action("Simply Supported Example", self.example))
        file_menu.addAction(self.action("Exit", self.close, "Ctrl+Q"))
        edit_menu = self.menuBar().addMenu("&Edit")
        undo = self.undo.createUndoAction(self, "Undo")
        undo.setShortcut("Ctrl+Z")
        redo = self.undo.createRedoAction(self, "Redo")
        redo.setShortcuts(["Ctrl+Shift+Z", "Ctrl+Y"])
        edit_menu.addActions([undo, redo])
        edit_menu.addAction(self.action("Delete Selection", self.delete_selected, "Delete", "edit-delete"))
        edit_menu.addAction(self.action("Materials...", self.manage_materials))
        edit_menu.addAction(self.action("Sections...", self.manage_sections))
        edit_menu.addAction(self.action("Load Cases and Combinations...", self.manage_load_cases))
        edit_menu.addAction(self.action("Grid...", self.settings))
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
        toolbar.addAction(self.action("Fit", self.view.fit, "F", "zoom-fit-best"))
        toolbar.addSeparator()
        toolbar.addAction(self.action("Load...", self.add_load, "L"))
        toolbar.addAction(self.action("Support...", self.assign_support))
        toolbar.addSeparator()
        self.analyze_action = self.action("Analyze", self.run_analysis, "F5", "media-playback-start")
        toolbar.addAction(self.analyze_action)
        self.deformed_action = self.action("Deformed", self.view.redraw)
        self.deformed_action.setCheckable(True)
        self.deformed_action.setEnabled(False)
        toolbar.addAction(self.deformed_action)
        self.deformation_scale = number(100, 0.01, 1e6, 2)
        self.deformation_scale.setPrefix("Scale ")
        self.deformation_scale.setFixedWidth(140)
        self.deformation_scale.valueChanged.connect(self.view.redraw)
        toolbar.addWidget(self.deformation_scale)
        toolbar.addAction(self.action("Diagrams...", self.diagrams))

    def dock(self, title, widget, area):
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.addDockWidget(area, dock)
        self.menuBar_view.addAction(dock.toggleViewAction())
        return dock

    def build_panels(self):
        self.menuBar_view = self.menuBar().addMenu("&View")
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Model", "Properties"])
        self.tree.setMinimumWidth(210)
        self.tree.itemSelectionChanged.connect(self.tree_selection)
        self.dock("Structure", self.tree, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.inspector = QWidget()
        self.form = QFormLayout(self.inspector)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.inspector.setMinimumWidth(240)
        self.dock("Properties", self.inspector, Qt.DockWidgetArea.RightDockWidgetArea)
        self.results_table = QTableWidget(0, 7)
        self.results_table.setHorizontalHeaderLabels(["Node", "DX (in)", "DY (in)", "RZ (rad)", "FX (kip)", "FY (kip)", "MZ (kip-in)"])
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
        self.statusBar().showMessage(f"{mode.capitalize()} | 2D frame | in, kip")

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

    def replace_project(self, project):
        self.project = project.clone()
        self.revision += 1
        self.result = None
        self.result_combination.setEnabled(False)
        self.result_combination.clear()
        self.results_table.setRowCount(0)
        self.results_dock.setWindowTitle("Results - Outdated")
        self.deformed_action.setEnabled(False)
        self.deformed_action.setChecked(False)
        if self.selected and self.selected[1] not in getattr(self.project, self.selected[0]):
            self.selected = None
        self.refresh()
        self.statusBar().showMessage("Model updated | Results require analysis | in, kip")

    def refresh(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        for kind, title in (("nodes", "Nodes"), ("members", "Members"), ("loads", "Loads")):
            parent = QTreeWidgetItem(self.tree, [f"{title} ({len(getattr(self.project, kind))})"])
            for name, entity in getattr(self.project, kind).items():
                detail = f"{entity.x:g}, {entity.y:g} | {entity.support}" if kind == "nodes" else f"{entity.start} - {entity.end}" if kind == "members" else f"{entity.target} | {entity.direction} {entity.magnitude:g}" + (f" to {entity.end_magnitude:g} kip/in" if entity.kind == "distributed" else "")
                if kind == "members" and (entity.release_start or entity.release_end):
                    ends = ", ".join(end for end, released in (("start", entity.release_start), ("end", entity.release_end)) if released)
                    detail += f" | hinge: {ends}"
                if kind == "loads":
                    detail += f" | {entity.case}"
                item = QTreeWidgetItem(parent, [name, detail])
                item.setToolTip(1, detail)
                item.setData(0, Qt.ItemDataRole.UserRole, (kind, name))
                if self.selected == (kind, name):
                    item.setSelected(True)
            parent.setExpanded(True)
        self.tree.blockSignals(False)
        self.update_inspector()
        self.view.redraw()
        self.update_title()

    def tree_selection(self):
        items = self.tree.selectedItems()
        self.select(items[0].data(0, Qt.ItemDataRole.UserRole) if items else None)

    def select(self, selection):
        self.selected = tuple(selection) if selection else None
        self.refresh()

    def update_inspector(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        if not self.selected:
            self.form.addRow("Units", QLabel("in, kip"))
            self.form.addRow("Default material", QLabel(self.project.default_material))
            self.form.addRow("Default section", QLabel(self.project.default_section))
            grid = number(self.project.grid, 0.001, 1e6)
            self.form.addRow("Grid (in)", grid)
            button = QPushButton("Apply")
            button.clicked.connect(lambda: self.edit("Change grid", lambda p: setattr(p, "grid", grid.value())))
            self.form.addRow(button)
            return
        kind, name = self.selected
        entity = getattr(self.project, kind)[name]
        self.form.addRow("ID", QLabel(name))
        fields = {}
        if kind == "nodes":
            for key in ("x", "y"):
                fields[key] = number(getattr(entity, key))
                self.form.addRow(f"{key.upper()} (in)", fields[key])
            fields["support"] = QComboBox()
            fields["support"].addItems(["free", "pin", "roller", "fixed"])
            fields["support"].setCurrentText(entity.support)
            self.form.addRow("Support", fields["support"])
        elif kind == "members":
            for key in ("start", "end"):
                fields[key] = QComboBox()
                fields[key].addItems(list(self.project.nodes))
                fields[key].setCurrentText(getattr(entity, key))
                self.form.addRow(key.capitalize(), fields[key])
            a, b = self.project.nodes[entity.start], self.project.nodes[entity.end]
            self.form.addRow("Length (in)", QLabel(f"{math.hypot(b.x - a.x, b.y - a.y):g}"))
            fields["section"] = QComboBox()
            fields["section"].addItems(list(self.project.sections))
            fields["section"].setCurrentText(entity.section)
            self.form.addRow("Section", fields["section"])
            fields["material"] = QComboBox()
            fields["material"].addItems(list(self.project.materials))
            fields["material"].setCurrentText(entity.material)
            self.form.addRow("Material", fields["material"])
            for key, label in (("release_start", f"Start moment ({entity.start})"), ("release_end", f"End moment ({entity.end})")):
                fields[key] = QCheckBox("Released (hinge)")
                fields[key].setObjectName(key)
                fields[key].setChecked(getattr(entity, key))
                fields[key].setToolTip("Release member-end moment about Z; translations remain connected.")
                self.form.addRow(label, fields[key])
        else:
            fields["target"] = QComboBox()
            fields["target"].addItems(list(self.project.members) if entity.kind == "distributed" else [*self.project.nodes, *self.project.members])
            fields["target"].setCurrentText(entity.target)
            fields["direction"] = QComboBox()
            fields["direction"].setObjectName("load_direction")
            fields["direction"].addItems(["FX", "FY"] if entity.kind == "distributed" else ["FX", "FY", "MZ"])
            fields["direction"].setCurrentText(entity.direction)
            fields["magnitude"] = number(entity.magnitude)
            fields["position"] = number(entity.position, 0, 1)
            fields["case"] = QComboBox()
            fields["case"].setObjectName("load_case")
            fields["case"].addItems(self.project.load_cases)
            fields["case"].setCurrentText(entity.case)
            self.form.addRow("Case", fields["case"])
            self.form.addRow("Type", QLabel(entity.kind.capitalize()))
            for key, label in (("target", "Target"), ("direction", "Global direction"),
                               ("magnitude", "Start (kip/in)" if entity.kind == "distributed" else "kip / kip-in"),
                               ("position", "Start fraction" if entity.kind == "distributed" else "Member fraction")):
                self.form.addRow(label, fields[key])
            if entity.kind == "distributed":
                fields["end_magnitude"] = number(entity.end_magnitude, decimals=6)
                fields["magnitude"].setDecimals(6)
                fields["end_position"] = number(entity.end_position, 0, 1, 6)
                fields["position"].setDecimals(6)
                self.form.addRow("End (kip/in)", fields["end_magnitude"])
                self.form.addRow("End fraction", fields["end_position"])
        def apply():
            values = {key: widget.currentText() if isinstance(widget, QComboBox) else widget.isChecked() if isinstance(widget, QCheckBox) else widget.value() for key, widget in fields.items()}
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
        if self.selected:
            kind, name = self.selected
            self.edit(f"Delete {name}", lambda project: project.delete(kind, name))

    def add_load(self):
        if not self.selected or self.selected[0] not in ("nodes", "members"):
            QMessageBox.information(self, "Load", "Select a node or member first.")
            return
        kind, target = self.selected
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Load on {target}")
        form = QFormLayout(dialog)
        load_type = QComboBox()
        load_type.addItems(["Point", "Distributed"] if kind == "members" else ["Point"])
        form.addRow("Type", load_type)
        direction = QComboBox()
        direction.addItems(["FY", "FX", "MZ"])
        magnitude = number(-10)
        position = number(0.5, 0, 1)
        end_magnitude = number(-0.1, decimals=6)
        end_position = number(1, 0, 1, 6)
        form.addRow("Global direction", direction)
        case = QComboBox()
        case.addItems(self.project.load_cases)
        case.setCurrentText(self.project.default_load_case)
        form.addRow("Case", case)
        form.addRow("kip / kip-in", magnitude)
        if kind == "members":
            form.addRow("Fraction from start", position)
        form.addRow("End (kip/in)", end_magnitude)
        form.addRow("End fraction", end_position)
        def update_type():
            distributed = load_type.currentText() == "Distributed"
            previous = direction.currentText()
            direction.clear()
            direction.addItems(["FY", "FX"] if distributed else ["FY", "FX", "MZ"])
            direction.setCurrentText(previous if previous in ("FY", "FX") or not distributed else "FY")
            magnitude.setDecimals(6 if distributed else 4)
            magnitude.setValue(-0.1 if distributed else -10)
            position.setDecimals(6)
            position.setValue(0 if distributed else 0.5)
            form.labelForField(magnitude).setText("Start (kip/in)" if distributed else "kip / kip-in")
            if kind == "members":
                form.labelForField(position).setText("Start fraction" if distributed else "Fraction from start")
            form.setRowVisible(end_magnitude, distributed)
            form.setRowVisible(end_position, distributed)
        load_type.currentTextChanged.connect(update_type)
        update_type()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            def mutate(project):
                name = project.next_name("L", project.loads)
                project.loads[name] = Load(name, target, direction.currentText(), magnitude.value(), position.value(),
                                           load_type.currentText().lower(), end_magnitude.value(), end_position.value(), case.currentText())
            self.edit("Add load", mutate)

    def assign_support(self):
        if not self.selected or self.selected[0] != "nodes":
            QMessageBox.information(self, "Support", "Select a node first.")
            return
        from PySide6.QtWidgets import QInputDialog
        name = self.selected[1]
        current = self.project.nodes[name].support
        choices = ["free", "pin", "roller", "fixed"]
        value, accepted = QInputDialog.getItem(self, f"Support on {name}", "Type", choices, choices.index(current), False)
        if accepted:
            self.edit("Assign support", lambda project: setattr(project.nodes[name], "support", value))

    def manage_materials(self):
        from .materials import MaterialDialog
        MaterialDialog(self).exec()

    def manage_load_cases(self):
        from .load_cases import LoadCasesDialog
        LoadCasesDialog(self).exec()

    def manage_sections(self):
        from .sections import SectionDialog
        SectionDialog(self).exec()

    def settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Grid")
        form = QFormLayout(dialog)
        fields = {}
        labels = {"grid": "Grid (in)"}
        for key, label in labels.items():
            fields[key] = number(getattr(self.project, key), 0, 1e12, 8)
            form.addRow(label, fields[key])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            def mutate(project):
                for key, widget in fields.items():
                    setattr(project, key, widget.value())
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
        self.set_mode("select")
        self.update_title()
        self.view.fit()

    def new_project(self):
        if self.confirm_discard():
            self.load_project(Project())

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
        self.update_title()
        return True

    def example(self):
        if not self.confirm_discard():
            return
        project = Project()
        project.add_member((0, 0), (420, 0))
        project.nodes["N1"].support = "pin"
        project.nodes["N2"].support = "roller"
        project.loads["L1"] = Load("L1", "M1", "FY", -10, 0.5)
        self.load_project(project)
        self.saved = Project().to_dict()
        self.update_title()

    def run_analysis(self):
        if self.thread is not None:
            return
        self.view.cancel()
        self.result = None
        self.result_combination.setEnabled(False)
        self.result_combination.clear()
        self.results_table.setRowCount(0)
        self.deformed_action.setChecked(False)
        self.deformed_action.setEnabled(False)
        self.view.redraw()
        self.analysis_revision = self.revision
        self.analyze_action.setEnabled(False)
        self.statusBar().showMessage("Analyzing...")
        self.thread = QThread(self)
        self.worker = AnalysisWorker(self.project.clone())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.analysis_stopped)
        self.thread.start()

    def analysis_stopped(self):
        self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self.analyze_action.setEnabled(True)

    def analysis_finished(self, result, error):
        if self.analysis_revision != self.revision:
            self.statusBar().showMessage("Model changed during analysis. Run analysis again.")
            return
        if error:
            self.statusBar().showMessage("Analysis failed")
            QMessageBox.warning(self, "Analysis", error)
            return
        self.result = result
        self.result_combination.blockSignals(True)
        self.result_combination.clear()
        self.result_combination.addItems(list(result.solver.load_combos))
        self.result_combination.setCurrentText(result.combination)
        self.result_combination.blockSignals(False)
        self.result_combination.setEnabled(True)
        self.select_result_combination(result.combination)
        self.results_dock.show()
        self.deformed_action.setEnabled(True)

    def select_result_combination(self, name):
        if self.result is None or not name:
            return
        self.result = self.result.for_combination(name)
        result = self.result
        self.results_table.setRowCount(len(result.displacements))
        for row, (name, displacement) in enumerate(result.displacements.items()):
            for col, value in enumerate((name, *displacement, *result.reactions[name])):
                item = QTableWidgetItem("n/a" if value is None else value if isinstance(value, str) else f"{value:.6g}")
                if value is None:
                    item.setToolTip("Released member ends rotate independently; no shared nodal rotation is defined.")
                self.results_table.setItem(row, col, item)
        self.results_table.resizeColumnsToContents()
        self.results_dock.setWindowTitle(f"Results - {result.combination}")
        self.view.redraw()
        self.statusBar().showMessage(f"Analysis complete | {result.combination} | in, kip")

    def diagrams(self):
        if self.result is None:
            QMessageBox.information(self, "Diagrams", "Run analysis on the current model first.")
            return
        from .diagrams import DiagramDialog
        selected = self.selected[1] if self.selected and self.selected[0] == "members" else None
        dialog = DiagramDialog(self, self.project, self.result, selected)
        dialog.show()

    def closeEvent(self, event):
        if self.thread is not None:
            QMessageBox.information(self, "Analysis Running", "Wait for analysis to finish before closing.")
            event.ignore()
        elif self.confirm_discard():
            event.accept()
        else:
            event.ignore()


def configure_theme(application):
    # Use a complete palette so desktop dark themes cannot mix with light surfaces.
    application.setStyle("Fusion")
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#f5f7f7",
        QPalette.ColorRole.WindowText: "#24343b",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#f2f6f6",
        QPalette.ColorRole.Text: "#24343b",
        QPalette.ColorRole.Button: "#edf1f2",
        QPalette.ColorRole.ButtonText: "#24343b",
        QPalette.ColorRole.Highlight: "#176b73",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#ffffff",
        QPalette.ColorRole.ToolTipText: "#24343b",
        QPalette.ColorRole.PlaceholderText: "#69777e",
        QPalette.ColorRole.Link: "#176b73",
        QPalette.ColorRole.LinkVisited: "#495c91",
        QPalette.ColorRole.Light: "#ffffff",
        QPalette.ColorRole.Midlight: "#e5ebed",
        QPalette.ColorRole.Mid: "#bac6cb",
        QPalette.ColorRole.Dark: "#86959c",
        QPalette.ColorRole.Shadow: "#47575c",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Accent: "#176b73",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#69777e"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#edf1f2"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#d5e8ea"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor("#24343b"))
    application.setPalette(palette)
    application.setStyleSheet("""
        QMainWindow { background: #f5f7f7; }
        QToolBar { spacing: 4px; padding: 5px; background: #f5f7f7; color: #24343b; border-bottom: 1px solid #d1d9dc; }
        QToolButton { padding: 4px; border: 1px solid transparent; border-radius: 3px; }
        QToolButton:hover { background: #e0eded; }
        QToolButton:checked { background: #d5e8ea; border-color: #62979c; }
        QDockWidget::title { padding: 7px; background: #e5ebed; color: #24343b; }
        QTreeWidget, QTableWidget { border: 0; alternate-background-color: #f2f6f6; }
        QPushButton { padding: 5px 10px; }
        QStatusBar { background: #e5ebed; color: #24343b; }
    """)


def main():
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("PyniteGUI")
    configure_theme(application)
    window = MainWindow()
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
