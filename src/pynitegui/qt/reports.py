"""Unit-aware snapshot exports, shared by the editor and retained diagrams."""
import csv
import base64
from dataclasses import dataclass
from html import escape
import io
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QMarginsF, QUrl, Qt
from PySide6.QtGui import QFont, QImage, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QListWidget, QListWidgetItem, QMenu, QMessageBox

from .analysis import model_signature
from .diagrams import draw_structure, member_result_rows
from .theme import LIGHT


@dataclass(frozen=True)
class ReportOptions:
    model: bool = True
    nodes: bool = True
    members: bool = True
    diagrams: tuple[str, ...] = ()
    side: int = 1
    sign: int = 1
    amplitude: float = 20
    envelope_combinations: tuple[str, ...] = ()
    supports: bool = True
    loads: bool = True

    def validate(self):
        if any(type(value) is not bool for value in (self.model, self.nodes, self.members, self.supports, self.loads)):
            raise ValueError("Report section choices must be boolean values.")
        if not isinstance(self.diagrams, tuple) or any(key not in ("axial", "shear", "moment") for key in self.diagrams):
            raise ValueError("Unknown report diagram selection.")
        if len(set(self.diagrams)) != len(self.diagrams):
            raise ValueError("Duplicate report diagrams.")
        if (not isinstance(self.envelope_combinations, tuple) or
                any(not isinstance(name, str) or not name for name in self.envelope_combinations) or
                len(set(self.envelope_combinations)) != len(self.envelope_combinations)):
            raise ValueError("Select distinct named envelope combinations.")
        if not any((self.model, self.nodes, self.members, self.diagrams, self.envelope_combinations)):
            raise ValueError("Select at least one report section.")
        if type(self.side) is not int or self.side not in (-1, 1) or type(self.sign) is not int or self.sign not in (-1, 1):
            raise ValueError("Report diagram side/sign must be +1 or -1.")
        if isinstance(self.amplitude, bool) or not isinstance(self.amplitude, (int, float)) or not 2 <= self.amplitude <= 60:
            raise ValueError("Report diagram amplitude must be between 2 and 60 percent.")


class ReportOptionsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Analysis Report")
        self.resize(460, 360)
        self.definition = None
        envelope_view = getattr(parent, "envelopes", None)
        envelope_only = hasattr(parent, "selected_combinations")
        if envelope_only:
            envelope_view = parent
        result = getattr(parent, "result", None)
        form = QFormLayout(self)
        self.sections = {}
        for key, label in (("model", "Model definitions"), ("nodes", "Node results"), ("members", "Member results")):
            widget = QCheckBox(label)
            widget.setChecked(not envelope_only)
            self.sections[key] = widget
            form.addRow(widget)
        self.diagrams = {}
        selected = parent.quantity.currentData() if hasattr(parent, "quantity") else "moment"
        for key, label in (("axial", "Axial-force diagram"), ("shear", "Shear-force diagram"), ("moment", "Bending-moment diagram")):
            widget = QCheckBox(label)
            widget.setChecked(key == selected and not envelope_only)
            self.diagrams[key] = widget
            form.addRow(widget)
        self.include_envelopes = QCheckBox("Combination envelopes")
        self.include_envelopes.setChecked(envelope_only or
                                         (envelope_view is not None and parent.tabs.currentWidget() is envelope_view))
        self.include_envelopes.setEnabled(result is not None)
        form.addRow(self.include_envelopes)
        self.envelope_combinations = QListWidget()
        self.envelope_combinations.setMaximumHeight(100)
        checked = envelope_view.selected_combinations() if envelope_view is not None else ()
        if result is not None:
            for name in result.solver.load_combos:
                item = QListWidgetItem(name, self.envelope_combinations)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if name in checked or envelope_view is None else Qt.CheckState.Unchecked)
        self.envelope_combinations.setEnabled(self.include_envelopes.isChecked())
        self.include_envelopes.toggled.connect(self.envelope_combinations.setEnabled)
        form.addRow("Envelope combinations", self.envelope_combinations)
        self.side = QComboBox()
        self.side.addItem("Default side", 1)
        self.side.addItem("Opposite side", -1)
        self.side.setCurrentIndex(1 if hasattr(parent, "diagram_side") and parent.diagram_side.currentData() == -1 else 0)
        self.sign = QCheckBox("Reverse diagram display signs")
        self.sign.setChecked(hasattr(parent, "reverse_sign") and parent.reverse_sign.isChecked())
        self.amplitude = QDoubleSpinBox()
        self.amplitude.setRange(2, 60)
        self.amplitude.setSuffix(" %")
        self.amplitude.setValue(parent.amplitude.value() if hasattr(parent, "amplitude") else 20)
        self.amplitude.setKeyboardTracking(False)
        form.addRow("Diagram side", self.side)
        form.addRow(self.sign)
        form.addRow("Diagram amplitude", self.amplitude)
        self.supports = QCheckBox("Diagram supports and springs")
        self.loads = QCheckBox("Diagram factored loads")
        for key, source in (("supports", "show_supports"), ("loads", "show_loads")):
            widget = getattr(self, key)
            widget.setChecked(getattr(parent, source).isChecked() if hasattr(parent, source) else True)
            form.addRow(widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Preview")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        combinations = tuple(self.envelope_combinations.item(index).text() for index in range(self.envelope_combinations.count())
                             if self.envelope_combinations.item(index).checkState() == Qt.CheckState.Checked)
        if self.include_envelopes.isChecked() and not combinations:
            QMessageBox.warning(self, "Analysis Report", "Select at least one envelope combination.")
            return
        options = ReportOptions(**{key: widget.isChecked() for key, widget in self.sections.items()},
                                diagrams=tuple(key for key, widget in self.diagrams.items() if widget.isChecked()),
                                side=self.side.currentData(), sign=-1 if self.sign.isChecked() else 1,
                                amplitude=self.amplitude.value(),
                                supports=self.supports.isChecked(), loads=self.loads.isChecked(),
                                envelope_combinations=combinations if self.include_envelopes.isChecked() else ())
        try:
            options.validate()
        except ValueError as error:
            QMessageBox.warning(self, "Analysis Report", str(error))
            return
        self.definition = options
        super().accept()


def html_table(headers, rows):
    def value_text(value):
        return value if isinstance(value, str) else format(value, ".6g")
    heading = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(value_text(value))}</td>" for value in row) + "</tr>" for row in rows)
    return f'<table width="100%" border="1" cellspacing="0" cellpadding="4"><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table>'


