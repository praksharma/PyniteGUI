"""Pinned PyNite unilateral examples adapted to the native planar editor.

Source revision and MIT notice match official_examples.SOURCE_COMMIT and the
bundled pynite-examples notice. Fixed vertical spring anchors can be condensed
exactly into global ground springs; this is not a general node-to-node API.
"""
from .model import Project, Material, Section, Node, Member, Load

SOURCES = {
    'official_foundation': 'Beam on Elastic Foundation.py',
    'official_tension_braced': 'Braced Frame - Tension Only.py',
    'official_ground_braced': 'Braced Frame - Spring Supported.py',
}
NAMES = {
    'official_foundation': 'Official PyNite - Beam on Compression-Only Foundation',
    'official_tension_braced': 'Official PyNite - Tension-Only Braced Frame',
    'official_ground_braced': 'Official PyNite - Braced Frame with One-Way Ground Springs',
}
NOTES = {
    'official_foundation': ('300 in beam, 24 negative-DY-only 22.5 kip/in soil springs, pinned ends and a -40 kip point load at x=150 in. Explicit 12 in members replace the source physical beam.',
        'Iterative elastic; soil springs release on uplift. Reactions sum to +40 kip. Inspect Active state for contact and compare mesh/result fields.'),
    'official_tension_braced': ('15 ft × 12 ft pinned-base frame with two tension-only axial braces. Preserves the pinned source geometry, sections, E/G and D/W member/nodal loads.',
        'Wind activates Brace1 and releases Brace2; reverse wind exchanges them. Gravity-only is an unstable active configuration and is intentionally not in the default combinations.'),
    'official_ground_braced': ('Pinned braced frame on +DY-only and -DY-only 10,000 kip/in ground springs. The source fixed vertical anchor nodes/spring elements are exactly condensed into ground springs.',
        'N1 moves up and N4 moves down for 1.2D+1.0W. Gravity-only is unstable. General node-to-node springs remain a separate capability.'),
}


def example_project(key, unit_system='imperial'):
    if key not in SOURCES:
        raise ValueError('Unknown unilateral official example.')
    if key == 'official_foundation':
        p = Project(unit_system=unit_system, analysis_method='iterative',
            materials={'Steel':Material('Steel', E=29000., nu=.3, rho=.490/12**3, shear_modulus=11200.)}, default_material='Steel',
            sections={'W8x35':Section('W8x35',A=10.3,Iy=42.6,Iz=127.,J=.769)}, default_section='W8x35',
            combinations={'Combo 1':{'Case 1':1.}})
        for index in range(25):
            p.add_member((index*12.,0.),((index+1)*12.,0.))
        p.nodes['N1'].support = p.nodes['N26'].support = 'pin'
        for node in list(p.nodes.values())[1:-1]:
            node.spring_y, node.spring_y_mode = 22.5, 'negative'
        p.loads['P'] = Load('P','M13','FY',-40.,.5)
    else:
        from .official_examples import moment_frame
        p = moment_frame(unit_system)
        p.analysis_method = 'iterative'
        p.materials['Steel'].shear_modulus = 11400. if key == 'official_tension_braced' else 11200.
        p.materials['Steel'].rho = .490/12**2  # Preserve the executable source.
        p.sections['L4x4x1/4'] = Section('L4x4x1/4',1.94,3.,3.,.0438)
        p.members['Beam'].release_start = p.members['Beam'].release_end = True
        for name in ('N1','N4'):
            p.nodes[name].support = 'pin'
        p.members['Brace1'] = Member('Brace1','N1','N3','Steel','L4x4x1/4',kind='truss',
                                    behavior='tension_only' if key == 'official_tension_braced' else 'bilateral')
        if key == 'official_tension_braced':
            p.members['Brace2'] = Member('Brace2','N4','N2','Steel','L4x4x1/4',kind='truss',behavior='tension_only')
        else:
            for name, mode in (('N1','positive'),('N4','negative')):
                node = p.nodes[name]
                node.support, node.restraint_x = 'custom', True
                node.spring_y, node.spring_y_mode = 10000., mode
        p.loads['L4'] = Load('L4','N2','FX',25.,case='W')
        p.loads['L5'] = Load('L5','N3','FX',25.,case='W')
    p.validate()
    return p
