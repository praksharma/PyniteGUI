"""Official adaptations and custom benchmarks in the separate plate workspace.

Sources: PyNite Examples/Rectangular Plate Bending - Qauds.py,
Examples/Hydrostatic Loads on a Wall.py, Examples/Mat Foundation.py,
Examples/Shear Wall - Basic.py and Examples/Shear Wall - Advanced.py at the
revision in official_examples.SOURCE_COMMIT. MIT notice: licenses/pynite-examples.txt.
"""
from .model import Material
from .plate_model import PlateDefinition


PLATE_EXAMPLES = {"official_plate_quad": "Official PyNite - Clamped Rectangular Quad Plate",
                  "official_wall_hydrostatic": "Official PyNite - Hydrostatic Tank Wall",
                  "official_mat_foundation": "Official PyNite - Mat Foundation",
                  "official_shear_wall_basic": "Official PyNite - Masonry Shear Wall with Openings",
                  "official_shear_wall_advanced": "Official PyNite - Concrete Coupled Shear Wall",
                  "thin_plate_recovered_shear": "Thin Plate - Recovered Centre Shear",
                  "opening_plate_recovered_shear": "Thin Plate Opening - Masked Recovered Shear"}
PLATE_CATEGORY = "Plates (Experimental)"
PLATE_NOTES = {
    'thin_plate_recovered_shear': ('Custom thin simply supported Quad plate, 120 by 180 in, t=0.6 in and mesh 7.5 in. Signed and zero pressure combinations. Recovered Q is a smoothed centre fit.',
        'Choose Recovered Qx/Qy after analysis. Raw Quad shear stays unavailable. Compare refinement; centre tables/CSV show eligibility and fit provenance.'),
    'opening_plate_recovered_shear': ('Custom 120 in square thin plate with a centred 40 in free opening, nu=0.2, t=0.6 in and 5 in mesh. Pressure -1e-7 kip/in2.',
        'Recovered centre shear is masked near reentrant corners and when a stencil includes a corner. Blank values are unavailable. Refine to 4 in and compare; no corner-peak/design claim.'),
    "official_mat_foundation": (
        "Official PyNite adaptation: 50 × 25 ft concrete mat foundation, 1 ft thick, on compression-only Winkler soil springs (ks = 100 pci = 172.8 kcf) with a 5 × 10 ft opening and concentrated column force/moment at (10, 10) ft.",
        "1,200 Quads (1,290 nodes); applied FY = -10 kip and MZ = +15 kip-ft (+180 kip-in) at (120, 120) in; compression-only soil reactions sum to +10 kip (normal reaction sum -10 kip) with global moment equilibrium about the origin."),
    "official_shear_wall_basic": (
        "Official PyNite adaptation: 26 × 16 ft masonry shear wall, 8 in thick (E = 1,800 ksi, nu = 0.17), 6 in Quad mesh, pinned base at y = 0, two 4 × 12 ft doors and two 4 × 4 ft windows under 100 kip top lateral shear.",
        "1,152 Quads (1,315 nodes); top story lateral drift 0.0860604 in and wall rigidity 1,161.97 kip/in; base shear reaction sum -100 kip with automatic pier/coupling-beam force summation and membrane stress contours (Sx, Sy, Txy)."),
    "official_shear_wall_advanced": (
        "Official PyNite adaptation: 50 × 25 ft cracked concrete coupled shear wall, 1 ft thick (f'c = 4,500 psi, ky_mod = 0.35), 1 ft Quad mesh, 40 × 20 ft opening and 150 kip roof seismic shear (1.2D+1.0E).",
        "450 Quads (546 nodes); roof lateral stiffness 291.171 kip/in (3,494.05 kip/ft); piers P1/P3 carry V = -75 kip, M = -888.753 kip-ft, P = ±43.833 kip and coupling beam B1 carries V = -43.833 kip, M = -733.281 kip-ft, P = +57.353 kip."),
    "official_wall_hydrostatic": (
        "Official PyNite adaptation: 25 × 15 ft tank wall, 1 ft thick, with 15 ft of water. Quad mesh 1 ft, left/right/bottom clamped, top free. Linear transverse pressure follows height.",
        "375 Quads; 1.4F normal load +245.7 kip and reaction sum −245.7 kip. Compare mesh refinements. Quad shear remains unverified and disabled; this is transverse plate bending, not an in-plane shear wall."),
    "official_plate_quad": (
        "Official PyNite adaptation: 10 × 20 ft clamped concrete plate, 1 ft thick, under +250 psf normal pressure. Opens the separate plate workspace.",
        "200 Quads; applied +50 kip; normal reactions total -50 kip. Classical thin-plate centre displacement +0.00171054 in (DKMQ +0.00191955 in); DKMQ includes transverse shear.")}


