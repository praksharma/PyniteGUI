"""Explicit shear-modulus contracts and independent official-frame benchmarks."""
import contextlib
import copy
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from PySide6.QtWidgets import QApplication
from pynitegui.qt.analysis import analyze, model_signature
from pynitegui.qt.automation_core import AutomationError, batch_candidate
from pynitegui.qt.automation_schema import model_reference
from pynitegui.qt.examples import EXAMPLE_GROUPS, example_project
from pynitegui.qt.materials import MaterialEditor
from pynitegui.qt.material_library import PRESETS
from pynitegui.qt.mesh_model import MeshDefinition
from pynitegui.qt.model import Material, Project
from pynitegui.qt.official_examples import SOURCE_COMMIT
from pynitegui.qt.plate_model import PlateDefinition
from pynitegui.qt.spatial_model import SpatialLoad, SpatialProject
from pynitegui.qt.units import UNIT_SYSTEMS

KEYS = ("3d_official_space_frame_1", "3d_official_space_frame_2")


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def independent_frame(project, number):
    """Assemble textbook Euler-Bernoulli axial/torsion/bending stiffness.

    Axis bases are explicit for these orthogonal benchmark members; no PyNite
    matrices, transforms or solver functions are used in this reference.
    """
    axes = (np.eye(3), np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]]), np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]])) if number == 1 else (
        np.eye(3), np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]]), np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]]))
    nodes = list(project.nodes)
    stiffness = np.zeros((6*len(nodes), 6*len(nodes)))
    force = np.zeros(6*len(nodes))
    elements = {}
    for (name, member), basis in zip(project.members.items(), axes):
        a, b = (project.nodes[n] for n in (member.start, member.end))
        length = math.dist(a.coords, b.coords)
        section = project.sections[member.section]
        k = np.zeros((12, 12))
        for indices, rigidity in (((0, 6), 30000.*section.A), ((3, 9), 10000.*section.J)):
            k[np.ix_(indices, indices)] = rigidity/length*np.array([[1., -1.], [-1., 1.]])
        bending = np.array([[12., 6*length, -12., 6*length], [6*length, 4*length**2, -6*length, 2*length**2],
                            [-12., -6*length, 12., -6*length], [6*length, 2*length**2, -6*length, 4*length**2]])
        k[np.ix_((1, 5, 7, 11), (1, 5, 7, 11))] = 30000.*section.Iz/length**3*bending
        signs = np.diag([1., -1., 1., -1.])
        k[np.ix_((2, 4, 8, 10), (2, 4, 8, 10))] = 30000.*section.Iy/length**3*(signs@bending@signs)
        transform = np.kron(np.eye(4), basis)
        indices = np.array([6*nodes.index(node)+dof for node in (member.start, member.end) for dof in range(6)])
        stiffness[np.ix_(indices, indices)] += transform.T@k@transform
        elements[name] = k, transform, indices
    forces = ("FX", "FY", "FZ", "MX", "MY", "MZ")
    for load in project.loads.values():
        force[6*nodes.index(load.target)+forces.index(load.direction)] += load.magnitude
    free = [6*i+d for i, name in enumerate(nodes) for d, fixed in enumerate(project.nodes[name].restraints) if not fixed]
    displacement = np.zeros(len(force))
    displacement[free] = np.linalg.solve(stiffness[np.ix_(free, free)], force[free])
    reactions = stiffness@displacement-force
    end_forces = {name: k@transform@displacement[indices] for name, (k, transform, indices) in elements.items()}
    return displacement.reshape(-1, 6), reactions.reshape(-1, 6), end_forces


