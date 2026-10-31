"""Explicit steel I-section yield data, separate from an elastic material preset."""
from .model import finite_number,identifier

MATERIAL_DEFAULTS={'fy':None}
SECTION_DEFAULTS={'Zy':None,'Zz':None,'steel_material':None}


def check_schema(values,version,required,defaults,label):
    if version>=required and not defaults.keys()<=values.keys():
        raise ValueError(f'Missing steel plastic {label} fields for version {required}.')
    if version<required and any(values.get(key,default)!=default for key,default in defaults.items()):
        raise ValueError(f'Steel plastic {label} fields require version {required}.')


def validate_material(material):
    if material.fy is not None and (not finite_number(material.fy) or material.fy<=0):
        raise ValueError(f'Material {material.name}: steel fy must be a positive finite stress or null for elastic-only properties.')


def validate_section(section):
    enabled=any(getattr(section,key) is not None for key in SECTION_DEFAULTS)
    if not enabled:return
    if not identifier(section.steel_material):
        raise ValueError(f'Section {section.name}: the steel I-section plastic model requires an explicit material binding.')
    for key in ('Zy','Zz'):
        value=getattr(section,key)
        if not finite_number(value) or value<=0:
            raise ValueError(f'Section {section.name}: {key} must be a positive finite plastic modulus in canonical in³.')
    if section.catalog is not None:
        raise ValueError(f'Section {section.name}: save supplied plastic properties as a custom I-section; the elastic catalog does not certify Zy/Zz.')


def validate_bindings(project):
    for section in project.sections.values():
        if section.steel_material is None:continue
        material=project.materials.get(section.steel_material)
        if material is None or material.fy is None:
            raise ValueError(f'Section {section.name}: bound steel material must exist and have positive fy.')
    for member in project.members.values():
        section=project.sections.get(member.section)
        if section is not None and section.steel_material is not None and member.material!=section.steel_material:
            raise ValueError(f'Member {member.name}: material must match plastic section binding {section.steel_material}.')
