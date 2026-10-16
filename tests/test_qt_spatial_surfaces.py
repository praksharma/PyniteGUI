"""Persisted main-viewport surfaces remain explicitly independent of frame joints."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtWidgets import QApplication, QDialog, QPushButton
from pynitegui.qt.analysis import analyze, model_signature
from pynitegui.qt.app import MainWindow
from pynitegui.qt.automation_core import AutomationCommands, AutomationError, batch_candidate
from pynitegui.qt.examples import example_project
from pynitegui.qt.mesh_model import GENERATORS, MeshDefinition
from pynitegui.qt.model import Project
from pynitegui.qt.model_tables import ModelTablesDialog
from pynitegui.qt.recovery import RecoveryStore
from pynitegui.qt.spatial_model import SpatialProject
from pynitegui.qt.spatial_surfaces import put_surface, surface_geometry
from pynitegui.qt.spatial_view import Bridge, viewport_payload


class SpatialSurfaceModelTests(unittest.TestCase):
    def test_all_generators_roundtrip_without_merging_frame_nodes(self):
        for generator, (_, parameters) in GENERATORS.items():
            project = example_project("3d_cantilever")
            before = deepcopy(project.nodes)
            recipe = MeshDefinition(name="Slab", generator=generator, parameters=dict(parameters))
            put_surface(project, recipe)
            project.validate()
            self.assertEqual(project.nodes, before)
            self.assertEqual(Project.from_dict(project.to_dict()).to_dict(), project.to_dict())
            clone = project.clone()
            clone.surfaces["Slab"].origin[0] += 7
            self.assertEqual(recipe.origin[0], 0)
            self.assertEqual(project.surfaces["Slab"].origin[0], 0)

    def test_legacy_spatial_versions_migrate_and_planar_stays_unchanged(self):
        project = example_project("3d_cantilever")
        for version in (16, 17, 18):
            document = project.to_dict()
            document["version"] = version
            document.pop("surfaces")
            if version == 16:
                for load in document["loads"].values():
                    load.pop("elevation")
            self.assertEqual(Project.from_dict(document).to_dict(), project.to_dict())
            document["surfaces"] = {}
            with self.assertRaises(ValueError):
                Project.from_dict(document)
        self.assertNotIn("surfaces", Project().to_dict())

    def test_strict_surface_schema_and_names(self):
        project = SpatialProject(surfaces={"S1": MeshDefinition(name="S1")})
        document = project.to_dict()
        for value in (None, [], {"WrongName": document["surfaces"]["S1"]},
                      {"S1": {**document["surfaces"]["S1"], "extra": True}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Project.from_dict({**document, "surfaces": value})
        missing = deepcopy(document)
        missing.pop("surfaces")
        with self.assertRaises(ValueError):
            Project.from_dict(missing)
        project = example_project("3d_cantilever")
        put_surface(project, MeshDefinition(name="N1"))
        with self.assertRaisesRegex(ValueError, "distinct"):
            project.validate()

    def test_duplicate_names_edit_rename_and_independent_deletion(self):
        project = example_project("3d_cantilever")
        put_surface(project, MeshDefinition(name="S1"))
        with self.assertRaisesRegex(ValueError, "already exists"):
            put_surface(project, MeshDefinition(name="S1"))
        put_surface(project, MeshDefinition(name="S2", origin=[12, 34, 56]), previous="S1")
        self.assertEqual(set(project.surfaces), {"S2"})
        project.delete("nodes", "N1")
        self.assertIn("S2", project.surfaces)
        project.delete("surfaces", "S2")
        self.assertFalse(project.surfaces)

    def test_bounded_project_meshes_and_generation_cache_is_immutable(self):
        project = SpatialProject(surfaces={f"S{i}": MeshDefinition(name=f"S{i}", mesh_size=4) for i in range(5)})
        with self.assertRaisesRegex(ValueError, "Combined"):
            project.validate()
        recipe = MeshDefinition()
        geometry = surface_geometry(recipe)
        with self.assertRaises(TypeError):
            geometry[2][0][0] = 10
        recipe.origin[0] = 10
        self.assertNotEqual(surface_geometry(recipe), geometry)

    def test_save_recovery_and_signature_include_surface_geometry(self):
        project = example_project("3d_cantilever")
        baseline = project.to_dict()
        signature = model_signature(project)
        put_surface(project, MeshDefinition(name="S1", plane="XZ"))
        self.assertNotEqual(model_signature(project), signature)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"slab.json"
            project.save(path)
            self.assertEqual(Project.open(path).to_dict(), project.to_dict())
            store = RecoveryStore(directory)
            store.write(project, baseline, path)
            recovered, original, saved = store.read(store.path)
            self.assertEqual(recovered.to_dict(), project.to_dict())
            self.assertEqual(original, path)
            self.assertEqual(saved, baseline)

    def test_solver_never_silently_ignores_surface_geometry(self):
        for project in (SpatialProject(), example_project("3d_cantilever")):
            put_surface(project, MeshDefinition(name="S1"))
            with self.assertRaisesRegex(ValueError, "Mixed frame/slab analysis"):
                analyze(project)
            self.assertTrue(any("uncoupled surface" in issue for issue in project.analysis_topology_issues()))


class SpatialSurfaceEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(example_project("3d_cantilever"))

    def tearDown(self):
        self.window.live_analysis.set_enabled(False)
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def add_surface(self):
        self.window.edit("Add surface", lambda p: put_surface(p, MeshDefinition(name="S1", plane="XZ")))

    def test_add_edit_delete_selection_and_one_step_undo(self):
        window = self.window
        before = window.project.to_dict()
        self.add_surface()
        window.select(("surfaces", "S1"))
        self.assertIsNotNone(window.findChild(QPushButton, "edit_surface"))
        self.assertEqual(window.tree.topLevelItem(3).childCount(), 1)
        Bridge(window.view).select("surfaces", "S1", False)
        self.assertEqual(window.selected, ("surfaces", "S1"))
        window.delete_selected()
        self.assertFalse(window.project.surfaces)
        window.undo.undo()
        self.assertIn("S1", window.project.surfaces)
        window.undo.undo()
        self.assertEqual(window.project.to_dict(), before)

    def test_native_workspace_insertion_and_cancel_are_atomic(self):
        from pynitegui.qt.mesh_workspace import MeshWorkspace
        def accept_mesh(dialog):
            dialog.mesh_name.setText("Floor")
            self.assertTrue(dialog.apply())
            return QDialog.DialogCode.Accepted
        with patch.object(MeshWorkspace, "exec", accept_mesh):
            self.window.show_mesh_workspace()
        self.assertEqual(set(self.window.project.surfaces), {"Floor"})
        count = self.window.undo.count()
        with patch.object(MeshWorkspace, "exec", return_value=QDialog.DialogCode.Rejected):
            self.window.show_mesh_workspace("Floor")
        self.assertEqual(self.window.undo.count(), count)

    def test_duplicate_name_keeps_recipe_editor_open(self):
        from pynitegui.qt.mesh_workspace import MeshWorkspace
        self.add_surface()
        def reject_duplicate(dialog):
            dialog.mesh_name.setText("S1")
            with patch("pynitegui.qt.mesh_workspace.QMessageBox.warning") as warning, patch.object(dialog, "accept") as accept:
                dialog.use_mesh()
            warning.assert_called_once()
            accept.assert_not_called()
            dialog.mesh_name.setText("Floor")
            self.assertTrue(dialog.apply())
            return QDialog.DialogCode.Accepted
        with patch.object(MeshWorkspace, "exec", reject_duplicate):
            self.window.show_mesh_workspace()
        self.assertEqual(set(self.window.project.surfaces), {"S1", "Floor"})

    def test_payloads_preserve_frame_nodes_and_surfaces_can_be_selected_together(self):
        window = self.window
        before = viewport_payload(window)["nodes"]
        self.add_surface()
        payload = viewport_payload(window)
        self.assertEqual(payload["nodes"], before)
        self.assertEqual(len(payload["surfaceMeshes"]), 1)
        self.assertEqual(payload["surfaceMeshes"][0]["name"], "S1")
        self.assertEqual(len(payload["surfaceMeshes"][0]["surfaces"]), 64)
        window.surface_visibility_action.trigger()
        self.assertFalse(viewport_payload(window)["surfaceMeshes"])
        self.assertIn("S1", window.project.surfaces)
        window.surface_visibility_action.trigger()
        window.select_all()
        self.assertIn(("surfaces", "S1"), window.selections)
        window.delete_selected()
        self.assertFalse(window.project.surfaces)
        window.undo.undo()
        self.assertIn("S1", window.project.surfaces)
        self.assertEqual(window.project.nodes.keys(), {"N1", "N2"})
        bridge = Bridge(window.view)
        window.load_project(Project())
        bridge.select("surfaces", "S1", False)
        self.assertIsNone(window.selected)

    def test_manual_live_and_mcp_analysis_are_blocked(self):
        window = self.window
        self.add_surface()
        window.live_analysis.set_enabled(True)
        self.assertFalse(window.live_analysis.pending)
        with patch("pynitegui.qt.app.QMessageBox.information") as info:
            window.run_analysis()
        info.assert_called_once()
        self.assertIsNone(window.thread)
        commands = AutomationCommands(window)
        with self.assertRaises(AutomationError) as error:
            commands.execute("run_analysis", {"session_id": window.project_session,
                                             "expected_revision": window.automation_revision})
        self.assertEqual(error.exception.code, "surface_geometry_only")
        response = commands.execute("read_model", {})
        self.assertIn("S1", response["model"]["surfaces"])
        self.assertIn("native-only", response["schema"]["surface_geometry"])

    def test_model_tables_and_mcp_frame_edits_retain_surface_recipes(self):
        self.add_surface()
        project = self.window.project
        candidate = batch_candidate(project, [{"op": "put", "collection": "nodes", "key": "N2", "value": {"x": 150}}])
        self.assertEqual(candidate.surfaces, project.surfaces)
        dialog = ModelTablesDialog(self.window, project)
        try:
            dialog.accept()
            self.assertEqual(dialog.definition.surfaces, project.surfaces)
        finally:
            dialog.deleteLater()
        with self.assertRaises(AutomationError):
            batch_candidate(project, [{"op": "delete", "collection": "surfaces", "key": "S1"}])

    def test_surface_changes_invalidate_results_and_failed_generation_is_atomic(self):
        from contextlib import redirect_stdout
        from io import StringIO
        window = self.window
        with redirect_stdout(StringIO()):
            result = analyze(window.project)
        window.analysis_revision = window.revision
        window.analysis_finished(result, "")
        self.assertIsNotNone(window.result)
        self.add_surface()
        self.assertIsNone(window.result)
        self.assertFalse(window.export_menu.isEnabled())
        self.assertFalse(window.deformed_action.isEnabled())
        before = window.project.to_dict()
        count = window.undo.count()
        invalid = MeshDefinition(name="S1", parameters={"width": .1, "height": 120.})
        with patch("pynitegui.qt.app.QMessageBox.warning") as warning:
            window.edit("Invalid surface", lambda p: put_surface(p, invalid, previous="S1"))
        warning.assert_called_once()
        self.assertEqual(window.project.to_dict(), before)
        self.assertEqual(window.undo.count(), count)
        for key in ("si", "si_mm", "imperial_ft", "imperial"):
            window.set_units(key)
            self.assertEqual(window.project.surfaces["S1"].to_dict(), before["surfaces"]["S1"])


if __name__ == "__main__":
    unittest.main()
