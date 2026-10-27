"""Small governing-station table inside retained envelope views."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from .station_queries import COMPONENTS, export_station_csv, governing_stations


class StationQueryPanel(QWidget):
    def __init__(self, envelope):
        super().__init__(envelope)
        self.envelope, self.rows, self.specification = envelope, [], None
        layout = QVBoxLayout(self)
        note = QLabel("Search members admitted by the current summary scope, component and value filter, across checked combinations. Returns each global extreme and its location, including both sides of jumps. Double-click a row to inspect its member curve. Local axes; N positive compression; independent extrema.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.search_button = QPushButton("Find governing stations")
        self.search_button.clicked.connect(self.search)
        layout.addWidget(self.search_button)
        self.message = QLabel("Choose a member component in the summary filters, then search.")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("Extreme", "Member", "Component", "Signed value", "Combination", "Station from start", "Side"))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.cellDoubleClicked.connect(lambda row, column: self.navigate(row))
        layout.addWidget(self.table)
        self.export_button = QPushButton("Export governing stations (CSV)...")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export)
        layout.addWidget(self.export_button)

    def invalidate(self):
        self.rows, self.specification = [], None
        self.table.setRowCount(0)
        self.export_button.setEnabled(False)
        self.message.setText("Scope, combinations or units changed. Choose a member component and search again.")

    def search(self):
        from .envelope_filters import filter_rows
        e = self.envelope
        self.invalidate()
        specification = e.filters.specification()
        component = specification["component"]
        if not component or component[0] != "Member":
            self.message.setText("Choose one Member component in the summary filters first.")
            return
        rows = list(filter_rows(e._summary_rows, specification))
        members = list(dict.fromkeys(row[1] for row in rows if row[0] == "Member"))
        try:
            self.rows = governing_stations(e.project, e.result, e.selected_combinations(), members, component[1])
        except ValueError as error:
            self.message.setText(str(error))
            return
        self.specification = {**specification, "queried_members": members}
        self.table.setRowCount(len(self.rows))
        units = e.project.units
        for i, row in enumerate(self.rows):
            quantity = COMPONENTS[row["component"]][1]
            values = (row["extreme"], row["member"], row["component"], f"{units.to_display(row['value'], quantity):.8g} {getattr(units, quantity)}",
                      row["combination"], f"{units.to_display(row['station'], 'length'):.8g} {units.length}", row["side"])
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self.export_button.setEnabled(bool(self.rows))
        self.message.setText(f"{len(members)} members × {len(e.selected_combinations())} combinations | {e.result.snapshot_id}\n"
                             "Segment derivative roots and one-sided limits; floating-point locations. First checked combination, then model member order wins ties.")

    def navigate(self, row):
        if not 0 <= row < len(self.rows):
            return
        e, value = self.envelope, self.rows[row]
        if e.spatial:
            from .spatial_results import LABELS, QUANTITIES
            quantity = dict(zip(LABELS, QUANTITIES))[value["component"]]
        else:
            quantity = COMPONENTS[value["component"]][0]
        e.member.setCurrentText(value["member"])
        e.quantity.setCurrentIndex(e.quantity.findData(quantity))
        e.side.setCurrentIndex(e.side.findData("left" if value["side"] == "left" else "right"))
        e.distance.setValue(e.project.units.to_display(value["station"], "length"))
        e.views.setCurrentIndex(2)

    def export(self):
        if not self.rows:
            return
        e = self.envelope
        path, _ = QFileDialog.getSaveFileName(self, "Export Governing Stations", f"stations-{e.result.snapshot_id}.csv", "CSV (*.csv)")
        if path:
            try:
                export_station_csv(path, e.project, e.result, e.selected_combinations(), self.rows, self.specification, e.source)
            except (ValueError, OSError) as error:
                QMessageBox.warning(self, "Export failed", str(error))
