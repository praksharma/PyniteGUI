"""Research-only constant-resultant segment and finite plastic-zone compatibility.

Conjugate pairs are (N, My, Mz) and (extension, rotation_y, rotation_z).
An elastic remainder plus a plastic zone share the same resultants. This is
not a 12-DOF beam, a bending-gradient integration or a frame assembly.
"""
from dataclasses import dataclass
import numpy as np
from section_return_map import SectionReturnMap,MaterialState


@dataclass(frozen=True)
class SegmentState:
    plastic_deformation: tuple=(0.,0.,0.)
    dissipation: float=0.

    def __post_init__(self):
        checked=MaterialState(self.plastic_deformation,self.dissipation)
        object.__setattr__(self,'plastic_deformation',checked.plastic_strain)
        object.__setattr__(self,'dissipation',checked.dissipation)


class ConstantResultantSegment:
    def __init__(self,section_stiffness,capacities,length,plastic_length):
        if (isinstance(length,bool) or isinstance(plastic_length,bool) or not np.isfinite([length,plastic_length]).all()
                or not 0<plastic_length<=length):
            raise ValueError('Require finite 0 < plastic length <= segment length.')
        self.length=float(length);self.plastic_length=float(plastic_length)
        # Series compatibility: u = L*C^-1*f + u_p. The equivalent elastic
        # stiffness is C/L, never C/lp plus a second full-length elastic beam.
        self.material=SectionReturnMap(np.asarray(section_stiffness,float)/self.length,capacities)
        self.section_stiffness=self.material.C*self.length

    def update(self,deformation,old=SegmentState(),max_iterations=30):
        if not isinstance(old,SegmentState):raise ValueError('Use committed segment deformation history.')
        material_old=MaterialState(old.plastic_deformation,old.dissipation)
        result=self.material.update(deformation,material_old,max_iterations)
        updated=result['state'];force=result['force'];plastic=np.array(updated.plastic_strain)
        elastic_strain=np.linalg.solve(self.section_stiffness,force)
        zone=self.plastic_length*elastic_strain+plastic
        remainder=(self.length-self.plastic_length)*elastic_strain
        error=np.asarray(deformation)-zone-remainder
        yield_scale=np.linalg.norm(np.linalg.solve(self.material.C,np.diag(self.material.cap)),axis=1)
        scale=np.maximum(abs(np.asarray(deformation))+abs(zone)+abs(remainder),yield_scale)
        if np.max(abs(error)/scale)>1e-8:raise ValueError('Constant-resultant compatibility failed; no state committed.')
        density=.5*float(force@elastic_strain)
        state=SegmentState(tuple(plastic),updated.dissipation)
        return dict(force=force,tangent=result['tangent'],state=state,plastic=result['plastic'],
            plastic_zone_strain=plastic/self.plastic_length,zone_deformation=zone,remainder_deformation=remainder,
            zone_elastic_energy=self.plastic_length*density,remainder_elastic_energy=(self.length-self.plastic_length)*density,
            elastic_energy=self.length*density,dissipation_increment=result['dissipation_increment'],
            zone_dissipation_density=updated.dissipation/self.plastic_length,
            compatibility_residual=error,yield_value=result['yield_value'],qualification='constant_resultant_segment_only')
