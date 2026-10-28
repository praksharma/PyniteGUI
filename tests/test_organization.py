"""Saved editing metadata, topology lifecycle and independent solver identity."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from pynitegui.qt.model import Project
from pynitegui.qt.examples import example_project
from pynitegui.qt.organization import level_selections, rename_entry, set_group, snap_elevation


class OrganizationModelTests(unittest.TestCase):
    def test_both_formats_roundtrip_legacy_migration_and_conversion(self):
        from pynitegui.qt.spatial_conversion import to_spatial
        for key, version, legacy in (("simple_beam", 25, 21), ("3d_space_frame", 28, 22)):
            p = example_project(key)
            old = p.to_dict()
            old["version"] = legacy
            for field in ("groups", "levels", "snap_levels"):
                old.pop(field)
            restored = Project.from_dict(old)
            self.assertEqual(restored.groups, {})
            set_group(p, "Frame A", [("nodes", "N1"), ("members", "M1")])
            p.levels, p.snap_levels = {"Base": -5.5, "Floor 1": 150.5}, True
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"grouped.json"
                p.save(path)
                self.assertEqual(Project.open(path).to_dict(), p.to_dict())
            self.assertEqual(p.to_dict()["version"], version)
            if version == 25:
                self.assertEqual(to_spatial(p).groups, p.groups)
                self.assertEqual(to_spatial(p).levels, p.levels)
            for field in ("groups", "levels", "snap_levels"):
                broken = p.to_dict()
                broken.pop(field)
                with self.assertRaisesRegex(ValueError, "Missing"):
                    Project.from_dict(broken)

    def test_split_subdivide_and_cascade_delete_keep_references(self):
        for key in ("simple_beam", "3d_space_frame"):
            for subdivision in (False, True):
                p = example_project(key)
                set_group(p, "Selected", [("nodes", "N1"), ("members", "M1")])
                parts = p.subdivide_members(["M1"], 3)["M1"] if subdivision else p.split_member("M1", .4)
                self.assertEqual(p.groups["Selected"]["members"], parts)
                self.assertEqual(p.groups["Selected"]["nodes"], ["N1"])
                p.delete("nodes", "N1")
                self.assertEqual(p.groups["Selected"]["nodes"], [])
                self.assertNotIn("M1", p.groups["Selected"]["members"])
                p.validate()
                self.assertEqual(p.clone().groups, p.groups)

    def test_invalid_metadata_is_rejected_without_rewriting_ids(self):
        p = example_project("simple_beam")
        set_group(p, "A", [("members", "M1"), ("members", "M1")])
        self.assertEqual(p.groups["A"]["members"], ["M1"])
        before = p.to_dict()
        with self.assertRaises(ValueError):
            set_group(p, "A", [("members", "missing")])
        self.assertEqual(p.to_dict(), before)
        bad = [({"A": {"nodes": [], "members": ["missing"]}}, {}, False),
               ({"A": {"nodes": [], "members": ["M1", "M1"]}}, {}, False),
               ({"A": {"nodes": []}}, {}, False), ({}, {"Bad": True}, False),
               ({}, {"Bad": float("nan")}, False), ({}, {" Bad ": 0.}, False), ({}, {}, 1)]
        for groups, levels, snap in bad:
            data = p.to_dict()
            data.update(groups=groups, levels=levels, snap_levels=snap)
            with self.assertRaises(ValueError):
                Project.from_dict(data)
        p.levels = {"First": 150.5}
        rename_entry(p, "levels", "First", "Roof")
        self.assertEqual(p.levels, {"Roof": 150.5})

    def test_levels_snap_before_grid_and_select_without_constraints(self):
        p = example_project("portal")
        p.levels, p.snap_levels = {"Roof": 150.5, "Base": -5.5}, True
        self.assertEqual(snap_elevation(p, 151.), 150.5)
        self.assertEqual(snap_elevation(p, -6.), -5.5)
        self.assertEqual(snap_elevation(p, 140.), 144.)
        p.unit_system = "si"
        self.assertEqual(snap_elevation(p, 151.), 150.5)
        p.snap_levels = False
        self.assertEqual(snap_elevation(p, 151.), 156.)
        bottom = {name for name, node in p.nodes.items() if node.y == 0}
        self.assertEqual(set(level_selections(p, 0)), {("nodes", n) for n in bottom})

    def test_mcp_geometry_deletion_prunes_groups_in_the_same_candidate(self):
        from pynitegui.qt.automation_core import batch_candidate
        p = example_project("simple_beam")
        set_group(p, "Beam", [("members", "M1")])
        operations = [{"op": "delete", "collection": "loads", "key": n} for n in p.loads]
        operations.append({"op": "delete", "collection": "members", "key": "M1"})
        candidate = batch_candidate(p, operations)
        self.assertEqual(candidate.groups["Beam"]["members"], [])
        self.assertEqual(p.groups["Beam"]["members"], ["M1"])


class OrganizationEngineeringTests(unittest.TestCase):
    def test_group_level_and_snap_metadata_leave_signature_and_solution_unchanged(self):
        from pynitegui.qt.analysis import analyze, model_signature
        for key in ("simple_beam", "3d_space_frame"):
            p = example_project(key)
            q = p.clone()
            set_group(q, "Frame", [("members", "M1")])
            q.levels, q.snap_levels = {"Floor": 150.5}, True
            self.assertEqual(model_signature(q), model_signature(p))
            with contextlib.redirect_stdout(io.StringIO()):
                a, b = analyze(p), analyze(q)
            self.assertEqual(a.reactions, b.reactions)
            self.assertEqual(a.displacements, b.displacements)
