"""Unit-labelled accepted-step results, without silent partial/full conflation."""
import numpy as np
from .pushover import DOFS,COMPONENTS


def step_index(result,step):
    if step is None:return len(result.factors)-1
    if type(step) is not int or not 0<=step<len(result.factors):raise ValueError('Choose a recorded accepted step, including 0 for elastic preload.')
    return step


def pushover_table(result,units,kind='capacity',step=None):
    p,s=result.project,result.settings
    selected=step_index(result,step)
    control_quantity='rotation' if s.control_direction.startswith('R') else 'length'
    control_unit='rad' if control_quantity=='rotation' else units.length
    reaction_quantity='force' if s.resultant.startswith('F') else 'moment'
    reaction_unit=getattr(units,reaction_quantity)
    if kind=='capacity':
        headers=['Step','Push factor',f'{s.control_node} {s.control_direction} ({control_unit})',
            f'Selected supports Σ{s.resultant} ({reaction_unit})','Max end steel Φ','Max equilibrium ratio']
        ratios=np.max(abs(result.equilibrium)/result.equilibrium_limits,axis=1)
        return headers,[[i,float(factor),units.to_display(float(point[0]),control_quantity),units.to_display(float(point[1]),reaction_quantity),
            float(np.max(result.phis[i])),float(ratios[i])] for i,(factor,point) in enumerate(zip(result.factors,result.curve))]
    if kind in ('nodes','displacements','reactions'):
        motion_units=[units.length]*3+['rad']*3
        reaction_units=[units.force]*3+[units.moment]*3
        headers=['Node',*(f'{key} ({unit})' for key,unit in zip(DOFS,motion_units)),*(f'{key} ({unit})' for key,unit in zip(COMPONENTS,reaction_units))]
        rows=[]
        for i,name in enumerate(p.nodes):
            rows.append([name,*(units.to_display(float(v),'length' if j<3 else 'rotation') for j,v in enumerate(result.displacements[selected,i])),
                *(units.to_display(float(v),'force' if j<3 else 'moment') for j,v in enumerate(result.reactions[selected,i]))])
        if kind=='displacements':return headers[:7],[row[:7] for row in rows]
        if kind=='reactions':return [headers[0],*headers[7:]],[[row[0],*row[7:]] for row in rows]
        return headers,rows
    if kind=='member_ends':
        headers=['Member','End','Node',*(f'Local {key} ({units.force if i<3 else units.moment})' for i,key in enumerate(COMPONENTS)),'Steel Φ','State']
        rows=[]
        for i,(name,member) in enumerate(p.members.items()):
            plastic=p.sections[member.section].steel_material is not None
            for end,node,offset in ((0,member.start,0),(1,member.end,6)):
                rows.append([name,'Start' if end==0 else 'End',node,
                    *(units.to_display(float(v),'force' if j<3 else 'moment') for j,v in enumerate(result.end_forces[selected,i,offset:offset+6])),
                    float(result.phis[selected,i,end]) if plastic else None,result.end_states[selected][i][end]])
        return headers,rows
    if kind=='equilibrium':
        keys=COMPONENTS if getattr(p,'dimension','2D')=='3D' else ('FX','FY','MZ')
        headers=['Component','Residual','Tolerance','Units','Passed']
        rows=[]
        for key,error,limit in zip(keys,result.equilibrium[selected],result.equilibrium_limits[selected]):
            quantity='force' if key.startswith('F') else 'moment'
            rows.append([key,units.to_display(float(error),quantity),units.to_display(float(limit),quantity),getattr(units,quantity),'Yes' if abs(error)<=limit else 'No'])
        return headers,rows
    raise ValueError('Choose capacity, nodes, member_ends or equilibrium.')
