"""Official adaptations and custom benchmarks in the separate plate workspace.

Source: PyNite Examples/Rectangular Plate Bending - Qauds.py at the revision
in official_examples.SOURCE_COMMIT. MIT notice: licenses/pynite-examples.txt.
"""
from .model import Material
from .plate_model import PlateDefinition


PLATE_EXAMPLES = {"official_plate_quad": "Official PyNite - Clamped Rectangular Quad Plate",
                  "official_wall_hydrostatic": "Official PyNite - Hydrostatic Tank Wall",
                  "thin_plate_recovered_shear": "Thin Plate - Recovered Centre Shear",
                  "opening_plate_recovered_shear": "Thin Plate Opening - Masked Recovered Shear"}
PLATE_CATEGORY = "Plates (Experimental)"
PLATE_NOTES = {
    'thin_plate_recovered_shear': ('Custom thin simply supported Quad plate, 120 by 180 in, t=0.6 in and mesh 7.5 in. Signed and zero pressure combinations. Recovered Q is a smoothed centre fit.',
        'Choose Recovered Qx/Qy after analysis. Raw Quad shear stays unavailable. Compare refinement; centre tables/CSV show eligibility and fit provenance.'),
    'opening_plate_recovered_shear': ('Custom 120 in square thin plate with a centred 40 in free opening, nu=0.2, t=0.6 in and 5 in mesh. Pressure -1e-7 kip/in2.',
        'Recovered centre shear is masked near reentrant corners and when a stencil includes a corner. Blank values are unavailable. Refine to 4 in and compare; no corner-peak/design claim.'),
    "official_wall_hydrostatic": (
        "Official PyNite adaptation: 25 × 15 ft tank wall, 1 ft thick, with 15 ft of water. Quad mesh 1 ft, left/right/bottom clamped, top free. Linear transverse pressure follows height.",
        "375 Quads; 1.4F normal load +245.7 kip and reaction sum −245.7 kip. Compare mesh refinements. Quad shear remains unverified and disabled; this is transverse plate bending, not an in-plane shear wall."),
    "official_plate_quad": (
        "Official PyNite adaptation: 10 × 20 ft clamped concrete plate, 1 ft thick, under +250 psf normal pressure. Opens the separate plate workspace.",
        "200 Quads; applied +50 kip; normal reactions total -50 kip. Classical thin-plate centre displacement +0.00171054 in (DKMQ +0.00191955 in); DKMQ includes transverse shear.")}


def example_definition(key="official_plate_quad", unit_system="imperial"):
    if key not in PLATE_EXAMPLES:
        raise ValueError(f"Unknown official plate example: {key}")
    if key in ('thin_plate_recovered_shear','opening_plate_recovered_shear'):
        opening=key=='opening_plate_recovered_shear'
        definition=PlateDefinition(width=120.,height=120. if opening else 180.,thickness=.6,mesh_size=5. if opening else 7.5,
            pressure=-1e-7,unit_system=unit_system,combinations={'Reverse':{'Case 1':-2.},'Zero':{'Case 1':0.}},
            openings=[dict(name='Opening',x_left=40.,y_bott=40.,width=40.,height=40.)] if opening else [])
        definition.validate();return definition
    if key=='official_wall_hydrostatic':
        definition=PlateDefinition(width=300.,height=180.,thickness=12.,mesh_size=12.,
            material=Material('Concrete',E=57000.*4500.**.5/1000.,nu=1/6,rho=150./1000./12**3),
            pressure=15*62.4/1000/144,load_case='F',load_factor=1.4,
            pressure_profiles={'F':{'axis':'y','end_pressure':0.}},combinations={'1.4F':{'F':1.4}},
            edges={'Left':'Clamped','Right':'Clamped','Bottom':'Clamped','Top':'Free'},unit_system=unit_system,mesh_name='MSH1')
        definition.validate();return definition
    definition = PlateDefinition(width=120., height=240., thickness=12., mesh_size=12.,
        material=Material("Concrete", E=57000.*4000.**.5/1000., nu=.17, rho=150./1000./12**3),
        pressure=250./1000./12**2, load_case="W", load_factor=1.,
        edges=dict.fromkeys(("Left", "Right", "Bottom", "Top"), "Clamped"),
        unit_system=unit_system, mesh_name="MSH1")
    definition.validate()
    return definition


def preview_project(definition):
    """Geometry only; plate inputs remain owned by PlateDefinition."""
    from .spatial_model import SpatialProject
    project = SpatialProject(unit_system=definition.unit_system)
    project.surfaces = {definition.mesh_name: definition.mesh_definition()}
    return project


def loading_summary(definition):
    u = definition.units
    pressures=[]
    for case,start in definition.case_pressures.items():
        profile=definition.pressure_profiles.get(case)
        text=f"{case}: {u.to_display(start,'pressure'):+.6g}"
        if profile:text+=f" → {u.to_display(profile['end_pressure'],'pressure'):+.6g} along local {profile['axis']}"
        pressures.append(text+' '+u.pressure)
    combinations='; '.join(name+' = '+' + '.join(f'{factor:g}{case}' for case,factor in factors.items())
                           for name,factors in definition.load_combinations.items())
    return (f"Separate plate workspace · {u.summary}\n"
            f"Size: {u.to_display(definition.width, 'length'):.6g} × {u.to_display(definition.height, 'length'):.6g} {u.length}\n"
            f"Thickness: {u.to_display(definition.thickness, 'length'):.6g} {u.length}\n"
            f"Mesh: {u.to_display(definition.mesh_size, 'length'):.6g} {u.length} · {definition.element_type}\n"
            +'; '.join(edge+': '+support for edge,support in definition.edges.items())+'\n'
            +'\n'.join(pressures)+'\nCombinations: '+combinations+'\n'
            +'Centroid pressure per element; compare refinements. Linear elastic transverse bending; self-weight off.\n'
            +'The main frame model and unsaved inputs remain unchanged.')