def model_definition_tables(project):
    units = project.units
    show = units.to_display
    nodes = (["Node", f"X ({units.length})", f"Y ({units.length})", "Support", "DX", "DY", "RZ",
              f"Spring DX ({units.stiffness})", f"Spring DY ({units.stiffness})", f"Spring RZ ({units.rotational_stiffness})"],
             [[node.name, show(node.x, "length"), show(node.y, "length"), node.support,
               *("Fixed" if fixed else "Free" for fixed in node.restraints),
               show(node.spring_x, "stiffness"), show(node.spring_y, "stiffness"), show(node.spring_rz, "rotational_stiffness")]
              for node in project.nodes.values()])
    members = (["Member", "Start", "End", "Type", "Material", "Section", "Start hinge", "End hinge", "Start releases (local)", "End releases (local)"],
               [[m.name, m.start, m.end, m.kind, m.material, m.section,
                 *("Yes" if release else "No" for release in m.moment_releases), *m.release_labels] for m in project.members.values()])
    materials = (["Material", f"E ({units.stress})", "Poisson ratio", f"G ({units.stress})", f"Weight ({units.density})", "Source"],
                 [[m.name, show(m.E, "stress"), m.nu, show(m.G, "stress"), show(m.rho, "density"), m.source_label]
                  for m in project.materials.values()])
    sections = (["Section", f"Area ({units.area})", f"Iy ({units.inertia})", f"Iz ({units.inertia})", f"J ({units.inertia})", "Source"],
                [[s.name, show(s.A, "area"), *(show(getattr(s, key), "inertia") for key in ("Iy", "Iz", "J")), s.source_label]
                 for s in project.sections.values()])
    def load_rows(loads):
        rows = []
        for load in loads:
            quantity = "intensity" if load.kind == "distributed" else "moment" if load.direction == "MZ" else "force"
            rows.append([load.name, load.target, load.case, load.kind, load.direction,
                         show(load.magnitude, quantity), getattr(units, quantity),
                         load.position if load.target in project.members else "",
                         show(load.end_magnitude, "intensity") if load.kind == "distributed" else "",
                         load.end_position if load.kind == "distributed" else "",
                         load.angle if load.direction in ("Angle", "Local angle") else ""])
        return rows
    load_headers = ["Load", "Target", "Case", "Type", "Direction", "Magnitude / start", "Units", "Start fraction",
                    f"End ({units.intensity})", "End fraction", "Angle (deg)"]
    combos = (["Combination", "Case factors"],
              [[name, ", ".join(f"{case}: {factor:.6g}" for case, factor in factors.items())] for name, factors in project.combinations.items()])
    return [("Nodes and Supports", *nodes), ("Members and Assignments", *members),
            ("Materials", *materials), ("Sections", *sections),
            ("Manual Loads (Unfactored)", load_headers, load_rows(project.loads.values())),
            ("Generated Self-Weight (Unfactored)", load_headers, load_rows(project.self_weight_loads())),
            ("Load Combinations", *combos)]


def report_images(project, result, options):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    images = {}
    for quantity in options.diagrams:
        figure = Figure(figsize=(9, 4.8), layout="constrained")
        FigureCanvasAgg(figure)
        draw_structure(figure.add_subplot(111), project, result, quantity, options.amplitude,
                       options.side, options.sign, palette=LIGHT, supports=options.supports, loads=options.loads)
        stream = io.BytesIO()
        figure.savefig(stream, format="png", dpi=160)
        images[quantity] = stream.getvalue()
        figure.clear()
    return images


def result_table(project, result, kind):
    if result.model_signature != model_signature(project):
        raise ValueError("The project does not match this analysis snapshot. Analyze the current model or export from its retained diagram window.")
    units = project.units
    if kind == "nodes":
        headers = ["Node", f"DX ({units.length})", f"DY ({units.length})", "RZ (rad)",
                   f"FX ({units.force})", f"FY ({units.force})", f"MZ ({units.moment})"]
        rows = []
        for name, displacements in result.displacements.items():
            values = (*displacements, *result.reactions[name])
            rows.append([name, *("n/a" if value is None else units.to_display(value, quantity)
                                 for value, quantity in zip(values, ("length", "length", "rotation", "force", "force", "moment")))])
    elif kind == "members":
        headers = ["Member", "Station", f"x ({units.length})", f"N ({units.force})", f"Fy ({units.force})",
                   f"Mz ({units.moment})", f"dy ({units.length})"]
        rows = [[*row[:2], *("" if value is None else units.to_display(value, quantity)
                            for value, quantity in zip(row[2:], ("length", "force", "force", "moment", "length")))]
                for row in member_result_rows(project, result)]
    else:
        raise ValueError("Unknown result export type.")
    return headers, rows


