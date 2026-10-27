"""Native playback of a retained static displacement field, never a time solve."""
import math
import time
import numpy as np
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)
from .plot_export import SnapshotPlotToolbar, snapshot_metadata
from .theme import colors, style_axes


def static_paths(project, result):
    """Sample once per combination; preserve local/global recovery conventions."""
    from .analysis import model_signature
    if model_signature(project) != result.model_signature:
        raise ValueError("The model does not match this analyzed snapshot.")
    paths = []
    if getattr(project, "dimension", "2D") == "3D":
        from .spatial_results import sampled_member
        from .spatial_surfaces import surface_payloads
        for name, member in project.members.items():
            positions, _, displacement = sampled_member(project, result, name)
            a, b = (np.array(project.nodes[n].coords) for n in (member.start, member.end))
            paths.append((a+positions[:, None]/np.linalg.norm(b-a)*(b-a), displacement))
        for mesh in surface_payloads(project, result, False):
            for cell in mesh["surfaces"]:
                nodes = [mesh["nodes"][i] for i in (*cell, cell[0])]
                paths.append((np.array([n["position"] for n in nodes]),
                              np.array([n.get("displacement", (0., 0., 0.)) for n in nodes])))
    else:
        from .app import deformation_paths
        for path in deformation_paths(project, result):
            data = np.array(path)
            paths.append((data[:, :2], data[:, 2:]))
    return paths


