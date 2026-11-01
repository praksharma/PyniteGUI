"""Reproduce independent Hermite energy references and opening recovery gaps."""
import argparse
from functools import lru_cache
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import numpy as np
from plate_energy_reference import OpeningEnergyReference
from plate_reference import OpeningRitz
from quad_shear_boundaries import solve_case,relative_l2,opening_mean_shear

PATCHES={'corner':(0.,20.,0.,20.),'outer_strip':(0.,20.,40.,80.),'near_rim':(20.,40.,48.,72.)}
GRIDS=(48,72,96)


@lru_cache(maxsize=6)
def energy_reference(n,order):return OpeningEnergyReference(nx=n,order=order)


def benchmark():
    references=[];gaps={};checks=True
    for order in (1,2):
        history=[]
        for n in GRIDS:
            reference=energy_reference(n,order)
            means={name:(-1e-7*reference.mean_shears(box)).tolist() for name,box in PATCHES.items()}
            history.append(means)
            references.append(dict(family='bicubic_C1' if order==1 else 'biquintic_C2',grid_n=n,order=order,
                **reference.diagnostics,means_kip_per_in=means))
        gaps[str(order)]={name:float(np.linalg.norm(np.array(history[-1][name])-history[-2][name])/np.linalg.norm(history[-1][name])) for name in PATCHES}
        checks &= all(gap<.005 for gap in gaps[str(order)].values())
    first,last=energy_reference(96,1),energy_reference(96,2)
    cross={name:float(np.linalg.norm(first.mean_shears(box)-last.mean_shears(box))/np.linalg.norm(last.mean_shears(box))) for name,box in PATCHES.items()}
    checks &= all(gap<.005 for gap in cross.values())
    candidates=[];coarse,fine=energy_reference(72,2),last
    corners=np.array([[40.,40.],[40.,80.],[80.,40.],[80.,80.]])
    for size in (10.,5.,4.):
        sample=solve_case('opening',size)['Service'];points=sample['points'];x,y=points.T
        distance=np.min(np.linalg.norm(points[:,None]-corners[None],axis=2),axis=1)
        away=sample['valid']&(distance>=10.)
        rim=away&(x>=20.)&(x<=40.)&(y>=48.)&(y<=72.)
        a,b=-1e-7*coarse.shears(points),-1e-7*fine.shears(points)
        regions={}
        for name,selected in (('away_from_corners',away),('near_rim',rim)):
            ref_error=relative_l2(a,b,sample['areas'],selected)
            error=relative_l2(sample['shear'],b,sample['areas'],selected)
            regions[name]=dict(compared_cells=int(selected.sum()),reference_relative_l2=ref_error,recovery_relative_l2=error)
            checks &= ref_error<.005
        means={name:dict(recovered_kip_per_in=opening_mean_shear(sample,box).tolist(),
                         reference_kip_per_in=(-1e-7*fine.mean_shears(box)).tolist()) for name,box in PATCHES.items()}
        candidates.append(dict(mesh_size_in=size,elements=len(points),regions=regions,means=means))
    # Preserve the actual production rejection: the reference now converges for
    # these observables, while the current recovery does not meet a 5% rim gate.
    reference_ready=bool(checks)
    checks &= candidates[-1]['regions']['near_rim']['recovery_relative_l2']>.10
    legacy=OpeningRitz(120.,120.,.2,40.,40.,terms=13)
    try:OpeningRitz(120.,120.,.2,40.,40.,terms=17)
    except ValueError as error:legacy_guard=str(error)
    else:raise ValueError('Original sine-reference condition rejection unexpectedly changed.')
    return dict(bounded_checks_passed=bool(checks),bounded_reference_observables_ready=reference_ready,production_ready=False,
        python=platform.python_version(),numpy=version('numpy'),scipy=version('scipy'),pynite=version('pynitefea'),brecon=version('brecon'),
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('tests/plate_energy_reference.py','tests/plate_reference.py','tests/quad_shear_boundaries.py','scripts/benchmark_opening_shear.py')},
        units=dict(length='in',pressure='kip/in2',shear='kip/in',compliance='in6 (D * integral(w dA) / q)'),
        definition='120x120 in isotropic Kirchhoff plate, nu=0.2, D=1, centred 40x40 in free opening, simply supported outer traces; q=-1e-7 kip/in2 for shear comparisons. No hole-edge restraints. Scale w by q/D, M and Q by q.',
        method='Independently assembled continuum curvature energy with conforming tensor-Hermite polynomials: 16-DOF bicubic C1 and 36-DOF biquintic C2 rectangles. Exact-degree Gaussian integration, width normalization, sparse solves, eigen-residual-aware condition estimate <=1e8, free residual, energy/work and global rigid force/moment checks. Reference imports neither application nor PyNite.',
        source_background='https://arxiv.org/abs/1911.00239 (tensor-Hermite plate space background only; our boundary-fitted grid uses neither cut stabilization nor Nitsche terms)',
        scope='Reference area means on three fixed material patches, two polynomial families, 48/72/96 grids. Pointwise reference/recovery comparisons use fixed FE cell centres at least 10 in from every reentrant corner; near-rim centres additionally lie in x=20..40,y=48..72 in. Relative L2 uses exact cell areas. This does not certify corner peaks or an entire arbitrary opening.',
        reference_gate=.005,production_recovery_rim_gate=.05,reference_mesh_gaps=gaps,cross_family_gaps=cross,
        legacy_sine_means_kip_per_in={name:(-1e-7*legacy.mean_shears(box)).tolist() for name,box in PATCHES.items()},
        legacy_17_term_rejection=legacy_guard,references=references,candidates=candidates,
        interpretation='bounded_checks_passed preserves both converged reference evidence and an explicit failed recovery gate. Bounded reference observables are now ready; recovered Quad shear is not production ready. Original sine reference/reports stay unchanged.',
        unresolved=['About 12% shear-vector L2 error remains in the finest tested free-rim region.',
                    'Pointwise reentrant-corner shear does not have a converged reference in this study.',
                    'General opening geometry, irregular/thick/curved shells and frame-shell interfaces remain unvalidated.'])


