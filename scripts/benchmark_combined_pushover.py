"""Reproduce elastic prerequisites for combined P-Delta/plastic qualification.

This deliberately tests the raw optional engine path outside the application.
A passing diagnostic/control run is not a passing combined-plastic formulation.
"""
import argparse
import hashlib
from importlib.metadata import version
import inspect
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import numpy as np
from Pynite import FEModel3D
from Pynite.Member3D import Member3D
from combined_pushover_probe import probe,supports_combined,LENGTH,RIGIDITY,AREA,CRITICAL
from combined_pushover_reference import compliance_path_integral


def benchmark():
    records=[]
    def add(group,**parameters):
        data=probe(**parameters)
        row={**parameters,'group':group,**{key:value for key,value in data.items() if key!='history'}}
        if data['supported']:
            if parameters['path']=='ramp':row['incomplete_compliance_integral_tip_in']=compliance_path_integral(LENGTH,RIGIDITY,data['final']['compression_kip'],parameters.get('force',1.))
            row['accepted_steps']=len(data['history'])
            row['max_free_joint_residual']=max(r['free_joint_residual'] for r in data['history'])
            row['max_reference_backward_error']=max(r['reference_backward_error'] for r in data['history'])
            row['max_deformed_moment_residual_kip_in']=float(max(np.linalg.norm(r['deformed_moment_residual_kip_in']) for r in data['history']))
        records.append(row)
    for ratio in (0.,.1,.3):
        for n in (2,4,8):
            add('ordinary_elastic_control',segments=n,ratio=ratio,steps=100,path='preload',variant='elastic_p_delta')
            if ratio==0.:add('first_order_control',segments=n,ratio=ratio,steps=100,path='preload',variant='first_order')
            for path in ('preload','ramp'):
                for variant in ('raw','half_axial_diagnostic'):
                    add('mesh_refinement',segments=n,ratio=ratio,steps=100,path=path,variant=variant)
    for steps in (20,100,400):
        for variant in ('raw','half_axial_diagnostic'):
            add('step_refinement',segments=8,ratio=.3,steps=steps,path='ramp',variant=variant)
    for plane in ('XY','YZ'):
        for force in (-2.,0.):
            for variant in ('raw','half_axial_diagnostic'):
                add('sign_plane_origin',segments=4,ratio=.1,steps=20,path='preload',variant=variant,
                    force=force,plane=plane,origin=(17.,-31.,49.))
    available=[r for r in records if r['supported']]
    baseline=[r for r in available if r['group'] in ('ordinary_elastic_control','first_order_control')]
    controls=all(r['final']['continuum_relative_error']<1e-4 and r['max_yield_interaction']<1e-10
        and r['max_deformed_moment_residual_kip_in']<.012 and r['max_free_joint_residual']<1e-5 for r in baseline)
    finite=all(np.isfinite(list(r['final']['deformed_moment_residual_kip_in'])).all()
        and r['max_reference_backward_error']<1e-11 and r['max_yield_interaction']<1e-10 for r in available)
    raw=[r for r in available if r['variant']=='raw' and r['group'] in ('mesh_refinement','step_refinement')]
    qualifies=bool(raw) and all(r['final']['continuum_relative_error']<.001 and
        r['max_deformed_moment_residual_kip_in']<.012 for r in raw)
    sources=('tests/combined_pushover_reference.py','tests/combined_pushover_probe.py',
             'tests/test_combined_pushover.py','scripts/benchmark_combined_pushover.py')
    return dict(diagnostic_checks_passed=bool(controls and finite),engine_supports_combined=supports_combined(),
        elastic_prerequisite_passed=bool(qualifies),combined_plastic_validated=False,production_ready=False,
        python=platform.python_version(),pynite=version('pynitefea'),brecon=version('brecon'),
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        engine_source_sha256={cls.__name__:hashlib.sha256(Path(inspect.getfile(cls)).read_bytes()).hexdigest() for cls in (FEModel3D,Member3D)},
        scope=dict(length_in=LENGTH,rigidity_kip_in2=RIGIDITY,area_in2=AREA,critical_compression_kip=float(CRITICAL),
            yield_stress_ksi=1e9,load='Global lateral tip force 1 kip; prescribed compressive force ratio times the elastic critical load. Artificially high strength keeps every probe elastic. Large axial area makes shortening negligible for the bending reference.',
            paths='Constant compression preload then lateral push; simultaneous axial/lateral ramp. 2/4/8 explicit members; 20/100/400 steps. Signed/zero lateral, XY/YZ and translated-origin controls.',
            references="Independent closed-form cantilever solution of EI*w(4) + N*w(2) = 0, cross-checked against a state-transfer solution; independent Gauss-integrated Hermite bending/geometric energy.",
            gates='Elastic relative displacement-field error <0.1%; deformed-lever-arm moment residual <0.012 kip-in for the 1 kip, 120 in reference. Controls and reference backward errors are separate checks. No tolerance is relaxed for a candidate.',
            diagnostic='The half-axial ramp approaches an incomplete compliance integral rather than the static equilibrium field. Isolated half-axial patch only while the raw engine is in Pushover mode, restoring Member3D.kg on every exit. It is not used by Brecon and is not a complete solver correction.',
            meaning='diagnostic_checks_passed means reference/control checks succeeded, not that the raw candidate qualified. Even an elastic pass would still need yielding, unloading, interaction, stability and accepted-step validation before production.'),
        records=records)


def plot(data,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.8),layout='constrained')
    for variant,label,color in (('raw','Raw engine','#ad4936'),('half_axial_diagnostic','Half-axial diagnostic','#3e659f')):
        rows=[r for r in data['records'] if r['supported'] and r['group']=='mesh_refinement' and r['path']=='preload' and r['ratio']==.3 and r['variant']==variant]
        if rows:axes[0].plot([r['segments'] for r in rows],[100*r['final']['continuum_relative_error'] for r in rows],'o-',label=label,color=color)
        rows=[r for r in data['records'] if r['supported'] and r['group']=='step_refinement' and r['variant']==variant]
        if rows:axes[1].plot([r['steps'] for r in rows],[100*r['final']['continuum_relative_error'] for r in rows],'o-',label=label,color=color)
    for ax,title,xlabel in zip(axes,('Constant compression preload','Simultaneous axial/lateral ramp'),('Explicit beam members','Push increments')):
        ax.set(title=title,xlabel=xlabel,ylabel='Elastic displacement-field error (%)',yscale='log')
        ax.axhline(.1,color='#267357',ls='--',label='0.1% elastic gate');ax.grid(alpha=.2);ax.legend(frameon=False,fontsize=9)
    axes[0].set_xticks([2,4,8]);axes[1].set_xticks([20,100,400])
    fig.suptitle(f"Brecon: P-Delta pushover elastic prerequisite (PyNite {data['pynite']})",fontsize=13)
    fig.supxlabel('N / Ncr = 0.3; no yielding. Half-axial changes isolate a defect; they do not qualify combined plastic analysis.',fontsize=9)
    path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=160);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--figure',type=Path);options=parser.parse_args();data=benchmark()
    options.output.parent.mkdir(parents=True,exist_ok=True);options.output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    if options.figure:plot(data,options.figure)
    print(json.dumps({k:data[k] for k in ('diagnostic_checks_passed','engine_supports_combined','elastic_prerequisite_passed','combined_plastic_validated','production_ready')},indent=2))
    print(f"{len(data['records'])} records; {sum(r['supported'] for r in data['records'])} supported solves")
    if not data['diagnostic_checks_passed']:raise SystemExit('Reference/control checks failed; inspect the report.')
