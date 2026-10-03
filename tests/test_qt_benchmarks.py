"""Larger-model analytical references, equilibrium, and superposition benchmarks."""
import contextlib
import io
import math
import unittest

import numpy as np
from pynitegui.qt.analysis import analyze
from pynitegui.qt.model import Load, Material, Project, Section


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def building(support="fixed", stories=4):
    project = Project()
    project.set_load_case("Gravity", "Case 1")
    project.set_load_case("Wind")
    project.set_combination("Gravity", {"Gravity": 1}, "Service")
    project.set_combination("Wind", {"Wind": 1})
    project.set_combination("Factored", {"Gravity": 1.4, "Wind": 1.6})
    for floor in range(stories):
        for column in range(3):
            project.add_member((column * 240, floor * 120), (column * 240, (floor + 1) * 120))
        for bay in range(2):
            member = project.add_member((bay * 240, (floor + 1) * 120), ((bay + 1) * 240, (floor + 1) * 120))
            name = project.next_name("L", project.loads)
            project.loads[name] = Load(name, member, "FY", -0.01, 0, "distributed", -0.02, 1, "Gravity")
        node = next(node.name for node in project.nodes.values() if (node.x, node.y) == (0, (floor + 1) * 120))
        name = project.next_name("L", project.loads)
        project.loads[name] = Load(name, node, "FX", (floor + 1) * 0.2, case="Wind")
    for node in project.nodes.values():
        if node.y == 0:
            node.support = support
    roof = next(node.name for node in project.nodes.values() if (node.x, node.y) == (480, stories * 120))
    name = project.next_name("L", project.loads)
    project.loads[name] = Load(name, roof, "MZ", 5, case="Wind")
    return project


def applied_resultant(project, factors):
    fx = fy = moment = 0.0
    for load in project.loads.values():
        factor = factors.get(load.case, 0)
        if load.target in project.nodes:
            node = project.nodes[load.target]
            for direction, value in load.components(project):
                value *= factor
                fx += value if direction == "FX" else 0
                fy += value if direction == "FY" else 0
                moment += value if direction == "MZ" else node.x * value if direction == "FY" else -node.y * value
        else:
            member = project.members[load.target]
            a, b = project.nodes[member.start], project.nodes[member.end]
            length = math.hypot(b.x - a.x, b.y - a.y)
            for (direction, start), (_, end) in zip(load.components(project), load.components(project, load.end_magnitude)):
                force = (start + end) * length / 2 * factor
                first_moment = (start + 2 * end) * length**2 / 6 * factor
                if direction == "FX":
                    fx += force
                    moment -= a.y * force + (b.y - a.y) / length * first_moment
                else:
                    fy += force
                    moment += a.x * force + (b.x - a.x) / length * first_moment
    return np.array([fx, fy, moment])


class BenchmarkTests(unittest.TestCase):
    def test_twenty_segment_mixed_stiffness_column_against_integrated_beam(self):
        project = Project()
        project.set_material(Material("Other", 18000, 0.25, 0))
        project.set_section(Section("Other", 8, 10, 300, 0.4))
        segments, step, tip_force, wind, gravity = 20, 60, 0.05, 0.0001, 5
        height = segments * step
        dx = rz = dy = 0.0
        for i in range(segments):
            name = project.add_member((0, i * step), (0, (i + 1) * step))
            member = project.members[name]
            if i % 2:
                member.material = member.section = "Other"
            E = project.materials[member.material].E
            section = project.sections[member.section]
            a, b = i * step, (i + 1) * step
            dx += (tip_force * ((height - a)**3 - (height - b)**3) / 3 +
                   wind * ((height - a)**4 - (height - b)**4) / 8) / (E * section.Iz)
            rz -= (tip_force * ((height - a)**2 - (height - b)**2) / 2 +
                   wind * ((height - a)**3 - (height - b)**3) / 6) / (E * section.Iz)
            dy -= gravity * step / (E * section.A)
            project.loads[f"L{i + 1}"] = Load(f"L{i + 1}", name, "FX", wind, 0, "distributed", wind, 1)
        project.nodes["N1"].support = "fixed"
        project.loads["Tip X"] = Load("Tip X", "N21", "FX", tip_force)
        project.loads["Tip Y"] = Load("Tip Y", "N21", "FY", -gravity)
        result = solve(project)
        np.testing.assert_allclose(result.displacements["N21"], (dx, dy, rz), rtol=2e-7, atol=1e-10)
        np.testing.assert_allclose(result.reactions["N1"], (-tip_force - wind * height, gravity,
                                                         tip_force * height + wind * height**2 / 2), rtol=2e-7)

    def test_multistorey_equilibrium_and_superposition_with_varied_supports(self):
        for support in ("fixed", "pin", "mixed"):
            project = building("fixed" if support == "mixed" else support)
            if support == "mixed":
                for node in project.nodes.values():
                    if node.y == 0 and node.x:
                        node.support = "pin" if node.x == 240 else "roller"
                for member in project.members.values():
                    a, b = project.nodes[member.start], project.nodes[member.end]
                    if a.y == b.y:
                        member.release_end = True
            result = solve(project)
            with self.subTest(support=support):
                for combination, factors in project.combinations.items():
                    view = result.for_combination(combination)
                    reaction = np.zeros(3)
                    for name, (fx, fy, mz) in view.reactions.items():
                        node = project.nodes[name]
                        reaction += (fx, fy, mz + node.x * fy - node.y * fx)
                    np.testing.assert_allclose(reaction + applied_resultant(project, factors), 0, atol=2e-7)
                gravity = result.for_combination("Gravity")
                wind = result.for_combination("Wind")
                factored = result.for_combination("Factored")
                for name in project.nodes:
                    expected = 1.4 * np.array(gravity.displacements[name]) + 1.6 * np.array(wind.displacements[name])
                    np.testing.assert_allclose(factored.displacements[name], expected, rtol=1e-8, atol=1e-10)

    def test_multistorey_endpoint_reversal_preserves_physical_results(self):
        project = building()
        original = solve(project).for_combination("Factored")
        for member in project.members.values():
            member.start, member.end = member.end, member.start
        for load in project.loads.values():
            if load.kind == "distributed":
                load.magnitude, load.end_magnitude = load.end_magnitude, load.magnitude
        reversed_result = solve(project).for_combination("Factored")
        for name in project.nodes:
            np.testing.assert_allclose(original.displacements[name], reversed_result.displacements[name], rtol=1e-8, atol=1e-10)
            np.testing.assert_allclose(original.reactions[name], reversed_result.reactions[name], atol=1e-7)
