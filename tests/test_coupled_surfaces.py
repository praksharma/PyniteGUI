"""Independent load-transfer, conformity and rectangular plate benchmarks."""
import contextlib
import io
import unittest

import numpy as np
from Pynite import FEModel3D

from pynitegui.qt.mesh_model import MeshDefinition
from pynitegui.qt.spatial_examples import example_project
from pynitegui.qt.spatial_model import DOFS, SpatialProject
from pynitegui.qt.surface_solver import attach_surfaces
from pynitegui.qt.analysis import analyze
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.model import Project


def slab_frame(size=60.):
    project = example_project("3d_space_frame")
    project.loads.clear()
    project.surfaces["Floor"] = MeshDefinition(name="Floor", plane="XZ", origin=[0., 144., 0.],
        parameters={"width": 240., "height": 180.}, mesh_size=size, thickness=6.)
    project.surface_pressures = {"Floor": {"Gravity": .001}}
    project.surface_analysis_enabled = True
    return project


def frame_solver(project):
    model = FEModel3D()
    for material in project.materials.values():
        model.add_material(material.name, material.E, material.G, material.nu, material.rho)
    for section in project.sections.values():
        model.add_section(section.name, section.A, section.Iy, section.Iz, section.J)
    for node in project.nodes.values():
        model.add_node(node.name, *node.coords)
        model.def_support(node.name, **dict(zip(("support_"+dof for dof in DOFS), node.restraints)))
    for member in project.members.values():
        model.add_member(member.name, member.start, member.end, member.material, member.section)
    for name, factors in project.combinations.items():
        model.add_load_combo(name, dict(factors))
    return model


