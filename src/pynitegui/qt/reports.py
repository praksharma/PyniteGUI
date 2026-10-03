"""Unit-aware snapshot exports, shared by the editor and retained diagrams."""
import csv
from html import escape
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox

from .analysis import model_signature
from .diagrams import member_result_rows


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
    metadata = [source, result.snapshot_id, result.analyzed_at, result.model_signature, result.combination, project.units.label]
    path, temporary = Path(path), None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream)
            writer.writerow(["Source", "Analysis ID", "Analyzed (UTC)", "Model signature", "Combination", "Unit system", *headers])
            writer.writerows([csv_text(value) for value in (*metadata, *row)] for row in rows)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def report_html(project, result, source="Untitled"):
    def table(kind):
        headers, rows = result_table(project, result, kind)
        heading = "".join(f"<th>{escape(header)}</th>" for header in headers)
        body = "".join("<tr>" + "".join(f"<td>{escape(value if isinstance(value, str) else format(value, '.6g'))}</td>"
                                       for value in row) + "</tr>" for row in rows)
        return f'<table width="100%" border="1" cellspacing="0" cellpadding="5"><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table>'
    factors = ", ".join(f"{case}: {factor:.6g}" for case, factor in result.solver.load_combos[result.combination].factors.items())
    return f'''<html><head><style>
        body {{ font-family: sans-serif; color: #24343b; }}
        h1 {{ font-size: 20pt; }} h2 {{ font-size: 12pt; }}
        th {{ background-color: #e5ebed; text-align: left; }}
        td {{ text-align: right; }} table {{ border-color: #bac6cb; }}
        </style></head><body><h1>PyniteGUI Analysis Results</h1>
        <p><b>Source:</b> {escape(source)}<br>
        <b>Analysis ID:</b> {escape(result.snapshot_id)} | <b>Model:</b> {escape(result.model_signature[:12])}<br>
        <b>Analyzed (UTC):</b> {escape(result.analyzed_at)}<br>
        <b>Combination:</b> {escape(result.combination)} | <b>Factors:</b> {escape(factors)}<br>
        <b>Units:</b> {escape(project.units.label)}</p>
        <h2>Node Displacements and Support Reactions</h2>{table('nodes')}
        <p>RZ is n/a where released member ends have no shared nodal rotation.</p>
        <h2>Member End Values and Extrema</h2>{table('members')}
        <p>Member values use local solver axes; N is positive in compression.
        Min/max columns are independent extrema, not forces at one shared station.
        Display amplification does not affect these results.</p></body></html>'''


def report_document(project, result, source="Untitled"):
    document = QTextDocument()
    document.setDefaultFont(QFont("DejaVu Sans", 9))
    document.setDocumentMargin(0)
    document.setHtml(report_html(project, result, source))
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
        try:
            document = report_document(project, result, source)
            printer = report_printer()
            printer.setDocName(f"PyniteGUI Results {result.snapshot_id}")
            preview = QPrintPreviewDialog(printer, self.parentWidget())
            preview.setWindowTitle(f"Analysis Report | {result.combination} | {result.snapshot_id}")
            preview.resize(1050, 750)
            preview.paintRequested.connect(document.print_)
            preview.exec()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.parentWidget(), "Print Results", str(error))
