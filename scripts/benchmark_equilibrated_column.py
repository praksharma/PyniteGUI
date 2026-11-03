"""Reproduce bounded elastic correction of the combined-pushover prerequisites.

The old negative report and its hashed helpers are frozen. This separate
candidate owns total-state equilibrium, never patches an installed engine and
has no plastic return mapping or application integration.
"""
import argparse
import hashlib
from importlib.metadata import version
import inspect
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
import numpy as np
from Pynite import Analysis
from Pynite.Member3D import Member3D
from equilibrated_column_cases import corrected

OLD_REPORT='docs/assets/combined-pushover-prerequisite.json'


def benchmark():
    old=json.loads((ROOT/OLD_REPORT).read_text())
    # Keep the original negative measurements reproducible; never silently
    # re-label an earlier report after changing its hashed source code.
    for name,digest in old['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen prerequisite source changed: '+name)
    records=[]
    def add(group,**parameters):
        data=corrected(**parameters);history=data['history']
        records.append(dict(group=group,**{k:v for k,v in data.items() if k!='history'},
            max_zero_field_error_in=max((r['continuum_absolute_error_in'] for r in history if r['continuum_relative_error'] is None),default=0.),
            max_zero_rotation_error_rad=max((r['rotation_absolute_error_rad'] for r in history if r['rotation_relative_error'] is None),default=0.),
            max_equilibrium_residual=max(r['max_equilibrium_residual'] for r in history),
            max_scaled_residual=max(r['max_scaled_residual'] for r in history),
            max_axial_error_kip=max(r['mean_axial_error_kip'] for r in history),
            max_deformed_moment_residual_kip_in=float(max(np.linalg.norm(r['deformed_moment_residual_kip_in']) for r in history)),
            max_yield_interaction=max(r['max_yield_interaction'] for r in history),
            min_normalized_stiffness=min(r['min_normalized_stiffness'] for r in history),
            max_newton_iterations=max(r['iterations'] for r in history)))
    for ratio in (-.3,0.,.1,.3):
        for path in ('preload','ramp'):
            for segments in (2,4,8):add('mesh_refinement',segments=segments,ratio=ratio,steps=20,path=path)
    for steps in (1,20,100,400):add('step_refinement',segments=8,ratio=.3,steps=steps,path='ramp')
    for path in ('preload','ramp'):
        for plane in ('XY','YZ'):
            for force in (-2.,0.):add('sign_plane_origin',segments=4,ratio=.3,steps=10,path=path,
                force=force,plane=plane,origin=(17.,-31.,49.))
    balanced=all(r['max_scaled_residual']<=1 and r['max_axial_error_kip']<1e-8 and
        r['max_equilibrium_residual']<1e-8 and r['max_deformed_moment_residual_kip_in']<.012 and
        r['max_zero_field_error_in']<1e-12 and r['max_zero_rotation_error_rad']<1e-12 and
        r['max_yield_interaction']<1e-10 and r['min_normalized_stiffness']>1e-10 for r in records)
    refined=True
    for ratio in (-.3,0.,.1,.3):
        for path in ('preload','ramp'):
            rows=[r for r in records if r['group']=='mesh_refinement' and r['ratio']==ratio and r['path']==path]
            errors=[r['final']['continuum_relative_error'] for r in rows]
            refined &= bool((not ratio or all(b<a/10 for a,b in zip(errors,errors[1:]))) and errors[-1]<3e-7)
    step_rows=[r for r in records if r['group']=='step_refinement'];endpoints=[r['final']['tip_translation_in'] for r in step_rows]
    invariant=bool(np.allclose(endpoints,endpoints[0],rtol=1e-10,atol=1e-11))
    sources=('tests/equilibrated_beam_column.py','tests/equilibrated_column_cases.py','tests/test_equilibrated_column.py',
             'scripts/benchmark_equilibrated_column.py','tests/combined_pushover_reference.py')
    return dict(bounded_elastic_checks_passed=bool(balanced and refined and invariant),plastic_validated=False,production_ready=False,
        python=platform.python_version(),pynite=version('pynitefea'),brecon=version('brecon'),
        frozen_prerequisite_report=OLD_REPORT,frozen_prerequisite_sha256=hashlib.sha256((ROOT/OLD_REPORT).read_bytes()).hexdigest(),
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        engine_source_sha256={Path(inspect.getfile(item)).name:hashlib.sha256(Path(inspect.getfile(item)).read_bytes()).hexdigest() for item in (Analysis,Member3D)},
        method='Unknowns are free joint motions and one tension-positive physical mean axial action per explicit member. At every target load solve r_u=assembled (Ke+N*Kg_unit)*u-P=0 and r_N=N-(f_jx-f_ix)/2=0 with the full analytical block Jacobian, equilibrated linear solves and residual-decreasing line search.',
        acceptance='Every stored state closes free-joint/axial equations, stays on a positive resolved effective elastic stiffness branch and stays strictly below end yield. No trial state is returned after yield, instability, unsupported input or nonconvergence.',
        scope='Bounded elastic cantilever only: L=120 in, EI=2900000 kip-in2, large A=1000 in2 and artificial fy=1e9 ksi. N/Ncr=-0.3,0,0.1,0.3. Two paths, 2/4/8 explicit members, 1/20/100/400 increments, signed/zero lateral forces, XY/YZ and translated origins. Independent continuum and Gauss-integrated Hermite energy references. No plastic yielding, general frame, finite-rotation, member-load, spring, release or shell qualification.',
        gates='Same 0.1% elastic displacement-field and 0.012 kip-in deformed-moment gates as the frozen prerequisite study, with additional fine-field <3e-7 and exact discrete/axial/residual checks. No gate is relaxed. A positive elastic report cannot enable combined plastic analysis.',
        records=records)


