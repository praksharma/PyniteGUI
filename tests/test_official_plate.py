"""Pinned official Quad plate: upstream parity, reference checks and native entry."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np
from Pynite import FEModel3D
from PySide6.QtWidgets import QApplication, QDialog
from pynitegui.qt.official_plate import PLATE_CATEGORY, PLATE_EXAMPLES, example_definition
from pynitegui.qt.plate_inspection import inspect_plate
from pynitegui.qt.plate_model import PlateDefinition, analyze_plate, select_plate_combination
from pynitegui.qt.units import UNIT_SYSTEMS


class OfficialPlateTests(unittest.TestCase):
    def test_upstream_transverse_parity_equilibrium_and_classical_reference(self):
        definition = example_definition()
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze_plate(definition)
            # Construction from the pinned official script, in its original ft/lb
            # system. Retain G=0.4E and free internal membrane/drilling DOFs.
            model = FEModel3D()
            E = 57000.*4000.**.5*144.
            model.add_material("Concrete", E, .4*E, .17, 150.)
            model.add_rectangle_mesh("MSH1", 1., 10., 20., 1., "Concrete", 1., 1., [0, 0, 0], "XY", element_type="Quad")
            model.meshes["MSH1"].generate()
            for element in model.quads.values():
                model.add_quad_surface_pressure(element.name, 250., case="W")
            for node in model.nodes.values():
                if node.X in (0., 10.) or node.Y in (0., 20.):
                    model.def_support(node.name, True, True, True, True, True, True)
            model.add_load_combo("1.0W", {"W": 1.})
            model.analyze(check_statics=False)
        self.assertEqual(len(result["cells"]), 200)
        self.assertEqual(len(result["names"]), 231)
        expected = [model.nodes[name].DZ["1.0W"]*12 for name in result["names"]]
        np.testing.assert_allclose(result["displacement"], expected, rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(result["reactions"], [model.nodes[n].RxnFZ["1.0W"]*.001 for n in result["names"]], atol=1e-10)
        np.testing.assert_allclose(result["moments"], [q.moment(0, 0, combo_name="1.0W").ravel()*.001 for q in model.quads.values()], atol=1e-9)
        self.assertAlmostEqual(result["applied"], 50.)
        self.assertAlmostEqual(result["reactions"].sum(), -50., places=8)
        self.assertAlmostEqual(result["displacement"].max(), .00191954863696, places=12)
        rigidity = definition.material.E*definition.thickness**3/(12*(1-definition.material.nu**2))
        thin = .00254*definition.pressure*definition.width**4/rigidity
        self.assertAlmostEqual(thin, .0017105384, places=10)
        self.assertGreater(result["displacement"].max(), thin)  # Transverse shear retained.

    def test_all_unit_persistence_and_fresh_definitions(self):
        for key in ("official_plate_quad", "official_mat_foundation"):
            for units in UNIT_SYSTEMS:
                d = example_definition(key, unit_system=units)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory)/"official.pyniteplate"
                    import json
                    path.write_text(json.dumps(d.to_dict()))
                    self.assertEqual(PlateDefinition.open(path).to_dict(), d.to_dict())
                d.edges["Left"] = "Simply supported"
                self.assertNotEqual(example_definition(key, unit_system=units).edges["Left"], "Simply supported")
        with self.assertRaises(ValueError):
            example_definition("unknown")

    def test_official_mat_foundation_upstream_parity_soil_pressure_and_equilibrium(self):
        definition = example_definition("official_mat_foundation")
        with contextlib.redirect_stdout(io.StringIO()):
            result = select_plate_combination(analyze_plate(definition), "D")
            model = FEModel3D()
            E = 0.35*57.*(4000.)**0.5*144.
            model.add_material("Concrete", E, .4*E, .17, .150)
            ks = 100./1000.*12**3
            model.add_mat_foundation("MAT1", mesh_size=1., length_X=50., length_Z=25., thickness=1.,
                                     material_name="Concrete", ks=ks, origin=[0, 0, 0])
            model.mats["MAT1"].add_mat_pt_load((10., 10.), "FY", -10., "D")
            model.mats["MAT1"].add_mat_pt_load((10., 10.), "MZ", 15., "D")
            model.mats["MAT1"].add_rect_opening("OPNG1", 5., 5., 10., 15.)
            model.mats["MAT1"].generate()
            model.mats["MAT1"].needs_update = False
            for q in model.quads.values():
                ke = q.Ke()
                q.Ke = lambda ke=ke: ke
            model.add_load_combo("D", {"D": 1.})
            model.analyze(log=False, check_statics=False, num_steps=1)
        self.assertEqual(len(result["cells"]), 1200)
        self.assertEqual(len(result["names"]), 1290)
        upstream_nodes = list(model.nodes.values())
        np.testing.assert_allclose(result["points"], [(n.X*12., n.Z*12.) for n in upstream_nodes], atol=1e-10)
        expected_disp = [-n.DY["D"]*12. for n in upstream_nodes]
        expected_rxn = [-n.RxnFY["D"] for n in upstream_nodes]
        expected_moments = [q.moment(0, 0, combo_name="D").ravel() for q in model.quads.values()]
        np.testing.assert_allclose(result["displacement"], expected_disp, rtol=1e-9, atol=1e-11)
        np.testing.assert_allclose(result["reactions"], expected_rxn, atol=1e-10)
        np.testing.assert_allclose(result["moments"], expected_moments, atol=1e-9)
        self.assertAlmostEqual(result["applied"], 10., places=9)
        self.assertAlmostEqual(result["reactions"].sum(), -10., places=8)
        rows = {row["component"]: row for row in result["equilibrium"]}
        self.assertAlmostEqual(rows["FY"]["applied"], -10., places=9)
        self.assertAlmostEqual(rows["MX"]["applied"], 1200., places=7)
        self.assertAlmostEqual(rows["MZ"]["applied"], -1020., places=7)
        self.assertLess(result["active_soil_springs"], result["total_soil_springs"])
        self.assertGreater(len(result["uplift_nodes"]), 0)
        for idx in (0, 15, 210, 500, 1199):
            ename = result["element_names"][idx]
            for xi, eta in ((0., 0.), (.4, -.3)):
                probe = inspect_plate(result, ename, xi, eta)
                x_ft, z_ft = probe["position"][0]/12., probe["position"][1]/12.
                upstream_p = model.mats["MAT1"].soil_pressure(x_ft, z_ft, "D")/144.
                self.assertAlmostEqual(probe["soil_bearing_pressure"], upstream_p, places=11)


class OfficialPlateUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_menu_and_browser_open_separate_workspace_and_preserve_editor(self):
        from pynitegui.qt.app import MainWindow
        from pynitegui.qt.example_browser import ExampleBrowser
        from pynitegui.qt.plate_workspace import PlateWorkspace
        window = MainWindow()
        window.project.unit_system = "si"
        browser = ExampleBrowser(window)
        before = window.project.to_dict(), window.revision, window.saved, window.undo.count()
        captured = []
        def execute(dialog):
            captured.append(dialog.definition.to_dict())
            self.assertIsNone(dialog.result)
            self.assertEqual(dialog.fields["width"].value(), 3.048)
            return QDialog.DialogCode.Rejected
        try:
            browser.search.setText("official clamped")
            self.assertEqual(browser.selected_key, "official_plate_quad")
            self.assertIn("Separate plate workspace", browser.details.toPlainText())
            self.assertFalse(browser.preview.grab().isNull())
            menu = next(a.menu() for a in window.examples_menu.actions() if a.text() == PLATE_CATEGORY)
            with patch.object(PlateWorkspace, "exec", execute), patch.object(window, "confirm_discard") as discard:
                menu.actions()[0].trigger()
                def accept_plate(dialog):
                    dialog.search.setText("official clamped")
                    dialog.accept()
                    return QDialog.DialogCode.Accepted
                with patch.object(ExampleBrowser, "exec", accept_plate):
                    window.browse_examples()
                discard.assert_not_called()
            self.assertEqual(len(captured), 2)
            self.assertEqual(captured[0], example_definition(unit_system="si").to_dict())
            self.assertEqual(before, (window.project.to_dict(), window.revision, window.saved, window.undo.count()))
            window.mcp_mode = True
            with patch.object(PlateWorkspace, "exec") as execute_mock:
                window.example("official_plate_quad")
                execute_mock.assert_not_called()
            window.mcp_mode = False
        finally:
            browser.reject()
            browser.deleteLater()
            window.saved = window.project.to_dict()
            window.close()
            window.deleteLater()
            self.app.processEvents()
