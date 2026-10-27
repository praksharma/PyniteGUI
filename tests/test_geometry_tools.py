"""Atomic geometry plans, physical assignments and native preview lifecycle."""
import contextlib
import io
import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.analysis import analyze
from pynitegui.qt.geometry_tools import plan_transform, plan_generator, plan_merge, preview_geometry, spacing_list
from pynitegui.qt.geometry_panel import open_geometry_tool
from pynitegui.qt.model import Project, Node, Load
from pynitegui.qt.spatial_model import SpatialProject, SpatialLoad
from pynitegui.qt.spatial_results import member_axes


class GeometryPlanTests(unittest.TestCase):
    def beam(self, spatial=False):
        p = SpatialProject() if spatial else Project()
        p.add_member((0, 0, 0) if spatial else (0, 0), (120, 0, 0) if spatial else (120, 0))
        p.nodes["N1"].support = "fixed"
        cls = SpatialLoad if spatial else Load
        p.loads["L1"] = cls("L1", "M1", "Fy" if spatial else "Local y", -2., .3, "distributed", -4., .9)
        p.loads["L2"] = cls("L2", "N2", "FY", -3.)
        p.groups = {"Original": {"nodes": ["N1"], "members": ["M1"]}}
        return p

    def test_connected_array_requires_explicit_reuse_and_preserves_loads_releases(self):
        p = self.beam()
        p.members["M1"].release_end = True
        before = p.to_dict()
        with self.assertRaisesRegex(ValueError, "collision"):
            plan_transform(p, [("members", "M1")], "repeat", offset=(120., 0., 0.))
        plan = plan_transform(p, [("members", "M1")], "repeat", offset=(120., 0., 0.), copies=2, reuse=True, copy_loads=True)
        q = plan.definition
        self.assertEqual((len(q.nodes), len(q.members), len(q.loads)), (4, 3, 6))
        self.assertEqual(q.members["M2"].start, "N2")
        self.assertTrue(q.members["M3"].release_end)
        load = q.loads["L3"]
        self.assertEqual((load.direction, load.position, load.end_position, load.end_magnitude), ("Local y", .3, .9, -4.))
        self.assertEqual(q.nodes["N3"].support, "free")
        self.assertEqual(q.groups, p.groups)
        self.assertEqual(p.to_dict(), before)
        self.assertEqual(Project.from_dict(q.to_dict()).to_dict(), q.to_dict())
        with self.assertRaisesRegex(ValueError, "Support conflict"):
            plan_transform(p, [("members", "M1")], "repeat", offset=(120., 0., 0.), reuse=True, copy_supports=True)

    def test_rotation_and_mirror_keep_spatial_section_axes_and_local_global_loads(self):
        p = self.beam(True)
        p.members["M1"].roll = 31.
        for operation, axis, angle in (("rotate", "Y", 90.), ("mirror", "X", 0.)):
            from pynitegui.qt.geometry_tools import transform_matrix
            matrix = transform_matrix(operation, angle, axis)
            q = plan_transform(p, [("members", "M1")], operation, axis=axis, angle=angle).definition
            np.testing.assert_allclose(member_axes(q, "M1")[:2], member_axes(p, "M1")[:2] @ matrix.T, atol=1e-12)
            self.assertEqual(q.loads, p.loads)
            self.assertEqual(q.nodes["N1"].restraints, p.nodes["N1"].restraints)
            self.assertEqual(SpatialProject.from_dict(q.to_dict()).to_dict(), q.to_dict())

    def test_moves_incident_members_and_rejects_collisions_overlaps_and_implicit_crossings(self):
        p = self.beam()
        p.add_member((120, 0), (120, 120))
        q = plan_transform(p, [("nodes", "N2")], "move", offset=(30., 0., 0.)).definition
        self.assertEqual(q.nodes["N2"].x, 150.)
        self.assertEqual(q.members["M2"].start, "N2")
        for selections, operation, options in (
                ([("nodes", "N2")], "move", {"offset": (-120., 0., 0.)}),
                ([("members", "M1")], "repeat", {"offset": (60., 0., 0.), "reuse": True}),
                ([("members", "M1")], "repeat", {"offset": (60., 30., 0.), "reuse": True}),
                ([("loads", "L1")], "move", {})):
            with self.assertRaises(ValueError):
                plan_transform(p, selections, operation, **options)

    def test_generators_connect_nonuniform_grid_use_properties_and_block_duplicate_placement(self):
        p = Project()
        plan = plan_generator(p, "frame", [120., 180.], [100., 140.], origin=(20., 30.), support="pin")
        q = plan.definition
        self.assertEqual((len(q.nodes), len(q.members)), (9, 10))
        self.assertEqual((max(n.x for n in q.nodes.values()), max(n.y for n in q.nodes.values())), (320., 270.))
        self.assertEqual(sum(n.support == "pin" for n in q.nodes.values()), 3)
        self.assertFalse(q.analysis_topology_issues())
        with self.assertRaises(ValueError):
            plan_generator(q, "frame", [120., 180.], [100., 140.], origin=(20., 30.), support="pin", reuse=True)
        beam = plan_generator(p, "beam", [120., 180.]).definition
        self.assertEqual([n.support for n in beam.nodes.values()], ["pin", "roller", "roller"])
        self.assertEqual(len(beam.members), 2)
        self.assertEqual(len(p.nodes), 0)
        for text in ("", "1,,2", "0,1", "nan", "-2"):
            with self.assertRaises(ValueError):
                spacing_list(text, p.units)
        self.assertEqual(spacing_list("1, 2", p.units), [1., 2.])
        with self.assertRaises(ValueError):
            plan_generator(SpatialProject(), "frame", [120.], [120.])

    def test_merge_preserves_every_reference_and_requires_conflict_choices(self):
        p = self.beam()
        p.nodes["N3"] = Node("N3", 120.01, 0., support="pin")
        p.loads["L3"] = Load("L3", "N3", "FX", 1.)
        p.groups["Original"]["nodes"].append("N3")
        before = p.to_dict()
        with self.assertRaisesRegex(ValueError, "Supports"):
            plan_merge(p, "N2", "N3", .02)
        with self.assertRaisesRegex(ValueError, "Both joints"):
            plan_merge(p, "N2", "N3", .02, support_policy="source")
        plan = plan_merge(p, "N2", "N3", .02, support_policy="source", combine_loads=True)
        q = plan.definition
        self.assertNotIn("N3", q.nodes)
        self.assertEqual(q.loads["L3"].target, "N2")
        self.assertEqual(q.nodes["N2"].support, "pin")
        self.assertEqual(q.groups["Original"]["nodes"], ["N1", "N2"])
        self.assertEqual(len(q.loads), len(p.loads))
        self.assertEqual(p.to_dict(), before)
        with self.assertRaises(ValueError):
            plan_merge(p, "N1", "N2", 200., support_policy="target")
        with self.assertRaises(ValueError):
            plan_merge(p, "N2", "N3", .001, support_policy="source", combine_loads=True)

    def test_merge_updates_member_ends_without_deleting_duplicate_or_zero_length_members(self):
        p = Project()
        p.add_member((0, 0), (120, 0))
        p.add_member((0, 10), (-120, 10))
        q = plan_merge(p, "N1", "N3", 10.).definition
        self.assertEqual(q.members["M2"].start, "N1")
        self.assertEqual(len(q.members), 2)
        p.add_member((0, 10), (120, 0))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            plan_merge(p, "N1", "N3", 10.)

    def test_unknown_and_bounded_parameters_are_rejected(self):
        p = self.beam()
        for options in ({"copies": 51}, {"offset": (math.nan, 0., 0.)}, {"axis": "bad"}):
            with self.assertRaises(ValueError):
                plan_transform(p, [("members", "M1")], "rotate", **options)
        with self.assertRaises(ValueError):
            plan_generator(Project(), "frame", [1.]*40, [1.]*40)


