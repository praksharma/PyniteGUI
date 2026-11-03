"""Research-only raw-engine P-Delta pushover diagnostics, never app imports.

The half-axial variant is an isolated diagnostic, not a repaired solver. The
patch is confined to a context and restored even if the solve raises. Neither
this helper nor its results may be imported by production application code.
"""
from functools import lru_cache
from inspect import signature
from unittest.mock import patch
import numpy as np
from Pynite import FEModel3D
from Pynite.Member3D import Member3D
from combined_pushover_reference import column_field,energy_column

LENGTH=120.
E=29000.
INERTIA=100.
AREA=1000.
RIGIDITY=E*INERTIA
CRITICAL=np.pi**2*RIGIDITY/(4*LENGTH**2)
YIELD_STRESS=1e9  # Deliberately no yielding: validate the elastic prerequisite first.


def supports_combined():return 'P_Delta' in signature(FEModel3D.analyze_pushover).parameters


def _build(segments,ratio,steps,path,force,plane,origin):
    if type(segments) is not int or not 1<=segments<=32 or type(steps) is not int or not 1<=steps<=2000:
        raise ValueError('Bound research meshes/steps to 1–32 and 1–2000.')
    if path not in ('preload','ramp'):raise ValueError('Choose preload or ramp loading.')
    if plane not in ('XY','YZ'):raise ValueError('Choose the verified XY or YZ column plane.')
    if not np.isfinite([ratio,force,*origin]).all() or abs(ratio)>.4:raise ValueError('Research loads exceed the bounded scope.')
    lateral=0 if plane=='XY' else 2;rotation=2 if plane=='XY' else 0
    model=FEModel3D();model.add_material('Steel',E,11200.,.3,0.,YIELD_STRESS)
    model.add_steel_section('I',AREA,INERTIA,INERTIA,1.,20.,20.,'Steel')
    for i in range(segments+1):
        point=np.asarray(origin,float).copy();point[1]+=LENGTH*i/segments
        model.add_node(str(i),*point)
        flags=[True]*6
        if i:flags[lateral]=flags[1]=flags[rotation+3]=False
        model.def_support(str(i),*flags)
        if i:model.add_member(str(i),str(i-1),str(i),'Steel','I')
    model.add_node_load(str(segments),'FY',-ratio*CRITICAL,'D' if path=='preload' else 'Push')
    model.add_node_load(str(segments),'FX' if plane=='XY' else 'FZ',force,'Push')
    model.add_load_combo('Primary',{'D':1.});model.add_load_combo('Push',{'Push':1/steps})
    return model,lateral,rotation


@lru_cache(maxsize=128)
def probe(segments=8,ratio=.3,steps=100,path='preload',variant='raw',force=1.,plane='XY',origin=(0.,0.,0.)):
    if variant not in ('raw','half_axial_diagnostic','first_order','elastic_p_delta'):
        raise ValueError('Unknown research variant.')
    if variant in ('raw','half_axial_diagnostic') and not supports_combined():
        return dict(supported=False,reason='Installed engine has no public P_Delta pushover option.')
    model,lateral,rotation=_build(segments,ratio,steps,path,force,plane,origin)
    records=[];axial_arguments=[];original=Member3D.kg
    def kg(member,P=0.):
        actual=P
        if member.model.solution=='Pushover' and getattr(member.model,'_pushover_P_Delta',False):
            axial_arguments.append(float(P))
            if variant=='half_axial_diagnostic':actual=P/2
        return original(member,actual)
    def capture(combo):
        index=len(records)+1;factor=index/steps
        nodes=[model.nodes[str(i)] for i in range(segments+1)]
        motion=np.array([[getattr(n,dof)[combo] for dof in ('DX','DY','DZ')] for n in nodes])
        internal=np.zeros((segments+1,6));phis=[];axials=[]
        for i in range(1,segments+1):
            member=next(iter(model.members[str(i)].sub_members.values()))
            f=member.f(combo)[:,0];global_f=member.T().T@f
            internal[i-1]+=global_f[:6];internal[i]+=global_f[6:]
            axials.append(float((f[0]-f[6])/2))
            phis.extend(float(member.section.Phi(*f[list(indices)])) for indices in ((0,4,5),(6,10,11)))
        compression=float(np.mean(axials));h=factor*force
        expected=column_field(np.linspace(0.,LENGTH,segments+1),LENGTH,RIGIDITY,compression,h)
        discrete,backward=energy_column(segments,LENGTH,RIGIDITY,compression,h)
        actual=motion[:,lateral]
        external=np.zeros_like(internal);external[-1,lateral]=h
        external[-1,1]=-ratio*CRITICAL*(1. if path=='preload' else factor)
        reaction=internal[0]-external[0]
        # Actual deformed lever arms, including axial shortening and translated
        # origin. Global moments are about the displaced base, not the old mesh.
        coords=np.array([[n.X,n.Y,n.Z] for n in nodes])+motion
        lever=coords[-1]-coords[0]
        moment= reaction[3:]+np.cross(lever,external[-1,:3])+external[-1,3:]
        free=[]
        for i,n in enumerate(nodes):
            for d,dof in enumerate(('DX','DY','DZ','RX','RY','RZ')):
                if not getattr(n,'support_'+dof):free.append(internal[i,d]-external[i,d])
        reference_tip=float(expected[-1,0]);scale=max(abs(reference_tip),np.finfo(float).tiny)
        record=dict(factor=factor,tip_translation_in=float(actual[-1]),reference_tip_in=reference_tip,
            compression_kip=compression,applied_compression_kip=float(-external[-1,1]),
            continuum_relative_error=float(np.linalg.norm(actual-expected[:,0])/max(np.linalg.norm(expected[:,0]),np.finfo(float).tiny)),
            discrete_relative_error=float(np.linalg.norm(actual-discrete[:,0])/max(np.linalg.norm(discrete[:,0]),np.finfo(float).tiny)),
            tip_relative_error=float((actual[-1]-reference_tip)/scale),base_reaction= reaction.tolist(),
            deformed_moment_residual_kip_in=moment.tolist(),free_joint_residual=float(max(map(abs,free),default=0.)),
            max_yield_interaction=float(max(phis)),reference_backward_error=backward)
        if not np.isfinite(motion).all() or not np.isfinite(list(record['base_reaction'])).all():raise ValueError('Nonfinite research solve.')
        records.append(record)
        return float(actual[-1])
    with patch.object(Member3D,'kg',kg):
        if variant=='elastic_p_delta':
            # Solve the complete final pattern by the ordinary elastic path.
            model.load_combos['Primary'].factors={'D':1.,'Push':1.}
            model.load_combos.pop('Push');model.analyze_PDelta(max_iter=100)
            # Capture expects one full increment in this separate baseline.
            steps=1;capture('Primary')
        else:
            options={'P_Delta':variant!='first_order'} if supports_combined() else {}
            model.analyze_pushover(push_combo='Push',max_iter=100,tol=1e-10,traces={'research':capture},**options)
    maximum=max(r['max_yield_interaction'] for r in records)
    if maximum>=1e-10:raise ValueError('The elastic prerequisite unexpectedly yielded.')
    return dict(supported=True,segments=segments,steps=steps,ratio=ratio,path=path,variant=variant,force_kip=force,
        plane=plane,origin=list(origin),history=records,final=records[-1],max_yield_interaction=maximum,
        geometric_arguments=axial_arguments[-min(len(axial_arguments),4):],production_ready=False)
