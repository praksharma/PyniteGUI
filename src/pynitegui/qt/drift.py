"""Explicit node-pair drift from one retained static analysis; no code checks."""
import csv
import math
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from .envelopes import selected_results


def drift_rows(project, result, pairs, combinations):
    """Signed (upper displacement - lower displacement) / positive Y height."""
    results = selected_results(project, result, combinations)
    rows = []
    spatial = getattr(project, "dimension", "2D") == "3D"
    if len(set(pairs)) != len(pairs):
        raise ValueError("This node pair and direction are already listed.")
    for lower, upper, axis in pairs:
        if lower not in project.nodes or upper not in project.nodes or axis not in (("X", "Z") if spatial else ("X",)):
            raise ValueError("Choose existing nodes and a horizontal global direction.")
        height = project.nodes[upper].y - project.nodes[lower].y
        if height <= 1e-8:
            raise ValueError("Upper node must have a higher global Y elevation than the lower node.")
        index = 0 if axis == "X" else 2
        values = []
        for selected in results:
            a, b = (selected.displacements[node][index] for node in (lower, upper))
            if not all(v is not None and math.isfinite(v) for v in (a, b)):
                raise ValueError("The snapshot has no finite translation for this pair.")
            values.append((selected.combination, a, b, b-a, (b-a)/height))
        governing = max(range(len(values)), key=lambda i: abs(values[i][4]))
        for i, (combination, a, b, delta, ratio) in enumerate(values):
            rows.append((lower, upper, axis, combination, height, a, b, delta, ratio, i == governing))
    return rows


def display_rows(project, rows):
    u = project.units
    for lower, upper, axis, combo, height, a, b, delta, ratio, governing in rows:
        yield (lower, upper, axis, combo, *(u.to_display(v, "length") for v in (height, a, b, delta)),
               ratio, "Yes" if governing else "")


def headers(project):
    unit = project.units.length
    return ("Lower node", "Upper node", "Global axis", "Combination", f"Y height ({unit})",
            f"Lower displacement ({unit})", f"Upper displacement ({unit})", f"Difference ({unit})",
            "Signed drift ratio", "Governing |ratio|")


def export_drift_csv(path, project, result, pairs, combinations, source):
    from .reports import csv_text
    rows = list(display_rows(project, drift_rows(project, result, pairs, combinations)))
    if not rows:
        raise ValueError("Add at least one explicit node pair before exporting.")
    metadata = (Path(source).name, result.snapshot_id, result.analyzed_at, result.model_signature,
                result.method_label, project.units.summary,
                "Static signed delta/h; global Y height; largest absolute ratio per pair; first combination wins ties; no code check")
    path, temporary = Path(path), None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream)
            writer.writerow(("Source", "Analysis ID", "Analyzed (UTC)", "Model signature", "Analysis method",
                             "Units", "Convention", *headers(project)))
            writer.writerows([csv_text(v) for v in (*metadata, *row)] for row in rows)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class DriftWidget(QWidget):
    def __init__(self, parent, project, result, source):
        super().__init__(parent)
        self.project, self.result, self.source = project, result, source
        self.pairs = []
        layout = QVBoxLayout(self)
        note = QLabel("Static drift from explicit node pairs: (upper displacement − lower displacement) / Y height. "
                      "No rigid-floor assumption, seismic amplification or code pass/fail. Governing uses the largest absolute ratio per pair; first combination wins ties.")
        note.setWordWrap(True)
        layout.addWidget(note)
        controls = QHBoxLayout()
        self.lower, self.upper, self.axis, self.combination = QComboBox(), QComboBox(), QComboBox(), QComboBox()
        for label, control in (("Lower", self.lower), ("Upper", self.upper)):
            control.addItems(list(project.nodes))
            controls.addWidget(QLabel(label))
            controls.addWidget(control)
        self.axis.addItems(["X", "Z"] if getattr(project, "dimension", "2D") == "3D" else ["X"])
        controls.addWidget(QLabel("Global direction"))
        controls.addWidget(self.axis)
        self.add = QPushButton("Add pair")
        self.add.clicked.connect(self.add_pair)
        controls.addWidget(self.add)
        layout.addLayout(controls)
        controls = QHBoxLayout()
        self.combination.addItem("All analyzed combinations", None)
        for name in result.solver.load_combos:
            self.combination.addItem(name, name)
        self.combination.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.combination, 1)
        self.remove = QPushButton("Remove selected pair")
        self.remove.clicked.connect(self.remove_pair)
        controls.addWidget(self.remove)
        self.export = QPushButton("Export CSV…")
        self.export.clicked.connect(self.export_csv)
        controls.addWidget(self.export)
        layout.addLayout(controls)
        self.message = QLabel("Add lower/upper nodes explicitly; each column can have its own pairs.")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        self.table = QTableWidget(0, 10)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(lambda: self.remove.setEnabled(self.table.currentRow() >= 0))
        layout.addWidget(self.table)
        self.refresh()

    def combinations(self):
        name = self.combination.currentData()
        return tuple(self.result.solver.load_combos) if name is None else (name,)

    def add_pair(self):
        candidate = [*self.pairs, (self.lower.currentText(), self.upper.currentText(), self.axis.currentText())]
        try:
            drift_rows(self.project, self.result, candidate, self.combinations())
        except ValueError as error:
            self.message.setText(str(error))
            return
        self.pairs = candidate
        self.message.setText("Pairs belong to this retained snapshot window; they do not edit model definitions.")
        self.refresh()

    def remove_pair(self):
        row = self.table.currentRow()
        if row >= 0:
            pair = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.pairs.remove(tuple(pair))
            self.refresh()

    def refresh(self, *unused):
        rows = drift_rows(self.project, self.result, self.pairs, self.combinations())
        self.table.setHorizontalHeaderLabels(headers(self.project))
        self.table.setRowCount(len(rows))
        for i, (raw, row) in enumerate(zip(rows, display_rows(self.project, rows))):
            for j, value in enumerate(row):
                item = QTableWidgetItem(value if isinstance(value, str) else f"{value:.10g}")
                item.setData(Qt.ItemDataRole.UserRole, raw[:3])
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.remove.setEnabled(self.table.currentRow() >= 0)
        self.export.setEnabled(bool(rows))

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Static Drift", "storey-drift.csv", "CSV (*.csv)")
        if path:
            try:
                export_drift_csv(path, self.project, self.result, self.pairs, self.combinations(), self.source)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Export failed", str(error))
