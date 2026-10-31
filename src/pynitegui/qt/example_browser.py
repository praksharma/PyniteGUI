"""Offline example discovery; previewing never replaces or analyzes a model."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from .analysis_method import METHODS
from .examples import EXAMPLES as FRAME_EXAMPLES, EXAMPLE_GROUPS as FRAME_GROUPS, example_project
from .official_plate import (PLATE_EXAMPLES, PLATE_CATEGORY, PLATE_NOTES,
                             example_definition, preview_project, loading_summary as plate_loading_summary)
from .theme import colors

EXAMPLES = {**FRAME_EXAMPLES, **PLATE_EXAMPLES}
EXAMPLE_GROUPS = {**FRAME_GROUPS, PLATE_CATEGORY: tuple(PLATE_EXAMPLES)}


# Reference values carry explicit units, independent of the editor's display
# preference. Detailed scope/provenance belongs to GUIDE.md.
NOTES = {
    "simple_beam": ("Simply supported beam with a downward midspan point load.", "Service: 5 kip vertical reaction at each support."),
    "portal": ("Fixed-base portal with uniform gravity load and lateral force.", "Service: total FY reaction 6 kip; total FX reaction -2 kip."),
    "cantilever": ("Partial distributed load, inclined force, tip force and moment.", "Service: total FY reaction 6.89205 kip; FX -1 kip."),
    "continuous": ("Two-span continuous beam with partial, triangular and point loads.", "Service: total FY reaction 12.4 kip."),
    "pitched": ("Pitched roof frame with member-local distributed forces.", "Service: total FY reaction 7.2 kip."),
    "multistorey": ("Two-storey frame with separate gravity and wind cases.", "Gravity: total FY 9.6 kip. Wind: total FX -3 kip."),
    "self_weight": ("Beam loaded only by automatic member self-weight.", "Each support carries half the member weight; no extra applied load."),
    "truss": ("Planar triangular, bilateral axial-only truss.", "Service: 5 kip vertical reaction at each support; joint rotations are n/a."),
    "elastic": ("Cantilever with bilateral translational and rotational base springs.", "Service: base DY -0.01 in; total FY reaction 10 kip."),
    "inclined_roller": ("Pin and frictionless roller with a 30-degree global tangent.", "Service: N2 FX -0.346410 kip, FY +0.6 kip; N1 FX +0.346410 kip, FY +0.6 kip. Roller motion follows its tangent."),
    "support_settlement": ("120 in fixed-ended beam. Right support moves -0.1 in in Y and rotates +0.001 rad in every combination, under -0.01 kip/in. Includes reversed load and settlement-only cases.", "Settlement only: N1 FY +16.433333 kip / MZ +862.75 kip-in; N2 FY -16.433333 kip / MZ +1109.25 kip-in. Imposed motion does not change with load factors."),
    "3d_inclined_roller": ("Frictionless support with normal azimuth 60 degrees (+X toward +Z) and elevation 30 degrees toward +Y; two free tangent translations.", "Normal (0.433013, 0.5, 0.75). Normal displacement and global force/moment residuals are zero within numerical tolerance. Reversed and Zero combinations are included."),
    "shear_release": ("Fixed-guided beam with a released member-end transverse translation.", "Released end transfers zero member shear; fixed nodal translations stay zero."),
    "3d_cantilever": ("Spatial cantilever with biaxial bending and torsion.", "Service: base FY 1.9 kip, FZ -0.5 kip and MX -5 kip-in."),
    "3d_space_frame": ("Four-column spatial frame with gravity and wind cases.", "Gravity: total FY 12.6 kip. Wind: total FX -1 kip and FZ -1.5 kip."),
    "3d_slab_frame": ("Experimental frame/slab coupling with pressure and uplift.", "Gravity: 10.8 kip FY per base; total 43.2 kip. Linear elastic only."),
    "3d_tripod": ("Three axial-only spatial bars supporting one loaded joint.", "Service: 1 kip vertical reaction per base; free-joint rotations are n/a."),
    "3d_multistorey_slabs": ("Three floors of coupled elastic concrete slabs and steel frames.", "Gravity: 45.9 kip FY per base; Factored: 60.48 kip per base. Self-weight off."),
    "p_delta_column": ("Segmented slender column with gravity-induced sway amplification.", "Combined: tip DX 3.9919 in; Lateral: 2.4925 in. P-Delta recovery may flag force residuals."),
    "official_beam_point": ("Official PyNite adaptation: 14-foot beam with D/L point loads.", "1.2D+1.6L: each FY 9.4 kip; midspan dy -0.42692855 in."),
    "official_beam_uniform": ("Official PyNite adaptation: 14-foot beam under 200 lb/ft.", "Combo 1: each FY 1.4 kip; midspan dy -0.03974069 in."),
    "official_beam_envelope": ("Official PyNite adaptation: signed D/S/L point loads and factored envelopes.", "Mz envelope: -222.17143 kip-in (1.2D+1.6L) to +596.57143 kip-in (1.2D+1.6S)."),
    "official_moment_frame": ("Official PyNite adaptation: moment frame with explicit weights, wind and P-Delta.", "1.2D+1.0W: N2 DX 0.48084117 in; N1 FY -2.10031058 kip (uplift). Recovery can flag force residuals."),
    "official_p_delta": ("Official PyNite adaptation: six-node, 20-foot elastic column benchmark.", "Combo 1: tip DX about 40.2722 in; tangent reference 40.2740 in. Recovery can flag force residuals."),
    "3d_official_space_frame_1": ("Official PyNite adaptation: three orthogonal cantilever arms joined at a loaded node, preserving independent G.", "Combo 1: N1 DY -0.01399513 in; RX -0.00399609 rad. E 30000 ksi, G 10000 ksi, nu 0.3."),
    "3d_official_space_frame_2": ("Official PyNite adaptation: spatial bent frame with biaxial loading and torsion, preserving independent G.", "Combo 1: N2 DY -0.06223194 in; N3 DZ 1.82176236 in. Check the guide for precise benchmarks."),
    "3d_official_truss": ("Official PyNite adaptation: metre/kN space truss, converted to axial bars.", "Combo 1: BC -32.65333 kN and BD -45.23538 kN (tension); BE +112.05467 kN (compression)."),
    "gerber": ("Continuous beam and suspended span sharing an internal moment hinge.", "Service: FY at N1 = 0.15 kip, N2 = 2.25 kip, N4 = 0.6 kip. Both hinge-end moments zero."),
    "three_hinged_arch": ("Polygonal arch with pinned bases and a shared crown moment hinge.", "Service: each FY 7.5 kip; left FX +6.25 kip, right FX -6.25 kip; crown moments zero."),
}
NOTES["p_delta_support_motion"] = (
    "Elastic second-order column with base DX +0.03 in and RZ +0.0007 rad unchanged in every combination.",
    "Combined: tip DX about 3.51866 in. Base motion only: DX -0.306 in and zero member forces. Gravity amplifies the base-rotation response; refine the explicit segments.")
NOTES.update(PLATE_NOTES)
from .official_unilateral import NOTES as UNILATERAL_NOTES
NOTES.update(UNILATERAL_NOTES)
from .steel_examples import NOTES as STEEL_NOTES
NOTES.update(STEEL_NOTES)
NOTES["3d_released_beam"] = ("Inclined, rolled beam with local RY/RZ released at both ends. N1 anchors torsion; its released bending rotations do not clamp the member.",
    "Local end My/Mz are zero; both uniform-load reactions balance. Recovered member-end bending slopes are nonzero even when shared nodal rotations are undefined.")
NOTES["3d_sliding_beam"] = ("Inclined, rolled fixed-guided beam: end-j DX/DY/DZ are released while its rotations remain connected. Both joints are fixed; member-side motion is separate.",
    "End-j axial force and both shears are zero. Local released end dx = qx L²/(2EA), dy = qy L⁴/(24EIz), dz = qz L⁴/(24EIy); joint translations remain zero. Idealized linear connection.")


def loading_summary(project):
    units = project.units
    lines = [f"{len(project.nodes)} nodes · {len(project.members)} members · {len(getattr(project, 'surfaces', {}))} surfaces",
             f"{getattr(project, 'dimension', '2D')} · {METHODS[project.analysis_method]} · {units.summary}",
             "Automatic self-weight: " + (project.self_weight_case or "off"), "", "Loads (current display units)"]
    for load in project.loads.values():
        distributed = load.kind == "distributed"
        quantity = "intensity" if distributed else "moment" if load.direction.upper().startswith("M") else "force"
        unit = units.intensity if distributed else units.moment if quantity == "moment" else units.force
        value = f"{units.to_display(load.magnitude, quantity):.6g}"
        if distributed:
            value += f" to {units.to_display(load.end_magnitude, quantity):.6g}"
        if load.direction in ("Angle", "Local angle"):
            value += f" at {load.angle:g}°" + (f", elevation {load.elevation:g}°" if hasattr(load, "elevation") else "")
        where = f" · {load.position:.0%}–{load.end_position:.0%} of span" if distributed else (
            f" · {load.position:.0%} of span" if load.target in project.members else "")
        lines.append(f"{load.case} · {load.target} · {load.direction}: {value} {unit}{where}")
    for surface, cases in getattr(project, "surface_pressures", {}).items():
        for case, value in cases.items():
            lines.append(f"{case} · {surface}: {units.to_display(value, 'pressure'):.6g} {units.pressure} pressure")
    lines.extend(("", "Combinations"))
    lines.extend(f"{name}: " + ", ".join(f"{factor:g} × {case}" for case, factor in factors.items())
                 for name, factors in project.combinations.items())
    return "\n".join(lines)

from .official_modal import KEY as MODAL_KEY, NOTES as MODAL_NOTES
NOTES[MODAL_KEY] = MODAL_NOTES


class ExamplePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.setMinimumSize(260, 190)
        self.setAccessibleName("Undeformed example geometry preview")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = colors()
        painter.fillRect(self.rect(), QColor(c["canvas"]))
        if self.project is None:
            return
        project = self.project
        spatial = getattr(project, "dimension", "2D") == "3D"

        def project_point(point):
            x, y, z = point
            return (x-.65*z, -y+.35*(x+z)) if spatial else (x, -y)

        points = {name: project_point((node.x, node.y, getattr(node, "z", 0.))) for name, node in project.nodes.items()}
        surfaces = []
        for definition in getattr(project, "surfaces", {}).values():
            from .spatial_surfaces import surface_geometry
            _, _, vertices, cells = surface_geometry(definition)
            surfaces.extend([[project_point(vertices[index]) for index in cell] for cell in cells])
        all_points = [*points.values(), *(p for cell in surfaces for p in cell)]
        if not all_points:
            return
        low = [min(p[i] for p in all_points) for i in (0, 1)]
        high = [max(p[i] for p in all_points) for i in (0, 1)]
        scale = min((self.width()-55)/max(high[0]-low[0], 1.), (self.height()-55)/max(high[1]-low[1], 1.))

        def screen(point):
            return QPointF(self.width()/2+(point[0]-(low[0]+high[0])/2)*scale,
                           self.height()/2+(point[1]-(low[1]+high[1])/2)*scale)

        painter.setPen(QPen(QColor(c["border"]), 1.))
        painter.setBrush(QColor(c["panel"]))
        for cell in surfaces:
            painter.drawPolygon(QPolygonF([screen(p) for p in cell]))
        painter.setPen(QPen(QColor(c["member"]), 2.))
        for member in project.members.values():
            painter.drawLine(screen(points[member.start]), screen(points[member.end]))
        for name, node in project.nodes.items():
            point = screen(points[name])
            painter.setPen(QPen(QColor(c["support"] if node.support == "inclined" or any(node.restraints) else c["member"]), 1.5))
            painter.setBrush(QColor(c["canvas"]))
            painter.drawEllipse(point, 3., 3.)
            if node.support == "inclined":
                from .annotations import support_geometry
                angle = node.support_angle
                if spatial:
                    import math
                    from .support_axes import support_normal
                    px, py = project_point(support_normal(node))
                    angle = math.degrees(math.atan2(px, py)) if math.hypot(px, py) > 1e-12 else 0.
                paths, circles = support_geometry('inclined', (), angle)
                for path in paths:
                    for a, b in zip(path, path[1:]):
                        painter.drawLine(point+QPointF(*a)*.65, point+QPointF(*b)*.65)
                for x, y, radius in circles:
                    painter.drawEllipse(point+QPointF(x, y)*.65, radius*.65, radius*.65)
            elif any(node.restraints):
                if node.support == "fixed":
                    painter.drawLine(point+QPointF(-7, 5), point+QPointF(7, 5))
                    for x in (-6, -1, 4):
                        painter.drawLine(point+QPointF(x, 5), point+QPointF(x-3, 9))
                else:
                    painter.drawPolygon(QPolygonF([point+QPointF(-6, 10), point+QPointF(6, 10), point+QPointF(0, 3)]))
            if len(points) <= 20:
                painter.drawText(point+QPointF(5, -5), name)
        painter.setBrush(QColor(c["canvas"]))
        painter.setPen(QPen(QColor(c["accent"]), 1.5))
        for member in project.members.values():
            if member.kind != "frame":
                continue
            for name, released in zip((member.start, member.end), member.moment_releases):
                if released:
                    painter.drawEllipse(screen(points[name]), 5., 5.)


class ExampleBrowser(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle("Browse Examples")
        self.resize(940, 730)
        self.selected_key = None
        self.unit_system = window.project.unit_system
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search examples, loads or expected results…")
        self.search.setAccessibleName("Search examples")
        self.search.setClearButtonEnabled(True)
        self.category = QComboBox()
        self.category.setAccessibleName("Example category")
        self.category.addItem("All categories", None)
        for category in EXAMPLE_GROUPS:
            self.category.addItem(category, category)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.category)
        layout.addLayout(controls)
        self.count = QLabel()
        layout.addWidget(self.count)
        splitter = QSplitter()
        self.list = QListWidget()
        self.list.setAccessibleName("Matching examples")
        splitter.addWidget(self.list)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.preview = ExamplePreview()
        right_layout.addWidget(self.preview)
        self.details = QTextBrowser()
        self.details.setAccessibleName("Example loading summary and reference checks")
        right_layout.addWidget(self.details, 1)
        splitter.addWidget(right)
        splitter.setSizes([290, 620])
        layout.addWidget(splitter, 1)
        note = QLabel("Geometry preview only; browsing does not analyze or change your model. "
                      "Frame examples ask before discarding unsaved work; plate examples open a separate workspace. Both use your current units.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        self.open_button = self.buttons.button(QDialogButtonBox.StandardButton.Open)
        self.open_button.setText("Open Example")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.search.textChanged.connect(self.filter_examples)
        self.category.currentIndexChanged.connect(self.filter_examples)
        self.list.currentItemChanged.connect(self.selection_changed)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.filter_examples()

    def filter_examples(self, *_):
        selected = self.selected_key
        query = self.search.text().casefold().split()
        category = self.category.currentData()
        self.list.blockSignals(True)
        self.list.clear()
        for group, keys in EXAMPLE_GROUPS.items():
            if category is not None and group != category:
                continue
            for key in keys:
                text = " ".join((EXAMPLES[key], group, *NOTES[key])).casefold()
                if all(term in text for term in query):
                    item = QListWidgetItem(EXAMPLES[key], self.list)
                    item.setData(Qt.ItemDataRole.UserRole, key)
                    item.setToolTip(group)
        self.count.setText(f"{self.list.count()} matching example(s)" if self.list.count() else "No matching examples. Clear the search or choose another category.")
        row = next((i for i in range(self.list.count()) if self.list.item(i).data(Qt.ItemDataRole.UserRole) == selected), 0)
        self.list.setCurrentRow(row if self.list.count() else -1)
        self.list.blockSignals(False)
        self.selection_changed()

    def selection_changed(self, *_):
        item = self.list.currentItem()
        self.selected_key = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.open_button.setEnabled(item is not None)
        if item is None:
            self.preview.project = None
            self.details.clear()
        else:
            key = self.selected_key
            if key in PLATE_EXAMPLES:
                definition = example_definition(key, self.unit_system)
                project = preview_project(definition)
                summary = plate_loading_summary(definition)
            else:
                project = example_project(key, self.unit_system)
                summary = loading_summary(project)
            self.preview.project = project
            description, check = NOTES[key]
            self.details.setPlainText(f"{EXAMPLES[key]}\n\n{description}\n\nReference checks (units as stated)\n{check}\n\n{summary}")
        self.preview.update()

    def accept(self):
        if self.selected_key is not None:
            super().accept()

    def apply_theme(self):
        self.preview.update()
