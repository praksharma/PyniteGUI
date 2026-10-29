"""Reproduce bounded Quad shear research; no application output is enabled."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tests"))
from quad_shear_validation import CASES, METHODS, SIZES, metrics, solve_case


def benchmark():
    records = []
    for case in CASES:
        for plane in ("XY", "XZ", "YZ"):
            for size in SIZES:
                for combination, sample in solve_case(case, size, plane).items():
                    records.append(dict(case=case, plane=plane, mesh_size_in=size,
                        combination=combination, **metrics(sample)))
    checks = True
    for case in CASES:
        for plane in ("XY", "XZ", "YZ"):
            for combination in ("Service", "Reverse"):
                rows = [row for row in records if row["case"] == case and row["plane"] == plane
                        and row["combination"] == combination]
                if case.endswith("navier"):
                    errors = [row["patch_divergence"]["relative_l2"] for row in rows]
                    checks &= all(b < a for a, b in zip(errors, errors[1:])) and errors[-1] < .003
                    checks &= all(value < .003 for value in rows[-1]["patch_divergence"]["component_relative_l2"])
                else:
                    checks &= all(row[method]["relative_l2"] < 1e-6 for row in rows for method in METHODS)
    checks &= all(row[method]["max_absolute_error_kip_per_in"] < 1e-12
        for row in records if row["combination"] == "Zero" for method in METHODS)
    return dict(checks_passed=bool(checks), python=platform.python_version(),
        pynite=importlib.metadata.version("pynitefea"), brecon=importlib.metadata.version("brecon"),
        units={"length": "in", "pressure": "kip/in2", "shear": "kip/in"},
        scope="120 x 180 x 0.6 in isotropic rectangles; E=3600 ksi, pressure=-1e-7 kip/in2. Simply supported Navier plate and coupled slab (edge beam E=1e-6 ksi), plus nu=0 cantilevers clamped at x=0 or y=0. XY/XZ/YZ, three meshes, Service/-2 Reverse/Zero. Every combination passes the existing independent six-component equilibrium gate.",
        methods={"raw": "PyNite Quad3D.shear at the element centre, unchanged.",
            "element_divergence": "Qx=Mx,x+Mxy,y; Qy=Mxy,x+My,y, from the element's own bilinear recovered moment field.",
            "patch_divergence": "Same equilibrium derivatives, from a quadratic least-squares fit to centre moments of a complete 3 x 3 neighbouring-element patch, scaled by grid spacing. Test-only; incomplete patches return no value."},
        comparison="All methods use identical element centres, complete 3 x 3 patches and a fixed >20 in outer-boundary exclusion. Report vector/component relative L2 norms; zero references use absolute errors, not division by zero. No peak-error accuracy claim.",
        reference="Independent double-sine Kirchhoff Navier series in tests/plate_reference.py; truncation checked at 160 versus 320 terms. Cantilever cut equilibrium Q=q*(L-coordinate), with zero transverse component. References import neither application nor engine.",
        interpretation="checks_passed covers the bounded interior candidate's refinement/component limits, cantilever and zero-reference errors, and unchanged equilibrium gates. Independent reference-truncation, coordinate and signed-scaling checks are in test_quad_shear_validation. This does not approve raw shear, general recovery, engineering design or UI publication. Review each method's measured errors separately.",
        limitations="No boundary/extrapolated values, holes/notches, stiffness jumps, irregular meshes, thick plates, curved shells, shear peaks, frame rotational interfaces or drilling validation. The neighbouring-centre fit smooths across elements and is not the existing unsmoothed point probe. Quad Qx/Qy remain unavailable in production snapshots, probes, CSV and MCP.",
        records=records)


def plot(data, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullLocator
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.7), layout="constrained")
    for ax, case, title in zip(axes, ("plate_navier", "coupled_navier"),
            ("Separate plate", "Coupled slab / negligible-stiffness edge beam")):
        rows = [row for row in data["records"] if row["case"] == case
                and row["plane"] == "XY" and row["combination"] == "Service"]
        for method, label, colour in zip(METHODS,
                ("Raw Quad shear", "Own-element moment derivative", "Neighbouring-centre fit (research)"),
                ("#b85427", "#455e9e", "#207b70")):
            ax.plot([row["elements"] for row in rows], [100*row[method]["relative_l2"] for row in rows],
                    "o-", label=label, color=colour)
        ax.set(title=title, xlabel="Quad elements", ylabel="Interior shear vector L2 error (%)", xscale="log", yscale="log")
        ax.set_xticks([24, 96, 384], labels=["24", "96", "384"])
        ax.xaxis.set_minor_locator(NullLocator())
        ax.grid(alpha=.2)
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Brecon: Quad shear recovery feasibility", fontsize=13)
    fig.supxlabel("Bounded thin-plate interior comparison. Boundary / opening recovery unvalidated; Quad shear remains disabled.", fontsize=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight", pad_inches=.15)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--figure", type=Path)
    options = parser.parse_args()
    data = benchmark()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")
    if options.figure:
        plot(data, options.figure)
    print(json.dumps(dict(checks_passed=data["checks_passed"], records=len(data["records"]),
        fine_xy_service=[row for row in data["records"] if row["mesh_size_in"] == SIZES[-1]
            and row["plane"] == "XY" and row["combination"] == "Service"]), indent=2))
    if not data["checks_passed"]:
        raise SystemExit("Quad shear research checks failed; inspect the numerical report.")
