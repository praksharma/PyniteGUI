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
from pynitegui.qt.plate_model import PlateDefinition, analyze_plate
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
        for units in UNIT_SYSTEMS:
            d = example_definition(unit_system=units)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"official.pyniteplate"
                import json
                path.write_text(json.dumps(d.to_dict()))
                self.assertEqual(PlateDefinition.open(path).to_dict(), d.to_dict())
            d.edges["Left"] = "Free"
            self.assertEqual(example_definition(unit_system=units).edges["Left"], "Clamped")
        with self.assertRaises(ValueError):
            example_definition("unknown")


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
