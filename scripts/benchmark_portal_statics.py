"""Reproduce bounded corotational portal comparisons against joint statics."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import numpy as np
from displacement_hinge_frame import DisplacementHingeFrame
from portal_statics_reference import solve


def benchmark():
    records=[]
    nodes=((0.,0.),(120.,0.),(0.,120.),(120.,120.))
    members=((0,2,290000.,2900000.),(1,3,290000.,2900000.),(2,3,290000.,2900000.))
    hinges=((0,0,1000.),(1,0,1000.),(0,1,1000.),(1,1,1000.))
    def history(label,targets,steps):
        preload=np.zeros(12);preload[[7,10]]=-50.
        b=DisplacementHingeFrame(nodes,members,tuple(range(6)),hinges,preload,6)
        old=reference=None;previous=0.
        for stage,target in enumerate(targets):
            for x in np.linspace(previous,target,steps+1)[1:]:
                r=b.solve_displacement(x,old);s=solve(120.,120.,290000.,2900000.,1000.,50.,x,reference)
                old=r['state'];reference=s['state']
            difference=(r['motion'][6:]-s['roof_motion']).reshape(2,3)
            records.append(dict(path=label,stage=stage,steps_per_stage=steps,target=float(target),
                prototype_roof_motion=r['motion'][6:].tolist(),reference_roof_motion=s['roof_motion'].tolist(),
                prototype_load=r['actuator_load'],reference_load=s['actuator_load'],
                prototype_slope=r['actuator_tangent'],reference_slope=s['actuator_tangent'],
                active=list(map(int,r['active'])),reference_active=list(map(int,s['active'])),
                load_control_tangent_positive=r['load_control_stable'],
                translation_error=float(np.max(abs(difference[:,:2]))),rotation_error=float(np.max(abs(difference[:,2]))),
                load_error=abs(r['actuator_load']-s['actuator_load']),slope_error=abs(r['actuator_tangent']-s['actuator_tangent']),
                moment_error=float(np.max(abs(r['hinge_moments']-s['hinge_moments']))),
                support_error=float(np.max(abs(r['reaction'][:6]-s['support_reactions']))),
                plastic_rotation_error=float(np.max(abs(np.array(old.rotations)-reference.rotations))),
                dissipation_error=abs(old.dissipation-reference.dissipation),energy_error=abs(r['elastic_energy']-s['elastic_energy'])))
            previous=target
    for steps in (1,10):history('yield_soften_reverse',(0.,.5,1.,1.3,1.5,2.,3.,0.,-3.,0.),steps)
    history('cold_large_step',(5.,),1);history('staged_large_step',(3.,5.),1)
    gates=dict(translation_error=1e-7,rotation_error=1e-9,load_error=1e-6,slope_error=2e-6,
        moment_error=1e-6,support_error=1e-6,plastic_rotation_error=1e-9,dissipation_error=1e-5,energy_error=1e-6)
    maximum={key:max(r[key] for r in records) for key in gates}
    passed=all(maximum[key]<limit for key,limit in gates.items()) and all(r['active']==r['reference_active'] for r in records)
    sources=('tests/displacement_hinge_frame.py','tests/corotational_hinge_frame.py','tests/planar_hinge_frame.py',
        'tests/beam_gradient_compatibility.py','tests/portal_statics_reference.py','tests/test_portal_statics_reference.py',
        'scripts/benchmark_portal_statics.py')
    frozen=('docs/assets/combined-pushover-prerequisite.json','docs/assets/equilibrated-column.json',
        'docs/assets/section-return.json','docs/assets/corotational-cantilever.json')
    for report in frozen:
        for source,digest in json.loads((ROOT/report).read_text())['source_sha256'].items():
            if hashlib.sha256((ROOT/source).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen source changed: '+source)
    return dict(bounded_portal_joint_statics_checks_passed=bool(passed),production_ready=False,
        general_frame_plastic_validated=False,pynite_combined_source_parity=False,
        scope='One three-member planar portal, equal 50 kip roof gravity, one left-roof horizontal actuator, four scalar column-end hinges. Same bounded corotational elastic-span law; no axial-moment yield interaction, continuum plasticity, general branch uniqueness or source parity claim.',
        reference='Independent local end-force/current-chord formulas and roof joint balance. Finite-difference root/Jacobian with local constrained positivity, signed plastic increments and final geometry bounds. No frame energy/tangent/assembly imports.',
        units='inch, kip, rad',gates=gates,maximum_errors=maximum,
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        frozen_report_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in frozen},records=records)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    options=parser.parse_args();data=benchmark();options.output.parent.mkdir(parents=True,exist_ok=True)
    options.output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    if not data['bounded_portal_joint_statics_checks_passed']:raise SystemExit('Portal comparison gates failed.')
    print(f"PASS: {len(data['records'])} independent portal comparisons; research-only.")