def csv_text(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(path, project, result, kind, source="Untitled"):
    headers, rows = result_table(project, result, kind)
    metadata = [source, result.snapshot_id, result.analyzed_at, result.model_signature, result.combination, project.units.label,
                project.self_weight_case or "", project.self_weight_factor if project.self_weight_case is not None else ""]
    path, temporary = Path(path), None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream)
            writer.writerow(["Source", "Analysis ID", "Analyzed (UTC)", "Model signature", "Combination", "Unit system",
                             "Self-weight case", "Self-weight factor", *headers])
            writer.writerows([csv_text(value) for value in (*metadata, *row)] for row in rows)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def report_html(project, result, source="Untitled", options=None, *, image_urls=None):
    options = options or ReportOptions()
    options.validate()
    # Check identity even when no numerical result tables are selected.
    result_table(project, result, "nodes")
    def table(kind):
        headers, rows = result_table(project, result, kind)
        return html_table(headers, rows)
    factors = ", ".join(f"{case}: {factor:.6g}" for case, factor in result.solver.load_combos[result.combination].factors.items())
    weight = "Off" if project.self_weight_case is None else f"{project.self_weight_case}; factor {project.self_weight_factor:.6g}"
    if options.envelope_combinations and not any((options.nodes, options.members, options.diagrams)):
        combination_metadata = "<b>Envelope combinations:</b> " + escape(", ".join(options.envelope_combinations))
    else:
        label = "Single-combination results" if options.envelope_combinations else "Combination"
        combination_metadata = f"<b>{label}:</b> {escape(result.combination)} | <b>Factors:</b> {escape(factors)}"
    sections = []
    if options.model:
        sections.append("<h2>Model Definitions</h2><p>Loads below are unfactored; results and diagrams use the selected combination. Member positions are start-to-end fractions. Global angles are counterclockwise from +X; local angles are from member +x.</p>")
        sections.extend(f"<h3>{escape(title)}</h3>{html_table(headers, rows)}" for title, headers, rows in model_definition_tables(project))
        sections.append(f"<p>Default material: {escape(project.default_material)} | Default section: {escape(project.default_section)} | Default load case: {escape(project.default_load_case)}</p>")
    if options.nodes:
        page = ' style="page-break-before: always"' if options.model else ""
        sections.append(f"<h2{page}>Node Displacements and Support Reactions</h2>" +
                        "<p>RZ is n/a where released member ends have no shared nodal rotation.</p>" + table("nodes"))
    if options.members:
        page = ' style="page-break-before: always"' if options.model or options.nodes else ""
        sections.append(f"<h2{page}>Member End Values and Extrema</h2>" +
                        "<p>Member values use local solver axes; N is positive in compression. Min/max columns are independent extrema, not forces at one shared station. Display amplification does not affect these results.</p>" + table("members"))
    if options.envelope_combinations:
        from .envelopes import HEADERS, display_rows, envelope_rows
        rows = list(display_rows(project, envelope_rows(project, result, options.envelope_combinations)))
        page = ' style="page-break-before: always"' if sections else ""
        selected_factors = [(name, ", ".join(f"{case}: {factor:.6g}" for case, factor in result.solver.load_combos[name].factors.items()))
                            for name in options.envelope_combinations]
        sections.append(f"<h2{page}>Selected-Combination Envelopes</h2>" +
                        "<p>These bounds compare the combinations below, independently of the single-combination sections. "
                        "Each result has its own governing combination, not one simultaneous load state. "
                        "Member extrema are solver extrema over the full member, in local axes with N positive in compression. "
                        "First selected combination wins ties; undefined joint rotations remain n/a. "
                        "Diagram side/sign settings do not change envelope results.</p>" +
                        html_table(("Combination", "Case factors"), selected_factors) +
                        "<h3>Node Envelopes</h3>" + html_table(HEADERS, [row for row in rows if row[0] == "Node"]))
        sections.append('<h2 style="page-break-before: always">Member Envelopes</h2>' +
                        "<p>Independent full-member solver extrema in the selected units; minimum and maximum combinations may differ.</p>" +
                        html_table(HEADERS, [row for row in rows if row[0] == "Member"]))
    if image_urls is None:
        image_urls = {key: "data:image/png;base64," + base64.b64encode(data).decode("ascii")
                      for key, data in report_images(project, result, options).items()}
    titles = {"axial": "Axial-Force Diagram", "shear": "Shear-Force Diagram", "moment": "Bending-Moment Diagram"}
    for quantity in options.diagrams:
        side = "default" if options.side == 1 else "opposite"
        sign = "standard" if options.sign == 1 else "reversed"
        sections.append(f'<h2 style="page-break-before: always">{titles[quantity]}</h2>'
                        f'<p>Analysis {escape(result.snapshot_id)} | {escape(result.combination)} | {escape(project.units.label)}<br>'
                        f'Placement: {side} side | Diagram display signs: {sign} | Amplitude: {options.amplitude:g}%<br>'
                        f'Supports/springs: {"shown" if options.supports else "hidden"} | '
                        f'Factored combination loads: {"shown" if options.loads else "hidden"}<br>'
                        'Member tables and CSV keep the local solver signs.</p>'
                        f'<img src="{escape(image_urls[quantity], quote=True)}" width="800" height="427">')
    return f'''<html><head><style>
        body {{ font-family: sans-serif; color: #24343b; }}
        h1 {{ font-size: 20pt; }} h2 {{ font-size: 12pt; }} h3 {{ font-size: 10pt; }}
        th {{ background-color: #e5ebed; text-align: left; }}
        td {{ text-align: right; }} table {{ border-color: #bac6cb; }}
        </style></head><body><h1>PyniteGUI Analysis Results</h1>
        <p><b>Source:</b> {escape(source)}<br>
        <b>Analysis ID:</b> {escape(result.snapshot_id)} | <b>Model:</b> {escape(result.model_signature[:12])}<br>
        <b>Analyzed (UTC):</b> {escape(result.analyzed_at)}<br>
        {combination_metadata}<br>
        <b>Units:</b> {escape(project.units.label)}<br>
        <b>Self-weight:</b> {escape(weight)}</p>
        {''.join(sections)}</body></html>'''


