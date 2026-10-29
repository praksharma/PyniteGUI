"""Independent local recovery, geometry-owned restraints and coupled solve gates."""
import contextlib
from copy import deepcopy
import io
import unittest
import numpy as np
from Pynite import FEModel3D

from pynitegui.qt.analysis import AnalysisResult, analyze
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.mesh_model import MeshDefinition
from pynitegui.qt.model import Project
from pynitegui.qt.spatial_model import SpatialProject, SpatialNode, SpatialMember, DOFS
from pynitegui.qt.spatial_surfaces import surface_geometry, put_surface
from pynitegui.qt.surface_solver import attach_surfaces, validate_coupled_topology
from pynitegui.qt.surface_supports import EDGES, PLANE_AXES, resolved_supports, support_segments
from pynitegui.qt.surface_results import FIELDS, centre_results, inspect_surface, surface_table
from pynitegui.qt.units import UNIT_SYSTEMS
from test_coupled_surfaces import slab_frame
from plate_reference import navier


def supported_plate(size=15., plane="XY"):
    """A negligible-stiffness perimeter beam keeps this a coupled project.

    The beam's E is 360,000 times smaller than the slab's E. Its boundary
    rotation stiffness is deliberately retained, not subtracted from results.
    """
    p = SpatialProject()
    p.materials[p.default_material].E = .01
    u, v, n = PLANE_AXES[plane]
    origin = np.array((17., -31., 49.))
    end = origin.copy()
    end[u] += 120.
    p.nodes = {"A": SpatialNode("A", origin[0], origin[1], z=origin[2]),
               "B": SpatialNode("B", end[0], end[1], z=end[2])}
    p.members = {"Beam": SpatialMember("Beam", "A", "B")}
    p.surfaces["Plate"] = MeshDefinition(name="Plate", plane=plane, origin=origin.tolist(),
        parameters={"width": 120., "height": 120.}, mesh_size=size, thickness=1.)
    p.surface_analysis_enabled = True
    p.surface_pressures = {"Plate": {"Case 1": -.001}}
    p.surface_supports = {"Plate": {edge: list(DOFS[:3]) for edge in EDGES}}
    return p


def quiet_solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


