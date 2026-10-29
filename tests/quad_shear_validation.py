"""Test-only Quad shear feasibility; never imported by application recovery.

Compare raw shear and two moment-divergence candidates on uniform rectangular
meshes. A complete 3 x 3 patch is mandatory for the neighbouring-centre fit.
No extrapolation to boundaries, bridging holes or general-mesh certification.
"""
import numpy as np

from pynitegui.qt.plate_model import PlateDefinition, build_plate, plate_equilibrium
from pynitegui.qt.model import Material
from plate_reference import navier


METHODS = ("raw", "element_divergence", "patch_divergence")
FACTORS = {"Service": 1., "Reverse": -2., "Zero": 0.}
SIZES = (30., 15., 7.5)
CASES = ("plate_navier", "coupled_navier", "strip_x", "strip_y")


def patch_divergence(points, moments):
    """Quadratic fit to nine neighbouring centre moments, canonical kip/in.

    Coordinates are common surface-local x/y, moments are [Mx, My, Mxy].
    Missing patches return NaN plus a false mask, never a guessed boundary value.
    This research routine is restricted to one uniform, isotropic flat region.
    """
    points, moments = np.asarray(points, float), np.asarray(moments, float)
    if (points.ndim != 2 or points.shape[1] != 2 or moments.shape != (len(points), 3)
            or not len(points) or not np.isfinite(points).all() or not np.isfinite(moments).all()):
        raise ValueError("Finite centre points and three moments per element are required.")
    axes = [np.unique(points[:, i]) for i in (0, 1)]
    spacing = []
    for axis in axes:
        differences = np.diff(axis)
        if not len(differences) or not np.allclose(differences, differences[0], rtol=1e-9, atol=1e-10):
            raise ValueError("Research patch recovery requires a uniform rectangular grid.")
        spacing.append(differences[0])
    grid = np.rint((points-np.array([axis[0] for axis in axes]))/spacing).astype(int)
    lookup = {tuple(index): i for i, index in enumerate(grid)}
    if len(lookup) != len(points):
        raise ValueError("Duplicate element centres are not a valid patch.")
    offsets = [(x, y) for y in (-1, 0, 1) for x in (-1, 0, 1)]
    x, y = np.array(offsets, float).T
    design = np.column_stack((np.ones(9), x, y, x*x, x*y, y*y))
    shears = np.full((len(points), 2), np.nan)
    valid = np.zeros(len(points), bool)
    for i, (ix, iy) in enumerate(grid):
        keys = [(ix+dx, iy+dy) for dx, dy in offsets]
        if not all(key in lookup for key in keys):
            continue
        coefficients = np.linalg.lstsq(design, moments[[lookup[key] for key in keys]], rcond=None)[0]
        dx, dy = coefficients[1]/spacing[0], coefficients[2]/spacing[1]
        shears[i] = (dx[0]+dy[2], dx[2]+dy[1])
        valid[i] = True
    return shears, valid


