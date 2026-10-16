"""Frame-derived rectangle placement never assumes arbitrary polygon filling."""
import unittest

from pynitegui.qt.examples import example_project
from pynitegui.qt.mesh_model import MeshDefinition, generate_mesh, mesh_geometry
from pynitegui.qt.spatial_model import SpatialProject
from pynitegui.qt.surface_placement import frame_levels, selected_rectangle


def rectangle(plane="XZ", offset=144):
    axes = {"XY": (0, 1, 2), "XZ": (0, 2, 1), "YZ": (2, 1, 0)}[plane]
    points = []
    for a, b in ((-30, 10), (210, 10), (210, 190), (-30, 190)):
        point = [0., 0., 0.]
        point[axes[0]], point[axes[1]], point[axes[2]] = a, b, offset
        points.append(tuple(point))
    project = SpatialProject()
    for i in range(4):
        project.add_member(points[i], points[(i+1) % 4])
    return project


class SurfacePlacementTests(unittest.TestCase):
    def test_example_top_perimeter_and_corner_nodes_match_exactly(self):
        project = example_project("3d_space_frame")
        for selections in ([('members', f'M{i}') for i in range(5, 9)],
                           [('nodes', f'N{i}') for i in (2, 4, 6, 8)]):
            placement = selected_rectangle(project, selections)
            self.assertEqual(placement.plane, "XZ")
            self.assertEqual(placement.origin, (0, 144, 0))
            self.assertEqual((placement.width, placement.height), (240, 180))
            self.assertEqual(frame_levels(project), [placement])

    def test_all_planes_use_pynite_local_width_height_and_negative_origins(self):
        for plane in ("XY", "XZ", "YZ"):
            project = rectangle(plane)
            placement = selected_rectangle(project, [('members', name) for name in project.members])
            self.assertEqual(placement.plane, plane)
            recipe = placement.recipe(MeshDefinition())
            self.assertEqual(recipe.parameters, {"width": 240, "height": 180})
            _, _, points, _ = mesh_geometry(generate_mesh(recipe))
            self.assertEqual(set(map(tuple, points.min(axis=0, keepdims=True))), {placement.origin})
            for node in project.nodes.values():
                self.assertTrue(any(tuple(p) == node.coords for p in points))

    def test_split_perimeter_adds_control_lines_without_merging_nodes(self):
        project = rectangle()
        project.split_member("M1", .3)
        before = project.to_dict()
        placement = selected_rectangle(project, [('members', name) for name in project.members])
        self.assertEqual(placement.x_control, (72.,))
        recipe = placement.recipe(MeshDefinition())
        self.assertIn(72, recipe.x_control)
        self.assertEqual(project.to_dict(), before)

    def test_incomplete_diagonal_nonplanar_and_interior_selections_are_rejected(self):
        project = rectangle()
        for selections in ([], [('nodes', 'N1')], [('members', 'M1'), ('members', 'M2'), ('members', 'M3')],
                           [('surfaces', 'S1')], [('loads', 'L1')]):
            with self.subTest(selections=selections), self.assertRaises(ValueError):
                selected_rectangle(project, selections)
        project.add_member(project.nodes['N1'].coords, project.nodes['N3'].coords)
        with self.assertRaisesRegex(ValueError, "diagonals"):
            selected_rectangle(project, [('members', name) for name in project.members])
        project = rectangle()
        project.nodes['N3'].y += 2
        with self.assertRaisesRegex(ValueError, "plane"):
            selected_rectangle(project, [('nodes', name) for name in project.nodes])
        project = rectangle()
        project.node_at(100, 144, 100)
        with self.assertRaisesRegex(ValueError, "interior"):
            selected_rectangle(project, [('nodes', name) for name in project.nodes])

    def test_frame_levels_are_sorted_and_do_not_fill_an_open_or_l_shaped_outline(self):
        project = rectangle(offset=120)
        upper = rectangle(offset=240)
        for member in upper.members.values():
            project.add_member(upper.nodes[member.start].coords, upper.nodes[member.end].coords)
        self.assertEqual([p.origin[1] for p in frame_levels(project)], [240, 120])
        project.delete('members', 'M1')
        self.assertEqual([p.origin[1] for p in frame_levels(project)], [240])
        project = rectangle()
        project.nodes['N3'].x -= 40
        self.assertFalse(frame_levels(project))

    def test_existing_openings_material_and_size_are_preserved_or_rejected_atomically(self):
        placement = frame_levels(rectangle())[0]
        base = MeshDefinition(name="Floor", mesh_size=20, thickness=3,
                              openings=[dict(name="Hole", x_left=20, y_bott=20, width=30, height=40)])
        before = base.to_dict()
        fitted = placement.recipe(base)
        self.assertEqual(fitted.openings, base.openings)
        self.assertEqual(fitted.material, base.material)
        self.assertEqual((fitted.name, fitted.thickness, fitted.mesh_size), ("Floor", 3, 20))
        self.assertEqual(base.to_dict(), before)
        small = rectangle()
        for node in small.nodes.values():
            node.x *= .1
            node.z *= .1
        with self.assertRaises(ValueError):
            frame_levels(small)[0].recipe(base)
        self.assertEqual(base.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
