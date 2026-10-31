"""Pinned official modal column, converted from ft/kip to canonical in/kip."""
from .model import Project,Material,Section,Load

KEY='official_modal'
NAME='Official PyNite - Three-Storey Modal Column'
NOTES=('30 ft column with W12x26, three 2 kip nodal weights and generated steel self-weight in Mass = D + D-SW. Preserves the pinned source E/G, density, supports and 32.2 ft/s² gravity.',
       'Opens Vibration Modes with three modes and gravity 386.4 in/s². Compare natural frequencies and normalized shapes; these are free-vibration modes, not earthquake response or static force results.')


def example_project(unit_system='imperial'):
    p=Project(unit_system=unit_system,
        materials={'Steel':Material('Steel',29000.,.3,.490/12**3,shear_modulus=11200.)},default_material='Steel',
        sections={'W12x26':Section('W12x26',7.625,17.3,204.,.3)},default_section='W12x26',
        load_cases=['D','D-SW'],default_load_case='D',combinations={'Mass':{'D':1.,'D-SW':1.}},self_weight_case='D-SW')
    for index in range(3):p.add_member((0.,120*index),(0.,120*(index+1)))
    p.nodes['N1'].support='fixed'
    for name in ('N2','N3','N4'):p.loads['Weight '+name]=Load('Weight '+name,name,'FY',-2.,case='D')
    p.validate();return p
