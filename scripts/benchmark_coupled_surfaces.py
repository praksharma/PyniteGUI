"""Reproduce bounded coupled-plate, membrane, interface and drilling checks."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tests"))
from plate_reference import navier
from test_surface_results import supported_plate, quiet_solve
from pynitegui.qt.surface_results import centre_results
from pynitegui.qt.equilibrium import check_equilibrium
from coupled_validation import (AXES, membrane_patch, membrane_metrics, beam_strip,
    strip_metrics, drilling_project, drilling_metrics)


def validation_benchmarks():
    membrane, interfaces, drilling = [], [], []
    for plane in AXES:
        for size in (40., 20., 10.):
            project = membrane_patch(size, plane)
            result = quiet_solve(project)
            for combination in project.combinations:
                membrane.append(dict(plane=plane, mesh_size_in=size, combination=combination,
                    **membrane_metrics(project, result.for_combination(combination))))
    for ratio in (.25, 1., 4.):
        for size in (30., 15., 7.5):
            project = beam_strip(size, ratio)
            result = quiet_solve(project)
            for combination in project.combinations:
                interfaces.append(dict(mesh_size_in=size, combination=combination,
                    **strip_metrics(project, result.for_combination(combination))))
    for size in (60., 30., 15.):
        drilling.append(dict(mesh_size_in=size, **drilling_metrics(drilling_project(size))))
    fine = [row for row in interfaces if row["mesh_size_in"] == 7.5]
    passed = (all(row["equilibrium_passed"] and row["max_displacement_error_in"] < 1e-10
                  and row["max_stress_error_ksi"] < 1e-9 for row in membrane)
              and all(row["equilibrium_passed"] for row in interfaces)
              and all(row["field_error_relative_to_peak"] < .002 and row["beam_moment_relative_error"] < .005
                      and row["slab_moment_relative_l2"] < .003 for row in fine)
              and all(row["production_rejected"] and not row["raw_equilibrium_passed"] for row in drilling))
    return dict(checks_passed=passed,
        membrane_scope="Applied constant edge tractions on a 120 x 80 x 0.8 in rectangle. Three rigid-mode restraints; out-of-plane bending edge supports. Exact affine plane stress; no prescribed displacements. Signed/zero combinations in XY/XZ/YZ. Does not validate general walls or nonuniform membrane loads.",
        interface_scope="240 x 12 x 0.6 in nu=0 slender strip with a coincident axial beam, simply supported ends, positive shell-normal pressure or equivalent negative-global-Y member line load. Independent EI-sum narrow-strip limit; stiffness ratios 0.25/1/4; no eccentric/composite offsets.",
        drilling_scope="Diagnostic raw-engine lateral frame/slab solves, never accepted application results. Compare six-component external equilibrium with summed weak local drilling torque and separately confirm production rejection. No stiffness or equilibrium tolerance changes.",
        membrane_records=membrane, interface_records=interfaces, drilling_records=drilling)


def plot_validation(data, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullLocator
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), layout="constrained")
    records = data["validation"]["interface_records"]
    for ratio, colour in ((.25, "#207b70"), (1., "#b85427"), (4., "#455e9e")):
        for ax, case, key in ((axes[0], "Pressure", "field_error_relative_to_peak"),
                              (axes[1], "Beam", "beam_moment_relative_error")):
            rows = [row for row in records if np.isclose(row["stiffness_ratio"], ratio) and row["combination"] == case]
            ax.plot([row["beam_segments"] for row in rows], [100*row[key] for row in rows],
                    "o-", color=colour, label=f"Beam/slab EI = {ratio:g}")
    axes[0].set(title="Pressure → beam + slab", ylabel="Displacement-field error / reference peak (%)")
    axes[1].set(title="Member load → beam + slab", ylabel="Beam midspan moment error (%)")
    for ax in axes[:2]:
        ax.set(xlabel="Beam segments", xscale="log", yscale="log")
        ax.set_xticks([8, 16, 32], labels=["8", "16", "32"])
        ax.legend(frameon=False, fontsize=8)
    rows = data["validation"]["drilling_records"]
    axes[2].plot([row["elements"] for row in rows], [abs(row["residuals"]["MY"]) for row in rows],
                 "o-", color="#a73c40", label="External moment residual")
    axes[2].plot([row["elements"] for row in rows], [row["limits"]["MY"] for row in rows],
                 "--", color="#303a40", label="Existing acceptance limit")
    axes[2].set(title="Lateral drilling case: rejected", xlabel="Slab elements", ylabel="Global MY (kip-in)",
                xscale="log", yscale="log")
    axes[2].set_xticks([12, 48, 192], labels=["12", "48", "192"])
    axes[2].legend(frameon=False, fontsize=8)
    for ax in axes:
        ax.xaxis.set_minor_locator(NullLocator())
        ax.grid(alpha=.2)
    fig.suptitle("Brecon coupled surfaces: bounded load-transfer validation", fontsize=13)
    fig.supxlabel("Flat coincident nu=0 strip limit only; no offsets or shear certification. Lateral refinement does not cure weak drilling.", fontsize=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def benchmark():
    rows = []
    for size in (30., 15., 7.5):
        project = supported_plate(size)
        result = quiet_solve(project)
        records = centre_results(result, "Plate")
        points = np.array([row["position"][:2] for row in records])-np.array((17., -31.))
        mesh = project.surfaces["Plate"]
        D = mesh.material.E*mesh.thickness**3/(12*(1-mesh.material.nu**2))
        _, moments, shears = navier(points, 120., 120., mesh.material.nu, -.001, D)
        select = np.all((points > 20.) & (points < 100.), axis=1)
        calculated = np.array([[row[key] for key in ("Mx", "My", "Mxy")] for row in records])
        # These raw engine values are diagnostic evidence only; production
        # output deliberately withholds them rather than implying validation.
        raw = np.array([result.solver.quads[row["element"]].shear(combo_name=result.combination).ravel() for row in records])
        def relative(values, expected):
            return (np.linalg.norm((values-expected)[select], axis=0)/np.linalg.norm(expected[select], axis=0)).tolist()
        classical = -.00406235*.001*120**4/D
        peak = min(row[2] for row in result.displacements.values())
        rows.append(dict(mesh_size_in=size, elements=len(records),
                         moment_relative_l2=relative(calculated, moments),
                         raw_unvalidated_quad_shear_relative_l2=relative(raw, shears),
                         peak_deflection_relative_error=abs(peak/classical-1),
                         equilibrium_passed=check_equilibrium(project, result).passed))
    return dict(pynite=importlib.metadata.version("pynitefea"), brecon=importlib.metadata.version("brecon"),
                scope="One thin, simply supported isotropic square; negligible-stiffness boundary beam retained. Interior element centres only; no corner stress certification.",
                fields="Moment components Mx/My/Mxy; raw Qx/Qy included solely to document the withheld recovery.",
                records=rows, validation=validation_benchmarks())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--figure", type=Path, help="Optional scientific summary figure (PNG/PDF).")
    options = parser.parse_args()
    data = benchmark()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(data, indent=2)+"\n")
    if options.figure:
        plot_validation(data, options.figure)
    print(json.dumps(dict(output=str(options.output), checks_passed=data["validation"]["checks_passed"],
        maximum_membrane_stress_error_ksi=max(row["max_stress_error_ksi"] for row in data["validation"]["membrane_records"]),
        fine_interfaces=[row for row in data["validation"]["interface_records"] if row["mesh_size_in"] == 7.5],
        drilling=data["validation"]["drilling_records"]), indent=2))
    if not data["validation"]["checks_passed"]:
        raise SystemExit("A bounded validation check failed; inspect the report before accepting results.")
