"""Reproduce local section plastic-return checks and the excluded nonconvex region.

No frame integration is exercised. The prior elastic/prerequisite studies stay
frozen. Positive local checks cannot qualify general associated plasticity for a
nonconvex interaction polynomial.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
import numpy as np
from itertools import product
from section_return_cases import cycle,mixed,STIFFNESS,CAPACITIES
from section_return_reference import nonconvex_witness


def benchmark():
    records=[]
    for axis in range(3):
        for substeps in (1,10,40):
            data=cycle(axis,substeps)
            records.append(dict(kind='uniaxial_cycle',**{key:value for key,value in data.items() if key!='history'}))
    for base in ((1.2,.1,.1),(.1,1.2,.1),(.1,.2,1.2)):
        for signs in product((-1.,1.),repeat=3):records.append(dict(kind='mixed_return',**mixed(tuple(np.array(base)*signs))))
    cyclic=[r for r in records if r['kind']=='uniaxial_cycle'];coupled=[r for r in records if r['kind']=='mixed_return']
    cycles_pass=all(r['max_force_error']<1e-11 and r['max_plastic_strain_error']<1e-11 and r['max_dissipation_error']<1e-10
        and r['max_incremental_energy_error']<1e-12 and r['max_yield_overshoot']<1e-11 for r in cyclic)
    mixed_pass=all(r['reference_error']<2e-6 and r['consistent_tangent_relative_error']<2e-7 and abs(r['yield_value']-1)<1e-10
        and r['curvature']>1e-8 and r['dissipation_increment']>=0 and r['reference']['successful_starts']>=6 for r in coupled)
    witness=nonconvex_witness()
    sources=('tests/section_return_map.py','tests/section_return_reference.py','tests/section_return_cases.py',
        'tests/test_section_return.py','scripts/benchmark_section_return.py')
    frozen=('docs/assets/combined-pushover-prerequisite.json','docs/assets/equilibrated-column.json')
    for report in frozen:
        old=json.loads((ROOT/report).read_text())
        for source,digest in old['source_sha256'].items():
            if hashlib.sha256((ROOT/source).read_bytes()).hexdigest()!=digest:raise ValueError('Prior research source changed: '+source)
    return dict(bounded_local_section_checks_passed=bool(cycles_pass and mixed_pass),global_yield_domain_convex=False,
        frame_plastic_validated=False,production_ready=False,python=platform.python_version(),pynite=version('pynitefea'),
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        frozen_report_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in frozen},
        section_stiffness=STIFFNESS.tolist(),section_capacities=CAPACITIES.tolist(),
        force_order=['N','My','Mz'],strain_order=['axial_strain','curvature_y','curvature_z'],
        scope='Local perfect-plastic force point only, same stated steel interaction polynomial with signed gradient/Hessian. Three scalar cyclic paths at three step refinements; 24 mixed returns on locally convex patches across all force-sign octants. Full backward-Euler consistency tangent. No hardening, finite frame, hinge length, P-Delta/plastic assembly, interior-yield or RC formulation.',
        method='Normalize resultants by strengths and solve the four-variable backward-Euler consistency/flow KKT system in the elastic compliance metric. Frozen committed history is advanced only after residual, surface-curvature, tangent, strain-decomposition and dissipation checks. The tangent is the derivative at fixed old history, not an elastic stiffness reduction guess.',
        reference='Exact scalar perfect-plastic clip/projection, endpoint-work/elastic-energy/plastic-dissipation identity, central differences of yield derivatives and algorithmic force derivatives, independent multistart SLSQP with numerical constraint derivatives. At least six converged feasible starts and matching objective levels are required per mixed case; this is not a proof of global uniqueness.',
        exclusion='The original polynomial has a nonconvex elastic domain. The candidate rejects nonpositive or unresolved tangential yield-surface curvature. A positive result is local-branch validation only; this guard is not a global convexity certificate.',
        documentation_sources=['https://getfem.org/userdoc/model_plasticity_small_strain.html','https://pynite.readthedocs.io/en/latest/pushover.html'],
        nonconvex_witness=witness,records=records)


def plot(data,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from section_return_reference import scalar_cycle
    history=cycle(2,40)['history'];strain=np.array([r['normalized_strain'] for r in history]);force=np.array([r['force'][2]/CAPACITIES[2] for r in history])
    exact=scalar_cycle(strain*CAPACITIES[2]/STIFFNESS[2,2],STIFFNESS[2,2],CAPACITIES[2])[:,0]/CAPACITIES[2]
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.8),layout='constrained')
    axes[0].plot(strain,force,color='#267357',lw=2,label='Local return-map candidate')
    indices=np.arange(0,len(strain),12);axes[0].scatter(strain[indices],exact[indices],marker='x',s=28,color='#3e659f',label='Independent scalar reference',zorder=3)
    axes[0].set(title='Strong-axis yield, unload and reverse yield',xlabel='Curvature / elastic yield curvature',ylabel='Moment / plastic moment')
    axes[0].grid(alpha=.2);axes[0].legend(frameon=False,fontsize=9)
    from section_return_reference import phi
    w=data['nonconvex_witness'];a,b=(np.array(w[key]) for key in ('first','second'))
    fraction=np.linspace(0.,1.,301);values=np.array([phi((1-t)*a+t*b) for t in fraction])
    axes[1].plot(fraction,values,color='#5b527f',lw=2,label='Phi along straight segment')
    axes[1].axhline(1.,color='#777777',ls='--',label='Elastic boundary Phi = 1')
    axes[1].fill_between(fraction,1.,values,where=values>1.,color='#ad4936',alpha=.15)
    axes[1].scatter([0.,1.],w['endpoint_phi'],color='#267357',label='Elastic endpoints',zorder=3)
    axes[1].scatter([.5],[w['midpoint_phi']],color='#ad4936',label='Inelastic midpoint',zorder=4)
    axes[1].annotate(f"Midpoint Phi = {w['midpoint_phi']:.6f}",xy=(.5,w['midpoint_phi']),xytext=(.07,1.0009),fontsize=9,arrowprops={'arrowstyle':'->','color':'#ad4936'})
    axes[1].set(title='Excluded nonconvex interaction region',xlabel='Fraction along endpoint-to-endpoint segment',ylabel='Interaction Phi',ylim=(.9982,1.0011))
    axes[1].ticklabel_format(axis='y',style='plain',useOffset=False)
    axes[1].grid(alpha=.2);axes[1].legend(frameon=False,fontsize=8,loc='lower center')
    fig.suptitle('Brecon: local steel-section return map and explicit branch rejection',fontsize=13)
    fig.supxlabel('Test-only force point. Local yielding/unloading checks do not qualify combined frame or P-Delta/plastic analysis.',fontsize=9)
    path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=160);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--figure',type=Path)
    options=parser.parse_args();data=benchmark();options.output.parent.mkdir(parents=True,exist_ok=True)
    options.output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    if options.figure:plot(data,options.figure)
    print(json.dumps({key:data[key] for key in ('bounded_local_section_checks_passed','global_yield_domain_convex','frame_plastic_validated','production_ready')},indent=2))
    print(f"{len(data['records'])} bounded section records plus an explicit nonconvex-domain counterexample")
    if not data['bounded_local_section_checks_passed']:raise SystemExit('Local section checks failed; inspect the report.')