class IndependentGModelTests(unittest.TestCase):
    def test_derived_default_explicit_validation_and_library_provenance(self):
        self.assertAlmostEqual(Material("Default").G, 29000/2.6)
        for value in (True, False, 0., -1., math.inf, math.nan, "10000"):
            with self.assertRaisesRegex(ValueError, "independent G"):
                Material("Bad", shear_modulus=value).validate()
        material = Material("Independent", E=30000., nu=.3, shear_modulus=10000.)
        material.validate()
        self.assertEqual(material.G, 10000.)
        preset = PRESETS[0]
        with self.assertRaisesRegex(ValueError, "library properties differ"):
            Material("Preset", **preset.properties(), preset=preset.key, shear_modulus=10000.).validate()
        with self.assertRaisesRegex(ValueError, "effective G"):
            Material("Overflow", E=1e308, nu=-.9999999999999999).validate()

    def test_versioned_roundtrips_legacy_migration_and_conversion(self):
        from pynitegui.qt.spatial_conversion import to_spatial
        for cls, version, legacy in ((Project, 25, 23), (SpatialProject, 28, 24)):
            p = cls()
            old = p.to_dict()
            old["version"] = legacy
            for material in old["materials"].values():
                material.pop("shear_modulus")
            before = copy.deepcopy(old)
            restored = Project.from_dict(old)
            self.assertIsNone(restored.materials[restored.default_material].shear_modulus)
            self.assertEqual(old, before)
            p.materials[p.default_material].shear_modulus = 10000.
            self.assertEqual(p.to_dict()["version"], version)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"model.json"
                p.save(path)
                self.assertEqual(Project.open(path).to_dict(), p.to_dict())
            lowered = p.to_dict()
            lowered["version"] = legacy
            with self.assertRaisesRegex(ValueError, "Independent G"):
                Project.from_dict(lowered)
            if cls is Project:
                self.assertEqual(to_spatial(p).materials[p.default_material].G, 10000.)

    def test_surface_and_plate_recipes_reject_ignored_independent_g(self):
        for definition in (MeshDefinition(), PlateDefinition()):
            data = definition.to_dict()
            self.assertNotIn("shear_modulus", data["material"])
            self.assertEqual(type(definition).from_dict(data).to_dict(), data)
            definition.material.shear_modulus = 1000.
            with self.assertRaisesRegex(ValueError, "Surface/plate"):
                definition.validate()

    def test_mcp_schema_atomic_validation_and_preset_clearing(self):
        p = Project()
        item = PRESETS[0]
        p.materials["Preset"] = Material("Preset", **item.properties(), preset=item.key)
        schema = model_reference()
        g = schema["entities"]["materials"]["properties"]["shear_modulus"]
        self.assertEqual(g["type"], ["number", "null"])
        q = batch_candidate(p, [{"op":"put", "collection":"materials", "key":"Preset", "value":{"shear_modulus":10000.}}])
        self.assertIsNone(q.materials["Preset"].preset)
        self.assertEqual(q.materials["Preset"].G, 10000.)
        self.assertEqual(p.materials["Preset"].preset, item.key)
        restored = batch_candidate(q, [{"op":"put", "collection":"materials", "key":"Preset", "value":{"shear_modulus":None}}])
        self.assertIsNone(restored.materials["Preset"].shear_modulus)
        before = p.to_dict()
        with self.assertRaises(AutomationError):
            batch_candidate(p, [{"op":"put", "collection":"materials", "key":"Preset", "value":{"shear_modulus":-1.}}])
        self.assertEqual(p.to_dict(), before)