class StaticDeformationDialog(QDialog):
    def __init__(self, parent, project, result):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Static Deformation Animation — Display Only")
        self.resize(1100, 760)
        self.project, self.result = project.clone(), result
        self.source = str(getattr(parent, "path", None) or "Untitled")
        self.spatial = getattr(project, "dimension", "2D") == "3D"
        self.phase = 0.
        layout = QVBoxLayout(self)
        self.snapshot = QLabel(f"Retained analysis {result.snapshot_id} | {result.method_label} | {result.analyzed_at} (UTC). Editor changes do not replace this snapshot.")
        self.snapshot.setTextFormat(Qt.TextFormat.PlainText)
        self.snapshot.setWordWrap(True)
        layout.addWidget(self.snapshot)
        note = QLabel("Static deformation animation: cycles 0–100% of an amplified solved displacement field. "
                      "Loop duration is display timing, not physical time. No mass, dynamics, mode shapes or cross-section twist is calculated. Surface meshes use nodal wireframes.")
        note.setWordWrap(True)
        layout.addWidget(note)
        controls = QHBoxLayout()
        self.combination = QComboBox()
        self.combination.addItems(list(result.solver.load_combos))
        self.combination.setCurrentText(result.combination)
        controls.addWidget(self.combination, 1)
        self.mode = QComboBox()
        for label, key in (("Auto", "auto"), ("True scale", "true"), ("Custom factor", "custom")):
            self.mode.addItem(label, key)
        controls.addWidget(self.mode)
        self.scale = QDoubleSpinBox()
        self.scale.setRange(.001, 1e9)
        self.scale.setDecimals(3)
        self.scale.setValue(100.)
        self.scale.setSuffix("x")
        self.scale.setKeyboardTracking(False)
        controls.addWidget(self.scale)
        self.play = QPushButton("Play")
        self.play.setCheckable(True)
        controls.addWidget(self.play)
        self.reset = QPushButton("Reset")
        controls.addWidget(self.reset)
        layout.addLayout(controls)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Loop (display seconds)"))
        self.duration = QDoubleSpinBox()
        self.duration.setRange(.5, 30.)
        self.duration.setValue(4.)
        controls.addWidget(self.duration)
        controls.addWidget(QLabel("Displacement fraction"))
        self.fraction = QDoubleSpinBox()
        self.fraction.setRange(0., 1.)
        self.fraction.setDecimals(3)
        self.fraction.setSingleStep(.05)
        self.fraction.setKeyboardTracking(False)
        controls.addWidget(self.fraction)
        controls.addStretch()
        layout.addLayout(controls)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.figure = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(SnapshotPlotToolbar(self.canvas, self, self.frame_metadata))
        layout.addWidget(self.canvas, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)
        self.play.toggled.connect(self.playback)
        self.reset.clicked.connect(self.reset_frame)
        self.duration.valueChanged.connect(self.pause)
        self.fraction.valueChanged.connect(self.scrub)
        self.combination.currentTextChanged.connect(self.select_combination)
        self.mode.currentIndexChanged.connect(self.rebuild)
        self.scale.valueChanged.connect(self.rebuild)
        if parent is not None and hasattr(parent, "automation_mode"):
            parent.automation_mode.changed.connect(self.pause)
        self.paths = static_paths(self.project, result)
        self.rebuild()

    def frame_metadata(self):
        # The native file dialog runs an event loop. Freeze this exact frame
        # before it opens so pixels and provenance cannot drift apart.
        self.pause()
        self.draw_fraction()
        return snapshot_metadata(self, "Static deformation animation frame", amplification=self.factor,
                                 displacement_fraction=self.fraction.value(), display_only=True,
                                 representation="Sampled members and nodal surface wireframes")

    def select_combination(self, name):
        self.pause()
        self.result = self.result.for_combination(name)
        self.paths = static_paths(self.project, self.result)
        self.rebuild()

    def rebuild(self, *unused):
        self.pause()
        self.phase = 0.
        self.fraction.blockSignals(True)
        self.fraction.setValue(0.)
        self.fraction.blockSignals(False)
        peak = max((float(np.linalg.norm(motion, axis=1).max()) for _, motion in self.paths), default=0.)
        base = np.vstack([p for p, _ in self.paths])
        extent = max(float(np.ptp(base, axis=0).max()), 1.)
        mode = self.mode.currentData()
        self.factor = .15*extent/peak if mode == "auto" and peak else self.scale.value() if mode == "custom" else 1.
        self.scale.setEnabled(mode == "custom")
        self.figure.clear()
        self.ax = self.figure.add_subplot(projection="3d" if self.spatial else None)
        collection = Line3DCollection if self.spatial else LineCollection
        self.reference = collection([], colors=colors()["member"], linewidths=1., linestyles="--")
        self.animated = collection([], colors=colors()["load"], linewidths=1.7)
        self.ax.add_collection(self.reference)
        self.ax.add_collection(self.animated)
        self.set_unit_system(self.project.unit_system)

    def set_unit_system(self, key):
        self.project.unit_system = key
        u = self.project.units
        self.reference.set_segments([u.to_display(base, "length") for base, _ in self.paths])
        full = np.vstack([point for base, motion in self.paths for point in (base, base+self.factor*motion)])
        low, high = full.min(axis=0), full.max(axis=0)
        padding = max(float((high-low).max())*.08, 1.)
        for index, axis in enumerate(("x", "y", "z") if self.spatial else ("x", "y")):
            getattr(self.ax, f"set_{axis}lim")(u.to_display(low[index]-padding, "length"), u.to_display(high[index]+padding, "length"))
            getattr(self.ax, f"set_{axis}label")(f"Global {axis.upper()} ({u.length})")
        if self.spatial:
            self.ax.set_box_aspect(high-low+2*padding)
        else:
            self.ax.set_aspect("equal", adjustable="box")
        self.apply_theme()
        # Rebuild/update labels without resampling the solver or resetting phase.
        peak = max(float(np.linalg.norm(m, axis=1).max()) for _, m in self.paths)
        self.status.setText(f"{self.result.combination} | Factor {self.factor:.6g}x | Sampled peak {u.to_display(peak, 'length'):.6g} {u.length} (unamplified). Dashed reference; coloured shape animated.")
        self.draw_fraction()

    def draw_fraction(self):
        u, fraction = self.project.units, self.fraction.value()
        self.animated.set_segments([u.to_display(base+self.factor*fraction*motion, "length") for base, motion in self.paths])
        self.ax.set_title(f"Static displacement field | {self.result.combination} | fraction {fraction:.3f} × {self.factor:.5g}x")
        self.canvas.draw_idle()

    def scrub(self, fraction):
        self.pause()
        self.phase = math.acos(1-2*fraction)/(2*math.pi)
        self.draw_fraction()

    def playback(self, running):
        self.play.setText("Pause" if running else "Play")
        if running:
            self.origin = time.monotonic()-self.phase*self.duration.value()
            self.timer.start()
        else:
            self.timer.stop()

    def tick(self):
        self.phase = ((time.monotonic()-self.origin)/self.duration.value()) % 1.
        fraction = .5*(1-math.cos(2*math.pi*self.phase))
        self.fraction.blockSignals(True)
        self.fraction.setValue(fraction)
        self.fraction.blockSignals(False)
        self.draw_fraction()

    def pause(self, *unused):
        self.play.setChecked(False)
        self.timer.stop()

    def reset_frame(self):
        self.pause()
        self.phase = 0.
        self.fraction.setValue(0.)
        self.draw_fraction()

    def hideEvent(self, event):
        self.pause()
        super().hideEvent(event)

    def apply_theme(self):
        if not hasattr(self, "ax"):
            return
        self.reference.set_color(colors()["member"])
        self.animated.set_color(colors()["load"])
        style_axes(self.ax)
        if self.spatial:
            self.ax.zaxis.label.set_color(colors()["text"])
        self.canvas.draw_idle()
