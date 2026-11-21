"""Pinned official Quad plate: upstream parity, reference checks and native entry."""
import contextlib
import io
import math
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
        for key in ("official_plate_quad", "official_mat_foundation",
                    "official_shear_wall_basic", "official_shear_wall_advanced"):
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

    def test_official_shear_walls_basic_and_advanced_upstream_parity(self):
        # 1. Official Shear Wall - Basic.py (pinned upstream recipe)
        basic_def = example_definition("official_shear_wall_basic")
        with contextlib.redirect_stdout(io.StringIO()):
            basic = select_plate_combination(analyze_plate(basic_def), "Seismic")
            m_basic = FEModel3D()
            E_m = 900.*2000./1000.
            m_basic.add_material("Masonry", E_m, .4*E_m, .17, .0000710)
            m_basic.add_rectangle_mesh("SW1", 6., 26.*12., 16.*12., 8., "Masonry", 1., 1., [0, 0, 0], "XY", element_type="Quad")
            m_basic.meshes["SW1"].add_rect_opening("Door 1", 2.*12., 0.*12., 4.*12., 12.*12.)
            m_basic.meshes["SW1"].add_rect_opening("Window 1", 8.*12., 8.*12., 4.*12., 4.*12.)
            m_basic.meshes["SW1"].add_rect_opening("Window 2", 14.*12., 8.*12., 4.*12., 4.*12.)
            m_basic.meshes["SW1"].add_rect_opening("Door 2", 20.*12., 0.*12., 4.*12., 12.*12.)
            m_basic.meshes["SW1"].generate()
            m_basic.meshes["SW1"].needs_update = False
            for q in m_basic.quads.values():
                k_loc = q.ke()
                q.ke = lambda k_loc=k_loc: k_loc
                ke_glob = q.Ke()
                q.Ke = lambda ke_glob=ke_glob: ke_glob
            for node in m_basic.nodes.values():
                if math.isclose(node.Y, 16.*12.):
                    m_basic.add_node_load(node.name, "FX", 100./53., case="E")
                if math.isclose(node.Y, 0.):
                    m_basic.def_support(node.name, True, True, True, False, False, False)
            m_basic.add_load_combo("Seismic", {"E": 1.})
            m_basic.analyze_linear(log=False, check_statics=False)
        self.assertEqual(len(basic["cells"]), 1152)
        self.assertEqual(len(basic["names"]), 1315)
        up_basic_nodes = list(m_basic.nodes.values())
        np.testing.assert_allclose(basic["points"], [(n.X, n.Y) for n in up_basic_nodes], atol=1e-10)
        np.testing.assert_allclose(basic["displacement_u"], [n.DX["Seismic"] for n in up_basic_nodes], rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(basic["displacement_v"], [n.DY["Seismic"] for n in up_basic_nodes], rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(basic["reactions_u"], [n.RxnFX["Seismic"] for n in up_basic_nodes], atol=1e-10)
        np.testing.assert_allclose(basic["reactions_v"], [n.RxnFY["Seismic"] for n in up_basic_nodes], atol=1e-10)
        up_basic_membrane = np.array([q.membrane(0, 0, combo_name="Seismic").ravel() for q in m_basic.quads.values()])
        np.testing.assert_allclose(basic["membrane_stresses"], up_basic_membrane, rtol=1e-9, atol=1e-10)
        self.assertAlmostEqual(basic["displacement_u"].max(), 0.08606040631292898, places=11)
        self.assertAlmostEqual(basic["wall_rigidity"], 1161.9745279424374, places=8)
        self.assertAlmostEqual(basic["reactions_u"].sum(), -100., places=8)

        # 2. Official Shear Wall - Advanced.py (pinned upstream Pynite.ShearWall recipe)
        adv_def = example_definition("official_shear_wall_advanced")
        with contextlib.redirect_stdout(io.StringIO()):
            adv = select_plate_combination(analyze_plate(adv_def), "1.2D+1.0E")
            m_adv = FEModel3D()
            E_c = 57000.*(4500.)**0.5*12**2/1000.
            m_adv.add_material("Concrete", E_c, .4*E_c, .17, .150)
            m_adv.add_load_combo("1.2D+1.0E", {"D": 1.2, "E": 1.})
            m_adv.add_shear_wall("Wall 1", 1, 50, 25, 1, "Concrete", ky_mod=.35)
            m_adv.shear_walls["Wall 1"].add_opening("Opng 1", 5, 0, 40, 20)
            m_adv.shear_walls["Wall 1"].add_support()
            m_adv.shear_walls["Wall 1"].add_story("Roof", 25, 0, 50)
            m_adv.shear_walls["Wall 1"].add_shear("Roof", 150, "E")
            m_adv.shear_walls["Wall 1"].generate()
            m_adv.shear_walls["Wall 1"].needs_update = False
            for q in m_adv.quads.values():
                k_loc = q.ke()
                q.ke = lambda k_loc=k_loc: k_loc
                ke_glob = q.Ke()
                q.Ke = lambda ke_glob=ke_glob: ke_glob
            m_adv.analyze_linear(log=False, check_statics=False)
        self.assertEqual(len(adv["cells"]), 450)
        self.assertEqual(len(adv["names"]), 546)
        up_adv_nodes = list(m_adv.nodes.values())
        np.testing.assert_allclose(adv["points"], [(n.X*12., n.Y*12.) for n in up_adv_nodes], atol=1e-10)
        np.testing.assert_allclose(adv["displacement_u"], [n.DX["1.2D+1.0E"]*12. for n in up_adv_nodes], rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(adv["displacement_v"], [n.DY["1.2D+1.0E"]*12. for n in up_adv_nodes], rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(adv["reactions_u"], [n.RxnFX["1.2D+1.0E"] for n in up_adv_nodes], atol=1e-10)
        np.testing.assert_allclose(adv["reactions_v"], [n.RxnFY["1.2D+1.0E"] for n in up_adv_nodes], atol=1e-10)
        up_adv_membrane = np.array([q.membrane(0, 0, combo_name="1.2D+1.0E").ravel()/144. for q in m_adv.quads.values()])
        np.testing.assert_allclose(adv["membrane_stresses"], up_adv_membrane, rtol=1e-9, atol=1e-10)
        up_sw = m_adv.shear_walls["Wall 1"]
        np.testing.assert_allclose(adv["story_stiffnesses"]["Roof"]*12., up_sw.stiffness("Roof"), rtol=1e-9)
        self.assertEqual([p["name"] for p in adv["piers"]], list(up_sw.piers.keys()))
        for pier in adv["piers"]:
            up_pier = up_sw.piers[pier["name"]]
            up_p, up_m, up_v, up_m_vl = up_pier.sum_forces("1.2D+1.0E")
            self.assertAlmostEqual(pier["width"]/12., up_pier.width, places=9)
            self.assertAlmostEqual(pier["height"]/12., up_pier.height, places=9)
            self.assertAlmostEqual(pier["V"], up_v, places=8)
            self.assertAlmostEqual(pier["M"]/12., up_m, places=7)
            self.assertAlmostEqual(pier["P"], up_p, places=8)
            self.assertAlmostEqual(pier["M_VL"], up_m_vl, places=8)
        self.assertEqual([b["name"] for b in adv["coupling_beams"]], list(up_sw.coupling_beams.keys()))
        for beam in adv["coupling_beams"]:
            up_beam = up_sw.coupling_beams[beam["name"]]
            up_p, up_m, up_v, up_m_vh = up_beam.sum_forces("1.2D+1.0E")
            self.assertAlmostEqual(beam["length"]/12., up_beam.length, places=9)
            self.assertAlmostEqual(beam["height"]/12., up_beam.height, places=9)
            self.assertAlmostEqual(beam["V"], up_v, places=8)
            self.assertAlmostEqual(beam["M"]/12., up_m, places=7)
            self.assertAlmostEqual(beam["P"], up_p, places=8)
            self.assertAlmostEqual(beam["M_VH"], up_m_vh, places=8)
        up_adv_quads = list(m_adv.quads.values())
        for idx in (0, 25, 180, 449):
            ename = adv["element_names"][idx]
            for xi, eta in ((0., 0.), (.35, -.45)):
                probe = inspect_plate(adv, ename, xi, eta)
                up_mem = up_adv_quads[idx].membrane(xi, eta, combo_name="1.2D+1.0E").ravel()/144.
                np.testing.assert_allclose([probe["Sx"], probe["Sy"], probe["Txy"]], up_mem, rtol=1e-9, atol=1e-11)

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
