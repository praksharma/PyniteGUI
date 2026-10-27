"""Closed-form references for the adapted official beam examples."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNITEGUI_NO_WEBENGINE", "1")
import numpy as np

from pynitegui.qt.analysis import analyze
from pynitegui.qt.envelopes import envelope_rows, member_envelope
from pynitegui.qt.equilibrium import check_equilibrium
from pynitegui.qt.examples import example_project
from pynitegui.qt.model import Project
from pynitegui.qt.official_examples import SOURCES
from pynitegui.qt.units import UNIT_SYSTEMS


LENGTH, EI = 168., 29000.*150.


def solve(project):
    with contextlib.redirect_stdout(io.StringIO()):
        return analyze(project)


def point_deflection(x, station, force):
    """Simply supported Euler-Bernoulli beam; force and displacement +up."""
    a, b = station, LENGTH-station
    if x <= a:
        return force*b*x*(LENGTH**2-b**2-x**2)/(6*LENGTH*EI)
    return force*a*(LENGTH-x)*(LENGTH**2-a**2-(LENGTH-x)**2)/(6*LENGTH*EI)


def point_reactions(loads):
    return (-sum(force*(LENGTH-station)/LENGTH for station, force in loads),
            -sum(force*station/LENGTH for station, force in loads))


def point_moment(x, loads):
    # PyNite's local Mz sign is opposite the conventional sagging-positive sign.
    left, _ = point_reactions(loads)
    return -left*x-sum(force*max(0., x-station) for station, force in loads)


class OfficialBeamExampleTests(unittest.TestCase):
    def test_point_beam_matches_closed_form_for_both_factored_cases(self):
        project = example_project("official_beam_point")
        original = project.to_dict()
        result = solve(project)
        for combo, force in (("1.4D", -7.), ("1.2D+1.6L", -18.8)):
            selected = result.for_combination(combo)
            beam = selected.solver.members["M1"]
            self.assertTrue(check_equilibrium(project, selected).passed)
            for reaction in selected.reactions.values():
                np.testing.assert_allclose(reaction, (0., -force/2, 0.), atol=1e-10)
            for x in (0., 21., 84., 113., 168.):
                self.assertAlmostEqual(beam.deflection("dy", x, combo), point_deflection(x, 84., force), places=10)
                self.assertAlmostEqual(beam.moment("Mz", x, combo), point_moment(x, [(84., force)]), places=9)
            self.assertAlmostEqual(beam.min_moment("Mz", combo), force*LENGTH/4, places=9)
            # PyNite's extrema helper samples 100 stations and misses midspan;
            # the exact station responses above retain the tight formula check.
            self.assertAlmostEqual(beam.min_deflection("dy", combo)/(force*LENGTH**3/(48*EI)), 1., delta=2e-4)
        self.assertEqual(project.to_dict(), original)

    def test_uniform_beam_matches_closed_form_over_the_span(self):
        project = example_project("official_beam_uniform")
        result = solve(project)
        self.assertEqual(result.combination, "Combo 1")
        self.assertTrue(check_equilibrium(project, result).passed)
        force = -200./1000./12.
        beam = result.solver.members["M1"]
        for reaction in result.reactions.values():
            np.testing.assert_allclose(reaction, (0., 1.4, 0.), atol=1e-10)
        for x in np.linspace(0., LENGTH, 17):
            expected = force*x*(LENGTH**3-2*LENGTH*x*x+x**3)/(24*EI)
            self.assertAlmostEqual(beam.deflection("dy", x, "Combo 1"), expected, places=10)
            self.assertAlmostEqual(beam.moment("Mz", x, "Combo 1"), force*x*(LENGTH-x)/2, places=9)
        self.assertAlmostEqual(beam.deflection("dy", LENGTH/2, "Combo 1"), 5*force*LENGTH**4/(384*EI), places=10)

    def test_signed_envelope_loads_reactions_and_governing_moments(self):
        project = example_project("official_beam_envelope")
        self.assertEqual([load.case for load in project.loads.values()], ["D", "S", "L"])
        np.testing.assert_allclose([(load.magnitude, load.position*LENGTH) for load in project.loads.values()],
                                   [(5., 48.), (8., 108.), (-8., 144.)], atol=1e-12, rtol=0.)
        # Reference loads are specified independently of the example factory.
        loads_by_combo = {"1.4D": [(48., 7.)], "1.2D+1.6L": [(48., 6.), (144., -12.8)],
                          "1.2D+1.6S": [(48., 6.), (108., 12.8)]}
        result = solve(project)
        for combo, loads in loads_by_combo.items():
            selected = result.for_combination(combo)
            beam = selected.solver.members["M1"]
            self.assertTrue(check_equilibrium(project, selected).passed)
            expected = point_reactions(loads)
            np.testing.assert_allclose([selected.reactions[node][1] for node in ("N1", "N2")], expected, atol=1e-10)
            for x in (0., 31., 48., 84., 108., 144., 168.):
                self.assertAlmostEqual(beam.moment("Mz", x, combo), point_moment(x, loads), places=9)
                self.assertAlmostEqual(beam.deflection("dy", x, combo),
                                       sum(point_deflection(x, station, force) for station, force in loads), places=10)
        names = tuple(loads_by_combo)
        curve = member_envelope(project, result, names, "M1", "moment")
        expected = np.array([[point_moment(x, loads) for x in curve["x"]] for loads in loads_by_combo.values()])
        np.testing.assert_allclose(curve["minimum"], expected.min(axis=0), atol=1e-9)
        np.testing.assert_allclose(curve["maximum"], expected.max(axis=0), atol=1e-9)
        row = next(row for row in envelope_rows(project, result, names) if row[:3] == ("Member", "M1", "Mz"))
        self.assertAlmostEqual(row[4], -222.17142857142858, places=8)
        self.assertEqual(row[5], "1.2D+1.6L")
        self.assertAlmostEqual(row[6], 596.5714285714286, places=8)
        self.assertEqual(row[7], "1.2D+1.6S")

    def test_units_fresh_models_and_saved_models_retain_the_reference_response(self):
        with tempfile.TemporaryDirectory() as directory:
            for key in SOURCES:
                baseline = example_project(key).to_dict()
                for units in UNIT_SYSTEMS:
                    with self.subTest(key=key, units=units):
                        project = example_project(key, units)
                        self.assertEqual(project.to_dict(), {**baseline, "unit_system": units})
                        path = Path(directory)/f"{key}.pynite.json"
                        project.save(path)
                        restored = Project.from_dict(json.loads(path.read_text()))
                        self.assertEqual(restored.to_dict(), project.to_dict())
                        self.assertIsNone(restored.self_weight_case)
                        self.assertEqual(restored.nodes["N1"].restraints, (True, True, False))
                        self.assertEqual(restored.nodes["N2"].restraints, (True, True, False))
                        self.assertEqual((restored.E, restored.Iz), (29000., 150.))
                        result = solve(restored)
                        self.assertTrue(all(check_equilibrium(restored, result.for_combination(c)).passed for c in restored.combinations))
                        project.materials["Steel"].E = 1.
                        project.combinations[next(iter(project.combinations))].clear()
                        project.loads["L1"].magnitude = 99.
                        self.assertEqual(example_project(key).to_dict(), baseline)