def gather(elements, combination):
    """Take common-local centre data without changing any solved displacement."""
    points, moments, raw, divergence = [], [], [], []
    axes = np.asarray(elements[0].T())[:3, :3]
    origin = np.array([elements[0].i_node.X, elements[0].i_node.Y, elements[0].i_node.Z])
    for element in elements:
        np.testing.assert_allclose(element.T()[:3, :3], axes, atol=1e-12)
        nodes = (element.i_node, element.j_node, element.m_node, element.n_node)
        polygon = (np.array([(n.X, n.Y, n.Z) for n in nodes])-origin) @ axes.T
        xy = polygon[:, :2]
        a, b = xy[1, 0]-xy[0, 0], xy[3, 1]-xy[0, 1]
        if a <= 0 or b <= 0:
            raise ValueError("Research sample requires positively oriented rectangles.")
        np.testing.assert_allclose(xy-xy[0], [[0, 0], [a, 0], [a, b], [0, b]], atol=1e-9)
        corner = np.array([element.moment(xi, eta, combo_name=combination).ravel()
                           for xi, eta in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        dx = np.array([-.5, .5, .5, -.5]) @ corner/a
        dy = np.array([-.5, -.5, .5, .5]) @ corner/b
        points.append(xy.mean(axis=0))
        moments.append(element.moment(combo_name=combination).ravel())
        raw.append(element.shear(combo_name=combination).ravel())
        divergence.append([dx[0]+dy[2], dx[2]+dy[1]])
    points, moments = np.asarray(points), np.asarray(moments)
    patch, valid = patch_divergence(points, moments)
    return dict(points=points, moments=moments, raw=np.asarray(raw),
                element_divergence=np.asarray(divergence), patch_divergence=patch, valid=valid)


def solve_case(case, size, plane="XY"):
    """Applied-pressure solves, not prescribed reference displacements."""
    if case not in CASES:
        raise ValueError("Unknown shear benchmark case.")
    width, height, pressure, thickness = 120., 180., -1e-7, .6
    if case == "coupled_navier":
        from test_surface_results import supported_plate, quiet_solve
        from pynitegui.qt.equilibrium import check_equilibrium
        project = supported_plate(size, plane)
        # Retain a real frame member, with negligible directional stiffness.
        # A larger edge-beam EI changes the physical problem on axis permutation.
        project.materials[project.default_material].E = 1e-6
        mesh = project.surfaces["Plate"]
        mesh.parameters["height"] = height
        mesh.thickness = thickness
        project.surface_pressures["Plate"]["Case 1"] = pressure
        for name, factor in FACTORS.items():
            project.set_combination(name, {"Case 1": factor}, name if name in project.combinations else None)
        result = quiet_solve(project)
        elements = [result.solver.quads[name] for name in result.solver._pynitegui_surfaces["Plate"]["elements"]]
        samples = {name: gather(elements, name) for name in FACTORS}
        if not all(check_equilibrium(project, result.for_combination(name)).passed for name in FACTORS):
            raise AssertionError("Coupled equilibrium failed.")
        E, nu = mesh.material.E, mesh.material.nu
    else:
        nu = 0. if case.startswith("strip") else .2
        definition = PlateDefinition(width=width, height=height, thickness=thickness,
            mesh_size=size, pressure=pressure, plane=plane, origin=[17., -31., 49.],
            material=Material("Reference", E=3600., nu=nu, rho=0.),
            combinations={name: {"Case 1": factor} for name, factor in FACTORS.items()})
        if case.startswith("strip"):
            fixed = "Left" if case == "strip_x" else "Bottom"
            definition.edges = {edge: "Clamped" if edge == fixed else "Free" for edge in definition.edges}
        model = build_plate(definition)
        model.analyze_linear(check_stability=True, check_statics=False)
        elements = list(model.quads.values())
        samples = {name: gather(elements, name) for name in FACTORS}
        for name, factor in FACTORS.items():
            plate_equilibrium(model, definition, name, pressure*factor)
        E = definition.material.E
    D = E*thickness**3/(12*(1-nu**2))
    for name, sample in samples.items():
        points = sample["points"]
        q = pressure*FACTORS[name]
        if case.endswith("navier"):
            _, _, reference = navier(points, width, height, nu, q, D, terms=160)
        else:
            axis = 0 if case == "strip_x" else 1
            reference = np.zeros((len(points), 2))
            reference[:, axis] = q*((width, height)[axis]-points[:, axis])
        sample["reference"] = reference
        # Same interior region and same points for all three methods.
        sample["selected"] = sample["valid"] & np.all((points > 20.) & (points < [width-20, height-20]), axis=1)
    return samples


def metrics(sample):
    selected = sample["selected"]
    if not np.any(selected):
        raise ValueError("No complete interior patches in the comparison region.")
    expected = sample["reference"][selected]
    scale = np.linalg.norm(expected)
    data = dict(elements=len(selected), compared_elements=int(selected.sum()),
                complete_patches=int(sample["valid"].sum()))
    for method in METHODS:
        difference = sample[method][selected]-expected
        if not np.isfinite(difference).all():
            raise ValueError("Nonfinite shear comparison.")
        norms = np.linalg.norm(expected, axis=0)
        data[method] = dict(relative_l2=float(np.linalg.norm(difference)/scale) if scale else None,
            component_relative_l2=[float(error/norm) if norm else None
                for error, norm in zip(np.linalg.norm(difference, axis=0), norms)],
            max_absolute_error_kip_per_in=float(np.max(abs(difference))))
    return data
