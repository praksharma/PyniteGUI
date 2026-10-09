"""Sortable, entity-linked tables for the current analysis snapshot."""
from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QLabel, QStyledItemDelegate, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


IDENTITY_ROLE = int(Qt.ItemDataRole.UserRole) + 1


class ResultItem(QTableWidgetItem):
    def __init__(self, value):
        super().__init__()
        if isinstance(value, (int, float)):
            value = float(value)
        self.setData(Qt.ItemDataRole.DisplayRole, value)
        self.setData(Qt.ItemDataRole.UserRole, value)
        if value == "n/a":
            self.setToolTip("Released member ends rotate independently; no shared nodal rotation is defined.")


class ResultDelegate(QStyledItemDelegate):
    def displayText(self, value, locale):
        return f"{value:.6g}" if isinstance(value, (int, float)) else str(value)


class ResultsPanel(QWidget):
    entities_selected = Signal(object)
    member_activated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = self.result = None
        self.selections = []
        self.syncing = False
        self.source_table = None
        self.members_loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.snapshot = QLabel("Run analysis to show results.")
        self.snapshot.setWordWrap(True)
        self.snapshot.setTextFormat(Qt.TextFormat.PlainText)
        self.snapshot.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.snapshot)
        self.tabs = QTabWidget()
        self.tables = {}
        for key, title in (("nodes", "Nodes"), ("displacements", "Displacements"),
                           ("reactions", "Reactions"), ("members", "Member forces")):
            table = QTableWidget(0, 1)
            table.setObjectName("result_" + key)
            table.setItemDelegate(ResultDelegate(table))
            table.setMinimumHeight(120)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            table.setSortingEnabled(True)
            table.sortItems(0, Qt.SortOrder.AscendingOrder)
            table.itemSelectionChanged.connect(lambda key=key: self.table_selection(key))
            self.tables[key] = table
            self.tabs.addTab(table, title)
        self.tables["members"].itemDoubleClicked.connect(self.activate_member)
        self.tables["members"].setToolTip("Select rows to highlight members. Double-click for Member Detail. Minimum/Maximum columns are independent extrema, not one common station.")
        self.tabs.currentChanged.connect(self.tab_changed)
        self.tabs.setEnabled(False)
        layout.addWidget(self.tabs)

    def set_headers(self, project):
        units = project.units
        spatial = getattr(project, "dimension", "2D") == "3D"
        dofs = ("DX", "DY", "DZ", "RX", "RY", "RZ") if spatial else ("DX", "DY", "RZ")
        forces = ("FX", "FY", "FZ", "MX", "MY", "MZ") if spatial else ("FX", "FY", "MZ")
        motions = [f"{dof} ({units.length if dof.startswith('D') else 'rad'})" for dof in dofs]
        reactions = [f"{force} ({units.force if force.startswith('F') else units.moment})" for force in forces]
        members = ("N", "Vy", "Vz", "T", "My", "Mz", "dy", "dz") if spatial else ("N", "Fy", "Mz", "dy")
        quantities = ("force", "force", "force", "moment", "moment", "moment", "length", "length") if spatial else ("force", "force", "moment", "length")
        headers = {"nodes": ["Node", *motions, *reactions], "displacements": ["Node", *motions],
                   "reactions": ["Node", *reactions],
                   "members": ["Member", "Station", f"x ({units.length})",
                               *(f"{label} ({getattr(units, quantity)})" for label, quantity in zip(members, quantities))]}
        for key, labels in headers.items():
            table = self.tables[key]
            table.setColumnCount(len(labels))
            table.setHorizontalHeaderLabels(labels)

    def clear(self, project):
        self.project, self.result = project, None
        self.selections = []
        self.members_loaded = False
        for table in self.tables.values():
            table.blockSignals(True)
            table.setRowCount(0)
            table.blockSignals(False)
        self.set_headers(project)
        self.snapshot.setText("Model changed | Run analysis to show current results.")
        self.tabs.setEnabled(False)

    def update_results(self, project, result):
        from .reports import result_table
        headers, rows = result_table(project, result, "nodes")
        self.project, self.result = project, result
        self.members_loaded = False
        self.set_headers(project)
        self.fill("nodes", headers, rows, "nodes")
        count = (len(headers) - 1) // 2
        self.fill("displacements", headers[:count + 1], [row[:count + 1] for row in rows], "nodes")
        self.fill("reactions", [headers[0], *headers[count + 1:]], [[row[0], *row[count + 1:]] for row in rows], "nodes")
        table = self.tables["members"]
        table.blockSignals(True)
        table.setRowCount(0)
        table.blockSignals(False)
        self.tabs.setEnabled(True)
        self.snapshot.setText(f"Current | Analysis {result.snapshot_id} | {result.combination} | {project.units.summary}")
        self.snapshot.setToolTip(f"Analyzed (UTC): {result.analyzed_at}\nModel signature: {result.model_signature}")
        if self.tabs.currentWidget() is table:
            self.load_members()
        self.sync_selection(self.selections)

    def fill(self, key, headers, rows, kind):
        table = self.tables[key]
        table.blockSignals(True)
        table.setSortingEnabled(False)
        table.clearContents()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = ResultItem(value)
                if column == 0:
                    item.setData(IDENTITY_ROLE, (kind, values[0]))
                table.setItem(row, column, item)
        table.setSortingEnabled(True)
        table.resizeColumnsToContents()
        table.blockSignals(False)

    def load_members(self):
        if self.result is None or self.members_loaded:
            return
        from .reports import result_table
        headers, rows = result_table(self.project, self.result, "members")
        self.fill("members", headers, rows, "members")
        self.members_loaded = True

    def table_selection(self, key):
        if self.syncing or self.result is None:
            return
        table = self.tables[key]
        identities = [table.item(index.row(), 0).data(IDENTITY_ROLE)
                      for index in table.selectionModel().selectedRows()]
        # Qt is still changing this table's selection while emitting its signal.
        # Synchronize other views without mutating the originating selection.
        self.source_table = table
        try:
            self.entities_selected.emit(list(dict.fromkeys(tuple(identity) for identity in identities)))
        finally:
            self.source_table = None

    def sync_selection(self, selections):
        self.selections = list(selections)
        if self.result is None or self.syncing:
            return
        self.syncing = True
        try:
            selected = set(tuple(selection) for selection in selections)
            kinds = {kind for kind, _ in selected}
            if kinds == {"members"}:
                self.tabs.setCurrentWidget(self.tables["members"])
                self.load_members()
            elif kinds == {"nodes"} and self.tabs.currentWidget() is self.tables["members"]:
                self.tabs.setCurrentWidget(self.tables["nodes"])
            for table in self.tables.values():
                if table is self.source_table:
                    continue
                table.blockSignals(True)
                current = table.currentItem()
                keep_current = current is not None and tuple(table.item(current.row(), 0).data(IDENTITY_ROLE)) in selected
                table.clearSelection()
                first = None
                for row in range(table.rowCount()):
                    item = table.item(row, 0)
                    if tuple(item.data(IDENTITY_ROLE)) in selected:
                        table.selectionModel().select(table.model().index(row, 0),
                            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                        first = first or item
                if first is not None:
                    table.setCurrentItem(current if keep_current else first, QItemSelectionModel.SelectionFlag.NoUpdate)
                    table.scrollToItem(current if keep_current else first)
                else:
                    table.setCurrentItem(None)
                table.blockSignals(False)
        finally:
            self.syncing = False

    def tab_changed(self, _):
        if self.tabs.currentWidget() is self.tables["members"]:
            self.load_members()
        self.sync_selection(self.selections)

    def activate_member(self, item):
        identity = self.tables["members"].item(item.row(), 0).data(IDENTITY_ROLE)
        if self.result is not None and identity:
            self.member_activated.emit(identity[1])