def example_definition(key="official_plate_quad", unit_system="imperial"):
    if key not in PLATE_EXAMPLES:
        raise ValueError(f"Unknown official plate example: {key}")
    if key == "official_shear_wall_basic":
        definition = PlateDefinition(
            width=312., height=192., thickness=8., mesh_size=6., plane="XY",
            material=Material("Masonry", E=900.*2000./1000., nu=.17, rho=.0000710),
            kx_mod=1., ky_mod=1.,
            pressure=0., load_case="E", load_factor=1.,
            edges=dict.fromkeys(("Left", "Right", "Bottom", "Top"), "Free"),
            openings=[
                dict(name="Door 1", x_left=24., y_bott=0., width=48., height=144.),
                dict(name="Window 1", x_left=96., y_bott=96., width=48., height=48.),
                dict(name="Window 2", x_left=168., y_bott=96., width=48., height=48.),
                dict(name="Door 2", x_left=240., y_bott=0., width=48., height=144.),
            ],
            analysis_mode="shear_wall",
            wall_supports=[dict(elevation=0., x_start=0., x_end=312.)],
            wall_stories=[dict(name="Top", elevation=192., x_start=0., x_end=312.)],
            wall_loads=[dict(story="Top", case="E", kind="shear", magnitude=100.)],
            combinations={"Seismic": {"E": 1.}},
            unit_system=unit_system, mesh_name="SW1")
        definition.validate()
        return definition
    if key == "official_shear_wall_advanced":
        definition = PlateDefinition(
            width=600., height=300., thickness=12., mesh_size=12., plane="XY",
            material=Material("Concrete", E=57000.*4500.**.5/1000., nu=.17, rho=.150/12**3),
            kx_mod=1., ky_mod=.35,
            pressure=0., load_case="E", additional_pressures={"D": 0.}, load_factor=1.,
            edges=dict.fromkeys(("Left", "Right", "Bottom", "Top"), "Free"),
            openings=[dict(name="Opng 1", x_left=60., y_bott=0., width=480., height=240.)],
            analysis_mode="shear_wall",
            wall_supports=[dict(elevation=0., x_start=0., x_end=600.)],
            wall_stories=[dict(name="Roof", elevation=300., x_start=0., x_end=600.)],
            wall_loads=[dict(story="Roof", case="E", kind="shear", magnitude=150.)],
            combinations={"1.2D+1.0E": {"D": 1.2, "E": 1.}},
            unit_system=unit_system, mesh_name="Wall 1")
        definition.validate()
        return definition
    if key == "official_mat_foundation":
        definition = PlateDefinition(
            width=600., height=300., thickness=12., mesh_size=12., plane="XZ",
            material=Material("Concrete", E=0.35*57.*4000.**.5, nu=.17, rho=.150/12**3),
            pressure=0., load_case="D", load_factor=1.,
            edges=dict.fromkeys(("Left", "Right", "Bottom", "Top"), "Free"),
            openings=[dict(name="OPNG1", x_left=60., y_bott=60., width=60., height=120.)],
            subgrade_modulus=.1, subgrade_mode="compression_only",
            point_loads=[
                dict(case="D", x=120., y=120., direction="FY", magnitude=-10.),
                dict(case="D", x=120., y=120., direction="MZ", magnitude=180.),
            ],
            combinations={"D": {"D": 1.}},
            unit_system=unit_system, mesh_name="MAT1")
        definition.validate()
        return definition
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
    project.surfaces = {definition.mesh_name: definition.mesh_definition(include_point_loads=True)}
    return project


def loading_summary(definition):
    u = definition.units
    pressures=[]
    for case,start in definition.case_pressures.items():
        profile=definition.pressure_profiles.get(case)
        text=f"{case}: {u.to_display(start,'pressure'):+.6g}"
        if profile:text+=f" → {u.to_display(profile['end_pressure'],'pressure'):+.6g} along local {profile['axis']}"
        pressures.append(text+' '+u.pressure)
    for load in definition.point_loads:
        quantity = "moment" if load["direction"].startswith("M") else "force"
        unit = u.moment if quantity == "moment" else u.force
        pressures.append(
            f"{load['case']} · ({u.to_display(load['x'], 'length'):.6g}, {u.to_display(load['y'], 'length'):.6g}) {u.length} · "
            f"{load['direction']}: {u.to_display(load['magnitude'], quantity):+.6g} {unit}")
    for load in definition.wall_loads:
        pressures.append(
            f"{load['case']} · Story {load['story']} · {load['kind']}: "
            f"{u.to_display(load['magnitude'], 'force'):+.6g} {u.force}")
    subgrade = (f"\nSoil subgrade: ks = {u.to_display(definition.subgrade_modulus, 'density'):.6g} {u.density} ({definition.subgrade_mode})"
                if definition.subgrade_modulus > 0 else "")
    wall_lines = ""
    if definition.analysis_mode == "shear_wall":
        supports = "; ".join(
            f"y={u.to_display(item['elevation'], 'length'):.6g} [{u.to_display(item['x_start'], 'length'):.6g}..{u.to_display(item['x_end'], 'length'):.6g}] {u.length}"
            for item in definition.wall_supports)
        stories = "; ".join(
            f"{item['name']} y={u.to_display(item['elevation'], 'length'):.6g} [{u.to_display(item['x_start'], 'length'):.6g}..{u.to_display(item['x_end'], 'length'):.6g}] {u.length}"
            for item in definition.wall_stories)
        wall_lines = f"\nWall supports: {supports}\nStories: {stories}"
    combinations='; '.join(name+' = '+' + '.join(f'{factor:g}{case}' for case,factor in factors.items())
                           for name,factors in definition.load_combinations.items())
    mode_note = ('In-plane shear wall membrane analysis with automatic pier & coupling-beam force summation; self-weight off.\n'
                 if definition.analysis_mode == "shear_wall"
                 else 'Centroid pressure per element; compare refinements. Linear elastic transverse bending; self-weight off.\n')
    return (f"Separate plate workspace · {u.summary}\n"
            f"Size: {u.to_display(definition.width, 'length'):.6g} × {u.to_display(definition.height, 'length'):.6g} {u.length}\n"
            f"Thickness: {u.to_display(definition.thickness, 'length'):.6g} {u.length}\n"
            f"Mesh: {u.to_display(definition.mesh_size, 'length'):.6g} {u.length} · {definition.element_type}\n"
            +'; '.join(edge+': '+support for edge,support in definition.edges.items())+subgrade+wall_lines+'\n'
            +'\n'.join(pressures)+'\nCombinations: '+combinations+'\n'
            +mode_note
            +'The main frame model and unsaved inputs remain unchanged.')
