"""Reproduce the centred-opening benchmark and its independent Ritz reference."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tests"))
from plate_reference import OpeningRitz
from pynitegui.qt.plate_model import PlateDefinition, analyze_plate


def benchmark(output):
    output.mkdir(parents=True, exist_ok=True)
    reference = OpeningRitz(120, 120, .2, 40, 40, terms=13)
    lower = OpeningRitz(120, 120, .2, 40, 40, terms=11)
    probe, patch = [[40., 60.]], (0., 40., 0., 40.)
    records = []
    for family in ("Quad", "Rect"):
        for size in (20., 10., 5.):
            definition = PlateDefinition(element_type=family, mesh_size=size, pressure=-1e-7, thickness=.6,
                openings=[dict(name="Opening", x_left=40., y_bott=40., width=40., height=40.)])
            result = analyze_plate(definition)
            rigidity = definition.material.E*definition.thickness**3/(12*(1-definition.material.nu**2))
            index = np.flatnonzero(np.all(np.isclose(result["points"], probe[0]), axis=1))[0]
            polygons = result["points"][result["cells"]]
            centres = polygons.mean(axis=1)
            area = np.abs(np.sum(polygons[:, :, 0]*np.roll(polygons[:, :, 1], -1, axis=1)
                                 -polygons[:, :, 1]*np.roll(polygons[:, :, 0], -1, axis=1), axis=1))/2
            selected = (centres[:, 0] < 40) & (centres[:, 1] < 40)
            mean = np.average(result["moments"][selected], axis=0, weights=area[selected])
            expected_w = float(reference.displacement(probe)[0]*definition.pressure/rigidity)
            expected_m = reference.mean_moments(patch)*definition.pressure
            records.append(dict(family=family, mesh_size=size, elements=len(result["cells"]),
                displacement=float(result["displacement"][index]), displacement_reference=expected_w,
                mean_moments=mean.tolist(), moments_reference=expected_m.tolist(),
                displacement_relative_error=float(abs(result["displacement"][index]/expected_w-1)),
                moment_relative_errors=np.abs(mean/expected_m-1).tolist(), definition=definition.to_dict()))
    data = dict(units={"length": "in", "force": "kip", "moment_per_width": "kip-in/in"},
                pynite=importlib.metadata.version("pynitefea"), brecon=importlib.metadata.version("brecon"),
                probe=probe[0], moment_patch=patch, ritz_terms=13, ritz_condition=reference.condition,
                basis_displacement_change=float(abs(lower.displacement(probe)[0]/reference.displacement(probe)[0]-1)),
                basis_moment_change=np.abs(lower.mean_moments(patch)/reference.mean_moments(patch)-1).tolist(),
                scope="One thin simply supported square with one centred free square opening; patch means, no corner-peak certification",
                records=records)
    (output/"plate-recovery.json").write_text(json.dumps(data, indent=2)+"\n")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for family, colour, marker in (("Quad", "#207b70", "o"), ("Rect", "#b85427", "s")):
        rows = [row for row in records if row["family"] == family]
        count = [row["elements"] for row in rows]
        axes[0].plot(count, [row["displacement"]*1000 for row in rows], marker=marker, color=colour, label=family)
        axes[1].plot(count, [max(row["moment_relative_errors"])*100 for row in rows], marker=marker, color=colour, label=family)
    axes[0].axhline(expected_w*1000, color="#303a40", linestyle="--", label="Independent Ritz")
    axes[0].set(title="Deflection at opening-edge midpoint", ylabel="Normal displacement (0.001 in)")
    axes[1].set(title="Moment recovery on a material patch", ylabel="Largest component error vs Ritz (%)")
    for ax in axes:
        ax.set_xlabel("Plate elements")
        ax.set_xscale("log", base=2)
        ax.set_xticks([32, 128, 512], labels=["32", "128", "512"])
        ax.grid(alpha=.2)
        ax.legend(frameon=False)
    fig.suptitle("Brecon: independent centred-opening refinement check", fontsize=13)
    fig.savefig(output/"plate-recovery.png", dpi=160)
    plt.close(fig)
    print(json.dumps({"reference_basis_change": data["basis_moment_change"],
                      "finest": [{k: row[k] for k in ("family", "elements", "displacement_relative_error", "moment_relative_errors")}
                                 for row in records if row["mesh_size"] == 5.]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/brecon-plate-benchmarks"))
    benchmark(parser.parse_args().output)