def report_document(project, result, source="Untitled", options=None):
    options = options or ReportOptions()
    options.validate()
    result_table(project, result, "nodes")
    document = QTextDocument()
    document.setDefaultFont(QFont("DejaVu Sans", 9))
    document.setDocumentMargin(0)
    images = report_images(project, result, options)
    urls = {key: f"pynitegui-report:{key}" for key in images}
    for key, data in images.items():
        document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(urls[key]), QImage.fromData(data, "PNG"))
    document.setHtml(report_html(project, result, source, options, image_urls=urls))
    return document


def report_printer():
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    return printer


class ResultExportMenu(QMenu):
    def __init__(self, parent, current):
        super().__init__("Export Results", parent)
        self.current = current
        for label, kind in (("Node Results (CSV)...", "nodes"), ("Member Results (CSV)...", "members")):
            self.addAction(label, lambda checked=False, kind=kind: self.save_csv(kind))
        self.addSeparator()
        self.addAction("Print Results...", self.print_report)

    def save_csv(self, kind):
        project, result, source = self.current()
        if result is None:
            return
        filename, _ = QFileDialog.getSaveFileName(self.parentWidget(), "Export Results", f"results-{result.snapshot_id}-{kind}.csv", "CSV (*.csv)")
        if not filename:
            return
        try:
            export_csv(filename, project, result, kind, source)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.parentWidget(), "Export Results", str(error))

    def print_report(self):
        project, result, source = self.current()
        if result is None:
            return
        choices = ReportOptionsDialog(self.parentWidget())
        if not choices.exec():
            return
        try:
            document = report_document(project, result, source, choices.definition)
            printer = report_printer()
            printer.setDocName(f"PyniteGUI Results {result.snapshot_id}")
            preview = QPrintPreviewDialog(printer, self.parentWidget())
            options = choices.definition
            scope = "Envelopes" if options.envelope_combinations and not any((options.nodes, options.members, options.diagrams)) else result.combination
            preview.setWindowTitle(f"Analysis Report | {scope} | {result.snapshot_id}")
            preview.resize(1050, 750)
            preview.paintRequested.connect(document.print_)
            preview.exec()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.parentWidget(), "Print Results", str(error))
