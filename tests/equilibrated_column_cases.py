"""Bounded independent observables for the elastic total-state candidate."""
from functools import lru_cache
import numpy as np
from combined_pushover_probe import _build,LENGTH,RIGIDITY,CRITICAL
from combined_pushover_reference import column_field,energy_column
from equilibrated_beam_column import ElasticSystem


@lru_cache(maxsize=128)
def corrected(segments=8,ratio=.3,steps=20,path='ramp',force=1.,plane='XY',origin=(0.,0.,0.)):
    model,lateral,rotation=_build(segments,ratio,steps,path,force,plane,origin)
    system=ElasticSystem(model);preload=model.P('Primary').ravel();push=steps*model.P('Push').ravel()
    states=system.path(preload,push,steps);records=[]
    for data in states:
        factor=data['factor'];external=(preload+factor*push).reshape(-1,6)
        displacement=data['motion'].reshape(-1,6);internal=data['internal'].reshape(-1,6)
        compression=float(-np.mean(data['axial']));h=factor*force
        expected=column_field(np.linspace(0.,LENGTH,segments+1),LENGTH,RIGIDITY,compression,h)
        discrete,backward=energy_column(segments,LENGTH,RIGIDITY,compression,h)
        actual=displacement[:,lateral];rotation_sign=1. if plane=='XY' else -1.
        theta=rotation_sign*displacement[:,rotation+3]
        reaction=internal[0]-external[0]
        coords=np.array([(node.X,node.Y,node.Z) for node in system.nodes])+displacement[:,:3]
        total_moment=reaction[3:]+np.cross(coords[-1]-coords[0],external[-1,:3])+external[-1,3:]
        norm=np.linalg.norm(expected[:,0]);rot_norm=np.linalg.norm(expected[:,1]);energy_norm=np.linalg.norm(discrete[:,0])
        records.append(dict(factor=factor,tip_translation_in=float(actual[-1]),reference_tip_in=float(expected[-1,0]),
            continuum_relative_error=float(np.linalg.norm(actual-expected[:,0])/norm) if norm else None,
            continuum_absolute_error_in=float(np.linalg.norm(actual-expected[:,0])),
            discrete_relative_error=float(np.linalg.norm(actual-discrete[:,0])/energy_norm) if energy_norm else None,
            discrete_absolute_error_in=float(np.linalg.norm(actual-discrete[:,0])),
            rotation_relative_error=float(np.linalg.norm(theta-expected[:,1])/rot_norm) if rot_norm else None,
            rotation_absolute_error_rad=float(np.linalg.norm(theta-expected[:,1])),
            compression_kip=compression,mean_axial_error_kip=float(max(abs(data['axial']-external[-1,1]))),
            max_equilibrium_residual=float(max(abs(data['residual']))),max_scaled_residual=float(max(abs(data['residual'])/data['limits'])),
            deformed_moment_residual_kip_in=total_moment.tolist(),reference_backward_error=backward,
            iterations=data['iterations'],min_normalized_stiffness=data['min_normalized_stiffness'],
            max_yield_interaction=data['max_yield_interaction']))
    return dict(segments=segments,ratio=ratio,steps=steps,path=path,force_kip=force,plane=plane,origin=list(origin),
        final=records[-1],history=records,production_ready=False,plastic_validated=False)
