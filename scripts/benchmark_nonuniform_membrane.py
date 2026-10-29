"""Reproduce two bounded, traction-solved nonuniform flat-membrane checks."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tests"))
from coupled_validation import AXES, FACTORS, quiet_solve
from nonuniform_validation import nonuniform_patch, metrics


ERRORS = ("displacement_relative_l2", "stress_relative_l2", "energy_relative_error")


def benchmark():
    records = []
    for kind in ("bending", "mixed"):
        for plane in AXES:
            for size in (40., 20., 10., 5.):
                project = nonuniform_patch(kind, size, plane)
                result = quiet_solve(project)
                for combination in FACTORS:
                    records.append(dict(field=kind, plane=plane, mesh_size_in=size,
                        combination=combination,
                        **metrics(project, result.for_combination(combination), kind)))
    balanced = all(row["equilibrium_passed"] and row["max_reaction"] < 1e-9
        and row["max_normal_displacement_in"] < 1e-12
        and row["max_drilling_rotation_rad"] < 1e-12 for row in records)
    zero = all(row["max_displacement_in"] < 1e-12 and row["max_stress_ksi"] < 1e-12
        and abs(row["strain_energy"]) < 1e-15
        for row in records if row["combination"] == "Zero")
    converged = True
    for kind in ("bending", "mixed"):
        for plane in AXES:
            for combination in ("Service", "Reverse"):
                rows = [row for row in records if row["field"] == kind
                    and row["plane"] == plane and row["combination"] == combination]
                converged &= all(all(a[key] > b[key] for a, b in zip(rows, rows[1:])) for key in ERRORS)
                converged &= all(rows[-1][key] < limit for key, limit in zip(ERRORS, (.005, .04, .002)))
    return dict(checks_passed=bool(balanced and zero and converged),
        python=platform.python_version(), pynite=importlib.metadata.version("pynitefea"),
        brecon=importlib.metadata.version("brecon"),
        scope="Two flat isotropic 120 x 80 x 0.8 in rectangles, E=3600 ksi, nu=0.2. Independent zero-body-force Airy fields, consistent edge tractions, three in-plane rigid-mode restraints and shell-normal edge supports. No solved displacement is prescribed. Four meshes in XY/XZ/YZ; Service, -2 Reverse and Zero combinations.",
        reference="tests/nonuniform_reference.py; Airy method: https://solidmechanics.org/Text/Chapter5_2/Chapter5_2.htm",
        errors="Domain-integrated relative L2 displacement and symmetric stress-tensor Frobenius norms at nine Gauss points per element; strain energy is external work/2 against the closed-form reference. Zero combinations report absolute errors.",
        limits="Finest-mesh relative errors: displacement <0.5%, stress <4%, energy <0.2%, all monotonically decreasing. Every solve must pass unchanged six-component global equilibrium. This does not validate general diaphragms/walls, corner stress peaks, drilling rotations or frame-to-shell rotational interfaces.",
        records=records)


def plot(data, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullLocator
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.7), layout="constrained")
    for ax, kind, title in zip(axes, ("bending", "mixed"),
                               ("Pure in-plane bending", "Mixed normal and shear stress")):
        rows = [row for row in data["records"] if row["field"] == kind
            and row["plane"] == "XY" and row["combination"] == "Service"]
        for key, label, colour in zip(ERRORS,
                ("Displacement L2", "Stress tensor L2", "Strain energy"),
                ("#207b70", "#b85427", "#455e9e")):
            ax.plot([row["elements"] for row in rows], [100*row[key] for row in rows],
                "o-", label=label, color=colour)
        ax.set(title=title, xlabel="Quad elements", ylabel="Relative error (%)",
               xscale="log", yscale="log")
        ax.set_xticks([6, 24, 96, 384], labels=["6", "24", "96", "384"])
        ax.xaxis.set_minor_locator(NullLocator())
        ax.grid(alpha=.2)
        ax.legend(frameon=False, fontsize=9)
    fig.suptitle("Brecon: nonuniform edge-traction membrane convergence", fontsize=13)
    fig.supxlabel("XY / Service shown; XZ, YZ and signed/zero cases also checked. Drilling and rotational interfaces remain unvalidated.", fontsize=8.5)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--figure", type=Path, help="Optional convergence figure (PNG/PDF).")
    options = parser.parse_args()
    data = benchmark()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(data, indent=2)+"\n")
    if options.figure:
        plot(data, options.figure)
    print(json.dumps(dict(output=str(options.output), checks_passed=data["checks_passed"],
        fine_xy_service=[row for row in data["records"] if row["mesh_size_in"] == 5.
            and row["plane"] == "XY" and row["combination"] == "Service"]), indent=2))
    if not data["checks_passed"]:
        raise SystemExit("Nonuniform membrane validation failed; inspect the report before accepting results.")