class CoupledAssemblyTests(unittest.TestCase):
    def solve(self, project):
        model = frame_solver(project)
        maps = attach_surfaces(project, model)
        with contextlib.redirect_stdout(io.StringIO()):
            model.analyze_linear(check_statics=True)
        return model, maps

    def test_slab_pressure_transfers_to_four_columns_and_segments_beams(self):
        project = slab_frame()
        model, maps = self.solve(project)
        self.assertEqual(len(model.quads), 12)
        self.assertEqual(len(model.nodes), 24)
        for node in project.nodes.values():
            if node.support == "fixed":
                self.assertAlmostEqual(model.nodes[node.name].RxnFY["Gravity"], 10.8, places=7)
        self.assertTrue(all(len(model.members[f"M{i}"].sub_members) > 1 for i in range(5, 9)))
        peak = min(model.nodes[name].DY["Gravity"] for name in maps["Floor"]["nodes"])
        self.assertLess(peak, 0)
        self.assertGreater(peak, -1)
        self.assertAlmostEqual(sum(n.RxnFY["Gravity"] for n in model.nodes.values()), 43.2, places=7)
        self.assertEqual(len(project.nodes), 8)

    def test_combinations_and_surface_self_weight(self):
        project = slab_frame()
        project.surfaces["Floor"].material.rho = .00009
        project.self_weight_case = "Gravity"
        project.set_combination("Double", {"Gravity": 2})
        model, _ = self.solve(project)
        expected = 240*180*(.001+.00009*6)
        self.assertAlmostEqual(sum(n.RxnFY["Gravity"] for n in model.nodes.values()), expected, places=7)
        self.assertAlmostEqual(sum(n.RxnFY["Double"] for n in model.nodes.values()), 2*expected, places=7)

    def test_conforming_adjacent_meshes_share_nodes_and_openings_remove_load(self):
        project = slab_frame()
        first = project.surfaces["Floor"]
        first.parameters["width"] = 120.
        other = MeshDefinition.from_dict(first.to_dict())
        other.name, other.origin = "Other", [120., 144., 0.]
        project.surfaces["Other"] = other
        project.surface_pressures["Other"] = {"Gravity": .001}
        model, maps = self.solve(project)
        self.assertEqual(len(set(maps["Floor"]["nodes"]) & set(maps["Other"]["nodes"])), 4)
        self.assertAlmostEqual(sum(n.RxnFY["Gravity"] for n in model.nodes.values()), 43.2, places=7)
        other.mesh_size = 30.
        with self.assertRaisesRegex(ValueError, "hanging|nonmatching"):
            attach_surfaces(project, frame_solver(project))
        project = slab_frame()
        project.surfaces["Floor"].openings = [{"name": "Hole", "x_left": 60., "y_bott": 60., "width": 60., "height": 60.}]
        model, _ = self.solve(project)
        self.assertAlmostEqual(sum(n.RxnFY["Gravity"] for n in model.nodes.values()), (240*180-60*60)*.001, places=7)

    def test_vertical_mesh_self_weight_and_normal_pressure_balance_independently(self):
        project = slab_frame()
        for node in project.nodes.values():
            node.y, node.z = node.z, node.y
        mesh = project.surfaces["Floor"]
        mesh.plane, mesh.origin = "XY", [0., 0., 144.]
        mesh.material.rho = .00009
        project.self_weight_case = "Gravity"
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(project)
        self.assertTrue(check_equilibrium(project, result).passed)
        self.assertAlmostEqual(sum(values[2] for values in result.reactions.values()), -43.2, places=7)

    def test_unstable_and_unsupported_production_models_fail(self):
        project = slab_frame()
        for node in project.nodes.values():
            node.support = "free"
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "unstable|singular|ill-conditioned|rigid body"):
            analyze(project)
        project = slab_frame()
        project.surfaces["Floor"].element_type = "Rect"
        with self.assertRaisesRegex(ValueError, "Quad"):
            analyze(project)
        project = slab_frame()
        project.members["M5"].kind = "truss"
        with self.assertRaisesRegex(ValueError, "split truss"):
            analyze(project)

    def test_lateral_drilling_imbalance_cannot_publish_coupled_results(self):
        from pynitegui.qt.spatial_model import SpatialLoad
        project = slab_frame(30.)
        project.loads["WindLoad"] = SpatialLoad("WindLoad", "N2", "FZ", 1.5, case="Wind")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "equilibrium failed.*Wind"):
            analyze(project)

    def test_drilling_penalty_cannot_stabilize_an_unrestrained_rigid_rotation(self):
        project = slab_frame()
        for node in project.nodes.values():
            if node.support == "fixed":
                node.support = "custom"
                node.restraint_y = True
        project.nodes["N1"].support = "pin"
        with self.assertRaisesRegex(ValueError, "rigid body"):
            analyze(project)

    def test_disconnected_nonmatching_and_unsupported_surfaces_fail(self):
        for change, message in ((lambda p: p.surfaces["Floor"].origin.__setitem__(1, 150.), "Disconnected"),
                                (lambda p: p.node_at(30., 144., 0.), "nonmatching"),
                                (lambda p: setattr(p.surfaces["Floor"], "element_type", "Rect"), "Quad")):
            project = slab_frame()
            change(project)
            with self.assertRaisesRegex(ValueError, message):
                attach_surfaces(project, frame_solver(project))

    def test_coplanar_overlap_and_hanging_mesh_interfaces_fail(self):
        for offset, message in (([0., 144., 0.], "duplicate"), ([30., 144., 0.], "hanging|nonmatching")):
            project = slab_frame()
            mesh = MeshDefinition.from_dict(project.surfaces["Floor"].to_dict())
            mesh.name, mesh.origin = "Other", offset
            project.surfaces["Other"] = mesh
            with self.assertRaisesRegex(ValueError, message):
                attach_surfaces(project, frame_solver(project))

    def test_simply_supported_square_matches_classical_thin_plate_deflection(self):
        project = SpatialProject()
        mesh = MeshDefinition(name="Plate", plane="XY", parameters={"width": 120., "height": 120.}, mesh_size=15., thickness=1.)
        project.surfaces["Plate"] = mesh
        project.surface_pressures = {"Plate": {"Case 1": -.001}}
        for x in np.linspace(0, 120, 9):
            for y in np.linspace(0, 120, 9):
                if x in (0, 120) or y in (0, 120):
                    name = project.node_at(float(x), float(y), 0.)
                    node = project.nodes[name]
                    node.support = "custom"
                    node.restraint_x = node.restraint_y = node.restraint_z = True
        model, maps = self.solve(project)
        peak = min(model.nodes[name].DZ["Service"] for name in maps["Plate"]["nodes"])
        rigidity = mesh.material.E*mesh.thickness**3/(12*(1-mesh.material.nu**2))
        classical = -.00406235*.001*120**4/rigidity
        self.assertAlmostEqual(peak/classical, 1., delta=.05)
        self.assertAlmostEqual(sum(n.RxnFZ["Service"] for n in model.nodes.values()), 14.4, places=7)

    def test_production_adapter_snapshots_equilibrium_and_units(self):
        project = slab_frame()
        project.surfaces["Floor"].material.rho = .00009
        project.self_weight_case = "Gravity"
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(project)
        self.assertTrue(check_equilibrium(project, result).passed)
        from pynitegui.qt.spatial_results import inspect_member, sampled_member
        left = inspect_member(project, result, "M5", 60., "left")
        right = inspect_member(project, result, "M5", 60., "right")
        self.assertGreater(abs(left[1]-right[1]), .001)
        stations, _, _ = sampled_member(project, result, "M5")
        self.assertEqual(np.count_nonzero(stations == 60.), 2)
        self.assertTrue(check_equilibrium(project, result.for_combination("Combined")).passed)
        self.assertGreater(len(result.displacements), len(project.nodes))
        self.assertEqual(project.to_dict(), Project.from_dict(project.to_dict()).to_dict())
        project.unit_system = "si"
        self.assertTrue(check_equilibrium(project, result).passed)

    def test_schema_pressure_case_rename_delete_and_geometry_migration(self):
        project = slab_frame()
        project.set_load_case("Dead", "Gravity")
        self.assertEqual(project.surface_pressures, {"Floor": {"Dead": .001}})
        with self.assertRaisesRegex(ValueError, "surface pressures"):
            project.delete_load_case("Dead")
        project.delete("surfaces", "Floor")
        self.assertFalse(project.surface_pressures)
        legacy = slab_frame().to_dict()
        legacy["version"] = 19
        legacy.pop("surface_analysis_enabled")
        legacy.pop("surface_pressures")
        migrated = Project.from_dict(legacy)
        self.assertFalse(migrated.surface_analysis_enabled)
        self.assertEqual(migrated.surface_pressures, {})
        legacy["surface_analysis_enabled"] = True
        with self.assertRaisesRegex(ValueError, "version 20"):
            Project.from_dict(legacy)
        for invalid in (None, 1, "true"):
            bad = slab_frame().to_dict()
            bad["surface_analysis_enabled"] = invalid
            with self.subTest(enabled=invalid), self.assertRaises(ValueError):
                Project.from_dict(bad)
        for invalid in (None, [], {"Missing": {}}, {"Floor": {"Gravity": float('nan')}}, {"Floor": {"Missing": 1}}):
            bad = slab_frame().to_dict()
            bad["surface_pressures"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                Project.from_dict(bad)


if __name__ == "__main__":
    unittest.main()
