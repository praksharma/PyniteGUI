"""Reproduce bounded nonlinear cantilever comparisons against scalar statics.

No production readiness, continuum plastic-beam or PyNite source parity claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import numpy as np
from corotational_hinge_frame import CorotationalHingeFrame
from corotational_cantilever_reference import solve


def benchmark():
    records=[]
    def history(label,targets,steps):
        b=CorotationalHingeFrame(((0.,0.),(0.,120.)),((0,1,290000.,2900000.),),(0,1,2),((0,0,1000.),))
        old=reference=None;previous=np.array([0.,targets[0][1]])
        for stage,target in enumerate(targets):
            for values in np.linspace(previous,target,steps+1)[1:]:
                lateral,tension=map(float,values);loads=np.zeros(6);loads[3:5]=values
                r=b.solve(loads,old);s=solve(120.,290000.,2900000.,1000.,lateral,tension,reference)
                old=r['state'];reference=s['state']
            compliance=np.linalg.solve(r['free_tangent'],[1.,0.,0.])
            error=np.array(r['motion'][3:])-s['motion']
            records.append(dict(path=label,steps_per_stage=steps,stage=stage,lateral=lateral,tension=tension,
                prototype_motion=r['motion'][3:].tolist(),reference_motion=list(s['motion']),
                moment=float(r['hinge_moments'][0]),reference_moment=s['moment'],
                plastic_rotation=float(old.rotations[0]),reference_plastic_rotation=reference.plastic_rotation,
                dissipation=old.dissipation,reference_dissipation=reference.dissipation,
                reference_compliance=list(s['compliance']),prototype_compliance=compliance.tolist(),
                translation_error=float(max(abs(error[:2]))),rotation_error=float(abs(error[2])),
                plastic_rotation_error=float(abs(old.rotations[0]-reference.plastic_rotation)),
                dissipation_error=float(abs(old.dissipation-reference.dissipation)),
                elastic_energy_error=float(abs(r['elastic_energy']-s['elastic_energy'])),
                moment_error=float(abs(r['hinge_moments'][0]-s['moment'])),
                axial_force_error=float(abs(r['basic_forces'][0,0]-s['axial_force'])),
                compliance_error=float(max(abs(compliance-s['compliance']))),
                active=bool(r['active']),reference_active=s['active']))
            previous=np.array(target,dtype=float)
    for tension,maximum in ((20.,10.),(40.,12.),(80.,16.)):
        targets=[(p,tension) for p in (0.,maximum/2,maximum,0.,-maximum,0.,maximum)]
        for steps in (1,20):history(f'cycle_tension_{tension:g}',targets,steps)
    history('changing_tension',[(12.,40.),(0.,40.),(-12.,40.),(8.,80.),(10.,20.),(0.,40.)],1)
    gates=dict(translation_error=1e-7,rotation_error=1e-9,plastic_rotation_error=1e-9,
        dissipation_error=1e-5,elastic_energy_error=1e-6,moment_error=1e-6,axial_force_error=1e-6,compliance_error=1e-6)
    maximum={key:max(r[key] for r in records) for key in gates}
    passed=all(maximum[key]<limit for key,limit in gates.items()) and all(r['active']==r['reference_active'] for r in records)
    sources=('tests/corotational_hinge_frame.py','tests/planar_hinge_frame.py','tests/beam_gradient_compatibility.py',
        'tests/corotational_cantilever_reference.py','tests/test_corotational_cantilever_reference.py',
        'scripts/benchmark_corotational_cantilever.py')
    frozen=('docs/assets/combined-pushover-prerequisite.json','docs/assets/equilibrated-column.json','docs/assets/section-return.json')
    for report in frozen:
        for source,digest in json.loads((ROOT/report).read_text())['source_sha256'].items():
            if hashlib.sha256((ROOT/source).read_bytes()).hexdigest()!=digest:raise ValueError('Prior source changed: '+source)
    return dict(bounded_member_reference_checks_passed=bool(passed),production_ready=False,
        general_frame_plastic_validated=False,pynite_combined_source_parity=False,
        python=platform.python_version(),units='inch, kip, rad',scope='One corotational member, fixed base, free tip, one base scalar hinge, positive dead tip tension. Reference chord angle bounded to +/-0.2 rad and axial strain to 1%. Elastic axial/bending law; no axial-moment yield interaction or continuum plastic-beam claim.',
        reference='Eliminate the free-end moment; solve scalar current-chord force/moment balance with a bracketed root, signed perfect-plastic return, and analytic implicit compliance. No assembled stiffness/Hessian/energy solver is imported by the reference.',
        sources_sha_note='Includes prototype and its inherited assembly/elastic compatibility dependencies.',
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        frozen_report_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in frozen},
        gates=gates,maximum_errors=maximum,records=records)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    options=parser.parse_args();data=benchmark()
    options.output.parent.mkdir(parents=True,exist_ok=True)
    options.output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    if not data['bounded_member_reference_checks_passed']:raise SystemExit('Reference comparison gates failed.')
    print(f"PASS: {len(data['records'])} reference comparisons; research-only.")
