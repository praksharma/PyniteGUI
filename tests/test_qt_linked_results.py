"""Selection links survive sorting, units, combinations and invalidation."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('PYNITEGUI_NO_WEBENGINE', '1')
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.analysis import analyze
from pynitegui.qt.examples import example_project
from pynitegui.qt.reports import result_table
from pynitegui.qt.results_panel import IDENTITY_ROLE, ResultItem

class LinkedResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def solved(self, key='portal'):
        project = example_project(key)
        project.set_combination('Double', {project.default_load_case: 2})
        self.window.load_project(project)
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(project)
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(result, '')
        return self.window.results_panel

    def rows(self, table, kind, name):
        return [row for row in range(table.rowCount())
                if tuple(table.item(row, 0).data(IDENTITY_ROLE)) == (kind, name)]

    def test_numeric_sort_uses_values(self):
        items = [ResultItem(value) for value in (10., -2., 2., -12.)]
        self.assertEqual([item.data(Qt.ItemDataRole.UserRole) for item in sorted(items)],
                         [-12., -2., 2., 10.])

    def test_sorted_row_links_node_tree_and_other_tabs(self):
        panel = self.solved()
        table = panel.tables['reactions']
        panel.tabs.setCurrentWidget(table)
        table.sortItems(2, Qt.SortOrder.DescendingOrder)
        table.selectRow(self.rows(table, 'nodes', 'N4')[0])
        self.assertEqual(self.window.selected, ('nodes', 'N4'))
        for key in ('nodes', 'displacements', 'reactions'):
            table2 = panel.tables[key]
            self.assertEqual([table2.item(i.row(), 0).text() for i in table2.selectionModel().selectedRows()], ['N4'])
        self.assertEqual([item.data(0, Qt.ItemDataRole.UserRole) for item in self.window.tree.selectedItems()], [('nodes', 'N4')])
        self.assertIs(panel.tabs.currentWidget(), table)

    def test_geometry_reveals_lazy_members_and_sorted_row_links_back(self):
        panel = self.solved()
        self.assertFalse(panel.members_loaded)
        self.window.select(('members', 'M2'))
        table = panel.tables['members']
        self.assertIs(panel.tabs.currentWidget(), table)
        self.assertTrue(panel.members_loaded)
        self.assertEqual(len(table.selectionModel().selectedRows()), 4)
        table.sortItems(5, Qt.SortOrder.AscendingOrder)
        row = self.rows(table, 'members', 'M3')[0]
        table.selectRow(row)
        self.assertEqual(self.window.selected, ('members', 'M3'))
        with patch.object(self.window, 'diagrams', return_value=None) as show:
            table.itemDoubleClicked.emit(table.item(row, 5))
            show.assert_called_once()
        self.window.select(('nodes', 'N3'))
        self.assertIs(panel.tabs.currentWidget(), panel.tables['nodes'])
        self.assertFalse(table.selectedItems())

    def test_extended_and_mixed_model_selection(self):
        panel = self.solved()
        table = panel.tables['nodes']
        table.selectRow(self.rows(table, 'nodes', 'N1')[0])
        row = self.rows(table, 'nodes', 'N4')[0]
        table.selectionModel().select(table.model().index(row, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.assertEqual(set(self.window.selections), {('nodes', 'N1'), ('nodes', 'N4')})
        self.window.select_many([('nodes', 'N2'), ('members', 'M2')])
        self.assertEqual(len(table.selectionModel().selectedRows()), 1)
        self.window.select(None)
        self.assertTrue(all(not table.selectedItems() for table in panel.tables.values()))

    def test_units_combinations_and_invalidation(self):
        panel = self.solved()
        self.window.select(('members', 'M2'))
        snapshot = self.window.result.snapshot_id
        self.window.set_units('custom_cm_lbf')
        self.assertEqual(self.window.result.snapshot_id, snapshot)
        self.assertIn('lbf', panel.tables['members'].horizontalHeaderItem(3).text())
        self.assertEqual(self.window.selected, ('members', 'M2'))
        self.window.result_combination.setCurrentText('Double')
        headers, expected = result_table(self.window.project, self.window.result, 'members')
        actual = {tuple(panel.tables['members'].item(r, c).data(Qt.ItemDataRole.UserRole)
                        for c in range(len(headers))) for r in range(panel.tables['members'].rowCount())}
        self.assertEqual(actual, {tuple(row) for row in expected})
        self.assertIn('Double', panel.snapshot.text())
        self.window.edit('Move', lambda p: setattr(p.nodes['N2'], 'y', 156))
        self.assertIsNone(panel.result)
        self.assertTrue(all(table.rowCount() == 0 for table in panel.tables.values()))
        self.assertFalse(panel.tabs.isEnabled())

    def test_spatial_components_and_inactive_rotations(self):
        panel = self.solved('3d_tripod')
        self.assertEqual(panel.tables['displacements'].columnCount(), 7)
        self.assertEqual(panel.tables['reactions'].columnCount(), 7)
        self.assertEqual(panel.tables['displacements'].item(0, 4).text(), 'n/a')
        self.window.select(('members', 'M1'))
        self.assertEqual(panel.tables['members'].columnCount(), 11)
        self.assertEqual(panel.tables['members'].horizontalHeaderItem(6).text(), 'T (kip-in)')

    def test_activated_member_opens_detail_tab(self):
        self.solved()
        self.window.open_result_member('M2')
        from pynitegui.qt.diagrams import DiagramDialog
        dialog = self.window.findChildren(DiagramDialog)[0]
        self.assertEqual(dialog.member.currentText(), 'M2')
        self.assertEqual(dialog.tabs.tabText(dialog.tabs.currentIndex()), 'Member Detail')
        dialog.close()
