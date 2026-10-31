"""Independent 3D release statics, slopes, oblique gauges and mechanism checks."""
import contextlib
from copy import deepcopy
import io
import math
import pickle
import unittest
from unittest.mock import patch

import numpy as np
from Pynite import FEModel3D

from pynitegui.qt.analysis import analyze
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Material, Project, Section
from pynitegui.qt.spatial_model import SpatialProject, SpatialLoad
from pynitegui.qt.spatial_releases import ROTATION_FIELDS, unused_rotation_axes
from pynitegui.qt.spatial_results import member_axes, member_values
from pynitegui.qt.spatial_conversion import to_spatial


def beam(end=(120., 0., 0.), roll=0.):
    p = SpatialProject()
    p.set_material(Material("Test", E=30000., nu=.25, rho=0.))
    p.set_section(Section("Test", A=8., Iy=20., Iz=80., J=5.))
    p.default_material = p.default_section = "Test"
    p.add_member((17., -31., 49.), tuple(np.array((17., -31., 49.))+end))
    p.nodes["N1"].support, p.nodes["N2"].support = "fixed", "pin"
    m = p.members["M1"]
    m.roll = roll
    m.release_start = m.release_end = m.release_start_ry = m.release_end_ry = True
    p.loads["Y"] = SpatialLoad("Y", "M1", "Fy", -.001, position=0., kind="distributed", end_magnitude=-.001)
    p.loads["Z"] = SpatialLoad("Z", "M1", "Fz", .0006, position=0., kind="distributed", end_magnitude=.0006)
    p.set_combination("Reverse", {"Case 1": -1.7})
    p.set_combination("Zero", {"Case 1": 0.})
    return p


def solve(p):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(p)


