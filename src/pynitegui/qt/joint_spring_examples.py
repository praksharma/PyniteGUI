"""Independent series, opposing one-way and oblique spatial spring checks."""
from .model import Project,Node,Load
from .joint_springs import JointSpring

NAMES={'joint_spring_series':'Joint Springs - Series Network',
       'joint_spring_one_way':'Joint Springs - Opposing One-Way Pair',
       '3d_joint_spring_network':'3D Joint Springs - Oblique Network'}
NOTES={
    'joint_spring_series':('Two massless axial springs, k = 100 and 200 kip/in, connect three horizontal joints. A is fixed; B/C slide in X. A 10 kip force acts at C.',
        'Service: B DX = +0.1 in, C DX = +0.15 in; both springs carry +10 kip tension. Equivalent stiffness is 66.6667 kip/in. Springs have no self-weight; rotations without physical stiffness are undefined.'),
    'joint_spring_one_way':('Parallel tension-only 200 kip/in and compression-only 300 kip/in links connect A to B. B slides in X under +10 kip, −10 kip and zero combinations. Iterative elastic is selected.',
        'Service: B DX = +0.05 in, tension link +10 kip. Reverse: B DX = −0.0333333 in, compression link −10 kip. The opposing pair is stable at zero load; no artificial residual stiffness is added.'),
    '3d_joint_spring_network':('Three oblique orthogonal spring directions connect a free translating joint to fixed anchors. Principal stiffnesses are 100/200/300 kip/in; global force is (10,20,−30) kip.',
        'Independent reference: solve R diag(k) Rᵀ u = F; total reaction is (−10,−20,+30) kip. Links transfer axial force only; joint rotations without stiffness are undefined. Inspect the Joint springs result tab.'),
}


def example_project(key,unit_system='imperial'):
    if key=='3d_joint_spring_network':
        import numpy as np
        from .spatial_model import SpatialProject,SpatialNode,SpatialLoad
        from scipy.spatial.transform import Rotation
        p=SpatialProject(unit_system=unit_system)
        R=Rotation.from_rotvec([.4,-.3,.2]).as_matrix();center=np.array([0.,120.,0.])
        p.nodes['B']=SpatialNode('B',*center[:2],z=center[2])
        for i,k in enumerate((100.,200.,300.)):
            name='A'+str(i+1);point=center-120*R[:,i]
            p.nodes[name]=SpatialNode(name,*point[:2],z=point[2],support='fixed')
            p.joint_springs['S'+str(i+1)]=JointSpring('S'+str(i+1),name,'B',k)
        for direction,value in zip(('FX','FY','FZ'),(10.,20.,-30.)):
            p.loads[direction]=SpatialLoad(direction,'B',direction,value)
    else:
        p=Project(unit_system=unit_system,nodes={'A':Node('A',0.,0.,support='fixed'),'B':Node('B',120.,0.,support='roller')})
        if key=='joint_spring_series':
            p.nodes['C']=Node('C',240.,0.,support='roller')
            p.joint_springs={'S1':JointSpring('S1','A','B',100.),'S2':JointSpring('S2','B','C',200.)}
            p.loads['P']=Load('P','C','FX',10.)
        elif key=='joint_spring_one_way':
            p.analysis_method='iterative';p.combinations.update(Reverse={'Case 1':-1.},Zero={'Case 1':0.})
            p.joint_springs={'T':JointSpring('T','A','B',200.,'tension_only'),'C':JointSpring('C','A','B',300.,'compression_only')}
            p.loads['P']=Load('P','B','FX',10.)
        else:raise ValueError('Unknown joint spring example.')
    p.validate();return p
