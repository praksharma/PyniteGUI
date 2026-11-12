"""Connected portal reference from independent symmetric slope-deflection equations."""
import unittest
from dataclasses import replace
import numpy as np
from planar_hinge_frame import PlanarHingeFrame

H=120.;B=120.;EA=290000.;EI=2900000.;MP=1000.
NODES=((0.,0.),(B,0.),(0.,H),(B,H))
MEMBERS=((0,2,EA,EI),(1,3,EA,EI),(2,3,EA,EI))
HINGES=((0,0,MP),(1,0,MP),(0,1,MP),(1,1,MP))


def portal(hinges=HINGES,nodes=NODES,members=MEMBERS):
    return PlanarHingeFrame(nodes,members,tuple(range(6)),hinges)


def load(p):
    f=np.zeros(12);f[[6,9]]=p/2;return f


def reference(p):
    """Symmetric sway x, common roof rotation t, opposite axial extensions ±v.

    Column and beam slope-deflection plus column axial compatibility, not an
    assembled frame stiffness. The base plastic rotations are equal to alpha.
    """
    denominator=2*EA/H+48*EI/B**3
    C=8*EI/H+12*EI/B-(24*EI/B**2)**2/denominator
    matrix=np.array([[24*EI/H**3,12*EI/H**2],[12*EI/H**2,C]])
    x,t=np.linalg.solve(matrix,[p,0.]);alpha=0.
    base=6*EI/H**2*x+2*EI/H*t
    if abs(base)>MP:
        augmented=np.array([[matrix[0,0],matrix[0,1],-12*EI/H**2],
            [matrix[1,0],matrix[1,1],-4*EI/H],[-12*EI/H**2,-4*EI/H,8*EI/H]])
        x,t,alpha=np.linalg.solve(augmented,[p,0.,-2*np.sign(base)*MP])
    v=-24*EI/B**2*t/denominator
    u=np.zeros(12);u[6:]=[x,v,t,x,-v,t]
    return u,alpha


