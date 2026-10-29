"""Reproduce test-only planar inclined-support feasibility; no GUI enablement."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tests"))
from inclined_constraints import solve
from inclined_reference import cantilever, pinned_beam
from inclined_validation import assemble, beam, constraints, balance


def measure(project, names, result, combination, expected_d, expected_r, reaction_indices):
    d = result['displacement'].reshape(-1, 3)
    r = result['rigid_reaction'].reshape(-1, 3)
    spring_values = np.array([project.nodes[name].springs for name in names])
    equilibrium = balance(project, names, r-spring_values*d, combination)
    delta_d = abs(d-expected_d)
    delta_r = abs(r[reaction_indices]-expected_r)
    values = dict(nodes=len(names), max_translation_error_in=float(delta_d[:, :2].max()),
        max_rotation_error_rad=float(delta_d[:, 2].max()),
        max_reference_force_error_kip=float(delta_r[:, :2].max()),
        max_reference_moment_error_kip_in=float(delta_r[:, 2].max()),
        max_force_balance_error_kip=float(abs(equilibrium[:2]).max()),
        moment_balance_error_kip_in=float(abs(equilibrium[2])),
        max_constraint_residual=result['max_constraint_residual'],
        minimum_scaled_eigenvalue=result['minimum_scaled_eigenvalue'],
        stability_roundoff_bound=result['stability_roundoff_bound'],
        tip_displacement=d[-1].tolist(), tip_rigid_reaction=r[-1].tolist())
    values['passed'] = (values['max_translation_error_in'] < 1e-10
        and values['max_rotation_error_rad'] < 1e-10
        and values['max_reference_force_error_kip'] < 1e-9
        and values['max_reference_moment_error_kip_in'] < 1e-9
        and values['max_force_balance_error_kip'] < 1e-9
        and values['moment_balance_error_kip_in'] < 1e-8
        and values['max_constraint_residual'] < 1e-10)
    return values


def benchmark():
    records = []
    for beam_angle in (0., 37., 90., -143.):
        project = beam(angle=beam_angle)
        names, matrices, forces = assemble(project)
        for roller in (-170., -90., -30., 0., 25., 89.9, 90., 135., 180.):
            C = constraints(names, fixed=(names[0],), rollers=((names[-1], roller),))
            d, r = cantilever(roller, beam_angle)
            for combination, factors in project.combinations.items():
                factor = factors['Case 1']
                result = solve(matrices[combination], forces[combination], C, 120.)
                records.append(dict(case='cantilever', beam_angle_deg=beam_angle,
                    roller_tangent_angle_deg=roller, combination=combination,
                    **measure(project, names, result, combination,
                        np.array((np.zeros(3), d))*factor, np.array((r,))*factor, [-1])))
    for fractions in ((0., 1.), (0., .17, .53, 1.), tuple(np.linspace(0., 1., 9))):
        project = beam(fractions=fractions, nodal=(0., 0., 0.), distributed=(0., -.005))
        names, matrices, forces = assemble(project)
        for roller in (-65., 0., 17., 60.):
            C = constraints(names, pinned=(names[0],), rollers=((names[-1], roller),))
            d, left, right = pinned_beam(np.array(fractions)*120., roller)
            for combination, factors in project.combinations.items():
                factor = factors['Case 1']
                result = solve(matrices[combination], forces[combination], C, 120.)
                records.append(dict(case='pin_roller', beam_angle_deg=0.,
                    roller_tangent_angle_deg=roller, combination=combination,
                    **measure(project, names, result, combination, d*factor,
                        np.array((left, right))*factor, [0, -1])))
    for beam_angle, roller, springs in ((0., 27., (500., 0., 0.)), (37., -26., (0., 700., 200.)),
                                       (-73., 61., (50000., 300., 900.))):
        project = beam(angle=beam_angle)
        tip = next(reversed(project.nodes))
        project.nodes[tip].spring_x, project.nodes[tip].spring_y, project.nodes[tip].spring_rz = springs
        names, matrices, forces = assemble(project)
        C = constraints(names, fixed=(names[0],), rollers=((tip, roller),))
        d, r = cantilever(roller, beam_angle, springs=springs)
        for combination, factors in project.combinations.items():
            factor = factors['Case 1']
            result = solve(matrices[combination], forces[combination], C, 120.)
            records.append(dict(case='global_springs', beam_angle_deg=beam_angle,
                roller_tangent_angle_deg=roller, combination=combination, springs=list(springs),
                **measure(project, names, result, combination,
                    np.array((np.zeros(3), d))*factor, np.array((r,))*factor, [-1])))
    project = beam(nodal=(0., 0., 0.), distributed=(0., 0.))
    names, matrices, forces = assemble(project)
    guards = []
    for name, C in (
            ('unsupported rigid motions', constraints(names)),
            ('pin alone', constraints(names, pinned=(names[0],))),
            ('roller cannot stop rigid rotation', constraints(names, pinned=(names[0],), rollers=((names[-1], 90.),))),
            ('nearly unrestrained rigid rotation', constraints(names, pinned=(names[0],), rollers=((names[-1], 89.999999),))),
            ('duplicate constraints', constraints(names, rollers=((names[-1], 0.), (names[-1], 0.)))),
            ('nearly dependent constraints', constraints(names, rollers=((names[-1], 0.), (names[-1], 1e-10))))):
        try:
            solve(matrices['Zero'], forces['Zero'], C, 120.)
        except ValueError as error:
            guards.append(dict(case=name, rejected=True, reason=str(error)))
        else:
            guards.append(dict(case=name, rejected=False))
    return dict(checks_passed=all(row['passed'] for row in records) and all(row['rejected'] for row in guards),
        python=platform.python_version(), pynite=importlib.metadata.version('pynitefea'),
        brecon=importlib.metadata.version('brecon'),
        scope='Test-only dense constrained-coordinate feasibility, unreleased planar linear frames. Actual engine stiffness and equivalent nodal loads including FER, assembled on a clamped copy; its displacements are discarded. No production result snapshots or UI/MCP enablement.',
        method='d=S Z q, where C S Z=0; solve Z.T S K S Z q=Z.T S f. Normalize rows and reduced diagonal; reject nonpositive modes and modes unresolved above the pre-cancellation projection roundoff bound. Recover rigid reactions from K d-f. Global ground springs retain their axes; subtract k*d separately for external equilibrium. No penalty stiffness or artificial gauges.',
        convention='Roller tangent angle alpha is CCW from global +X in degrees; unit normal is (-sin alpha, cos alpha). Zero/180 degrees restrain DY; 90 degrees restrain DX. Displacement/reaction arrays use global DX/DY/RZ and FX/FY/MZ in in/rad and kip/kip-in.',
        references='Independent axial/Euler-Bernoulli tip flexibility and statically determined pin/roller fields in tests/inclined_reference.py. Cantilever force comparison uses the inclined tip reaction; pin/roller comparison uses both supports. Every case independently checks total external force/moment balance.',
        limitations='Dense prototype only; not a production performance/stability certification. Needs sparse local constraints, support-aware diagnostics, physical member/release recovery, reaction metadata, persistence/UI/MCP and lifecycle validation. No P-Delta, trusses, settlements, spatial constraints or released frames. Quadratic-energy identities concern equivalent nodal equations, not full distributed-load strain-energy recovery.',
        records=records, rejection_checks=guards)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    data = benchmark()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(data, indent=2)+'\n')
    keys = ('max_translation_error_in', 'max_rotation_error_rad', 'max_reference_force_error_kip',
            'max_reference_moment_error_kip_in', 'max_force_balance_error_kip', 'moment_balance_error_kip_in')
    print(json.dumps(dict(checks_passed=data['checks_passed'], cases=len(data['records']),
        maximum_errors={key:max(row[key] for row in data['records']) for key in keys},
        rejections=data['rejection_checks']), indent=2))
    if not data['checks_passed']:
        raise SystemExit('Inclined-support feasibility failed; inspect the report.')
