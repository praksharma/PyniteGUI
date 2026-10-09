"""PyNite generator, option, topology, migration and analysis contracts."""
from dataclasses import replace
import copy
import math
import unittest

import numpy as np

from pynitegui.qt.mesh_model import (GENERATORS, RECT_FAMILIES, MeshDefinition,
    generate_mesh, mesh_export, mesh_geometry, mesh_quality)
from pynitegui.qt.plate_model import PlateDefinition, analyze_plate, build_plate


class MeshModelTests(unittest.TestCase):
    def test_every_generator_all_axes_and_repeatability(self):
        for generator, (_, parameters) in GENERATORS.items():
            for axis in "XYZ":
                with self.subTest(generator=generator, axis=axis):
                    definition = MeshDefinition(generator=generator, parameters=dict(parameters), axis=axis)
                    before = definition.to_dict()
                    first, second = generate_mesh(definition), generate_mesh(definition)
                    self.assertEqual(mesh_export(definition, first), mesh_export(definition, second))
                    self.assertEqual(definition.to_dict(), before)
                    self.assertGreater(mesh_quality(first)["elements"], 0)
                    self.assertEqual(len(first.quads)+len(first.plates), len(first.meshes["Surface"].elements))

    def test_translation_numbering_modifiers_and_rect_families(self):
        for generator, (_, parameters) in GENERATORS.items():
            for family in (("Quad", "Rect") if generator in RECT_FAMILIES else ("Quad",)):
                with self.subTest(generator=generator, family=family):
                    definition = MeshDefinition(generator=generator, parameters=dict(parameters), element_type=family)
                    baseline = generate_mesh(definition)
                    moved = replace(definition, origin=[123., -47., 81.], kx_mod=.35, ky_mod=.7, node_start=25, element_start=50)
                    model = generate_mesh(moved)
                    names, elements, points, cells = mesh_geometry(model)
                    np.testing.assert_allclose(points, mesh_geometry(baseline)[2]+moved.origin, atol=1e-10)
                    self.assertEqual(names[0], "N25")
                    self.assertEqual(elements[0], ("R" if family == "Rect" else "Q")+"50")
                    for element in model.meshes["Surface"].elements.values():
                        self.assertEqual((element.kx_mod, element.ky_mod), (.35, .7))
                        self.assertTrue(all(model.nodes[node.name] is node for node in (
                            element.i_node, element.j_node, element.m_node, element.n_node)))

    def test_rectangle_control_lines_and_openings(self):
        opening = {"name": "Hole", "x_left": 30., "y_bott": 40., "width": 20., "height": 30.}
        definition = MeshDefinition(x_control=[17., 83.], y_control=[21.], openings=[opening])
        model = generate_mesh(definition)
        _, _, points, cells = mesh_geometry(model)
        self.assertTrue(np.any(np.isclose(points[:, 0], 17)))
        self.assertTrue(np.any(np.isclose(points[:, 0], 83)))
        centre = points[cells].mean(axis=1)
        self.assertFalse(np.any((centre[:, 0] > 30)&(centre[:, 0] < 50)&(centre[:, 1] > 40)&(centre[:, 1] < 70)))
        poly = points[cells]
        area = sum(abs(np.cross(cell[1]-cell[0], cell[3]-cell[0])[2]) for cell in poly)
        self.assertAlmostEqual(area, 120*120-20*30)
        self.assertEqual(len(set(cells.ravel())), len(points))

    def test_circumferential_and_transition_counts(self):
        for kind, count, key, expected in (("annulus_ring", 12, "num_quads", 12),
                ("annulus_transition", 12, "num_inner_quads", 48),
                ("cylinder_ring", 12, "num_elements", 12), ("cylinder", 12, "num_elements", 96)):
            parameters = {**GENERATORS[kind][1], key: count}
            model = generate_mesh(MeshDefinition(generator=kind, parameters=parameters))
            self.assertEqual(len(model.meshes["Surface"].elements), expected)

    def test_roundtrip_strict_schema_and_invalid_options(self):
        definition = MeshDefinition()
        self.assertEqual(MeshDefinition.from_dict(definition.to_dict()), definition)
        for overrides in ({"version": 2}, {"version": True}, {"arbitrary": 1}, {"units": "m-N"}):
            with self.assertRaises(ValueError):
                MeshDefinition.from_dict({**definition.to_dict(), **overrides})
        for overrides in ({"mesh_size": 0}, {"mesh_size": math.nan}, {"mesh_size": .00001},
                {"origin": [1, 2]}, {"origin": [1, math.inf, 3]}, {"node_start": True},
                {"kx_mod": 0}, {"plane": "YX"}, {"parameters": {"width": 1}},
                {"x_control": [-1]}, {"x_control": [120]}, {"generator": "triangles"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                replace(definition, **overrides).validate()
        for kind in ("annulus", "frustum"):
            with self.assertRaisesRegex(ValueError, "too large"):
                replace(definition, generator=kind, parameters=dict(GENERATORS[kind][1]), mesh_size=1000).validate()
        with self.assertRaises(ValueError):
            MeshDefinition(generator="annulus", parameters=dict(GENERATORS["annulus"][1]), element_type="Rect").validate()

    def test_invalid_openings_and_bounded_controls(self):
        hole = {"name": "Hole", "x_left": 30., "y_bott": 30., "width": 15., "height": 15.}
        for holes in ([{**hole, "width": -1}], [{**hole, "x_left": 119}], [hole, hole],
                      [hole, {**hole, "name": "Touch", "x_left": 45}],
                      [{**hole, "x_left": 0, "width": 120}]):
            with self.assertRaises(ValueError):
                MeshDefinition(openings=holes).validate()
        with self.assertRaises(ValueError):
            MeshDefinition(x_control=list(range(1, 34))).validate()
        with self.assertRaises(ValueError):
            MeshDefinition(generator="cylinder", parameters={"radius": 60, "height": 120, "num_elements": 1000}).validate()

    def test_old_plate_migration_and_new_options_roundtrip(self):
        definition = PlateDefinition()
        old = definition.to_dict()
        for key in ("element_type", "origin", "x_control", "y_control", "openings", "kx_mod", "ky_mod", "node_start", "element_start", "mesh_name"):
            old.pop(key)
        old["version"] = 1
        self.assertEqual(PlateDefinition.from_dict(old), definition)
        for key in ("version", "format", "width"):
            broken = copy.deepcopy(old)
            broken.pop(key)
            with self.assertRaises(ValueError):
                PlateDefinition.from_dict(broken)

    def test_rectangular_polynomial_navier_and_opening_equilibrium(self):
        quad = analyze_plate(PlateDefinition(mesh_size=15))
        rectangle = analyze_plate(PlateDefinition(element_type="Rect", mesh_size=15, origin=[14, -9, 11]))
        self.assertAlmostEqual(min(rectangle["displacement"])/min(quad["displacement"]), 1, delta=.025)
        hole = {"name": "Hole", "x_left": 30., "y_bott": 30., "width": 30., "height": 30.}
        for family in ("Quad", "Rect"):
            definition = PlateDefinition(element_type=family, openings=[hole], x_control=[80.], origin=[14., 25., -11.])
            result = analyze_plate(definition)
            self.assertAlmostEqual(result["applied"], definition.pressure*(120**2-30**2))
            self.assertAlmostEqual(result["reactions"].sum(), -result["applied"], places=8)
            self.assertEqual(PlateDefinition.from_dict(definition.to_dict()), definition)


if __name__ == "__main__":
    unittest.main()
