"""Reproduce boundary/graded/interface shear evidence and unresolved opening gates.

Research only: no recovered shear enters the application or accepted snapshots.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import numpy as np
from quad_shear_boundaries import CASES,SIZES,FACTORS,OpeningRitz,solve_case,relative_l2,opening_mean_shear

BOXES={'corner':(0.,20.,0.,20.),'outer_strip':(0.,20.,40.,80.),'near_rim':(20.,40.,48.,72.)}
REFERENCE_LIMIT=.005


def references():
    data={name:[] for name in BOXES}
    conditions=[]
    for terms in (9,11,13):
        reference=OpeningRitz(120,120,.2,40,40,terms=terms)
        conditions.append(dict(terms=terms,condition=reference.condition))
        for name,box in BOXES.items():data[name].append((-1e-7*reference.mean_shears(box)).tolist())
    result={}
    for name,values in data.items():
        a,b=np.array(values[-2:]);gap=float(np.linalg.norm(a-b)/np.linalg.norm(b))
        result[name]=dict(box_in=BOXES[name],mean_shear_kip_per_in=values,relative_basis_gap=gap,
                          reference_stable=bool(gap<REFERENCE_LIMIT))
    try:OpeningRitz(120,120,.2,40,40,terms=17)
    except ValueError as error:higher=dict(terms=17,accepted=False,message=str(error))
    else:higher=dict(terms=17,accepted=True,message='Review whether reference conditioning changed.')
    return dict(conditions=conditions,patches=result,higher_truncation=higher,relative_gap_limit=REFERENCE_LIMIT)


def benchmark():
    reference=references();records=[]
    for case in CASES:
        for size in SIZES.get(case,(30.,15.,7.5)):
            for combination,sample in solve_case(case,size).items():
                v=sample['valid'];counts={str(k):int(n) for k,n in zip(*np.unique(sample['status'],return_counts=True))}
                record=dict(case=case,plane='XY',mesh_size_in=size,combination=combination,elements=len(v),
                    available=int(v.sum()),statuses=counts,equilibrium_verified=True)
                if sample['reference'] is not None:
                    record['errors']={}
                    for name,mask in (('all',v),('outer_boundary_row',v&sample['outer']),('interior',v&~sample['outer'])):
                        if mask.any():
                            record['errors'][name]=dict(recovered_relative_l2=relative_l2(sample['shear'],sample['reference'],sample['areas'],mask),
                                raw_relative_l2=relative_l2(sample['raw'],sample['reference'],sample['areas'],mask),
                                recovered_max_absolute_error=float(abs(sample['shear'][mask]-sample['reference'][mask]).max()))
                else:
                    record['opening_means']={}
                    for name,ref in reference['patches'].items():
                        actual=opening_mean_shear(sample,ref['box_in']);expected=np.array(ref['mean_shear_kip_per_in'][-1])*FACTORS[combination]
                        difference=float(np.linalg.norm(actual-expected));denominator=np.linalg.norm(expected)
                        record['opening_means'][name]=dict(recovered_kip_per_in=actual.tolist(),reference_stable=ref['reference_stable'],
                            reference_kip_per_in=expected.tolist(),diagnostic_absolute_difference=difference,
                            relative_difference=difference/denominator if ref['reference_stable'] and denominator else None)
                records.append(record)
    checks=True
    for case in ('boundary','graded','coupled_boundary','coupled_graded'):
        rows=[r for r in records if r['case']==case and r['combination']=='Service']
        for region,limit in (('all',.02),('outer_boundary_row',.03),('interior',.003)):
            errors=[r['errors'][region]['recovered_relative_l2'] for r in rows]
            checks &= all(b<a for a,b in zip(errors,errors[1:])) and errors[-1]<limit
    for r in records:
        if r['case'].startswith('stiffness') and r['available'] and r['combination']!='Zero':
            checks &= r['errors']['all']['recovered_relative_l2']<1e-6
        if r['combination']=='Zero':
            checks &= all(region['recovered_max_absolute_error']<1e-12 for region in r.get('errors',{}).values())
            checks &= all(region['diagnostic_absolute_difference']<1e-12 for region in r.get('opening_means',{}).values())
        if r['case']=='opening' and r['combination']!='Zero':
            checks &= r['opening_means']['corner']['relative_difference']<(.04 if r['mesh_size_in']==10. else .01)
    checks &= reference['patches']['corner']['reference_stable']
    checks &= not reference['patches']['outer_strip']['reference_stable'] and not reference['patches']['near_rim']['reference_stable']
    checks &= not reference['higher_truncation']['accepted']
    return dict(bounded_checks_passed=bool(checks),production_ready=False,
        python=platform.python_version(),pynite=version('pynitefea'),brecon=version('brecon'),
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('tests/quad_shear_boundaries.py','tests/plate_reference.py','scripts/benchmark_quad_shear_boundaries.py')},
        units=dict(length='in',pressure='kip/in2',shear='kip/in'),
        scope='Standalone and negligible-edge-beam coupled 120x180x0.6 in thin plates, uniform/graded rectangular meshes, outer boundary rows, and two nu=0 cantilever directions with E x4 and thickness x1.5 interfaces. Separate 120x120 in plate with a 40x40 in free square opening. XY report; XY/XZ/YZ and signed/zero invariance checked by regression tests.',
        method='Test-only quadratic centre-moment fits on complete contiguous 3x3 Cartesian stencils in one constitutive region. Centred stencils preferred; one-sided stencils allowed only with the target inside the patch. No nearest-point bridging of holes or jumps; excessive grading/rank loss/thin regions return NaN with status. This is smoothed equilibrium recovery, not raw element shear or an unsmoothed probe.',
        reference='Independent Kirchhoff Navier series (160/320 boundary truncation check in tests), cantilever cut force Q=q(L-x), and analytic area means of opening Rayleigh-Ritz third derivatives. Opening basis sizes 9/11/13, original condition limit 1e8 retained at size 17.',
        interpretation='bounded_checks_passed only verifies the stated bounds and preserves the negative opening gates. It is not permission to expose shear. Missing stencils remain missing; finite recovered values do not imply verified accuracy.',
        unresolved=['Opening outer-strip reference changes by more than 0.5% from 11 to 13 terms.',
                    'Near-rim opening reference is not converged; higher truncation breaches the existing conditioning limit.',
                    'Opening/reentrant-corner peaks, arbitrary irregular/skew/thick/curved elements and general frame-shell interfaces remain unverified.',
                    'No production integration: Quad shear remains unavailable in plots, probes, CSV and MCP.'],
        opening_reference=reference,records=records)


def plot(data,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullLocator
    fig,axes=plt.subplots(1,3,figsize=(14,4.7),layout='none')
    fig.subplots_adjust(left=.055,right=.99,bottom=.22,top=.81,wspace=.34)
    colors={'boundary':'#207b70','graded':'#455e9e','coupled_boundary':'#207b70','coupled_graded':'#455e9e'}
    for case in colors:
        rows=[r for r in data['records'] if r['case']==case and r['combination']=='Service']
        axes[0].plot([r['elements'] for r in rows],[100*r['errors']['outer_boundary_row']['recovered_relative_l2'] for r in rows],
            'o--' if case.startswith('coupled') else 'o-',color=colors[case],label=case.replace('_',' '),alpha=.8)
    axes[0].set(title='Outer boundary rows',xlabel='Quad elements',ylabel='Shear vector L2 error (%)',xscale='log',yscale='log')
    axes[0].set_xticks([24,100,425],labels=['24','100','425']);axes[0].xaxis.set_minor_locator(NullLocator())
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    patches=data['opening_reference']['patches'];names=list(patches)
    axes[1].bar(range(3),[100*patches[n]['relative_basis_gap'] for n in names],
                     color=['#207b70' if patches[n]['reference_stable'] else '#b85427' for n in names])
    axes[1].axhline(.5,ls='--',color='#555555',label='0.5% reference gate')
    axes[1].set_xticks(range(3),[n.replace('_',' ') for n in names]);axes[1].set(title='Opening reference still incomplete',ylabel='11 to 13 term basis gap (%)',yscale='log')
    axes[1].legend(fontsize=8);axes[1].grid(axis='y',alpha=.2)
    for case,label,color in (('stiffness_x','x cantilever','#207b70'),('stiffness_y','y cantilever','#455e9e')):
        rows=[r for r in data['records'] if r['case']==case and r['combination']=='Service']
        axes[2].plot([r['elements'] for r in rows],[100*r['available']/r['elements'] for r in rows],'o-',label=label,color=color)
    axes[2].set(title='Do not cross stiffness interfaces',xlabel='Quad elements',ylabel='Available same-region stencils (%)',ylim=(-5,105),xscale='log')
    axes[2].set_xticks([24,96,384],labels=['24','96','384']);axes[2].xaxis.set_minor_locator(NullLocator())
    axes[2].legend(fontsize=8);axes[2].grid(alpha=.2)
    fig.suptitle('Brecon: one-sided Quad-shear validation',fontsize=14,y=.97)
    fig.supxlabel('Research only. Opening reference gates remain unresolved; no production Quad-shear output is enabled.',fontsize=10,y=.025)
    path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=150,bbox_inches='tight',pad_inches=.15);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--figure',type=Path)
    args=parser.parse_args();data=benchmark();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    if args.figure:plot(data,args.figure)
    print(f"{'PASS' if data['bounded_checks_passed'] else 'FAIL'}: {len(data['records'])} bounded records; production_ready=False; opening gates remain unresolved")
    if not data['bounded_checks_passed']:raise SystemExit(1)
