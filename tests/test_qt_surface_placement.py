"""Frame placement controls, preview context and main-model atomic application."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication, QDialog
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.mesh_model import MeshDefinition
from pynitegui.qt.mesh_workspace import MeshWorkspace


class SurfacePlacementEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.project = example_project("3d_space_frame")
        self.dialog = MeshWorkspace(placement_project=self.project, model_mode=True, auto_place=True)

    def tearDown(self):
        self.dialog.saved = self.dialog.definition.to_dict()
        self.dialog.pending = False
        self.dialog.reject()
        self.dialog.deleteLater()
        self.app.processEvents()

    def test_new_rectangle_defaults_to_top_level_with_frame_reference(self):
        dialog = self.dialog
        self.assertEqual(dialog.fit_source.currentIndex(), 2)
        self.assertEqual(dialog.definition.origin, [0, 144, 0])
        self.assertEqual(dialog.definition.parameters, dict(width=240, height=180))
        self.assertEqual(dialog.definition.plane, "XZ")
        payload = dialog.preview.render_payload()
        self.assertEqual(len(payload['nodes']), 8)
        self.assertEqual(len(payload['members']), 8)
        self.assertEqual(len(payload['surfaceMeshes']), 1)
        self.assertTrue(all(n['position'][1] == 144 for n in payload['surfaceMeshes'][0]['nodes']))
        dialog.preview.frame.setChecked(False)
        self.assertNotIn('surfaceMeshes', dialog.preview.render_payload())
        self.assertFalse(dialog.preview.render_payload()['members'])
        dialog.undo.undo()
        self.assertEqual(dialog.definition.origin, [0, 0, 0])
        dialog.undo.redo()
        self.assertEqual(dialog.definition.origin, [0, 144, 0])

    def test_selected_boundary_and_unit_changes_preserve_canonical_geometry(self):
        dialog = MeshWorkspace(placement_project=self.project, placement_selection=[('members', f'M{i}') for i in range(5,9)], auto_place=True)
        try:
            self.assertEqual(dialog.fit_source.currentIndex(), 1)
            before = dialog.definition.to_dict()
            for key in ('si', 'si_mm', 'imperial_ft', 'imperial'):
                dialog.units.setCurrentIndex(dialog.units.findData(key))
                dialog.fit_frame()
                self.assertEqual(dialog.definition.to_dict(), {**before, 'unit_system': key})
                self.assertIn(dialog.definition.units.length, dialog.frame_level.itemText(0))
        finally:
            dialog.saved = dialog.definition.to_dict()
            dialog.reject()
            dialog.deleteLater()

    def test_existing_slab_is_not_moved_until_fit_is_chosen(self):
        dialog = MeshWorkspace(definition=MeshDefinition(name="Existing"), placement_project=self.project)
        try:
            self.assertEqual(dialog.definition.origin, [0,0,0])
            dialog.fit_source.setCurrentIndex(2)
            self.assertEqual(dialog.definition.origin, [0,144,0])
            dialog.generator.setCurrentIndex(dialog.generator.findData('cylinder'))
            self.assertFalse(dialog.placement_panel.isEnabled())
        finally:
            dialog.saved = dialog.definition.to_dict()
            dialog.reject()
            dialog.deleteLater()

    def test_level_switch_and_manual_coordinates_do_not_create_live_constraints(self):
        upper = example_project('3d_space_frame')
        for member in list(upper.members.values())[4:]:
            a, b = upper.nodes[member.start].coords, upper.nodes[member.end].coords
            self.project.add_member((a[0], 288, a[2]), (b[0], 288, b[2]))
        dialog = MeshWorkspace(placement_project=self.project, auto_place=True)
        try:
            self.assertEqual(dialog.definition.origin[1], 288)
            dialog.frame_level.setCurrentIndex(1)
            self.assertEqual(dialog.definition.origin[1], 144)
            dialog.fit_source.setCurrentIndex(0)
            dialog.origin_fields[1].setValue(100)
            self.assertTrue(dialog.apply())
            self.assertEqual(dialog.definition.origin[1], 100)
            dialog.fit_source.setCurrentIndex(2)
            self.assertEqual(dialog.definition.origin[1], 144)
        finally:
            dialog.saved = dialog.definition.to_dict()
            dialog.reject()
            dialog.deleteLater()

    def test_fitted_recipe_commits_once_and_cancel_keeps_main_model_unchanged(self):
        window = MainWindow()
        window.load_project(self.project)
        before = window.project.to_dict()
        def accept(dialog):
            self.assertEqual(dialog.definition.origin, [0,144,0])
            return QDialog.DialogCode.Accepted
        try:
            with patch.object(MeshWorkspace, 'exec', return_value=QDialog.DialogCode.Rejected):
                window.show_mesh_workspace()
            self.assertEqual(window.project.to_dict(), before)
            with patch.object(MeshWorkspace, 'exec', accept):
                window.show_mesh_workspace()
            self.assertEqual(window.undo.count(), 1)
            self.assertEqual(window.project.surfaces['S1'].origin, [0,144,0])
            self.assertEqual(window.project.nodes, self.project.nodes)
            window.undo.undo()
            self.assertEqual(window.project.to_dict(), before)
        finally:
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()


if __name__ == '__main__':
    unittest.main()
