"""Malformed documents fail clearly without changing the active project."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.model import Load, Project


def document():
    project = Project()
    project.add_member((0, 0), (120, 0))
    project.nodes["N1"].support = "fixed"
    project.loads["L1"] = Load("L1", "M1")
    return project.to_dict()


class ValidationTests(unittest.TestCase):
    def test_top_level_and_version_types(self):
        for value in (None, [], "project", 123, True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "JSON object"):
                Project.from_dict(value)
        for version in (True, 15.0, "15", 0, 16, None):
            data = document()
            data["version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "version"):
                Project.from_dict(data)

    def test_required_fields_and_collection_shapes(self):
        for key in ("grid", "nodes", "members", "loads", "materials", "sections", "combinations", "unit_system"):
            data = document()
            del data[key]
            with self.subTest(missing=key), self.assertRaisesRegex(ValueError, key):
                Project.from_dict(data)
        for key in ("nodes", "members", "loads", "materials", "sections", "combinations"):
            for value in (None, [], "wrong"):
                data = document()
                data[key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key.capitalize() if key == "combinations" else key):
                    Project.from_dict(data)
        data = document()
        data["combinations"]["Service"] = [["Case 1", 1]]
        with self.assertRaisesRegex(ValueError, "combination"):
            Project.from_dict(data)

    def test_entity_shapes_unknown_and_missing_fields(self):
        for key, name in (("nodes", "N1"), ("members", "M1"), ("loads", "L1"),
                          ("materials", "Steel_A992"), ("sections", "W18x35")):
            for value in (None, [], {}, {"name": name, "unsupported": 1}):
                data = document()
                data[key][name] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                    Project.from_dict(data)

    def test_numbers_reject_strings_booleans_nonfinite_and_huge_integers(self):
        fields = (("nodes", "N1", "x"), ("nodes", "N1", "y"),
                  ("materials", "Steel_A992", "E"), ("materials", "Steel_A992", "nu"),
                  ("materials", "Steel_A992", "rho"), ("sections", "W18x35", "A"),
                  ("loads", "L1", "magnitude"), ("loads", "L1", "position"),
                  ("loads", "L1", "angle"), ("loads", "L1", "end_magnitude"),
                  ("loads", "L1", "end_position"), ("combinations", "Service", "Case 1"))
        for key, name, field in fields:
            for value in (True, "1", None, float("nan"), float("inf"), 10**400):
                data = document()
                data[key][name][field] = value
                with self.subTest(key=key, field=field, value=value), self.assertRaises(ValueError):
                    Project.from_dict(data)

    def test_identifiers_and_unhashable_references(self):
        for key, name, field in (("members", "M1", "start"), ("members", "M1", "material"),
                                 ("loads", "L1", "target")):
            for value in ([], {}, "", " missing "):
                data = document()
                data[key][name][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    Project.from_dict(data)
        data = document()
        data["members"]["N1"] = data["members"].pop("M1")
        data["members"]["N1"]["name"] = "N1"
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            Project.from_dict(data)

    def test_every_supported_version_migrates_without_mutating_input(self):
        for version in range(1, 16):
            data = document()
            data["version"] = version
            if version < 11:
                data.pop("self_weight_case")
                data.pop("self_weight_factor")
            if version < 7:
                data.pop("unit_system")
            if version < 5:
                for key in ("load_cases", "default_load_case", "combinations"):
                    data.pop(key)
                data["loads"]["L1"].pop("case")
            if version < 3:
                section = data.pop("sections")[data.pop("default_section")]
                data.update({key: section[key] for key in ("A", "Iy", "Iz", "J")})
                data["members"]["M1"].pop("section")
            if version == 1:
                material = data.pop("materials")[data.pop("default_material")]
                data.update({key: material[key] for key in ("E", "nu", "rho")})
                data["members"]["M1"].pop("material")
            before = copy.deepcopy(data)
            with self.subTest(version=version):
                project = Project.from_dict(data)
                self.assertEqual(project.to_dict()["version"], 15)
                self.assertEqual(project.nodes["N2"].x, 120)
                self.assertEqual(data, before)

    def test_duplicate_json_and_syntax_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for text, message in (('{"version":10,"version":1}', "Duplicate JSON"),
                                  ('{"nodes":{"N1":{},"N1":{}}}', "Duplicate JSON"),
                                  ('{\n "version":', "line 2")):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                    Project.open(path)

    def test_failed_open_preserves_editor_and_saved_file(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.load_project(Project.from_dict(document()))
        before = window.project.to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"version": 10, "units": "in-kip"}))
            original = path.read_bytes()
            with patch("pynitegui.qt.app.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
                    patch("pynitegui.qt.app.QMessageBox.warning") as warning:
                window.open_project()
                warning.assert_called_once()
                self.assertIn("Missing project fields", warning.call_args.args[2])
            self.assertEqual(window.project.to_dict(), before)
            self.assertEqual(path.read_bytes(), original)
        window.close()
        window.deleteLater()
        app.processEvents()
