"""Editable first-order steel checks with independent hand references."""
from .model import Project,Material,Section,Load
from .pushover import PushoverSettings

NAMES={
    'steel_redistribution':'Steel Beam - Plastic Redistribution',
    'steel_mechanism':'Steel Beam - Mechanism Limit',
    '3d_steel_weak_axis':'3D Steel Beam - Weak-Axis Plasticity',
}
NOTES={
    'steel_redistribution':('20 ft propped beam with a central 24 kip joint load, explicit steel fy = 50 ksi and plastic modulus Zz = 20 in³. The fixed-end hinge redistributes bending to the span.',
        'Opens Steel Pushover with 500 increments. Hand reference: first yield 22.2222 kip; collapse 25 kip; displacement at 24 kip = −1.142069 in. Refine increments to compare. F5 remains a separate elastic analysis.'),
    'steel_mechanism':('Same propped beam with a 26 kip requested pattern, exceeding the 25 kip ideal plastic mechanism load. Explicit member ends include the potential central hinge.',
        'Opens Steel Pushover with 1000 increments. Expect Partial / limit_state near 25 kip; no post-mechanism path is supplied. Repeat with finer steps to assess yield overshoot.'),
    '3d_steel_weak_axis':('Spatial version of the propped beam, with planar constraints and members rolled 90°. The 12 kip joint push bends about local y; fy Zy = 500 kip-in.',
        'Opens Steel Pushover with 500 increments. First yield 11.1111 kip; collapse 12.5 kip. Expected control displacement at 12 kip ≈ −1.903448 in; inspect local My and global reaction balance.'),
}


def example_project(key,unit_system='imperial'):
    if key not in NAMES:raise ValueError('Unknown steel example.')
    p=Project(unit_system=unit_system,
        materials={'Steel':Material('Steel',29000.,.3,0.,shear_modulus=11200.,fy=50.)},default_material='Steel',
        sections={'Steel I':Section('Steel I',10.,30.,100.,1.,Zy=10.,Zz=20.,steel_material='Steel')},default_section='Steel I',
        load_cases=['D','Push'],default_load_case='D',combinations={'Primary':{'D':0.},'Push':{'Push':1.}})
    p.add_member((0.,0.),(120.,0.));p.add_member((120.,0.),(240.,0.))
    p.nodes['N1'].support='fixed';p.nodes['N3'].support='pin'
    p.loads['Push']=Load('Push','N2','FY',-26. if key=='steel_mechanism' else -24.,case='Push')
    if key=='3d_steel_weak_axis':
        from .spatial_conversion import to_spatial
        p=to_spatial(p)
        for member in p.members.values():member.roll=90.
        p.loads['Push'].magnitude=-12.
    p.validate();return p


def example_settings(key):
    return PushoverSettings('Primary','Push','N2','DY',3.,('N1','N3'),'FY',1000 if key=='steel_mechanism' else 500)
