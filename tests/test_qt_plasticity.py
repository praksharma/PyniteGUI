"""Staged steel profile inputs, exact unit roundtrips and provenance."""
from dataclasses import asdict
import unittest
from PySide6.QtWidgets import QApplication
from pynitegui.qt.app import MainWindow
from pynitegui.qt.materials import MaterialEditor
from pynitegui.qt.sections import SectionEditor
from pynitegui.qt.section_library import BY_DESIGNATION,SOURCE
from pynitegui.qt.material_library import PRESETS
from pynitegui.qt.model import Material,Section
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.mesh_model import MeshDefinition
from pynitegui.qt.plate_model import PlateDefinition
from pynitegui.qt.reports import model_definition_tables
from test_pushover import propped_beam


class SteelProfileEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_exact_noop_units_staging_undo_and_profile_disabling(self):
        w=MainWindow()
        try:
            for spatial in (False,True):
                for unit in ('imperial','imperial_ft','si','si_mm','custom_cm_kN'):
                    p=propped_beam()
                    if spatial:p=to_spatial(p)
                    p.unit_system=unit;w.load_project(p);before=w.project.to_dict()
                    editor=MaterialEditor(w,w.project,w.project.materials['Steel'],'Steel')
                    editor.accept();self.assertEqual(asdict(editor.definition),asdict(w.project.materials['Steel']))
                    editor.deleteLater()
                    editor=SectionEditor(w,w.project,w.project.sections['I'],'I')
                    editor.accept();self.assertEqual(asdict(editor.definition),asdict(w.project.sections['I']))
                    editor.plastic_fields['Zz'].setValue(p.units.to_display(25.,'section_modulus'));editor.accept()
                    self.assertEqual(w.project.to_dict(),before)
                    w.edit('Change plastic modulus',lambda p:p.set_section(editor.definition,'I'))
                    self.assertAlmostEqual(w.project.sections['I'].Zz,25.,places=8)
                    w.undo.undo();self.assertEqual(w.project.to_dict(),before)
                    editor.plastic_enabled.setChecked(False);editor.accept()
                    self.assertIsNone(editor.definition.Zz);self.assertIsNone(editor.definition.steel_material)
                    editor.deleteLater()
                    self.assertIn('Steel fy',str(model_definition_tables(w.project)))
        finally:
            w.saved=w.project.to_dict();w.close();w.deleteLater();self.app.processEvents()

    def test_supplied_yield_data_clears_elastic_library_provenance(self):
        p=propped_beam();item=PRESETS[0];material=Material('Library',**item.properties(),preset=item.key)
        editor=MaterialEditor(None,p,material,'Library')
        editor.yield_enabled.setChecked(True);editor.fy.setValue(p.units.to_display(50.,'stress'));editor.accept()
        self.assertIsNone(editor.definition.preset);self.assertEqual(material.preset,item.key);editor.deleteLater()
        section=Section('Catalog',**BY_DESIGNATION['W18X35'].properties(),catalog=SOURCE,designation='W18X35')
        editor=SectionEditor(None,p,section,'Catalog');editor.plastic_enabled.setChecked(True)
        editor.plastic_material.setCurrentIndex(editor.plastic_material.findData('Steel'))
        for key,value in (('Zy',10.),('Zz',20.)):editor.plastic_fields[key].setValue(value)
        editor.accept();self.assertIsNone(editor.definition.catalog);self.assertEqual(editor.definition.steel_material,'Steel');editor.deleteLater()

    def test_surface_files_stay_elastic_and_omit_frame_yield_metadata(self):
        for definition in (MeshDefinition(),PlateDefinition()):
            self.assertNotIn('fy',definition.to_dict()['material'])
            definition.material.preset=None;definition.material.fy=50.
            with self.assertRaisesRegex(ValueError,'elastic'):definition.validate()
