"""Independent signed resultants, Rect polynomial recovery and hole refinement."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

import numpy as np

from pynitegui.qt.model import Material
from pynitegui.qt.plate_model import PlateDefinition, analyze_plate, build_plate
from pynitegui.qt.plate_recovery import rectangular_resultants
from plate_reference import OpeningRitz, navier


HOLE = dict(name="Opening", x_left=40., y_bott=40., width=40., height=40.)


def rigidity(definition):
    return definition.material.E*definition.thickness**3/(12*(1-definition.material.nu**2))


def opening_definition(family, size):
    return PlateDefinition(element_type=family, mesh_size=size, thickness=.6,
                           pressure=-1e-7, openings=[dict(HOLE)])


def patch_average(result):
    polygons = result["points"][result["cells"]]
    centres = polygons.mean(axis=1)
    select = (centres[:, 0] < 40) & (centres[:, 1] < 40)
    area = np.abs(np.sum(polygons[:, :, 0]*np.roll(polygons[:, :, 1], -1, axis=1)
                         -polygons[:, :, 1]*np.roll(polygons[:, :, 0], -1, axis=1), axis=1))/2
    return np.average(result["moments"][select], axis=0, weights=area[select])


class IndependentPlateReferenceTests(unittest.TestCase):
    def test_intact_ritz_reduces_to_navier(self):
        points = np.array([[60., 90.], [30., 60.], [90., 120.]])
        ritz = OpeningRitz(120, 180, .2, terms=9)
        series, _, _ = navier(points, 120, 180, .2, 1., 1., terms=18)
        np.testing.assert_allclose(ritz.displacement(points), series, rtol=1e-12)
        square = OpeningRitz(1., 1., .3, terms=13)
        self.assertAlmostEqual(square.displacement([[.5, .5]])[0], .00406235, delta=2e-8)

    def test_opening_basis_convergence_is_checked_separately(self):
        references = [OpeningRitz(120, 120, .2, 40, 40, terms=n) for n in (7, 9, 11, 13)]
        self.assertTrue(all(a.compliance < b.compliance for a, b in zip(references, references[1:])))
        np.testing.assert_allclose(references[-2].displacement([[40, 60], [20, 60]]),
                                   references[-1].displacement([[40, 60], [20, 60]]), rtol=.002)
        np.testing.assert_allclose(references[-2].mean_moments((0, 40, 0, 40)),
                                   references[-1].mean_moments((0, 40, 0, 40)), rtol=.002)
        self.assertLess(references[-1].condition, 1e8)


class RectResultantTests(unittest.TestCase):
    def test_manufactured_polynomial_and_rigid_motion(self):
        a, b, E, t, nu = 7., 11., 3200., .8, .3
        D = E*t**3/(12*(1-nu**2))
        # Independent explicit polynomials: rigid plane, twist, and all higher
        # polynomial terms (including x³y and xy³) used by the Rect element.
        functions = [
            (lambda x, y: (1+2*x-3*y, 2., -3.), lambda x, y: (0, 0, 0, 0, 0)),
            (lambda x, y: (x*y, y, x), lambda x, y: (0, 0, 1, 0, 0)),
            (lambda x, y: (x*x+2*y*y+x*y+x**3+y**3+x*x*y+x*y*y+x**3*y+x*y**3,
                           2*x+y+3*x*x+2*x*y+y*y+3*x*x*y+y**3,
                           4*y+x+3*y*y+x*x+2*x*y+x**3+3*x*y*y),
             lambda x, y: (2+6*x+2*y+6*x*y, 4+6*y+2*x+6*x*y,
                            1+2*x+2*y+3*x*x+3*y*y, 8+12*y, 8+12*x)),
        ]
        for field, derivatives in functions:
            nodal = np.zeros((4, 6))
            for row, (x, y) in enumerate(((0, 0), (a, 0), (a, b), (0, b))):
                w, wx, wy = field(x, y)
                nodal[row, [2, 3, 4]] = [w, wy, -wx]
            element = SimpleNamespace(width=lambda: a, height=lambda: b, d=lambda combo: nodal.reshape(24, 1))
            moments, shears = rectangular_resultants(element, E, nu, t)
            xx, yy, xy, gradient_x, gradient_y = derivatives(a/2, b/2)
            np.testing.assert_allclose(moments, -D*np.array([xx+nu*yy, yy+nu*xx, (1-nu)*xy]), atol=1e-8)
            np.testing.assert_allclose(shears, -D*np.array([gradient_x, gradient_y]), atol=1e-8)

    def test_local_displacement_contract_is_checked(self):
        for data in (np.zeros((12, 1)), np.full((24, 1), np.nan)):
            element = SimpleNamespace(width=lambda: 2., height=lambda: 3., d=lambda combo: data)
            with self.assertRaisesRegex(ValueError, "local displacement contract"):
                rectangular_resultants(element, 3600., .2, .6)

    def test_rect_bending_modifiers_are_rejected_but_recipe_previews_survive(self):
        for modifiers in ({"kx_mod": .35}, {"ky_mod": 1.7}):
            definition = replace(PlateDefinition(element_type="Rect", mesh_size=30), **modifiers)
            self.assertEqual(len(build_plate(definition).plates), 16)
            self.assertEqual(PlateDefinition.from_dict(definition.to_dict()), definition)
            with self.assertRaisesRegex(ValueError, "does not support stiffness modifiers"):
                analyze_plate(definition)

    def test_navier_non_square_moment_and_shear_refinement(self):
        errors = []
        for size in (30., 15., 7.5):
            definition = PlateDefinition(element_type="Rect", width=120., height=180., mesh_size=size,
                                         pressure=-1e-7, thickness=.6)
            result = analyze_plate(definition)
            points = result["points"][result["cells"]].mean(axis=1)
            _, moments, shears = navier(points, 120, 180, .2, definition.pressure, rigidity(definition))
            select = (points[:, 0] > 20) & (points[:, 0] < 100) & (points[:, 1] > 20) & (points[:, 1] < 160)
            combined = np.r_[np.linalg.norm((result["moments"]-moments)[select], axis=0)/np.linalg.norm(moments[select], axis=0),
                             np.linalg.norm((result["shears"]-shears)[select], axis=0)/np.linalg.norm(shears[select], axis=0)]
            errors.append(combined)
        self.assertTrue(np.all(errors[2] < errors[1]))
        self.assertTrue(np.all(errors[1] < errors[0]))
        self.assertTrue(np.all(errors[2] < .01), errors)

    def test_cantilever_strip_signed_moment_and_shear_in_both_directions(self):
        for support, direction, length in (("Left", 0, 120.), ("Bottom", 1, 60.)):
            definition = PlateDefinition(element_type="Rect", height=60., mesh_size=7.5, pressure=-1e-7,
                                         material=Material("Strip", E=3600., nu=0., rho=0.),
                                         edges={edge: "Clamped" if edge == support else "Free" for edge in ("Left", "Right", "Bottom", "Top")})
            result = analyze_plate(definition)
            points = result["points"][result["cells"]].mean(axis=1)
            distance = length-points[:, direction]
            # Cut equilibrium: M=-q*(L-x)²/2 and Q=q*(L-x).
            expected_moment = -definition.pressure*distance**2/2
            expected_shear = definition.pressure*distance
            np.testing.assert_allclose(result["moments"][:, direction], expected_moment, rtol=.03, atol=1e-6)
            np.testing.assert_allclose(result["shears"][:, direction], expected_shear, rtol=.03, atol=2e-7)


class OpeningRecoveryTests(unittest.TestCase):
    def test_free_opening_deflection_and_patch_moment_refinement(self):
        reference = OpeningRitz(120, 120, .2, 40, 40, terms=13)
        for family in ("Quad", "Rect"):
            displacements, errors = [], []
            for size in (20., 10., 5.):
                definition = opening_definition(family, size)
                result = analyze_plate(definition)
                indices = [np.flatnonzero(np.all(np.isclose(result["points"], point), axis=1))[0] for point in ([40, 60], [20, 60])]
                values = result["displacement"][indices]
                expected = reference.displacement([[40, 60], [20, 60]])*definition.pressure/rigidity(definition)
                displacements.append(values)
                moment_reference = reference.mean_moments((0, 40, 0, 40))*definition.pressure
                mean = patch_average(result)
                errors.append(np.linalg.norm(mean-moment_reference))
                self.assertAlmostEqual(result["applied"], definition.pressure*(120**2-40**2))
                self.assertAlmostEqual(result["reactions"].sum(), -result["applied"], places=10)
            np.testing.assert_allclose(values, expected, rtol=.005)
            np.testing.assert_allclose(mean, moment_reference, rtol=.015)
            self.assertTrue(np.all(np.abs(displacements[2]-displacements[1]) < np.abs(displacements[1]-displacements[0])))
            self.assertLess(errors[2], errors[1])
            self.assertLess(errors[1], errors[0])

    def test_plane_origin_and_factored_pressure_preserve_rect_fields(self):
        base = opening_definition("Rect", 20.)
        reference = analyze_plate(base)
        for plane in ("XY", "XZ", "YZ"):
            result = analyze_plate(replace(base, plane=plane, origin=[17., -31., 49.], load_factor=-2.))
            for key in ("displacement", "moments", "shears", "reactions"):
                np.testing.assert_allclose(result[key], -2*reference[key], rtol=1e-9, atol=1e-11)
            np.testing.assert_allclose(result["points"], reference["points"], atol=1e-12)
