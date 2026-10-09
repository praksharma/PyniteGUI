"""Spatial persistence, analytical benchmarks, native editing and export contracts."""
import contextlib
import base64
import io
import json
import math
import os
import pickle
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QMessageBox, QPushButton

from pynitegui.qt.analysis import analyze, model_signature
from pynitegui.qt.app import MainWindow
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Material, Project, Section
from pynitegui.qt.model_tables import ModelTablesDialog
from pynitegui.qt.reports import ReportOptions, ReportOptionsDialog, export_csv, report_html, result_table
from pynitegui.qt.spatial_model import DOFS, SpatialLoad, SpatialProject
from pynitegui.qt.spatial_results import QUANTITIES, DIAGRAM_AXES, member_axes, sampled_member
from pynitegui.qt.spatial_view import Bridge, viewport_payload
from pynitegui.qt.units import UNIT_SYSTEMS


def beam():
    project = SpatialProject()
    project.set_material(Material("Test", E=30000, nu=.25, rho=.0002))
    project.set_section(Section("Test", A=8, Iy=20, Iz=80, J=5))
    project.default_material = project.default_section = "Test"
    project.add_member((0, 0, 0), (120, 0, 0))
    project.nodes["N1"].support = "fixed"
    return project


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class SpatialModelTests(unittest.TestCase):
    def test_spatial_angle_components_follow_y_up_convention(self):
        for azimuth, elevation, expected in ((0,0,(10,0,0)),(90,0,(0,0,10)),(0,90,(0,10,0)),
                                             (45,0,(math.sqrt(50),0,math.sqrt(50))),(0,-90,(0,-10,0))):
            values = dict(SpatialLoad("L1","N2","Angle",10,angle=azimuth,elevation=elevation).components())
            for value, target in zip(values.values(), expected):
                self.assertAlmostEqual(value, target)
            self.assertAlmostEqual(math.sqrt(sum(value*value for value in values.values())),10)

    def test_legacy_spatial_migration_and_angle_validation(self):
        project = beam()
        project.loads["L1"] = SpatialLoad("L1","N2","FY",-2)
        old = project.to_dict()
        old["version"] = 16
        old["loads"]["L1"].pop("elevation")
        self.assertEqual(Project.from_dict(old).to_dict(), project.to_dict())
        old["loads"]["L1"]["direction"] = "Angle"
        with self.assertRaises(ValueError):
            Project.from_dict(old)
        for key, value in (("angle",361),("elevation",91),("elevation",float("nan")),("elevation",True)):
            project.loads["L1"] = SpatialLoad("L1","N2","Angle",10,angle=33.123456789,elevation=17.987654321)
            self.assertEqual(Project.from_dict(project.to_dict()).to_dict(),project.to_dict())
            setattr(project.loads["L1"],key,value)
            with self.assertRaises(ValueError):
                project.validate()

    def test_angle_load_analysis_matches_explicit_components(self):
        for target, kind in (("N2","point"),("M1","point"),("M1","distributed")):
            project = beam()
            project.loads["L1"] = SpatialLoad("L1",target,"Angle",-2,.2,kind,3,.8,angle=33,elevation=-17)
            project.set_combination("Scaled",{"Case 1":1.7})
            expected = project.clone()
            expected.loads.clear()
            load = project.loads["L1"]
            ends = dict(load.components(magnitude=load.end_magnitude))
            for i,(direction,value) in enumerate(load.components()):
                expected.loads[f"L{i+1}"] = SpatialLoad(f"L{i+1}",target,direction,value,.2,kind,ends[direction],.8)
            actual, reference = solve(project).for_combination("Scaled"), solve(expected).for_combination("Scaled")
            for node in project.nodes:
                for values in ((actual.displacements[node],reference.displacements[node]),(actual.reactions[node],reference.reactions[node])):
                    for value, target_value in zip(*values):
                        self.assertAlmostEqual(value,target_value)
    def test_schema_dispatch_roundtrip_and_legacy_unchanged(self):
        project = beam()
        project.nodes["N2"].z = 45
        project.members["M1"].roll = 23.123456789
        restored = Project.from_dict(project.to_dict())
        self.assertIsInstance(restored, SpatialProject)
        self.assertEqual(restored.to_dict(), project.to_dict())
        self.assertEqual(Project().to_dict()["version"], 15)

    def test_schema_rejects_future_missing_and_unknown_fields(self):
        for key, value in (("version", 18), ("version", True), ("dimension", "4D"), ("units", "m-kN"), ("extra", 1)):
            data = beam().to_dict()
            data[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                Project.from_dict(data)
        data = beam().to_dict()
        del data["dimension"]
        with self.assertRaises(ValueError):
            Project.from_dict(data)

    def test_invalid_entities_and_references(self):
        for kind, name, key, value in (("nodes", "N2", "z", float("nan")), ("nodes", "N2", "restraint_z", 1),
                                      ("nodes", "N2", "spring_rx", -1), ("members", "M1", "start", []),
                                      ("members", "M1", "material", []), ("members", "M1", "roll", 361),
                                      ("members", "M1", "release_end", True), ("members", "M1", "kind", "truss")):
            project = beam()
            setattr(getattr(project, kind)[name], key, value)
            with self.subTest(key=key), self.assertRaises(ValueError):
                project.validate()
        project = beam()
        project.loads["L1"] = SpatialLoad("L1", [])
        with self.assertRaises(ValueError):
            project.validate()

    def test_load_validation_local_nodal_and_distributed_moments(self):
        for target, direction, kind in (("N2", "Fy", "point"), ("N2", "FY", "distributed"),
                                        ("M1", "MY", "distributed"), ("M1", "Local angle", "point")):
            project = beam()
            project.loads["L1"] = SpatialLoad("L1", target, direction, -1, 0, kind)
            with self.subTest(target=target, direction=direction), self.assertRaises(ValueError):
                project.validate()

    def test_xyz_nodes_not_projected_or_merged(self):
        project = SpatialProject()
        project.add_member((0, 0, 0), (0, 0, 120))
        project.validate()
        self.assertEqual(len(project.nodes), 2)
        self.assertEqual(project.member_position("M1", 0, 0, 60), .5)
        self.assertIsNone(project.member_position("M1", 0, 1, 60))

    def test_crossings_skew_lines_and_overlaps(self):
        project = SpatialProject()
        project.add_member((-10, 0, 0), (10, 0, 0))
        project.add_member((0, -10, 2), (0, 10, 2))
        self.assertIsNone(project.member_intersection("M1", "M2"))
        project.nodes["N3"].z = project.nodes["N4"].z = 0
        self.assertEqual(project.member_intersection("M1", "M2"), (.5, .5))
        self.assertTrue(any("cross" in text for text in project.analysis_topology_issues()))
        project.nodes["N3"].x, project.nodes["N3"].y = -5, 0
        project.nodes["N4"].x, project.nodes["N4"].y = 15, 0
        with self.assertRaisesRegex(ValueError, "overlap"):
            project.member_intersection("M1", "M2")

    def test_interior_node_and_disconnected_group_rejected(self):
        project = beam()
        project.node_at(60, 0, 0)
        with self.assertRaisesRegex(ValueError, "inside"):
            solve(project)
        project = beam()
        project.add_member((0, 0, 20), (120, 0, 20))
        with self.assertRaisesRegex(ValueError, "Disconnected"):
            solve(project)

    def test_no_silent_planar_split(self):
        for callback in (lambda p: p.split_member("M1", .5), lambda p: p.connect_intersections()):
            with self.assertRaisesRegex(ValueError, "planned"):
                callback(beam())

    def test_json_save_open_preserves_dimension(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.json"
            project = beam()
            project.save(path)
            self.assertEqual(Project.open(path).to_dict(), project.to_dict())


class SpatialAnalysisTests(unittest.TestCase):
    def test_cantilever_all_six_dofs_and_equilibrium(self):
        project = beam()
        magnitudes = (2, -3, 4, 5, 0, 0)
        for direction, magnitude in zip(("FX", "FY", "FZ", "MX", "MY", "MZ"), magnitudes):
            name = project.next_name("L", project.loads)
            project.loads[name] = SpatialLoad(name, "N2", direction, magnitude)
        result = solve(project)
        expected = (2*120/(30000*8), -3*120**3/(3*30000*80), 4*120**3/(3*30000*20),
                    5*120/(12000*5), -4*120**2/(2*30000*20), -3*120**2/(2*30000*80))
        for actual, target in zip(result.displacements["N2"], expected):
            self.assertAlmostEqual(actual, target, places=9)
        for actual, target in zip(result.reactions["N1"], (-2, 3, -4, -5, 480, 360)):
            self.assertAlmostEqual(actual, target, places=8)
        self.assertTrue(result.spatial)
        self.assertFalse(result.solver.nodes["N2"].support_DZ)
        self.assertFalse(result.solver.nodes["N2"].support_RX)

    def test_tip_moments_about_both_bending_axes(self):
        for direction, index, inertia in (("MY", 4, 20), ("MZ", 5, 80)):
            project = beam()
            project.loads["L1"] = SpatialLoad("L1", "N2", direction, 10)
            result = solve(project)
            self.assertAlmostEqual(result.displacements["N2"][index], 10*120/(30000*inertia))
            self.assertAlmostEqual(result.reactions["N1"][index], -10)

    def test_member_roll_swaps_bending_inertias(self):
        project = beam()
        project.loads["L1"] = SpatialLoad("L1", "N2", "FY", -1)
        zero = solve(project).displacements["N2"][1]
        project.members["M1"].roll = 90
        rolled = solve(project).displacements["N2"][1]
        self.assertAlmostEqual(rolled/zero, 4)

    def test_oblique_local_loading_and_displacement_transform(self):
        project = beam()
        project.nodes["N2"].x, project.nodes["N2"].y, project.nodes["N2"].z = 40, 80, 80
        project.members["M1"].roll = 33
        project.loads["L1"] = SpatialLoad("L1", "M1", "Fz", -2, 1)
        result = solve(project)
        axes = member_axes(project, "M1", result)
        global_tip = result.displacements["N2"][:3]
        local_tip = axes @ global_tip
        self.assertAlmostEqual(local_tip[2], -2*120**3/(3*30000*20))
        xs, values, displacement = sampled_member(project, result, "M1")
        for value, expected in zip(displacement[-1], global_tip):
            self.assertAlmostEqual(value, expected)

    def test_uniform_and_triangular_loads_both_planes(self):
        for direction, index, inertia in (("FY", 1, 80), ("FZ", 2, 20)):
            for end in (-.02, -.04):
                project = beam()
                project.loads["L1"] = SpatialLoad("L1", "M1", direction, -.02, 0, "distributed", end)
                result = solve(project)
                expected = -.02*120**4/(8*30000*inertia)
                if end == -.04:
                    expected += -.02*120**4*11/(120*30000*inertia)
                self.assertAlmostEqual(result.displacements["N2"][index], expected)
                self.assertAlmostEqual(result.reactions["N1"][index], -(.5*(-.02+end)*120))

    def test_global_self_weight_uses_spatial_length(self):
        project = beam()
        project.nodes["N2"].x, project.nodes["N2"].z = 72, 96
        project.self_weight_case = "Case 1"
        self.assertAlmostEqual(project.self_weight_total(), .0002*8*120)
        self.assertEqual(project.self_weight_loads()[0].direction, "FY")
        result = solve(project)
        self.assertAlmostEqual(result.reactions["N1"][1], project.self_weight_total())

    def test_all_six_bilateral_springs_are_real_supports(self):
        project = beam()
        base = project.nodes["N1"]
        base.support = "free"
        base.spring_x = base.spring_y = base.spring_z = 1000
        base.spring_rx = base.spring_ry = base.spring_rz = 100000
        project.loads["L1"] = SpatialLoad("L1", "N2", "FZ", -2)
        result = solve(project)
        self.assertAlmostEqual(result.displacements["N1"][2], -.002)
        self.assertAlmostEqual(result.displacements["N1"][4], 240/100000)
        self.assertAlmostEqual(result.reactions["N1"][2], 2)

    def test_missing_out_of_plane_restraint_is_not_artificially_added(self):
        project = beam()
        node = project.nodes["N1"]
        node.support = "custom"
        node.restraint_x = node.restraint_y = node.restraint_rx = node.restraint_ry = node.restraint_rz = True
        with self.assertRaisesRegex(ValueError, "DZ"):
            solve(project)

    def test_missing_torsional_restraint_is_reported(self):
        project = beam()
        project.nodes["N1"].support = "pin"
        with self.assertRaisesRegex(ValueError, "RX"):
            solve(project)

    def test_result_combinations_pickle_and_unit_invariance(self):
        project = beam()
        project.loads["L1"] = SpatialLoad("L1", "N2", "FZ", -2)
        project.set_combination("Double", {"Case 1": 2})
        result = pickle.loads(pickle.dumps(solve(project)))
        doubled = result.for_combination("Double")
        self.assertEqual(doubled.snapshot_id, result.snapshot_id)
        self.assertTrue(doubled.spatial)
        self.assertAlmostEqual(doubled.displacements["N2"][2], 2*result.displacements["N2"][2])
        for key in UNIT_SYSTEMS:
            project.unit_system = key
            self.assertEqual(model_signature(project), result.model_signature)

    def test_sampling_point_force_jump_has_both_sides(self):
        project = beam()
        project.loads["L1"] = SpatialLoad("L1", "M1", "FZ", -3, .5)
        xs, values, displacement = sampled_member(project, solve(project), "M1")
        indices = [i for i,x in enumerate(xs) if x == 60]
        self.assertEqual(len(indices), 2)
        self.assertAlmostEqual(abs(values[indices[0], 2]-values[indices[1], 2]), 3)

    def test_space_frame_combinations_equilibrium(self):
        project = example_project("3d_space_frame")
        result = solve(project)
        for combo, expected in (("Gravity", (0,12.6,0)), ("Wind", (-1,0,-1.5)), ("Combined", (-1,12.6,-1.5))):
            reactions = result.for_combination(combo).reactions
            for index, target in enumerate(expected):
                self.assertAlmostEqual(sum(row[index] for row in reactions.values()), target)


class SpatialWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.load_project(beam())

    def tearDown(self):
        self.window.saved = self.window.project.to_dict()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def result(self):
        self.window.analysis_revision = self.window.revision
        self.window.analysis_finished(solve(self.window.project), None)

    def test_switch_dimensions_preserves_planar_view(self):
        planar = self.window.planar_view
        self.assertEqual(self.window.results_table.columnCount(), 13)
        self.window.load_project(example_project("simple_beam"))
        self.assertIs(self.window.view, planar)
        self.assertEqual(self.window.results_table.columnCount(), 7)

    def test_angle_inspector_preview_undo_payload_and_report(self):
        project = self.window.project
        project.loads["L1"] = SpatialLoad("L1","N2","FY",10)
        self.window.select(("loads","L1"))
        inspector = self.window.inspector
        direction = inspector.findChild(QComboBox,"spatial_load_direction")
        direction.setCurrentIndex(direction.findData("Angle"))
        # An unchanged +FY converts to the shown +90 elevation, not an old default angle.
        inspector.findChild(QPushButton,"spatial_apply").click()
        self.assertEqual(self.window.project.loads["L1"].elevation,90)
        self.window.select(("loads","L1"))
        inspector.findChild(QDoubleSpinBox,"spatial_load_azimuth").setValue(30)
        inspector.findChild(QDoubleSpinBox,"spatial_load_elevation").setValue(20)
        self.assertIn("FZ",inspector.findChild(QLabel,"spatial_load_components").text())
        inspector.findChild(QPushButton,"spatial_apply").click()
        load = self.window.project.loads["L1"]
        self.assertEqual((load.angle,load.elevation),(30,20))
        payload = viewport_payload(self.window)
        for value, expected in zip(payload["loads"][0]["vector"],dict(load.components(magnitude=1)).values()):
            self.assertAlmostEqual(value,expected)
        self.assertIn("az 30",payload["loads"][0]["label"])
        from pynitegui.qt.spatial_results import definition_tables
        table = next(table for table in definition_tables(self.window.project) if table[0].startswith("Manual Loads"))
        self.assertEqual(table[2][0][-2:],[30,20])
        self.window.undo.undo()
        self.assertEqual(self.window.project.loads["L1"].elevation,90)

    def test_angle_tables_preserve_precision_and_units(self):
        self.window.project.loads["L1"] = SpatialLoad("L1","M1","Angle",-.02,0,"distributed",-.04,1,angle=33.123456789,elevation=17.987654321)
        self.window.set_units("si")
        dialog = ModelTablesDialog(self.window,self.window.project)
        self.assertEqual(dialog.preview().to_dict(),self.window.project.to_dict())
        table = dialog.tables["loads"]
        table.item(0,dialog.fields["loads"].index("elevation")).setText("-20")
        self.assertEqual(dialog.preview().loads["L1"].elevation,-20)
        self.assertEqual(dialog.preview().loads["L1"].magnitude,-.02)
        dialog.deleteLater()

    def test_graphics_diagnostics_distinguish_observed_and_requested(self):
        from pynitegui.qt.graphics_diagnostics import GraphicsDiagnostics
        dialog = GraphicsDiagnostics(self.window)
        self.assertEqual(dialog.values["renderer"].text(),"Unavailable")
        self.assertEqual(dialog.values["status"].text(),"Not ready")
        dialog.received(json.dumps({"renderer":"ANGLE (NVIDIA)","vendor":"NVIDIA","version":"WebGL 2.0","shader":"GLSL ES","source":"Unmasked WebGL driver","lost":False}),dialog.serial)
        self.assertEqual(dialog.values["renderer"].text(),"ANGLE (NVIDIA)")
        self.assertEqual(dialog.values["status"].text(),"Ready")
        self.assertEqual(dialog.values["mode"].text(),"auto")
        dialog.received(json.dumps({"renderer":"stale"}),dialog.serial-1)
        self.assertEqual(dialog.values["renderer"].text(),"ANGLE (NVIDIA)")
        dialog.received("invalid JSON",dialog.serial)
        self.assertEqual(dialog.values["status"].text(),"Renderer information unavailable")
        self.window.load_project(example_project("simple_beam"))
        dialog.refresh()
        self.assertEqual(dialog.values["status"].text(),"No active 3D viewport")
        dialog.deleteLater()

    def test_new_3d_project_respects_discard_and_units(self):
        self.window.project.unit_system = "si"
        before = self.window.project.to_dict()
        with patch.object(self.window,"confirm_discard",return_value=False):
            self.window.new_spatial_project()
        self.assertEqual(self.window.project.to_dict(),before)
        with patch.object(self.window,"confirm_discard",return_value=True):
            self.window.new_spatial_project()
        self.assertEqual(self.window.project.unit_system,"si")
        self.assertEqual(self.window.project.nodes,{})

    def test_xyz_inspector_is_atomic_and_undoable(self):
        self.result()
        self.window.select(("nodes","N2"))
        field = self.window.inspector.findChild(QDoubleSpinBox,"spatial_z")
        field.setValue(50)
        self.window.inspector.findChild(QPushButton,"spatial_apply").click()
        self.assertEqual(self.window.project.nodes["N2"].z,50)
        self.assertIsNone(self.window.result)
        self.window.undo.undo()
        self.assertEqual(self.window.project.nodes["N2"].z,0)

    def test_member_roll_and_selected_local_axes(self):
        self.window.select(("members","M1"))
        self.window.inspector.findChild(QDoubleSpinBox,"spatial_roll").setValue(45)
        self.window.inspector.findChild(QPushButton,"spatial_apply").click()
        self.assertEqual(self.window.project.members["M1"].roll,45)
        self.assertEqual(viewport_payload(self.window)["selection"],[["members","M1"]])

    def test_custom_support_retains_six_flags(self):
        self.window.select(("nodes","N1"))
        self.window.inspector.findChild(QComboBox,"spatial_support").setCurrentText("custom")
        self.window.inspector.findChild(QCheckBox,"restraint_z").setChecked(False)
        self.window.inspector.findChild(QPushButton,"spatial_apply").click()
        self.assertEqual(self.window.project.nodes["N1"].restraints,(True,True,False,True,True,True))

    def test_tables_preserve_precision_and_convert_xyz_moments(self):
        project = self.window.project
        project.unit_system = "si"
        project.nodes["N2"].z = 12.1234567890123
        project.members["M1"].roll = 32.1234567890123
        project.loads["L1"] = SpatialLoad("L1","N2","MY",12.1234567890123)
        dialog = ModelTablesDialog(self.window,project)
        self.assertEqual(dialog.preview().to_dict(),project.to_dict())
        for kind,key,row,value in (("nodes","z",1,"2"),("loads","magnitude",0,"3"),("members","roll",0,"45")):
            dialog.tables[kind].item(row,dialog.fields[kind].index(key)).setText(value)
        candidate = dialog.preview()
        self.assertAlmostEqual(candidate.nodes["N2"].z,project.units.from_display(2,"length"))
        self.assertAlmostEqual(candidate.loads["L1"].magnitude,project.units.from_display(3,"moment"))
        self.assertEqual(candidate.members["M1"].roll,45)
        self.assertEqual(dialog.tables["loads"].horizontalHeaderItem(dialog.fields["loads"].index("units")).text(),"Magnitude units")

    def test_native_member_load_dialog_creates_full_span_local_distribution(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QDialog
        self.window.select(("members","M1"))
        def fill():
            dialog = self.window.findChild(QDialog)
            dialog.findChild(QComboBox,"spatial_load_type").setCurrentText("distributed")
            direction = dialog.findChild(QComboBox,"spatial_load_direction")
            direction.setCurrentIndex(direction.findData("Fz"))
            dialog.accept()
        QTimer.singleShot(0,fill)
        self.window.add_load()
        load = self.window.project.loads["L1"]
        self.assertEqual((load.kind,load.direction,load.position,load.end_position),("distributed","Fz",0,1))
        self.window.undo.undo()
        self.assertEqual(self.window.project.loads,{})

    def test_view_payload_local_load_vectors_and_deformation(self):
        project = self.window.project
        project.members["M1"].roll = 90
        project.loads["L1"] = SpatialLoad("L1","M1","Fz",-2,.5)
        project.set_combination("Double",{"Case 1":2})
        self.result()
        self.window.select_result_combination("Double")
        self.window.deformed_action.setChecked(True)
        payload = viewport_payload(self.window)
        self.assertAlmostEqual(abs(payload["loads"][0]["vector"][1]),1)
        self.assertEqual(payload["loads"][0]["magnitude"],-4)
        self.assertTrue(payload["deformed"])
        self.assertGreater(payload["factor"],0)
        self.assertEqual(len(payload["members"][0]["points"]),len(payload["members"][0]["displacements"]))
        json.dumps(payload,allow_nan=False)

    def test_deformation_controls_are_enabled_and_custom_factor_is_used(self):
        self.window.project.loads["L1"] = SpatialLoad("L1","N2","FZ",2)
        self.result()
        self.window.deformed_action.setChecked(True)
        viewport_payload(self.window)
        self.assertTrue(self.window.deformation_mode.isEnabled())
        self.window.deformation_mode.setCurrentIndex(self.window.deformation_mode.findData("custom"))
        self.window.deformation_scale.setValue(25)
        self.assertEqual(viewport_payload(self.window)["factor"],25)
        self.assertTrue(self.window.deformation_scale.isEnabled())

    def test_all_six_overlay_components_and_units(self):
        for i, direction in enumerate(("FX", "FY", "FZ", "MX", "MY", "MZ")):
            self.window.project.loads[f"L{i+1}"] = SpatialLoad(f"L{i+1}", "N2", direction, i+1)
        self.window.project.members["M1"].roll = 37
        self.result()
        _, sampled, _ = sampled_member(self.window.project, self.window.result, "M1")
        for i, kind in enumerate(QUANTITIES[:6]):
            self.window.view.diagram.setCurrentIndex(self.window.view.diagram.findData(kind))
            payload = viewport_payload(self.window)
            self.assertEqual(payload["diagram"]["axis"], DIAGRAM_AXES[i])
            self.assertEqual(payload["members"][0]["diagramValues"], sampled[:, i].tolist())
            self.assertAlmostEqual(payload["diagram"]["minimum"], sampled[:, i].min())
            self.assertAlmostEqual(payload["diagram"]["maximum"], sampled[:, i].max())
            self.assertEqual(payload["diagram"]["unit"], "kip" if i<3 else "kip-in")
            json.dumps(payload, allow_nan=False)

    def test_diagram_combination_scale_and_units_preserve_physical_offsets(self):
        self.window.project.loads["L1"] = SpatialLoad("L1", "N2", "FY", -2)
        self.window.project.set_combination("Double", {"Case 1": 2})
        self.result()
        view = self.window.view
        view.diagram.setCurrentIndex(view.diagram.findData("moment_z"))
        original = viewport_payload(self.window)
        self.assertAlmostEqual(abs(original["members"][0]["diagramValues"][0]), 2*120)
        self.assertAlmostEqual(original["members"][0]["diagramValues"][-1], 0.)
        view.diagram_scale.setValue(2)
        doubled_scale = viewport_payload(self.window)
        self.assertAlmostEqual(doubled_scale["diagram"]["factor"], original["diagram"]["factor"]*2)
        self.window.select_result_combination("Double")
        doubled_load = viewport_payload(self.window)
        self.assertEqual(doubled_load["diagram"]["combination"], "Double")
        self.assertAlmostEqual(doubled_load["diagram"]["factor"], original["diagram"]["factor"])
        self.window.set_units("si")
        metric = viewport_payload(self.window)
        self.assertEqual(metric["diagram"]["unit"], "kN-m")
        self.assertEqual(metric["diagram"]["factor"], doubled_load["diagram"]["factor"])
        self.assertEqual(metric["members"][0]["diagramValues"], doubled_load["members"][0]["diagramValues"])

    def test_diagram_jump_zero_and_stale_results(self):
        self.window.project.loads["L1"] = SpatialLoad("L1", "M1", "FY", -10, .5)
        self.result()
        view = self.window.view
        view.diagram.setCurrentIndex(view.diagram.findData("shear_y"))
        member = viewport_payload(self.window)["members"][0]
        indices = [i for i,p in enumerate(member["points"]) if p == [60.,0.,0.]]
        self.assertEqual(len(indices), 2)
        self.assertAlmostEqual(abs(member["diagramValues"][indices[1]]-member["diagramValues"][indices[0]]), 10)
        view.diagram.setCurrentIndex(view.diagram.findData("axial"))
        self.assertEqual(viewport_payload(self.window)["diagram"]["factor"], 0.)
        self.window.edit("Move node", lambda p: setattr(p.nodes["N2"], "x", 144))
        self.assertIsNone(viewport_payload(self.window)["diagram"])
        self.assertFalse(view.diagram.isEnabled())
        self.assertFalse(view.diagram_scale.isEnabled())

    def test_diagram_controls_do_not_change_model_and_load_visibility(self):
        self.window.project.loads["L1"] = SpatialLoad("L1", "N2", "FY", -1)
        self.result()
        before = self.window.project.to_dict()
        view = self.window.view
        view.diagram.setCurrentIndex(view.diagram.findData("moment_z"))
        view.diagram_values.setChecked(False)
        view.show_loads.setChecked(False)
        payload = viewport_payload(self.window)
        self.assertEqual(payload["loads"], [])
        self.assertFalse(payload["diagram"]["values"])
        self.assertEqual(self.window.project.to_dict(), before)

    def test_spatial_png_save_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory)/"original.png"
            image = QImage(32, 24, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.red)
            self.assertTrue(image.save(str(original)))
            data = "data:image/png;base64," + base64.b64encode(original.read_bytes()).decode()
            output = Path(directory)/"export.png"
            self.window.view.save_image(str(output), data)
            exported = QImage(str(output))
            self.assertEqual(exported.size(), image.size())
            with patch.object(QMessageBox, "warning") as warning:
                self.window.view.save_image(str(output), "bad")
                warning.assert_called_once()

    def test_bridge_checks_selection_and_draw_arguments(self):
        bridge = Bridge(self.window.view)
        bridge.select("nodes","N2",False)
        bridge.select("members","M1",True)
        self.assertEqual(len(self.window.selections),2)
        bridge.select("__dict__","bad",False)
        self.assertEqual(self.window.selections,[])
        before = self.window.project.to_dict()
        self.window.set_mode("draw")
        for data in ('bad','[[1,2],[3,4]]','[[true,2,3],[4,5,6]]'):
            bridge.draw(data)
        self.assertEqual(self.window.project.to_dict(),before)
        bridge.draw('[[120,0,0],[120,0,120]]')
        self.assertEqual(len(self.window.project.members),2)
        self.window.undo.undo()
        self.assertEqual(self.window.project.to_dict(),before)

    def test_results_table_all_directions_with_units(self):
        self.window.project.loads["L1"] = SpatialLoad("L1","N2","FZ",2)
        self.result()
        self.window.set_units("si")
        self.assertEqual(self.window.results_table.columnCount(),13)
        self.assertEqual(self.window.results_table.horizontalHeaderItem(3).text(),"DZ (m)")
        actual = float(self.window.results_table.item(1,3).text())
        expected = self.window.project.units.to_display(self.window.result.displacements["N2"][2],"length")
        self.assertAlmostEqual(actual,expected,places=6)

    def test_retained_spatial_diagrams_and_report_options(self):
        self.result()
        self.window.diagrams()
        from pynitegui.qt.spatial_diagrams import SpatialDiagramDialog
        dialog = self.window.findChild(SpatialDiagramDialog)
        self.assertEqual(len(dialog.figure.axes),8)
        self.window.edit("Geometry",lambda p:setattr(p.nodes["N2"],"z",30))
        self.assertIn("Retained",dialog.snapshot_status.text())
        options = ReportOptionsDialog(dialog)
        options.accept()
        self.assertEqual(options.definition.diagrams,())
        self.assertEqual(options.definition.envelope_combinations,())
        self.assertIn("FZ (kip)",report_html(dialog.project,dialog.result))


class SpatialExportTests(unittest.TestCase):
    def test_six_direction_tables_and_snapshot_check(self):
        project = beam()
        project.loads["L1"] = SpatialLoad("L1","N2","MY",10)
        result = solve(project)
        project.unit_system = "si"
        headers,rows = result_table(project,result,"nodes")
        self.assertEqual(len(headers),13)
        self.assertAlmostEqual(rows[0][11],project.units.to_display(-10,"moment"))
        self.assertEqual(len(result_table(project,result,"members")[0]),11)
        project.nodes["N2"].z = 30
        with self.assertRaisesRegex(ValueError,"snapshot"):
            result_table(project,result,"nodes")

    def test_numerical_report_has_full_spatial_definitions(self):
        project = beam()
        project.loads["L1"] = SpatialLoad("L1","N2","MX",5)
        result = solve(project)
        html = report_html(project,result,source="<untrusted>")
        for text in ("3D spatial frame","DZ (in)","RX (rad)","MY (kip-in)","T (kip-in)","Roll (deg)","&lt;untrusted&gt;"):
            self.assertIn(text,html)
        self.assertNotIn("RZ is n/a",html)
        with self.assertRaisesRegex(ValueError,"3D reports"):
            report_html(project,result,options=ReportOptions(diagrams=("moment",)))
        with self.assertRaisesRegex(ValueError,"3D reports"):
            report_html(project,result,options=ReportOptions(envelope_combinations=("Service",)))

    def test_csv_includes_xyz_and_torsion(self):
        project = beam()
        result = solve(project)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"results.csv"
            export_csv(path,project,result,"nodes")
            self.assertIn("DZ (in)",path.read_text())
            export_csv(path,project,result,"members")
            self.assertIn("T (kip-in)",path.read_text())


if __name__ == "__main__":
    unittest.main()
