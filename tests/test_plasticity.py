"""Explicit steel yield/profile data, units, binding and strict migration."""
import unittest
from pynitegui.qt.model import Project,Material,Section
from pynitegui.qt.spatial_conversion import to_spatial
from pynitegui.qt.automation_core import batch_candidate
from pynitegui.qt.automation_schema import model_reference
from pynitegui.qt.units import UNIT_SYSTEMS


def steel_beam():
    p=Project();p.add_member((0.,0.),(120.,0.));p.nodes['N1'].support='fixed'
    p.materials[p.default_material].fy=50.
    section=p.sections[p.default_section]
    section.Zy,section.Zz,section.steel_material=10.,20.,p.default_material
    return p


class SteelDefinitionTests(unittest.TestCase):
    def test_roundtrip_new_formats_and_legacy_elastic_defaults(self):
        for p,current,legacy in ((steel_beam(),33,31),(to_spatial(steel_beam()),40,38)):
            data=p.to_dict();self.assertEqual(data['version'],current)
            self.assertEqual(Project.from_dict(data).to_dict(),data)
            for collection,key in (('materials','fy'),('sections','Zy'),('sections','Zz'),('sections','steel_material')):
                bad=p.to_dict();bad[collection][next(iter(bad[collection]))].pop(key)
                with self.assertRaisesRegex(ValueError,'Missing steel plastic'):Project.from_dict(bad)
            data['version']=legacy
            with self.assertRaisesRegex(ValueError,'require version'):Project.from_dict(data)
            for material in data['materials'].values():material.pop('fy')
            for section in data['sections'].values():
                for key in ('Zy','Zz','steel_material'):section.pop(key)
            restored=Project.from_dict(data)
            self.assertIsNone(restored.materials[restored.default_material].fy)
            self.assertIsNone(restored.sections[restored.default_section].steel_material)

    def test_positive_finite_values_material_binding_rename_and_delete(self):
        p=steel_beam()
        for value in (True,0.,-1.,float('inf'),float('nan'),'50'):
            p.materials[p.default_material].fy=value
            with self.assertRaises(ValueError):p.validate()
        p.materials[p.default_material].fy=50.
        for field in ('Zy','Zz'):
            old=getattr(p.sections[p.default_section],field)
            for value in (None,True,0.,-1.,float('nan')):
                setattr(p.sections[p.default_section],field,value)
                with self.assertRaises(ValueError):p.validate()
            setattr(p.sections[p.default_section],field,old)
        old=p.default_material
        p.set_material(Material('Renamed',fy=50.),previous=old)
        self.assertEqual(p.sections[p.default_section].steel_material,'Renamed');p.validate()
        with self.assertRaisesRegex(ValueError,'bound to plastic'):p.delete_material('Renamed')
        p.materials['Other']=Material('Other',fy=50.);p.members['M1'].material='Other'
        with self.assertRaisesRegex(ValueError,'must match'):p.validate()

    def test_atomic_typed_mcp_input_schema_and_cubic_section_units(self):
        p=Project();p.add_member((0.,0.),(120.,0.))
        q=batch_candidate(p,[{'op':'put','collection':'materials','key':p.default_material,'value':{'fy':50.}},
            {'op':'put','collection':'sections','key':p.default_section,'value':{'Zy':10.,'Zz':20.,'steel_material':p.default_material}}])
        self.assertIsNone(p.materials[p.default_material].fy);self.assertEqual(q.materials[q.default_material].fy,50.)
        schema=model_reference()
        self.assertEqual(schema['entities']['materials']['properties']['fy']['type'],['number','null'])
        self.assertEqual(schema['entities']['sections']['properties']['Zz']['type'],['number','null'])
        for key in ('imperial','imperial_ft','si','si_mm','custom_cm_kN'):
            unit=UNIT_SYSTEMS[key]
            self.assertAlmostEqual(unit.from_display(unit.to_display(20.,'section_modulus'),'section_modulus'),20.)
        self.assertEqual(UNIT_SYSTEMS['si'].section_modulus,'mm3')
        self.assertAlmostEqual(UNIT_SYSTEMS['si'].to_display(1.,'section_modulus'),25.4**3)