def plot(data,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullLocator
    fig,axes=plt.subplots(1,3,figsize=(14,4.7),layout='none')
    fig.subplots_adjust(left=.065,right=.99,bottom=.22,top=.81,wspace=.34)
    for order,label,color in ((1,'Bicubic C1','#455e9e'),(2,'Biquintic C2','#207b70')):
        rows=[r for r in data['references'] if r['order']==order]
        axes[0].plot([r['grid_n'] for r in rows],[1e8*r['means_kip_per_in']['near_rim'][0] for r in rows],'o-',label=label,color=color)
        axes[2].plot([r['grid_n'] for r in rows],[r['condition'] for r in rows],'o-',label=label,color=color)
    axes[0].set(title='Independent free-rim area mean',xlabel='Grid divisions per side',ylabel='Mean Qx (10⁻⁸ kip/in)')
    axes[0].legend(fontsize=9);axes[0].grid(alpha=.2)
    for name,label,color in (('away_from_corners','Away from corners','#207b70'),('near_rim','Near free rim','#b85427')):
        axes[1].plot([r['elements'] for r in data['candidates']],[100*r['regions'][name]['recovery_relative_l2'] for r in data['candidates']],
                     'o-',label=label,color=color)
    axes[1].axhline(5.,ls='--',color='#555555',label='5% rim recovery gate')
    axes[1].set(title='Recovery still fails near rim',xlabel='Quad elements',ylabel='Shear vector L2 error (%)',xscale='log',yscale='log')
    axes[1].set_xticks([128,512,800],labels=['128','512','800']);axes[1].xaxis.set_minor_locator(NullLocator())
    axes[1].legend(fontsize=8);axes[1].grid(alpha=.2)
    axes[2].axhline(1e8,ls='--',color='#555555',label='Unchanged 1e8 limit')
    axes[2].set(title='Conditioning remains checked',xlabel='Grid divisions per side',ylabel='Scaled stiffness condition',yscale='log')
    axes[2].legend(fontsize=8);axes[2].grid(alpha=.2)
    for ax in (axes[0],axes[2]):ax.set_xticks(GRIDS)
    fig.suptitle('Brecon: independent opening-shear reference',fontsize=14,y=.97)
    fig.supxlabel('Selected reference observables converge. Free-rim recovery and corner peaks remain outside production results.',fontsize=10,y=.025)
    path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path,dpi=150,bbox_inches='tight',pad_inches=.15);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--figure',type=Path)
    args=parser.parse_args();data=benchmark();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    if args.figure:plot(data,args.figure)
    print(f"{'PASS' if data['bounded_checks_passed'] else 'FAIL'}: 6 independent references, 3 recovery meshes; bounded reference ready; production_ready=False")
    if not data['bounded_checks_passed']:raise SystemExit(1)