class GeometryEngineeringTests(unittest.TestCase):
    def test_generated_two_span_beam_matches_continuous_beam_reactions(self):
        p = plan_generator(Project(), "beam", [120., 120.]).definition
        for i, name in enumerate(p.members, 1):
            p.loads[f"L{i}"] = Load(f"L{i}", name, "FY", -.01, 0., "distributed", -.01, 1.)
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(p)
        self.assertAlmostEqual(result.reactions["N1"][1], .45, places=8)
        self.assertAlmostEqual(result.reactions["N2"][1], 1.5, places=8)
        self.assertAlmostEqual(result.reactions["N3"][1], .45, places=8)


class GeometryPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = MainWindow()
        self.w.show()
        self.app.processEvents()

    def tearDown(self):
        self.w.saved = self.w.project.to_dict()
        self.w.close()
        self.w.deleteLater()
        self.app.processEvents()

    def test_generator_preview_apply_undo_redo_and_cancel(self):
        w = self.w
        open_geometry_tool(w, 1)
        panel = w.geometry_panel
        original, revision = w.project.to_dict(), w.revision
        panel.preview()
        self.assertTrue(panel.apply_button.isEnabled(), panel.summary.text())
        self.assertEqual(w.project.to_dict(), original)
        self.assertEqual(w.revision, revision)
        self.assertEqual(len(preview_geometry(w.project, panel.plan)["lines"]), 10)
        panel.apply()
        self.assertEqual(w.undo.count(), 1)
        self.assertEqual(len(w.project.members), 10)
        self.assertIsNone(w.geometry_preview)
        w.undo.undo()
        self.assertEqual(w.project.to_dict(), original)
        w.undo.redo()
        self.assertEqual(len(w.project.members), 10)
        panel.controls["insert_X"].setValue(1000.)
        panel.preview()
        self.assertIsNotNone(w.geometry_preview)
        panel.cancel()
        self.assertIsNone(w.geometry_preview)
        self.assertEqual(len(w.project.members), 10)

    def test_controls_model_changes_units_mcp_and_stale_preview_never_apply(self):
        w = self.w
        open_geometry_tool(w, 1)
        panel = w.geometry_panel
        panel.preview()
        panel.controls["bays"].setText("200, 200")
        self.assertFalse(panel.apply_button.isEnabled())
        panel.preview()
        w.edit("Grid", lambda p: setattr(p, "grid", 24.))
        panel.apply()
        self.assertFalse(w.project.members)
        panel.preview()
        w.mcp_mode = True
        panel.apply()
        self.assertFalse(w.project.members)
        w.mcp_mode = False
        w.set_units("si")
        self.assertIsNone(w.geometry_preview)
        self.assertFalse(panel.preview_button.isEnabled())
        open_geometry_tool(w, 1)
        self.assertIsNot(w.geometry_panel, panel)
        w.geometry_panel.preview()
        self.assertTrue(w.geometry_panel.apply_button.isEnabled(), w.geometry_panel.summary.text())

    def test_escape_and_model_findings_use_same_preview_workflow(self):
        w = self.w
        w.project.nodes = {"N1": Node("N1", 0., 0.), "N2": Node("N2", .01, 0.)}
        w.refresh()
        w.show_model_findings(["Disconnected node groups: N1; N2."], "Check")
        self.assertTrue(w.model_findings.merge_button.isEnabled())
        w.model_findings.review_merge()
        panel = w.geometry_panel
        self.assertEqual(panel.tool.currentIndex(), 2)
        self.assertEqual(panel.controls["target"].currentData(), "N1")
        self.assertEqual(panel.controls["source"].currentData(), "N2")
        panel.preview()
        self.assertTrue(panel.apply_button.isEnabled(), panel.summary.text())
        panel.controls["operation"].setCurrentIndex(panel.controls["operation"].findData("mirror"))
        self.assertIn(panel.controls["axis"].currentData(), ("X", "Y"))
        panel.controls["operation"].setCurrentIndex(panel.controls["operation"].findData("rotate"))
        self.assertEqual(panel.controls["axis"].currentData(), "Z")
        panel.tool.setCurrentIndex(2)
        panel.preview()
        w.cancel_interaction()
        self.assertIsNone(w.geometry_preview)
        self.assertFalse(panel.apply_button.isEnabled())
        self.assertEqual(len(w.project.nodes), 2)

    def test_spatial_preview_payload_is_separate_from_pickable_model(self):
        from pynitegui.qt.spatial_view import viewport_payload
        w = self.w
        p = SpatialProject()
        p.add_member((0, 0, 0), (120, 0, 0))
        w.load_project(p)
        w.select_many([("members", "M1")])
        open_geometry_tool(w, 0)
        panel = w.geometry_panel
        panel.controls["operation"].setCurrentIndex(1)
        panel.controls["offset_X"].setValue(0.)
        panel.controls["offset_Z"].setValue(120.)
        panel.preview()
        self.assertTrue(panel.apply_button.isEnabled(), panel.summary.text())
        payload = viewport_payload(w)
        self.assertEqual(len(payload["members"]), 1)
        self.assertEqual(len(payload["geometryPreview"]["lines"]), 3)
        panel.cancel()
        self.assertFalse(viewport_payload(w)["geometryPreview"]["lines"])