class SurfaceSupportModelTests(unittest.TestCase):
    def test_nonsquare_yz_edges_and_notch_follow_recipe_width_z_height_y(self):
        origin = np.array((19., -7., 41.))
        p = SpatialProject(surfaces={"Patch": MeshDefinition(name="Patch", plane="YZ", origin=origin.tolist(),
            parameters={"width": 120., "height": 80.}, mesh_size=20.,
            openings=[dict(name="Notch", x_left=0., y_bott=20., width=20., height=20.)])})
        p.surface_supports = {"Patch": {"left": ["DX"], "right": ["DY"], "bottom": ["DZ"], "top": ["RZ"]}}
        for size in (20., 10.):
            p.surfaces["Patch"].mesh_size = size
            p.validate()
            points = np.asarray(surface_geometry(p.surfaces["Patch"])[2])-origin
            supports = resolved_supports(p, "Patch")
            for index, dofs in supports.items():
                x, y, z = points[index]
                self.assertEqual(x, 0.)
                for dof, axis, value in (("DX", 2, 0.), ("DY", 2, 120.), ("DZ", 1, 0.), ("RZ", 1, 80.)):
                    if dof in dofs:
                        self.assertEqual(points[index, axis], value)
            segments = {row["edge"]: row["segments"] for row in support_segments(p, "Patch")}
            self.assertEqual(set(segments), set(EDGES))
            left_length = 0.
            for a, b in segments["left"]:
                a, b = np.asarray(a)-origin, np.asarray(b)-origin
                self.assertEqual(a[2], 0.)
                self.assertEqual(b[2], 0.)
                self.assertFalse(20. < (a[1]+b[1])/2 < 40.)
                left_length += np.linalg.norm(b-a)
            self.assertAlmostEqual(left_length, 60.)

    def test_version_migration_strict_schema_and_assignment_lifecycle(self):
        p = slab_frame()
        legacy = p.to_dict()
        legacy["version"] = 26
        legacy.pop("surface_supports")
        before = deepcopy(legacy)
        self.assertEqual(Project.from_dict(legacy).surface_supports, {})
        self.assertEqual(legacy, before)
        p.surface_supports = {"Floor": {"left": ["DY", "RZ"]}}
        data = p.to_dict()
        self.assertEqual(data["version"], 30)
        self.assertEqual(Project.from_dict(data).to_dict(), data)
        for change in ({"version": 26}, {"surface_supports": None},
                       {"surface_supports": {"missing": {"left": ["DY"]}}},
                       {"surface_supports": {"Floor": {"hole": ["DY"]}}},
                       {"surface_supports": {"Floor": {"left": ["DY", "DY"]}}},
                       {"surface_supports": {"Floor": {"left": [True]}}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                Project.from_dict({**data, **change})
        bad = dict(data)
        bad.pop("surface_supports")
        with self.assertRaisesRegex(ValueError, "Missing"):
            Project.from_dict(bad)
        mesh = MeshDefinition.from_dict(p.surfaces["Floor"].to_dict())
        mesh.name = "Roof"
        put_surface(p, mesh, "Floor")
        self.assertEqual(p.surface_supports, {"Roof": {"left": ["DY", "RZ"]}})
        p.delete("surfaces", "Roof")
        self.assertFalse(p.surface_supports)

    def test_remesh_move_corner_union_and_notch_display_follow_material(self):
        p = slab_frame()
        p.surface_supports = {"Floor": {"left": ["DY"], "bottom": ["DX"]}}
        coarse = resolved_supports(p, "Floor")
        self.assertIn({"DX", "DY"}, coarse.values())
        p.surfaces["Floor"].mesh_size = 30.
        p.surfaces["Floor"].origin = [12., 144., 36.]
        self.assertGreater(len(resolved_supports(p, "Floor")), len(coarse))
        # An opening touching the left boundary leaves a notch, not a supported
        # imaginary bridge across missing material or a restrained opening rim.
        mesh = p.surfaces["Floor"]
        mesh.openings = [dict(name="Notch", x_left=0., y_bott=60., width=60., height=60.)]
        p.validate()
        segments = support_segments(p, "Floor")[0]["segments"]
        self.assertTrue(segments)
        for a, b in segments:
            self.assertFalse(96. < (a[2]+b[2])/2 < 156.)
        points = surface_geometry(mesh)[2]
        for index, dofs in resolved_supports(p, "Floor").items():
            if "DY" in dofs:
                self.assertEqual(points[index][0], 12.)

    def test_shared_joint_union_and_spring_conflict_are_not_silent(self):
        p = slab_frame()
        p.surface_supports = {"Floor": {"left": ["DY", "RZ"]}}
        p.nodes["N2"].support = "custom"
        p.nodes["N2"].restraint_x = True
        p.nodes["N2"].spring_y = 10.
        # N2 is a floor corner in the space-frame example.
        with self.assertRaisesRegex(ValueError, "spring"):
            validate_coupled_topology(p)
        p.nodes["N2"].spring_y = 0.
        from test_coupled_surfaces import frame_solver
        model = frame_solver(p)
        before = p.to_dict()
        attach_surfaces(p, model)
        self.assertTrue(model.nodes["N2"].support_DX)
        self.assertTrue(model.nodes["N2"].support_DY)
        self.assertTrue(model.nodes["N2"].support_RZ)
        self.assertEqual(p.to_dict(), before)


class SurfaceRecoveryTests(unittest.TestCase):
    def test_independent_uniform_membrane_and_curvature_in_every_plane(self):
        for plane in PLANE_AXES:
            p = SpatialProject(surfaces={"Patch": MeshDefinition(name="Patch", plane=plane,
                origin=[19., -7., 41.], parameters={"width": 12., "height": 9.}, mesh_size=20., thickness=.8)})
            model = FEModel3D()
            attach_surfaces(p, model)
            model.add_load_combo("Patch", {})
            quad = next(iter(model.quads.values()))
            quad.ke()  # Public stiffness call initializes the element's local coordinates.
            axes = quad.T()[:3, :3]
            origin = np.array((quad.i_node.X, quad.i_node.Y, quad.i_node.Z))
            ex, ey, gamma = 2e-5, -1e-5, 3e-5
            kx, ky, kxy = 2e-4, -3e-4, 1e-4
            for node in model.nodes.values():
                x, y, _ = axes @ (np.array((node.X, node.Y, node.Z))-origin)
                displacement = axes.T @ np.array((ex*x+gamma*y, ey*y, -.5*kx*x*x-.5*ky*y*y-kxy*x*y))
                rotation = axes.T @ np.array((-ky*y-kxy*x, kx*x+kxy*y, -gamma/2))
                for key, value in zip(DOFS, (*displacement, *rotation)):
                    getattr(node, key)["Patch"] = float(value)
                for key in ("RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ"):
                    getattr(node, key)["Patch"] = 0.
            r = AnalysisResult.from_solver(model, "Patch", spatial=True)
            material, t = p.surfaces["Patch"].material, .8
            E, nu = material.E, material.nu
            expected_stress = E/(1-nu*nu)*np.array((ex+nu*ey, ey+nu*ex, (1-nu)*gamma/2))
            D = E*t**3/(12*(1-nu*nu))
            expected_moment = D*np.array((kx+nu*ky, ky+nu*kx, (1-nu)*kxy))
            for xi, eta in ((0., 0.), (.6, -.4), (-1., 1.)):
                row = inspect_surface(r, "Patch", quad.name, xi, eta)
                np.testing.assert_allclose([row[k] for k in ("Sx", "Sy", "Txy")], expected_stress, rtol=1e-12)
                np.testing.assert_allclose([row[k] for k in ("Mx", "My", "Mxy")], expected_moment, rtol=1e-11, atol=1e-12)
            for xi, eta in ((True, 0.), (0., float("nan")), (1.001, 0.)):
                with self.assertRaises(ValueError):
                    inspect_surface(r, "Patch", quad.name, xi, eta)
            with self.assertRaises(ValueError):
                inspect_surface(r, "missing", quad.name)

    def test_coupled_edge_supported_navier_moments_and_refinement(self):
        errors, deflections = [], []
        for size in (30., 15., 7.5):
            p = supported_plate(size)
            r = quiet_solve(p)
            rows = centre_results(r, "Plate")
            points = np.array([row["position"] for row in rows])[:, :2] - np.array((17., -31.))
            mesh = p.surfaces["Plate"]
            D = mesh.material.E/(12*(1-mesh.material.nu**2))
            _, moments, _ = navier(points, 120., 120., mesh.material.nu, -.001, D)
            select = np.all((points > 20.) & (points < 100.), axis=1)
            calculated = np.array([[row[key] for key in FIELDS] for row in rows])
            errors.append(np.linalg.norm(calculated[select, :3]-moments[select], axis=0)/np.linalg.norm(moments[select], axis=0))
            peak = min(values[2] for values in r.displacements.values())
            classical = -.00406235*.001*120**4/D
            deflections.append(abs(peak/classical-1))
            self.assertTrue(check_equilibrium(p, r).passed)
            self.assertAlmostEqual(sum(v[2] for v in r.reactions.values()), 14.4, places=7)
        self.assertTrue(np.all(errors[2] < errors[1]))
        self.assertLess(np.linalg.norm(errors[1]), np.linalg.norm(errors[0]))
        self.assertLess(max(errors[2]), .025)
        self.assertLess(deflections[2], .005)
        self.assertLess(deflections[2], deflections[1])

    def test_snapshot_combinations_axes_units_and_generated_support_reactions(self):
        reference = None
        for plane in PLANE_AXES:
            p = supported_plate(30., plane)
            p.set_combination("Reversed", {"Case 1": -2.})
            r = quiet_solve(p)
            base = centre_results(r, "Plate")
            reverse = centre_results(r.for_combination("Reversed"), "Plate")
            for a, b in zip(base, reverse):
                np.testing.assert_allclose([b[k] for k in FIELDS], [-2*a[k] for k in FIELDS], atol=1e-10)
            if reference is not None:
                np.testing.assert_allclose([[row[k] for k in FIELDS] for row in base], reference, atol=2e-6)
            reference = [[row[k] for k in FIELDS] for row in base]
            normal = PLANE_AXES[plane][2]
            self.assertTrue(any(name.startswith("__S") and abs(values[normal]) > .1 for name, values in r.reactions.items()))
            for units in ("si", "si_mm", "imperial_ft"):
                p.unit_system = units
                headers, rows = surface_table(p, r, "Plate")
                self.assertIn(UNIT_SYSTEMS[units].stress, headers[7])
                self.assertAlmostEqual(rows[0][4], base[0]["Mx"]*p.units.force_factor)
                self.assertAlmostEqual(rows[0][7], base[0]["Sx"]*p.units.stress_factor)
            p.surface_supports.clear()
            # Edge restraints were the only real supports; drilling cannot help.
            with self.assertRaisesRegex(ValueError, "rigid body"):
                quiet_solve(p)


if __name__ == "__main__":
    unittest.main()
