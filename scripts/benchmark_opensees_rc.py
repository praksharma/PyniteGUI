"""Optional pinned OpenSees evaluation. Each job uses a fresh external process."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from rc_fibre_section import MonotonicRCSection


def invoke(python,request,timeout=30):
    worker=ROOT/'scripts/opensees_rc_worker.py'
    p=subprocess.run([str(python),'-I',str(worker)],input=json.dumps(request,allow_nan=False),
        text=True,capture_output=True,timeout=timeout)
    try:result=json.loads(p.stdout)
    except ValueError:raise ValueError('External worker did not return JSON: '+p.stderr[-1000:])
    if p.returncode or 'error' in result:raise ValueError('External RC evaluation rejected: '+str(result.get('error',p.stderr[-1000:])))
    if result.get('production_ready') is not False or result.get('engine')!='3.8.0':raise ValueError('Unexpected evaluation engine/contract.')
    return result


def benchmark(python):
    steel_path=[0.,.001,.004,.001,-.004,0.,.004]
    steel=invoke(python,dict(job='steel',values=steel_path));ep=0.;E=29000.;H=.01*E/.99;steel_error=0.
    for row in steel['rows']:
        trial=E*(row['strain']-ep)-H*ep
        if abs(trial)>60.:ep+=(1. if trial>0 else -1.)*(abs(trial)-60.)/(E+H)
        expected=E*(row['strain']-ep);steel_error=max(steel_error,abs(row['stress']-expected))
    concrete_path=[0.,-.0005,-.001,-.0015,-.002,-.003,-.001,0.,-.002]
    concrete=invoke(python,dict(job='concrete',values=concrete_path))
    replay=invoke(python,dict(job='concrete',values=concrete_path))
    virgin=invoke(python,dict(job='concrete',values=[-.002,.001]))
    # Hand envelope checks; unloading is characterized/replayed, not independently certified.
    concrete_error=max(abs(row['stress']+4*(2*(-row['strain']/.002)-(-row['strain']/.002)**2)) for row in concrete['rows'][:5])
    concrete_error=max(concrete_error,abs(concrete['rows'][5]['stress']+3.25))
    fibres=[(12.,-9.5+i,'concrete') for i in range(20)]+[(1.,-8.,'steel'),(1.,8.,'steel')]
    local=MonotonicRCSection(fibres);records=[]
    for curvature in (.00005,.0001,.0002,.0003):
        expected=local.moment_at_axial_force(curvature,0.)
        for job in ('section','member'):
            result=invoke(python,dict(job=job,fibres=fibres,curvature=curvature));row=result['rows'][0]
            L=120. if job=='member' else 1.
            moment=-row['reaction'][2]
            records.append(dict(job=job,curvature=curvature,moment=moment,reference_moment=float(expected['resultants'][1]),
                moment_error=abs(moment-expected['resultants'][1]),
                axial_strain_error=abs(row['displacement'][0]/L-expected['axial_strain']),
                transverse_error=abs(row['displacement'][1]-(curvature*L**2/2 if job=='member' else 0.)),
                rotation_error=abs(row['displacement'][2]-curvature*L),
                axial_reaction_error=abs(row['reaction'][0]),shear_reaction_error=abs(row['reaction'][1]),
                section_moment_error=max(abs(v-moment) for v in row['all_section_forces'][1::2]),section_axial_error=max(abs(v) for v in row['all_section_forces'][::2]),raw=result))
    gates=dict(moment_error=1e-4,axial_strain_error=1e-9,transverse_error=1e-7,rotation_error=1e-10,
        axial_reaction_error=1e-6,shear_reaction_error=1e-6,section_moment_error=1e-4,section_axial_error=1e-5)
    maximum={k:max(r[k] for r in records) for k in gates}
    checks=dict(steel_kinematic_cycle=steel_error<1e-8,concrete_hand_envelope=concrete_error<1e-10,
        fresh_process_replay=concrete['rows']==replay['rows'],
        concrete_has_history=abs(concrete['rows'][-1]['stress']-virgin['rows'][0]['stress'])>1.,
        concrete_zero_tension=virgin['rows'][-1]['stress']==0.,
        section_member_checks=all(maximum[k]<limit for k,limit in gates.items()))
    sources=('scripts/opensees_rc_worker.py','scripts/benchmark_opensees_rc.py','tests/rc_fibre_section.py','tests/test_opensees_rc_evaluation.py')
    return dict(checks=checks,passed=all(checks.values()),production_ready=False,
        scope='Pinned external macOS arm64 evaluation only. Independent steel kinematic cycle, concrete envelope/descending line and history characterization, N=0 section and constant-couple linear-geometry force-based member. No full concrete cyclic oracle, general RC frame, geometric instability or slab validation.',
        bundling_approved=False,other_platforms_validated=False,metadata={k:steel[k] for k in ('package','engine','python','platform','machine','licences')},
        steel_cycle=steel,concrete_cycle=concrete,virgin_concrete=virgin,steel_max_error=steel_error,concrete_envelope_max_error=concrete_error,
        gates=gates,maximum_errors=maximum,records=records,
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--python',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();data=benchmark(args.python);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    if not data['passed']:raise SystemExit('External RC assessment gates failed.')
    print('PASS: external material cycles and eight section/member cases; research-only.')
