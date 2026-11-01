"""Massless, first-order axial springs between explicit existing joints."""
from dataclasses import dataclass
import numpy as np

BEHAVIORS={'bilateral':'Bilateral','tension_only':'Tension only','compression_only':'Compression only'}


@dataclass
class JointSpring:
    name: str
    start: str
    end: str
    stiffness: float
    behavior: str = 'bilateral'


def load_definitions(data,required):
    from .model import identifier
    version=data['version']
    if version>=required and 'joint_springs' not in data:raise ValueError('Missing joint_springs field.')
    values=data.get('joint_springs',{})
    if version<required and values!={}:raise ValueError(f'Joint springs require project version {required}.')
    if not isinstance(values,dict):raise ValueError('joint_springs must be an object keyed by identifiers.')
    result={}
    for name,value in values.items():
        if not identifier(name) or not isinstance(value,dict):raise ValueError('Invalid joint spring entry.')
        try:result[name]=JointSpring(**value)
        except TypeError as error:raise ValueError(f'Joint spring {name}: {error}') from error
    return result


def coordinates(project,name):
    n=project.nodes[name]
    return np.array(n.coords if hasattr(n,'coords') else (n.x,n.y,0.),dtype=float)


def validate(project):
    from .model import identifier,finite_number
    values=project.joint_springs
    if not isinstance(values,dict):raise ValueError('joint_springs must be an object keyed by identifiers.')
    used=set(project.nodes)|set(project.members)
    for name,spring in values.items():
        if not isinstance(spring,JointSpring) or not identifier(name) or spring.name!=name or name in used:
            raise ValueError('Joint springs need distinct identifiers, separate from nodes/members.')
        if not isinstance(spring.start,str) or not isinstance(spring.end,str) or spring.start not in project.nodes or spring.end not in project.nodes:
            raise ValueError(f'Joint spring {name}: choose two existing joints.')
        if spring.start==spring.end or np.linalg.norm(coordinates(project,spring.end)-coordinates(project,spring.start))<=1e-8:
            raise ValueError(f'Joint spring {name}: endpoints must be distinct and separated by more than the geometry tolerance.')
        if not finite_number(spring.stiffness) or spring.stiffness<=0:
            raise ValueError(f'Joint spring {name}: stiffness must be finite and positive, canonical kip/in.')
        if not isinstance(spring.behavior,str) or spring.behavior not in BEHAVIORS:
            raise ValueError(f'Joint spring {name}: invalid bilateral/tension_only/compression_only behavior.')



def attach(model,project):
    for s in project.joint_springs.values():
        # Activation/reactivation is controlled by our checked active-set solver.
        model.add_spring(s.name,s.start,s.end,s.stiffness)


def result_values(project,result,name):
    s=project.joint_springs[name];axis=coordinates(project,s.end)-coordinates(project,s.start);axis/=np.linalg.norm(axis)
    model=result.solver;combo=result.combination
    motion=lambda node:np.array([getattr(model.nodes[node],d)[combo] for d in ('DX','DY','DZ')])
    extension=float(axis @ (motion(s.end)-motion(s.start)))
    active=bool(model.springs[name].active[combo])
    return extension,s.stiffness*extension if active else 0.,active


def result_table(project,result):
    u=project.units
    headers=['Spring','Start','End',f'Axial stiffness ({u.stiffness})','Behavior','Active',f'Extension ({u.length})',f'Axial force, tension + ({u.force})']
    rows=[]
    for name,s in project.joint_springs.items():
        extension,force,active=result_values(project,result,name)
        rows.append([name,s.start,s.end,u.to_display(s.stiffness,'stiffness'),BEHAVIORS[s.behavior],'Yes' if active else 'No',
                     u.to_display(extension,'length'),u.to_display(force,'force')])
    return headers,rows


def zigzag(a,b,shift=0.):
    a,b=np.asarray(a,dtype=float),np.asarray(b,dtype=float);delta=b-a;length=np.linalg.norm(delta)
    axis=delta/length;seed=np.eye(3)[np.argmin(abs(axis))];side=np.cross(axis,seed);side/=np.linalg.norm(side)
    # For planar links keep the decorative symbol in the XY model plane.
    if abs(delta[2])<1e-12:side=np.array((-axis[1],axis[0],0.))
    points=[a,a+.15*delta+side*length*shift]
    for i in range(1,10):points.append(a+(.15+.07*i)*delta+side*length*(shift+.035*(1 if i%2 else -1)))
    points += [a+.85*delta+side*length*shift,b]
    return np.array(points).tolist()


def geometry(project):
    pairs={}
    for name,s in project.joint_springs.items():pairs.setdefault(frozenset((s.start,s.end)),[]).append(name)
    rows=[]
    for name,s in project.joint_springs.items():
        parallel=pairs[frozenset((s.start,s.end))];shift=(parallel.index(name)-(len(parallel)-1)/2)*.12
        rows.append({'name':name,'points':zigzag(coordinates(project,s.start),coordinates(project,s.end),shift)})
    return rows


def payload(window):
    p=window.project;result=window.result;rows=[]
    for item in geometry(p):
        s=p.joint_springs[item['name']]
        if not all(window.entity_visible('nodes',node) for node in (s.start,s.end)):continue
        active=True if result is None else result_values(p,result,s.name)[2]
        rows.append({**item,'active':active})
    return rows


def definition_table(project):
    u=project.units
    return ['Spring','Start','End',f'Axial stiffness ({u.stiffness})','Behavior'],[
        [s.name,s.start,s.end,u.to_display(s.stiffness,'stiffness'),BEHAVIORS[s.behavior]] for s in project.joint_springs.values()]
