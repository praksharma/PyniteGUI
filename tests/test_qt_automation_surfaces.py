"""Atomic surface recipes, pressure assignments and multistorey MCP workflows."""
import contextlib
from copy import deepcopy
import io
import math
import os
import time
import unittest
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from Pynite import FEModel3D
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.analysis import analyze
from pynitegui.qt.automation_core import Permissions, QtCommandBridge
from pynitegui.qt.automation_schema import model_reference
from pynitegui.qt.mesh_model import GENERATORS, MeshDefinition
from pynitegui.qt.model import Project
from pynitegui.qt.spatial_model import SpatialProject
from pynitegui.qt.spatial_view import Bridge
from surface_fixtures import two_storey_slabs


class SurfaceAutomationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(SpatialProject())
        self.permissions = Permissions()
        self.permissions.set_group("Model edits", True)
        self.bridge = QtCommandBridge(self.window, self.permissions)
        self.bridge.set_active(True)

    def tearDown(self):
        self.bridge.set_active(False)
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def invoke(self, name, **arguments):
        future = self.bridge.submit(name, arguments)
        deadline = time.monotonic()+15
        while not future.done() and time.monotonic()<deadline:
            self.app.processEvents()
            time.sleep(.005)
        return future.result(timeout=1)

    def edit(self, operations, **guards):
        return self.invoke("apply_batch", **{"session_id":self.window.project_session,
            "expected_revision":self.window.automation_revision, **guards}, operations=operations)

    def test_every_mesh_generator_and_schema_are_editable_with_partial_materials(self):
        schema = model_reference("3D")
        self.assertEqual(set(schema["entities"]["surfaces"]["generator_parameters"]), set(GENERATORS))
        self.assertNotIn("surfaces", model_reference("2D")["entities"])
        operations = [{"op":"put","collection":"surfaces","key":name,
            "value":{"generator":name,"parameters":dict(parameters)}} for name,(_,parameters) in GENERATORS.items()]
        result = self.edit(operations)
        self.assertTrue(result["ok"], result)
        self.assertEqual(set(self.window.project.surfaces), set(GENERATORS))
        old = self.window.project.surfaces["rectangle"].material
        result = self.edit([{"op":"put","collection":"surfaces","key":"rectangle","value":{"material":{"E":4200}}}])
        self.assertTrue(result["ok"], result)
        material = self.window.project.surfaces["rectangle"].material
        self.assertEqual((material.E, material.nu, material.rho), (4200, old.nu, old.rho))
        self.assertNotIn("Surface", self.window.project.materials)
        self.assertEqual(Project.from_dict(self.window.project.to_dict()).to_dict(), self.window.project.to_dict())

    def test_two_floor_creation_opt_in_and_pressures_are_one_undo_step(self):
        project = two_storey_slabs()
        definitions, pressures = deepcopy(project.surfaces), deepcopy(project.surface_pressures)
        project.surfaces.clear()
        project.surface_pressures.clear()
        project.surface_analysis_enabled = False
        self.window.load_project(project)
        before, count = self.window.project.to_dict(), self.window.undo.count()
        operations = [{"op":"set","collection":"settings","value":{"surface_analysis_enabled":True}}]
        # References may precede their definitions; validate the complete batch.
        operations += [{"op":"put","collection":"surface_pressures","key":key,"value":value} for key,value in pressures.items()]
        operations += [{"op":"put","collection":"surfaces","key":key,"value":mesh.to_dict()} for key,mesh in definitions.items()]
        from pynitegui.qt.surface_solver import validate_coupled_topology
        with patch("pynitegui.qt.surface_solver.validate_coupled_topology", wraps=validate_coupled_topology) as validate, patch.object(FEModel3D, "analyze_linear", side_effect=AssertionError("Edits must not solve")):
            response = self.edit(operations)
            self.assertTrue(response["ok"], response)
            self.assertEqual(validate.call_count, 1)
        self.assertEqual(self.window.undo.count(), count+1)
        after = self.window.project.to_dict()
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), before)
        self.window.undo.redo()
        self.assertEqual(self.window.project.to_dict(), after)

    def test_interface_and_assignment_errors_leave_model_revision_and_undo_unchanged(self):
        self.window.load_project(two_storey_slabs())
        before, revision, count = self.window.project.to_dict(), self.window.automation_revision, self.window.undo.count()
        bad_batches = [
            [{"op":"put","collection":"surfaces","key":"Floor2","value":{"origin":[0,241,0]}}],
            [{"op":"put","collection":"surfaces","key":"Floor2","value":{"origin":[0,120,0]}}],
            [{"op":"put","collection":"surface_pressures","key":"missing","value":{"Dead":.001}}],
            [{"op":"put","collection":"surface_pressures","key":"Floor1","value":{"missing":.001}}],
            [{"op":"delete","collection":"surfaces","key":"Floor1"}],
            [{"op":"delete","collection":"load_cases","key":"Live"}],
            [{"op":"put","collection":"surfaces","key":"Floor2","value":{"element_type":"Rect"}}],
            [{"op":"put","collection":"surfaces","key":"Floor2","value":{"material":{"shell":True}}}],
        ]
        for operations in bad_batches:
            with self.subTest(operations=operations):
                response = self.edit(operations)
                self.assertFalse(response["ok"], response)
                self.assertEqual(self.window.project.to_dict(), before)
                self.assertEqual(self.window.automation_revision, revision)
                self.assertEqual(self.window.undo.count(), count)

    def test_coordinated_floor_move_and_explicit_case_surface_cleanup(self):
        self.window.load_project(two_storey_slabs())
        operations = [{"op":"put","collection":"nodes","key":f"N2_{corner}","value":{"y":264}} for corner in range(4)]
        operations.append({"op":"put","collection":"surfaces","key":"Floor2","value":{"origin":[0,264,0]}})
        response = self.edit(operations)
        self.assertTrue(response["ok"], response)
        response = self.edit([
            {"op":"delete","collection":"load_cases","key":"Live"},
            {"op":"put","collection":"combinations","key":"Gravity","value":{"Dead":1}},
            {"op":"put","collection":"combinations","key":"Factored","value":{"Dead":1.2}},
            {"op":"put","collection":"surface_pressures","key":"Floor1","value":{"Dead":.001}},
            {"op":"put","collection":"surface_pressures","key":"Floor2","value":{"Dead":.0015}},
        ])
        self.assertTrue(response["ok"], response)
        response = self.edit([{"op":"delete","collection":"surfaces","key":"Floor2"},
                              {"op":"delete","collection":"surface_pressures","key":"Floor2"}])
        self.assertTrue(response["ok"], response)
        self.assertNotIn("Floor2", self.window.project.surfaces)

    def test_planar_surface_rejection_permissions_staleness_and_names(self):
        operation = {"op":"put","collection":"surfaces","key":"S","value":{}}
        self.permissions.set_group("Model edits", False)
        self.assertEqual(self.edit([operation])["error"]["code"], "permission_denied")
        self.permissions.set_group("Model edits", True)
        self.assertEqual(self.edit([operation], expected_revision=-1)["error"]["code"], "stale_revision")
        for key,value in (("N1",{"extra":True}), ("S",{"name":"Other"}), ("S",{"units":"m-kN"})):
            response = self.edit([{**operation,"key":key,"value":value}])
            self.assertFalse(response["ok"], response)
        self.window.load_project(Project())
        self.assertFalse(self.edit([operation])["ok"])
        self.assertFalse(self.edit([{"op":"set","collection":"settings","value":{"surface_analysis_enabled":True}}])["ok"])

    def test_surface_box_bridge_mixed_selection_invalid_messages_and_delete_undo(self):
        self.window.load_project(two_storey_slabs())
        bridge = Bridge(self.window.view)
        bridge.select_many('[["surfaces","Floor1"],["surfaces","Floor2"]]', False)
        self.assertEqual(self.window.selections, [("surfaces","Floor1"),("surfaces","Floor2")])
        before = self.window.project.to_dict()
        for invalid in ('[["surfaces","missing"]]', '[["surfaces","Floor1"],["nodes","missing"]]', '[["__dict__","Floor1"]]'):
            bridge.select_many(invalid, False)
            self.assertEqual(len(self.window.selections), 2)
        bridge.select_many('[["members","B1_0"]]', True)
        self.assertEqual(len(self.window.selections), 3)
        bridge.select_many('[["surfaces","Floor1"],["surfaces","Floor2"]]', False)
        self.window.delete_selected()
        self.assertFalse(self.window.project.surfaces)
        self.assertFalse(self.window.project.surface_pressures)
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(), before)