class PlanarHingeFrameTests(unittest.TestCase):
    def test_connected_portal_two_active_hinges_and_independent_reference(self):
        b=portal()
        for steps in (1,20,100):
            old=None
            for p in np.linspace(0,32,steps+1):
                r=b.solve(load(p),old);old=r['state'];u,alpha=reference(p)
                np.testing.assert_allclose(r['motion'],u,atol=2e-10)
                np.testing.assert_allclose(r['state'].rotations,[alpha,alpha,0.,0.],atol=2e-11)
                np.testing.assert_allclose(r['reaction'][[0,3]],[-p/2,-p/2],atol=1e-8)
                np.testing.assert_allclose(r['reaction'][[1,4]],[-EA/H*u[7],-EA/H*u[10]],atol=1e-8)
                self.assertLess(max(abs(r['hinge_moments'])),MP*(1+1e-9))
            self.assertEqual(r['active'],(0,1))
            np.testing.assert_allclose(r['hinge_moments'],[1000.,1000.,920.,920.],atol=1e-7)
            # Independent virtual-work collapse load: four Mp rotations, roof drift H*theta.
            before=repr(old)
            for p in (4*MP/H,34.,100.):
                with self.assertRaisesRegex(ValueError,'mechanism'):b.solve(load(p),old)
            self.assertEqual(repr(old),before)
            self.assertFalse(r['production_ready'])

    def test_member_subdivision_and_joint_force_moment_balance(self):
        expected=portal().solve(load(32.))
        for count in (2,4,8):
            nodes=list(NODES);members=[];hinges=[]
            for base,roof in ((0,2),(1,3)):
                chain=[base]
                for j in range(1,count):
                    chain.append(len(nodes));nodes.append((NODES[base][0],H*j/count))
                chain.append(roof);first=len(members)
                members.extend((i,j,EA,EI) for i,j in zip(chain,chain[1:]))
                hinges.extend(((first,0,MP),(len(members)-1,1,MP)))
            members.append((2,3,EA,EI))
            b=PlanarHingeFrame(nodes,members,tuple(range(6)),hinges)
            f=np.zeros(b.size);f[:12]=load(32.);r=b.solve(f)
            np.testing.assert_allclose(r['motion'][:12],expected['motion'],atol=1e-9)
            np.testing.assert_allclose(r['reaction'][:12],expected['reaction'],atol=1e-7)
            # Assemble recovered local forces independently at every joint.
            internal=np.zeros(b.size)
            for (ids,T,k),local_force in zip(b.elements,r['local_forces']):
                internal[ids]+=T.T@local_force
            np.testing.assert_allclose(internal,f+r['reaction'],atol=1e-7)
            total=(f+r['reaction']).reshape(-1,3);xy=np.asarray(nodes)
            np.testing.assert_allclose(total[:,:2].sum(axis=0),[0.,0.],atol=1e-7)
            self.assertAlmostEqual(np.sum(xy[:,0]*total[:,1]-xy[:,1]*total[:,0]+total[:,2]),0.,places=6)

    def test_unloading_reverse_yield_and_full_frame_work_balance(self):
        b=portal();old=None;u=np.zeros(12);alpha=np.zeros(4);energy=0.
        for p in (0.,25.,32.,0.,-32.):
            f=load(p);r=b.solve(f,old);du=r['motion']-u;da=np.array(r['state'].rotations)-alpha
            quadratic=.5*du@b.K@du-du@b.G@da+.5*da@b.H@da
            self.assertAlmostEqual(f@du-r['elastic_energy']+energy-r['dissipation_increment'],quadratic,places=8)
            if p==0. and old is not None:
                self.assertEqual(r['state'].rotations,old.rotations)
                self.assertEqual(r['state'].dissipation,old.dissipation)
                self.assertEqual(r['active'],())
            old=r['state'];u=r['motion'];alpha=np.array(old.rotations);energy=r['elastic_energy']
        np.testing.assert_allclose(r['motion'],-reference(32.)[0],atol=1e-10)
        self.assertEqual(r['active'],(0,1))

    def test_consistent_tangent_with_frozen_history_and_asymmetric_couple(self):
        b=portal();old=b.solve(load(25.))['state'];f=load(32.);f[8]=10.
        r=b.solve(f,old);direction=np.arange(1.,13.)/13
        epsilon=1e-5
        plus=b.solve(f+epsilon*direction,old);minus=b.solve(f-epsilon*direction,old)
        derivative=(plus['motion'][b.free]-minus['motion'][b.free])/(2*epsilon)
        np.testing.assert_allclose(derivative,np.linalg.solve(r['free_tangent'],direction[b.free]),rtol=1e-7,atol=1e-9)
        np.testing.assert_allclose(r['free_tangent'],r['free_tangent'].T,atol=1e-9)
        self.assertGreater(np.linalg.eigvalsh(r['free_tangent'])[0],0.)

    def test_rigid_coordinate_rotation_translation_member_reversal_and_units(self):
        b=portal();r=b.solve(load(32.));angle=.61
        R=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        transform=np.eye(12)
        for i in range(4):transform[3*i:3*i+2,3*i:3*i+2]=R
        moved=np.asarray(NODES)@R.T+np.array([1200.,-3100.])
        q=portal(nodes=moved).solve(transform@load(32.))
        np.testing.assert_allclose(q['motion'],transform@r['motion'],atol=1e-10)
        np.testing.assert_allclose(q['reaction'],transform@r['reaction'],atol=1e-8)
        reverse=tuple((j,i,ea,ei) for i,j,ea,ei in MEMBERS)
        reversed_hinges=tuple((m,1-e,mp) for m,e,mp in HINGES)
        q=portal(hinges=reversed_hinges,members=reverse).solve(load(32.))
        np.testing.assert_allclose(q['motion'],r['motion'],atol=1e-10)
        np.testing.assert_allclose(q['state'].rotations,r['state'].rotations,atol=1e-10)
        a=25.4;force=4448.2216152605
        scaled=portal(nodes=np.asarray(NODES)*a,
            members=tuple((i,j,ea*force,ei*force*a*a) for i,j,ea,ei in MEMBERS),
            hinges=tuple((m,e,mp*force*a) for m,e,mp in HINGES))
        q=scaled.solve(load(32.*force));expected=r['motion'].copy()
        expected.reshape(-1,3)[:,:2]*=a
        np.testing.assert_allclose(q['motion'],expected,atol=1e-9)
        self.assertAlmostEqual(q['elastic_energy']/(force*a),r['elastic_energy'],places=8)
        self.assertAlmostEqual(q['state'].dissipation/(force*a),r['state'].dissipation,places=8)

    def test_unequal_capacities_sequential_yield_and_interface_order(self):
        hinges=((0,0,600.),)+HINGES[1:];b=portal(hinges=hinges);old=None
        for p,active in ((15.,()),(20.,(0,)),(24.,(0,)),(26.,(0,1))):
            r=b.solve(load(p),old);old=r['state']
            self.assertEqual(r['active'],active)
            self.assertTrue(np.all(abs(r['hinge_moments'])<=b.capacity*(1+1e-9)))
        np.testing.assert_allclose(r['hinge_moments'][:2],[600.,1000.],atol=1e-7)
        direct=b.solve(load(26.))
        np.testing.assert_allclose(direct['motion'],r['motion'],atol=1e-10)
        perm=(3,1,0,2)
        q=portal(hinges=tuple(hinges[i] for i in perm)).solve(load(26.))
        np.testing.assert_allclose(q['motion'],r['motion'],atol=1e-10)
        np.testing.assert_allclose(q['state'].rotations,np.array(r['state'].rotations)[list(perm)],atol=1e-10)
        # A rejected overload preserves the previously accepted sequence.
        before=repr(old)
        with self.assertRaises(ValueError):b.solve(load(100.),old)
        self.assertEqual(repr(old),before)

    def test_elastic_axial_and_bending_cantilever_and_invalid_states(self):
        # Rotated member with independent EA/L and Euler-Bernoulli tip formulas.
        b=PlanarHingeFrame(((0.,0.),(0.,H)),((0,1,EA,EI),),(0,1,2))
        f=np.array([0.,0.,0.,2.,3.,4.]);r=b.solve(f)
        expected=[2*H**3/(3*EI)-4*H**2/(2*EI),3*H/EA,-2*H**2/(2*EI)+4*H/EI]
        np.testing.assert_allclose(r['motion'][3:],expected,atol=1e-12)
        b=portal();old=b.solve(load(32.))['state'];before=repr(old)
        for bad in (replace(old,rotations=(np.nan,0.,0.,0.)),replace(old,dissipation=-1.),replace(old,configuration=())):
            with self.assertRaises(ValueError):b.solve(load(30.),bad)
        with self.assertRaises(ValueError):b.solve(np.full(12,np.nan),old)
        self.assertEqual(repr(old),before)
        with self.assertRaisesRegex(ValueError,'mechanism'):
            PlanarHingeFrame(NODES,MEMBERS,(),HINGES).solve(load(1.))
        for hinges in (((0,0,0.),),((0,0,MP),(0,0,MP)),((3,0,MP),),((0,2,MP),)):
            with self.assertRaises(ValueError):portal(hinges=hinges)
