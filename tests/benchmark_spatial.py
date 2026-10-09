"""Optional repeatable canonical sampling benchmark; emits machine-readable timings."""
import contextlib
import io
import json
import platform
from time import perf_counter

from pynitegui.qt.analysis import analyze
from pynitegui.qt.spatial_model import SpatialLoad, SpatialProject
from pynitegui.qt.spatial_results import sampled_member


def benchmark(count):
    project = SpatialProject()
    for index in range(count):
        project.add_member((index * 12, 0, 0), ((index + 1) * 12, 0, 0))
    project.nodes["N1"].support = "fixed"
    project.loads["L1"] = SpatialLoad("L1", f"N{count + 1}", "FY", -1)
    start = perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        result = analyze(project)
    solve_seconds = perf_counter() - start
    def read():
        start = perf_counter()
        values = [sampled_member(project, result, name) for name in project.members]
        return perf_counter() - start, values
    cold, original = read()
    warm = []
    for _ in range(5):
        seconds, values = read()
        assert all(a is b for a, b in zip(original, values)), "Warm samples were recomputed"
        warm.append(seconds)
    return {"members": count, "solveSeconds": solve_seconds, "coldSeconds": cold,
            "warmSeconds": warm, "cacheBytes": result.solver._pynitegui_samples.bytes,
            "stations": sum(len(value[0]) for value in original)}


if __name__ == "__main__":
    print(json.dumps({"python": platform.python_version(), "platform": platform.platform(),
                      "models": [benchmark(count) for count in (10, 50, 100)]}, indent=2))