class MultistoreySurfaceBenchmarks(unittest.TestCase):
    def test_two_storey_load_path_combinations_refinement_and_weight(self):
        from pynitegui.qt.equilibrium import check_equilibrium
        signatures = []
        for size in (60.,30.):
            project = two_storey_slabs()
            for mesh in project.surfaces.values():
                mesh.mesh_size = size
            before = project.to_dict()
            with contextlib.redirect_stdout(io.StringIO()):
                result = analyze(project)
            self.assertEqual(project.to_dict(), before)
            signatures.append(result.model_signature)
            for combo in ("Gravity","Factored"):
                selected = result.for_combination(combo)
                expected = 43200*sum(sum(pressure*project.combinations[combo].get(case,0) for case,pressure in pressures.items()) for pressures in project.surface_pressures.values())
                self.assertTrue(check_equilibrium(project, selected).passed)
                for name in (f"N0_{corner}" for corner in range(4)):
                    self.assertAlmostEqual(selected.reactions[name][1], expected/4, places=6)
                # Independent axial shortening of the two stacked column lengths:
                # N1 carries both floors, N2 adds the upper floor's N*L/(E*A).
                ea = project.materials["Steel_A992"].E*project.sections["W18x35"].A
                lower_drop = expected/4*120/ea
                upper_load = 43200*sum(value*project.combinations[combo].get(case,0) for case,value in project.surface_pressures["Floor2"].items())
                upper_drop = lower_drop+upper_load/4*120/ea
                for corner in range(4):
                    self.assertAlmostEqual(selected.displacements[f"N1_{corner}"][1], -lower_drop, places=7)
                    self.assertAlmostEqual(selected.displacements[f"N2_{corner}"][1], -upper_drop, places=7)
            self.assertEqual(len(result.solver._pynitegui_surfaces), 2)
            for mapping in result.solver._pynitegui_surfaces.values():
                self.assertTrue(all(result.displacements[name][1] < 0 for name in mapping["nodes"]))
        self.assertNotEqual(*signatures)
        project = two_storey_slabs()
        project.self_weight_case = "Dead"
        for mesh in project.surfaces.values():
            mesh.material.rho = .00009
        expected = 43200*(.001+.0005+.0015+.00025)+2*43200*6*.00009
        expected += sum(project.materials[member.material].rho*project.sections[member.section].A*math.dist(project.nodes[member.start].coords, project.nodes[member.end].coords) for name,member in project.members.items())
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(project)
        self.assertAlmostEqual(sum(values[1] for values in result.reactions.values()), expected, places=6)