class OfficialSpaceFrameTests(unittest.TestCase):
    def test_both_frames_match_independent_stiffness_and_pinned_upstream_results(self):
        fixture = json.loads((Path(__file__).parent/"fixtures/official_space_frames.json").read_text())
        self.assertEqual(fixture["source_commit"], SOURCE_COMMIT)
        for number, key in enumerate(KEYS, 1):
            p = example_project(key)
            before = p.to_dict()
            r = solve(p)
            displacements, reactions, ends = independent_frame(p, number)
            upstream = fixture["examples"][str(number)]
            for i, name in enumerate(p.nodes):
                np.testing.assert_allclose(r.displacements[name], displacements[i], rtol=1e-10, atol=1e-12)
                np.testing.assert_allclose(r.reactions[name], reactions[i], rtol=1e-10, atol=1e-8)
                np.testing.assert_allclose(r.displacements[name], upstream["displacements"][name], rtol=1e-10, atol=1e-12)
                np.testing.assert_allclose(r.reactions[name], upstream["reactions"][name], rtol=1e-10, atol=1e-8)
            for name in p.members:
                actual = r.solver.members[name].f("Combo 1").flatten()
                np.testing.assert_allclose(actual, ends[name], rtol=1e-10, atol=1e-8)
                np.testing.assert_allclose(actual, upstream["member_end_forces"][name], rtol=1e-10, atol=1e-8)
            self.assertEqual(p.to_dict(), before)
            p.materials["Steel"].shear_modulus = None
            self.assertNotEqual(model_signature(p), r.model_signature)
            altered = solve(p)
            self.assertFalse(np.allclose(altered.displacements["N1" if number == 1 else "N2"], r.displacements["N1" if number == 1 else "N2"], rtol=1e-3, atol=1e-10))

    def test_explicit_g_controls_cantilever_torsion_in_all_display_units(self):
        for unit in UNIT_SYSTEMS:
            p = SpatialProject(unit_system=unit)
            p.materials[p.default_material].shear_modulus = 10000.
            p.add_member((0., 0., 0.), (120., 0., 0.))
            p.nodes["N1"].support = "fixed"
            p.loads["L1"] = SpatialLoad("L1", "N2", "MX", 12.)
            r = solve(p)
            self.assertAlmostEqual(r.displacements["N2"][3], 12.*120./(10000.*p.sections[p.default_section].J), places=12)

    def test_examples_are_fresh_and_save_reopen_in_every_unit_system(self):
        for key in KEYS:
            self.assertIn(key, EXAMPLE_GROUPS["3D Frames"])
            for unit in UNIT_SYSTEMS:
                p = example_project(key, unit)
                self.assertEqual(p.materials["Steel"].G, 10000.)
                self.assertEqual(Project.from_dict(p.to_dict()).to_dict(), p.to_dict())
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory)/"official.json"
                    p.save(path)
                    self.assertEqual(Project.open(path).to_dict(), p.to_dict())
                p.materials["Steel"].shear_modulus = 5000.
                self.assertEqual(example_project(key, unit).materials["Steel"].G, 10000.)


class IndependentGUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_unit_aware_editor_preserves_precision_and_explicit_derived_mode(self):
        for unit in UNIT_SYSTEMS:
            p = Project(unit_system=unit)
            material = Material("Exact", E=30000.123456789, nu=.3, shear_modulus=10000.123456789)
            d = MaterialEditor(None, p, material)
            self.assertTrue(d.independent_G.isChecked())
            self.assertTrue(d.G_input.isEnabled())
            d.accept()
            self.assertEqual(d.definition.shear_modulus, material.shear_modulus)
            self.assertEqual(d.definition.E, material.E)
            d.deleteLater()
            d = MaterialEditor(None, p, material)
            d.independent_G.setChecked(False)
            d.accept()
            self.assertIsNone(d.definition.shear_modulus)
            self.assertAlmostEqual(d.definition.G, material.E/2.6)
            d.deleteLater()
        self.app.processEvents()

    def test_library_g_override_becomes_custom_and_native_examples_load(self):
        from pynitegui.qt.app import MainWindow
        from pynitegui.qt.example_browser import NOTES
        p = Project()
        preset = PRESETS[0]
        d = MaterialEditor(None, p, Material("Library", **preset.properties(), preset=preset.key))
        d.independent_G.setChecked(True)
        d.G_input.setValue(10000.)
        d.accept()
        self.assertIsNone(d.definition.preset)
        d.deleteLater()
        window = MainWindow()
        try:
            for key in KEYS:
                self.assertIn(key, NOTES)
                window.example(key)
                self.assertEqual(window.project.materials["Steel"].G, 10000.)
                self.assertEqual(len(window.project.members), 3)
                window.saved = window.project.to_dict()
        finally:
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()
            self.app.processEvents()