class SpatialReleaseTests(unittest.TestCase):
    def test_uniform_biaxial_beam_recovers_slopes_in_oblique_rolled_and_reversed_axes(self):
        for end, roll in (((120., 0., 0.), 0.), ((72., 64., 80.), 31.), ((0., -120., 0.), -47.), ((-72., -64., -80.), 128.)):
            p = beam(end, roll)
            before = p.to_dict()
            result = pickle.loads(pickle.dumps(solve(p)))
            self.assertEqual(p.to_dict(), before)
            L = math.dist(p.nodes["N1"].coords, p.nodes["N2"].coords)
            E, Iy, Iz = 30000., 20., 80.
            axes = member_axes(p, "M1")
            for combo, factor in (("Service", 1.), ("Reverse", -1.7), ("Zero", 0.)):
                r = result.for_combination(combo)
                qy, qz = -.001*factor, .0006*factor
                self.assertTrue(check_equilibrium(p, r).passed)
                for x in np.linspace(0., L, 9):
                    values = member_values(r, "M1", x)
                    dy = qy*x*(L**3-2*L*x*x+x**3)/(24*E*Iz)
                    dz = qz*x*(L**3-2*L*x*x+x**3)/(24*E*Iy)
                    np.testing.assert_allclose(values[6:], [dy, dz], atol=1e-10)
                    # Both engine diagram components use the sagging sign;
                    # the right-handed physical Ry slope is -dz/dx below.
                    np.testing.assert_allclose(values[4:6], [qz*x*(L-x)/2, qy*x*(L-x)/2], atol=1e-9)
                sub = next(iter(r.solver.members["M1"].sub_members.values()))
                d = sub.d(combo).ravel()
                np.testing.assert_allclose(d[[4, 5, 10, 11]], [-qz*L**3/(24*E*Iy), qy*L**3/(24*E*Iz),
                    qz*L**3/(24*E*Iy), -qy*L**3/(24*E*Iz)], atol=1e-10)
                for node in ("N1", "N2"):
                    np.testing.assert_allclose(axes @ r.reactions[node][:3], [0., -qy*L/2, -qz*L/2], atol=1e-9)
                G = r.solver.gauge_matrix()
                K = FEModel3D.Ke(r.solver, combo, check_stability=False, sparse=True).tocsr()
                np.testing.assert_allclose((K@G).toarray(), 0., atol=1e-7)
                np.testing.assert_allclose(G.T @ r.solver.D(combo), 0., atol=1e-12)
                self.assertFalse(r.solver.nodes["N2"].support_RX)
                self.assertFalse(r.solver.nodes["N2"].support_RY)
                self.assertFalse(r.solver.nodes["N2"].support_RZ)
            if end == (72., 64., 80.):
                self.assertEqual(result.displacements["N2"][3:], (None, None, None))

    def test_released_rotation_at_a_free_tip_retains_cantilever_motion_not_zero_node_angle(self):
        p = beam()
        p.nodes["N2"].support = "free"
        m = p.members["M1"]
        m.release_start = m.release_start_ry = False
        p.loads.clear()
        p.loads["P"] = SpatialLoad("P", "N2", "FY", -2.)
        r = solve(p)
        self.assertIsNone(r.displacements["N2"][5])
        self.assertAlmostEqual(r.displacements["N2"][1], -2*120**3/(3*30000*80))
        sub = next(iter(r.solver.members["M1"].sub_members.values()))
        self.assertAlmostEqual(sub.d("Service")[11, 0], -2*120**2/(2*30000*80))
        self.assertAlmostEqual(member_values(r, "M1", 120.)[5], 0., places=9)

    def test_shared_internal_hinge_gives_fixed_pinned_reactions_and_distinct_member_slopes(self):
        p = beam()
        p.members["M1"].release_start = p.members["M1"].release_start_ry = False
        p.add_member(p.nodes["N2"].coords, (257., -31., 49.))
        p.nodes["N3"].support = "fixed"
        p.members["M2"].release_start = p.members["M2"].release_start_ry = True
        p.loads.pop("Z")
        p.loads["Other"] = SpatialLoad("Other", "M2", "Fy", -.001, position=0., kind="distributed", end_magnitude=-.001)
        r = solve(p)
        q, L, EI = -.001, 120., 30000.*80.
        self.assertAlmostEqual(r.reactions["N1"][1], -5*q*L/8)
        self.assertAlmostEqual(r.reactions["N2"][1], -3*q*L/4)
        self.assertAlmostEqual(r.reactions["N3"][1], -5*q*L/8)
        for x in np.linspace(0., L, 7):
            expected = q*x*x*(2*x*x-5*L*x+3*L*L)/(48*EI)
            self.assertAlmostEqual(member_values(r, "M1", x)[6], expected)
        a = next(iter(r.solver.members["M1"].sub_members.values())).d("Service")[11, 0]
        b = next(iter(r.solver.members["M2"].sub_members.values())).d("Service")[5, 0]
        self.assertAlmostEqual(a, -q*L**3/(48*EI))
        self.assertAlmostEqual(b, q*L**3/(48*EI))
        self.assertIsNone(r.displacements["N2"][5])
        self.assertTrue(check_equilibrium(p, r).passed)

    def test_unreleased_incident_member_or_spring_defines_joint_rotation_but_not_released_end(self):
        for spring in (False, True):
            p = beam()
            p.loads.clear()
            if spring:
                p.nodes["N2"].spring_rz = 100.
                expected = .05
            else:
                p.add_member(p.nodes["N2"].coords, (137., 89., 49.))
                p.nodes["N3"].support = "fixed"
                expected = 5*120/(4*30000*80)
            p.loads["Moment"] = SpatialLoad("Moment", "N2", "MZ", 5.)
            r = solve(p)
            self.assertAlmostEqual(r.displacements["N2"][5], expected)
            sub = next(iter(r.solver.members["M1"].sub_members.values()))
            self.assertAlmostEqual(sub.d("Service")[11, 0], 0.)
            self.assertAlmostEqual(sub.f("Service")[11, 0], 0.)
            self.assertTrue(check_equilibrium(p, r).passed)

    def test_one_torsion_release_recovers_member_twist_and_transfers_point_torque(self):
        p = beam()
        p.nodes["N2"].support = "free"
        m = p.members["M1"]
        m.release_start = m.release_end = m.release_start_ry = m.release_end_ry = False
        m.release_end_rx = True
        p.loads.clear()
        p.loads["T"] = SpatialLoad("T", "M1", "Mx", 5., position=.4)
        r = solve(p)
        self.assertIsNone(r.displacements["N2"][3])
        self.assertAlmostEqual(r.reactions["N1"][3], -5.)
        sub = next(iter(r.solver.members["M1"].sub_members.values()))
        self.assertAlmostEqual(sub.d("Service")[9, 0], 5*48/(12000*5))
        self.assertTrue(check_equilibrium(p, r).passed)

    def test_unresisted_nodal_and_member_moments_are_rejected_in_their_combination(self):
        for target, direction in (("N2", "MZ"), ("M1", "Mx")):
            p = beam()
            p.members["M1"].release_start_rx = True
            p.loads.clear()
            p.loads["Bad"] = SpatialLoad("Bad", target, direction, 2.)
            with self.assertRaisesRegex(ValueError, "Unresisted moment"):
                solve(p)

    def test_oblique_moment_components_are_combined_before_unused_direction_check(self):
        p = beam((72., 64., 80.), 31.)
        p.loads.clear()
        axis = member_axes(p, "M1")[0]
        for direction, value in zip(("MX", "MY", "MZ"), axis*5):
            p.loads[direction] = SpatialLoad(direction, "N2", direction, float(value))
        r = solve(p)
        self.assertTrue(check_equilibrium(p, r).passed)
        np.testing.assert_allclose(np.array(r.reactions["N1"][3:]), -5*axis, atol=1e-9)

    def test_physical_hinge_mechanisms_and_near_dependent_axes_are_never_gauged_away(self):
        p = beam()
        p.nodes["N2"].support = "free"
        with self.assertRaisesRegex(ValueError, "unstable|singular|rigid body"):
            solve(p)
        p = beam()
        p.nodes["N2"].support = "free"
        p.add_member(p.nodes["N2"].coords, tuple(np.array(p.nodes["N2"].coords)+(120., 1e-6, 0.)))
        p.nodes["N3"].support = "fixed"
        p.members["M2"].release_start = p.members["M2"].release_start_ry = True
        with self.assertRaisesRegex(ValueError, "nearly dependent"):
            unused_rotation_axes(p)

    def test_physical_equation_and_global_equilibrium_errors_reject_entire_snapshot(self):
        from pynitegui.qt.analysis import solve_model
        for fault in ("free equation", "global reaction"):
            p = beam()
            def corrupt(model, project, phase):
                solve_model(model, project, phase)
                # Corrupt only a later combination: Service must not escape as
                # an accepted snapshot when another combination is invalid.
                if fault == "free equation":
                    model._D["Reverse"][model.nodes["N2"].ID*6+3, 0] += .01
                else:
                    model.nodes["N1"].RxnFY["Reverse"] += .01
            expected = "physical equilibrium failed" if fault == "free equation" else "Released frame equilibrium failed"
            with self.subTest(fault=fault), patch("pynitegui.qt.analysis.solve_model", side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, expected):
                    solve(p)

    def test_serialization_strict_legacy_defaults_split_and_unsupported_boundaries(self):
        p = beam()
        data = p.to_dict()
        self.assertEqual(data["version"], 40)
        self.assertEqual(Project.from_dict(data).to_dict(), data)
        old = deepcopy(data)
        old["version"] = 28
        for row in old["members"].values():
            for key in ROTATION_FIELDS:
                if key in ("release_start", "release_end"):
                    row[key] = False
                else:
                    row.pop(key)
        before = deepcopy(old)
        migrated = Project.from_dict(old)
        self.assertEqual(old, before)
        self.assertTrue(all(getattr(migrated.members["M1"], key) is False for key in ROTATION_FIELDS))
        for override, message in (({"release_end_rx": True, "release_start_rx": True}, "both ends"),
                                  ({"release_end_ry": 1}, "boolean"), ({"release_start_x": 1}, "boolean"),
                                  ({"kind": "truss"}, "clear manual")):
            bad = p.clone()
            for key, value in override.items():
                setattr(bad.members["M1"], key, value)
            with self.assertRaisesRegex(ValueError, message):
                bad.validate()
        for key in ROTATION_FIELDS:
            bad = deepcopy(data)
            bad["members"]["M1"].pop(key)
            with self.assertRaisesRegex(ValueError, "Missing"):
                Project.from_dict(bad)
        old["members"]["M1"]["release_start"] = True
        with self.assertRaisesRegex(ValueError, "version 30"):
            Project.from_dict(old)
        for field in ("release_start_rx", "release_start_ry"):
            p = beam()
            setattr(p.members["M1"], field, True)
            names = p.split_member("M1", .4)
            self.assertTrue(getattr(p.members[names[0]], field))
            self.assertFalse(getattr(p.members[names[1]], field))
            self.assertFalse(p.members[names[0]].release_end)
            self.assertTrue(p.members[names[1]].release_end)
        p = beam()
        p.analysis_method = "p_delta"
        with self.assertRaisesRegex(ValueError, "Linear elastic"):
            solve(p)
        p = example_project("3d_slab_frame")
        p.members["M1"].release_end = True
        with self.assertRaisesRegex(ValueError, "frame-only"):
            solve(p)

    def test_rotational_planar_conversion_and_public_example_retain_releases(self):
        for key in ("simple_beam", "gerber", "three_hinged_arch"):
            p = example_project(key)
            if key == "simple_beam":
                p.members["M1"].release_start = p.members["M1"].release_end = True
            converted = to_spatial(p)
            r = solve(converted)
            self.assertTrue(check_equilibrium(converted, r).passed)
            for name, member in p.members.items():
                self.assertEqual(converted.members[name].moment_releases, member.moment_releases)
        p = example_project("3d_released_beam")
        r = solve(p)
        self.assertEqual(r.displacements["N2"][3:], (None, None, None))
        self.assertTrue(check_equilibrium(p, r).passed)


if __name__ == "__main__":
    unittest.main()
