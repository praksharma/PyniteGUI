"""Snapshot isolation, bounded memory and solver-call regressions for 3D sampling."""
import contextlib
import io
import pickle
import unittest
from unittest.mock import patch

import numpy as np

from pynitegui.qt.analysis import analyze
from pynitegui.qt.examples import example_project
from pynitegui.qt.spatial_results import SampleCache, sampled_member


class SpatialSampleCacheTests(unittest.TestCase):
    def setUp(self):
        self.project = example_project("3d_cantilever")
        self.project.combinations["Double"] = {case: 2 * factor for case, factor in
                                               next(iter(self.project.combinations.values())).items()}
        with contextlib.redirect_stdout(io.StringIO()):
            self.result = analyze(self.project)

    def test_repeated_reads_reuse_readonly_canonical_arrays(self):
        from pynitegui.qt import spatial_results
        with patch.object(spatial_results, "_sample_member", wraps=spatial_results._sample_member) as sample:
            original = sampled_member(self.project, self.result, "M1")
            self.project.unit_system = "si"
            again = sampled_member(self.project, self.result, "M1")
            self.assertIs(original, again)
            self.assertEqual(sample.call_count, 1)
            for array in again:
                self.assertFalse(array.flags.writeable)
                with self.assertRaises(ValueError):
                    array.flat[0] = 123

    def test_combination_views_share_storage_but_not_values(self):
        names = list(self.project.combinations)
        self.assertGreaterEqual(len(names), 2)
        first = sampled_member(self.project, self.result.for_combination(names[0]), "M1")
        second = sampled_member(self.project, self.result.for_combination(names[1]), "M1")
        self.assertIsNot(first, second)
        self.assertFalse(np.allclose(first[1], second[1]))
        self.assertIs(first, sampled_member(self.project, self.result.for_combination(names[0]), "M1"))

    def test_new_analysis_never_reuses_previous_snapshot(self):
        first = sampled_member(self.project, self.result, "M1")
        with contextlib.redirect_stdout(io.StringIO()):
            other = analyze(self.project)
        second = sampled_member(self.project, other, "M1")
        self.assertIsNot(first, second)
        for a, b in zip(first, second):
            np.testing.assert_allclose(a, b)

    def test_sampling_boundaries_are_part_of_cache_identity(self):
        first = sampled_member(self.project, self.result, "M1")
        load = next(load for load in self.project.loads.values() if load.target == "M1")
        load.position = .37
        second = sampled_member(self.project, self.result, "M1")
        self.assertIsNot(first, second)
        self.assertTrue(np.any(np.isclose(second[0], .37 * self.result.solver.members["M1"].L())))

    def test_memory_budget_evicts_least_recent_and_skips_oversize(self):
        cache = SampleCache(limit=48)
        sample = lambda: tuple(np.zeros(1) for _ in range(3))
        first, second, third = sample(), sample(), sample()
        cache.put("first", first)
        cache.put("second", second)
        self.assertIs(cache.get("first"), first)
        cache.put("third", third)
        self.assertIsNone(cache.get("second"))
        self.assertEqual(cache.bytes, 48)
        cache.put("first", sample())
        self.assertEqual(cache.bytes, 48)
        cache.put("oversize", (np.zeros(100),))
        self.assertIsNone(cache.get("oversize"))
        self.assertEqual(cache.bytes, 48)

    def test_solver_serialization_drops_cache_and_can_resample(self):
        first = sampled_member(self.project, self.result, "M1")
        restored = pickle.loads(pickle.dumps(self.result))
        self.assertEqual(restored.solver._pynitegui_samples.bytes, 0)
        second = sampled_member(self.project, restored, "M1")
        for a, b in zip(first, second):
            np.testing.assert_allclose(a, b)


if __name__ == "__main__":
    unittest.main()