def plot(data,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    old=json.loads((ROOT/OLD_REPORT).read_text())
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.8),layout='constrained')
    raw=[r for r in old['records'] if r['group']=='mesh_refinement' and r['path']=='preload' and r['ratio']==.3 and r['variant']=='raw']
    fixed=[r for r in data['records'] if r['group']=='mesh_refinement' and r['path']=='preload' and r['ratio']==.3]
    axes[0].plot([r['segments'] for r in raw],[100*r['final']['continuum_relative_error'] for r in raw],'o-',color='#ad4936',label='Frozen raw 3.2.1')
    axes[0].plot([r['segments'] for r in fixed],[100*r['final']['continuum_relative_error'] for r in fixed],'o-',color='#267357',label='Total-state elastic candidate')
    for variant,label,color in (('raw','Frozen raw 3.2.1','#ad4936'),('half_axial_diagnostic','Half-axial diagnostic','#3e659f')):
        rows=[r for r in old['records'] if r['group']=='step_refinement' and r['variant']==variant]
        axes[1].plot([r['steps'] for r in rows],[100*r['final']['continuum_relative_error'] for r in rows],'o-',label=label,color=color)
    rows=[r for r in data['records'] if r['group']=='step_refinement']
    axes[1].plot([r['steps'] for r in rows],[100*r['final']['continuum_relative_error'] for r in rows],'o-',color='#267357',label='Total-state elastic candidate')
    for ax,title,xlabel in zip(axes,('Constant compression preload','Simultaneous axial/lateral ramp'),('Explicit beam members','Push increments')):
        ax.set(title=title,xlabel=xlabel,ylabel='Elastic displacement-field error (%)',yscale='log')
        ax.axhline(.1,color='#666666',ls='--',label='Unchanged 0.1% elastic gate');ax.grid(alpha=.2);ax.legend(frameon=False,fontsize=8.5)
    axes[0].set_xticks([2,4,8]);axes[1].set_xscale('log');axes[1].set_xticks([1,20,100,400],labels=['1','20','100','400'])
    fig.suptitle(f"Brecon: corrected elastic equilibrium (PyNite {data['pynite']})",fontsize=13)
    fig.supxlabel('N / Ncr = 0.3; independent pre-yield references only. Test-only candidate; plastic and production gates remain open.',fontsize=9)
    path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=160);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--figure',type=Path)
    options=parser.parse_args();data=benchmark();options.output.parent.mkdir(parents=True,exist_ok=True)
    options.output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    if options.figure:plot(data,options.figure)
    print(json.dumps({key:data[key] for key in ('bounded_elastic_checks_passed','plastic_validated','production_ready')},indent=2))
    print(f"{len(data['records'])} bounded corrected elastic records")
    if not data['bounded_elastic_checks_passed']:raise SystemExit('Corrected elastic qualification failed; inspect the report.')
