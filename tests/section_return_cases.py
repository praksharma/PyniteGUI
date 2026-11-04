"""Measured local section-return observables and independent references."""
from dataclasses import asdict
from functools import lru_cache
import numpy as np
from section_return_map import SectionReturnMap,MaterialState,surface
from section_return_reference import scalar_cycle,constrained_reference

STIFFNESS=np.diag((29000.*10.,29000.*30.,29000.*100.))
CAPACITIES=np.array((500.,500.,1000.))
PEAKS=(0.,1.5,0.,-1.5,0.,1.5,0.)


@lru_cache(maxsize=32)
def cycle(axis=2,substeps=20):
    material=SectionReturnMap(STIFFNESS,CAPACITIES);state=MaterialState();history=[]
    path=np.r_[0.,np.concatenate([np.linspace(a,b,substeps+1)[1:] for a,b in zip(PEAKS,PEAKS[1:])])]
    previous_strain=np.zeros(3);previous_energy=0.;max_energy_error=0.
    for value in path:
        strain=np.zeros(3);strain[axis]=value*CAPACITIES[axis]/STIFFNESS[axis,axis]
        old=state;r=material.update(strain,old);state=r['state']
        increment=np.asarray(state.plastic_strain)-np.asarray(old.plastic_strain)
        elastic_increment=strain-previous_strain-increment
        numerical_dissipation=.5*elastic_increment@STIFFNESS@elastic_increment
        work=float(r['force']@(strain-previous_strain))
        balance=work-(r['elastic_energy']-previous_energy)-r['dissipation_increment']-numerical_dissipation
        max_energy_error=max(max_energy_error,abs(balance))
        history.append(dict(normalized_strain=float(value),force=r['force'].tolist(),plastic_strain=list(state.plastic_strain),
            dissipation=state.dissipation,plastic=r['plastic'],yield_value=r['yield_value'],iterations=r['iterations'],
            residual=r['residual'],dissipation_increment=r['dissipation_increment']))
        previous_strain=strain;previous_energy=r['elastic_energy']
    expected=scalar_cycle(path*CAPACITIES[axis]/STIFFNESS[axis,axis],STIFFNESS[axis,axis],CAPACITIES[axis])
    actual=np.array([[r['force'][axis],r['plastic_strain'][axis],r['dissipation']] for r in history])
    return dict(axis=('N','My','Mz')[axis],substeps=substeps,states=len(path),history=history,
        max_force_error=float(max(abs(actual[:,0]-expected[:,0]))/CAPACITIES[axis]),
        max_plastic_strain_error=float(max(abs(actual[:,1]-expected[:,1]))*STIFFNESS[axis,axis]/CAPACITIES[axis]),
        max_dissipation_error=float(max(abs(actual[:,2]-expected[:,2]))/(CAPACITIES[axis]**2/STIFFNESS[axis,axis])),
        max_incremental_energy_error=max_energy_error,max_yield_overshoot=max(0.,max(r['yield_value']-1 for r in history)),
        max_return_residual=max(r['residual'] for r in history),final_state=asdict(state))


@lru_cache(maxsize=64)
def mixed(trial):
    trial=np.array(trial);material=SectionReturnMap(STIFFNESS,CAPACITIES)
    strain=np.linalg.solve(STIFFNESS,CAPACITIES*trial);r=material.update(strain)
    reference=constrained_reference(trial,STIFFNESS,CAPACITIES)
    columns=[]
    for axis in range(3):
        step=1e-5*CAPACITIES[axis]/STIFFNESS[axis,axis];delta=np.zeros(3);delta[axis]=step
        columns.append((material.update(strain+delta)['force']-material.update(strain-delta)['force'])/(2*step))
    numerical=np.array(columns).T
    tangent_error=float(np.linalg.norm(numerical-r['tangent'])/np.linalg.norm(r['tangent']))
    normalized=r['force']/CAPACITIES
    return dict(trial=trial.tolist(),returned=normalized.tolist(),reference=reference,
        reference_error=float(np.linalg.norm(normalized-reference['point'])),consistent_tangent_relative_error=tangent_error,
        yield_value=r['yield_value'],curvature=r['curvature'],return_residual=r['residual'],
        dissipation_increment=r['dissipation_increment'],iterations=r['iterations'],
        plastic_strain=list(r['state'].plastic_strain),qualification=r['qualification'])
