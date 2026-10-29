"""Modeless local plate inspection, refreshed by its owning workspace snapshot."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget)

from .plate_inspection import inspect_plate, plate_probe_table, write_plate_probes
from .results_panel import ResultsPanel, ResultDelegate


class PlateInspector(QDialog):
    probe_changed = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Plate Result Inspection")
        self.resize(1000, 620)
        self.result, self.units, self.probe_data = None, None, None
        self.key, self.loading = object(), False
        layout = QVBoxLayout(self)
        self.context = QLabel()
        self.context.setWordWrap(True)
        self.context.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.context)
        self.tools = QWidget()
        tools = QHBoxLayout(self.tools)
        tools.setContentsMargins(0, 0, 0, 0)
        self.element = QComboBox()
        self.element.setObjectName("plate_probe_element")
        self.element.setAccessibleName("Plate probe element")
        tools.addWidget(QLabel("Element"))
        tools.addWidget(self.element, 1)
        self.xi, self.eta = QDoubleSpinBox(), QDoubleSpinBox()
        for label, control in (("xi", self.xi), ("eta", self.eta)):
            control.setRange(-1., 1.)
            control.setDecimals(6)
            control.setSingleStep(.1)
            control.setKeyboardTracking(False)
            control.setAccessibleName("Plate probe "+label)
            tools.addWidget(QLabel(label))
            tools.addWidget(control)
            control.valueChanged.connect(self.update_probe)
        layout.addWidget(self.tools)
        self.element.currentTextChanged.connect(self.update_probe)
        note = QLabel("Click a material element in the plate plot, select a centre row, or choose an element and xi/eta. "
            "Natural coordinates range from -1 to +1; (0,0) is its centre. "
            "Interface values belong to the selected element; no averaging. Moment/shear contours remain element-centred. "
            "The table shows local centre coordinates; global XYZ is in the probe and CSV. "
            "Probes show bending resultants; corner peaks and combined face stresses are unverified.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.probe = QLabel()
        self.probe.setWordWrap(True)
        self.probe.setTextFormat(Qt.TextFormat.PlainText)
        self.probe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.probe)
        self.table = QTableWidget()
        self.table.setObjectName("plate_element_results")
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setItemDelegate(ResultDelegate(self.table))
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self.choose_row)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.export_centres = QPushButton("Export Element Centres CSV…")
        self.export_probe = QPushButton("Export Probe CSV…")
        for button in (self.export_centres, self.export_probe):
            button.setAutoDefault(False)
        self.export_centres.clicked.connect(lambda: self.export_csv(False))
        self.export_probe.clicked.connect(lambda: self.export_csv(True))
        row.addWidget(self.export_centres)
        row.addWidget(self.export_probe)
        row.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        for button in buttons.buttons():
            button.setAutoDefault(False)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        layout.addLayout(row)
        self.set_snapshot(None, None)

    def set_snapshot(self, result, units):
        key = (result["snapshot_id"], result["combination"], units.key) if result else None
        if key == self.key:
            return
        old_element = self.element.currentText() if result and self.result and result["snapshot_id"] == self.result["snapshot_id"] else ""
        self.key, self.result, self.units, self.loading = key, result, units, True
        self.probe_data = None
        self.element.clear()
        self.tools.setEnabled(result is not None)
        self.export_centres.setEnabled(result is not None)
        self.export_probe.setEnabled(False)
        if result is None:
            self.table.setRowCount(0)
            self.context.setText("Run plate analysis to inspect results.")
            self.probe.setText("No current plate snapshot.")
        else:
            self.context.setText(f"{result['combination']} | Snapshot {result['snapshot_id']} | {result['analyzed_at']}\n"
                + "; ".join(f"{case} × {factor:g}" for case, factor in result["factors"].items()))
            try:
                headers, rows = plate_probe_table(result, units)
                ResultsPanel.populate(self.table, headers, rows)
                for column in (1, 2, 5, 6, 7):
                    self.table.setColumnHidden(column, True)
                self.element.addItems(result["element_names"])
                self.element.setCurrentIndex(max(0, self.element.findText(old_element)))
                if not old_element:
                    self.xi.setValue(0.)
                    self.eta.setValue(0.)
            except ValueError as error:
                self.result, self.key = None, object()
                self.table.setRowCount(0)
                self.tools.setEnabled(False)
                self.export_centres.setEnabled(False)
                self.probe.setText(f"Plate inspection unavailable: {error}")
        self.loading = False
        if self.result is not None:
            self.update_probe(notify=False)

    def update_probe(self, *_, notify=True):
        if self.loading or self.result is None or not self.element.currentText():
            return
        try:
            data = inspect_plate(self.result, self.element.currentText(), self.xi.value(), self.eta.value())
            self.probe_data = data
            units = self.units
            values = [f"{key} {data[key]*units.force_factor:.7g} {units.moment}/{units.length}" for key in ("Mx", "My", "Mxy")]
            if "Qx" in data:
                values += [f"{key} {data[key]*units.factor('intensity'):.7g} {units.intensity}" for key in ("Qx", "Qy")]
            else:
                values.append("Quad Qx/Qy unavailable: recovery is not validated")
            self.probe.setText(f"{data['element']} | xi {data['xi']:g}, eta {data['eta']:g}\n"
                + "Local x/y: "+", ".join(f"{v*units.length_factor:.7g}" for v in data["position"])+f" {units.length} | "
                + "Global XYZ: "+", ".join(f"{v*units.length_factor:.7g}" for v in data["global_position"])+f" {units.length}\n"
                + " | ".join(values)+"\nLocal unit axes: "
                + "; ".join(f"{key}={tuple(axis)}" for key, axis in zip("xyz", data["axes"])))
            self.export_probe.setEnabled(True)
        except ValueError as error:
            self.probe_data = None
            self.export_probe.setEnabled(False)
            self.probe.setText(str(error))
        if notify:
            self.probe_changed.emit()

    def choose_row(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.select_probe(self.table.item(rows[0].row(), 0).text(), 0., 0.)

    def select_probe(self, element, xi, eta):
        if self.result is None or element not in self.result["element_names"]:
            return
        self.loading = True
        self.element.setCurrentText(element)
        self.xi.setValue(xi)
        self.eta.setValue(eta)
        self.loading = False
        self.update_probe()

    def export_csv(self, single):
        if self.result is None or (single and self.probe_data is None):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Plate Probe" if single else "Export Plate Element Centres",
            "plate-probe.csv" if single else "plate-elements.csv", "CSV (*.csv)")
        if path:
            try:
                write_plate_probes(path, self.result, self.units, [self.probe_data] if single else None)
            except (ValueError, OSError) as error:
                QMessageBox.warning(self, "Export Plate Results", str(error))
