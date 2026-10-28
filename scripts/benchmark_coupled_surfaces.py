"""Reproduce the bounded coupled-plate comparison and Quad shear limitation."""
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
                records=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    data = benchmark()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(data, indent=2)+"\n")
    print(json.dumps(data, indent=2))
