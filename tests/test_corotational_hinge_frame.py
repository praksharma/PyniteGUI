"""Energy derivatives, objective motion, column reference and combined hinge cycles."""
import unittest
import numpy as np
from corotational_hinge_frame import CorotationalHingeFrame
from test_planar_hinge_frame import NODES,MEMBERS,HINGES,load,reference,H,EI


def portal(hinges=HINGES):
    return CorotationalHingeFrame(NODES,MEMBERS,tuple(range(6)),hinges)


def gravity():
    f=np.zeros(12);f[[7,10]]=-50.;return f


def column(count,axial):
    b=CorotationalHingeFrame([(0.,H*i/count) for i in range(count+1)],
        [(i,i+1,1e7,EI) for i in range(count)],(0,1,2))
    f=np.zeros(b.size);f[-2]=-axial
    return b,f


class CorotationalHingeFrameTests(unittest.TestCase):
    def test_energy_gradient_full_material_geometric_hessian(self):
        b=portal();rng=np.random.default_rng(614)
        units=np.ones(16);units[:12].reshape(-1,3)[:,:2]=H
        z=rng.normal(size=16)*1e-4
        def evaluate(z):
            physical=z*units;e=b.evaluate(physical[:12],physical[12:])
            gradient=np.r_[e['internal'],-e['hinge_moments']]*units
            matrix=np.block([[e['stiffness'],-e['coupling']],[-e['coupling'].T,e['hinge_stiffness']]])*np.outer(units,units)
            return e['elastic_energy'],gradient,matrix
        energy,gradient,matrix=evaluate(z);epsilon=1e-7
        for j in range(16):
            direction=np.eye(16)[j]*epsilon
            ep,gp,_=evaluate(z+direction);em,gm,_=evaluate(z-direction)
            self.assertAlmostEqual((ep-em)/(2*epsilon),gradient[j],delta=2e-5)
            np.testing.assert_allclose((gp-gm)/(2*epsilon),matrix[:,j],rtol=2e-6,atol=.03)
        np.testing.assert_allclose(matrix,matrix.T,atol=1e-8)
        self.assertGreater(energy,0.)

    def test_finite_rigid_motion_objectivity_and_element_work(self):
        b=portal();angle=.12;R=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        u=np.zeros(12);u.reshape(-1,3)[:,:2]=np.asarray(NODES)@R.T+[10.,-20.]-NODES
        u[2::3]=angle;e=b.evaluate(u,np.zeros(4))
        self.assertLess(e['elastic_energy'],1e-18);self.assertLess(max(abs(e['internal'])),1e-7)
        # Integrate the exact generalized energy gradient along a straight path.
        rng=np.random.default_rng(100);du=rng.normal(size=12)*.001;da=rng.normal(size=4)*.0001
        points,weights=np.polynomial.legendre.leggauss(8);work=0.
        start=b.evaluate(np.zeros(12),np.zeros(4))['elastic_energy']
        for t,w in zip((points+1)/2,weights/2):
            e=b.evaluate(t*du,t*da);work+=w*(e['internal']@du-e['hinge_moments']@da)
        end=b.evaluate(du,da)['elastic_energy']
        self.assertAlmostEqual(work,end-start,places=10)

    def test_column_continuum_mesh_convergence_and_physical_axial_force(self):
        compression=.2*np.pi**2*EI/(4*H**2);force=.01;errors=[]
        for n in (1,2,4,8,16):
            b,f=column(n,compression);pre=b.solve(f);f[-3]=force;r=b.solve(f,pre['state'])
            k=np.sqrt(compression/EI);exact=force/(compression*k)*(np.tan(k*H)-k*H)
            errors.append(abs(r['motion'][-3]/exact-1))
            np.testing.assert_allclose(r['basic_forces'][:,0],-compression,atol=1e-5)
            self.assertGreater(r['motion'][-3],force*H**3/(3*EI))
        self.assertTrue(all(a>b for a,b in zip(errors,errors[1:])))
        self.assertGreater(errors[0],.01)  # Preserve the coarse geometric interpolation miss.
        self.assertLess(errors[-1],.001)
        b,f=column(8,-compression);pre=b.solve(f);f[-3]=force;r=b.solve(f,pre['state'])
        k=np.sqrt(compression/EI);exact=force/(compression*k)*(k*H-np.tanh(k*H))
        self.assertLess(abs(r['motion'][-3]/exact-1),.002)
        self.assertLess(r['motion'][-3],force*H**3/(3*EI))

    def test_gravity_portal_yield_and_consistent_condensed_tangent(self):
        b=portal();pre=b.solve(gravity());f=gravity()+load(30.);r=b.solve(f,pre['state'])
        self.assertEqual(r['active'],(0,1));np.testing.assert_allclose(r['hinge_moments'][:2],[1000.,1000.],atol=1e-6)
        self.assertGreater(r['motion'][6],reference(30.)[0][6])
        direction=load(1.);epsilon=1e-4
        plus=b.solve(f+epsilon*direction,pre['state']);minus=b.solve(f-epsilon*direction,pre['state'])
        derivative=(plus['motion'][b.free]-minus['motion'][b.free])/(2*epsilon)
        np.testing.assert_allclose(derivative,np.linalg.solve(r['free_tangent'],direction[b.free]),rtol=2e-6,atol=2e-8)
        # Dead-load balance uses current, deformed nodal coordinates.
        total=(f+r['reaction']).reshape(-1,3);xy=np.asarray(NODES)+r['motion'].reshape(-1,3)[:,:2]
        np.testing.assert_allclose(total[:,:2].sum(axis=0),[0.,0.],atol=1e-7)
        self.assertAlmostEqual(np.sum(xy[:,0]*total[:,1]-xy[:,1]*total[:,0]+total[:,2]),0.,places=5)
        self.assertFalse(r['production_ready'])

    def test_elastic_ramp_preload_same_total_state_and_zero_load_limit(self):
        b=portal();target=gravity()+load(10.);direct=b.solve(target);old=None
        for factor in np.linspace(0,1,21):old=b.solve(target*factor,old)['state']
        np.testing.assert_allclose(old.motion,direct['motion'],atol=1e-9)
        pre=b.solve(gravity());r=b.solve(target,pre['state'])
        np.testing.assert_allclose(r['motion'],direct['motion'],atol=1e-9)
        small=b.solve(load(.001))
        np.testing.assert_allclose(small['motion'],reference(.001)[0],rtol=1e-6,atol=1e-10)

    def test_combined_unload_reverse_cycle_work_and_history(self):
        b=portal(HINGES[:2]);old=b.solve(gravity())['state'];initial_energy=b.evaluate(old.motion,old.rotations)['elastic_energy']
        work=0.;previous_load=gravity();previous_motion=np.array(old.motion)
        for start,end in ((0.,30.),(30.,0.),(0.,-30.),(-30.,0.)):
            for p in np.linspace(start,end,81)[1:]:
                f=gravity()+load(p);r=b.solve(f,old)
                work+=(f+previous_load)@(r['motion']-previous_motion)/2
                if p==0.:
                    self.assertEqual(r['active'],())
                old=r['state'];previous_motion=r['motion'];previous_load=f
        self.assertGreater(old.dissipation,0.)
        self.assertAlmostEqual(work-r['elastic_energy']+initial_energy,old.dissipation,delta=.01)
        self.assertLess(old.rotations[0],0.);self.assertLess(old.rotations[1],0.)

    def test_portal_mesh_coordinate_direction_and_unit_checks(self):
        b=portal();f=gravity()+load(30.);r=b.solve(f)
        angle=.63;R=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        transform=np.eye(12)
        for i in range(4):transform[3*i:3*i+2,3*i:3*i+2]=R
        moved=np.asarray(NODES)@R.T+[1200.,-3100.]
        q=CorotationalHingeFrame(moved,MEMBERS,tuple(range(6)),HINGES).solve(transform@f)
        np.testing.assert_allclose(q['motion'],transform@r['motion'],atol=2e-8)
        np.testing.assert_allclose(q['reaction'],transform@r['reaction'],atol=2e-6)
        reverse=tuple((j,i,ea,ei) for i,j,ea,ei in MEMBERS)
        q=CorotationalHingeFrame(NODES,reverse,tuple(range(6)),tuple((m,1-e,mp) for m,e,mp in HINGES)).solve(f)
        np.testing.assert_allclose(q['motion'],r['motion'],atol=1e-9)
        a=25.4;force=4448.2216152605
        scaled=CorotationalHingeFrame(np.asarray(NODES)*a,
            tuple((i,j,ea*force,ei*force*a*a) for i,j,ea,ei in MEMBERS),tuple(range(6)),
            tuple((m,e,mp*force*a) for m,e,mp in HINGES))
        q=scaled.solve(f*force);expected=r['motion'].copy();expected.reshape(-1,3)[:,:2]*=a
        np.testing.assert_allclose(q['motion'],expected,atol=2e-8)
        self.assertAlmostEqual(q['elastic_energy']/(force*a),r['elastic_energy'],places=7)
        drifts=[]
        for count in (2,4,8):
            nodes=list(NODES);members=[];hinges=[]
            for base,roof in ((0,2),(1,3)):
                chain=[base]
                for j in range(1,count):
                    chain.append(len(nodes));nodes.append((NODES[base][0],H*j/count))
                chain.append(roof);first=len(members)
                members.extend((i,j,MEMBERS[0][2],EI) for i,j in zip(chain,chain[1:]))
                hinges.extend(((first,0,1000.),(len(members)-1,1,1000.)))
            members.append(MEMBERS[-1])
            refined=CorotationalHingeFrame(nodes,members,tuple(range(6)),hinges)
            loads=np.zeros(refined.size);loads[:12]=f;q=refined.solve(loads)
            drifts.append(q['motion'][6]);self.assertEqual(q['active'],(0,2))
        # A refinement consistency gate, not an independent nonlinear portal oracle.
        self.assertLess(abs(drifts[-1]/drifts[-2]-1),.001)

    def test_bounds_instability_nonconvergence_and_transactional_failure(self):
        b=portal();old=b.solve(gravity())['state'];before=repr(old)
        with self.assertRaises(ValueError):b.solve(gravity()+load(30.),old,max_iterations=1)
        with self.assertRaises(ValueError):b.solve(np.full(12,np.nan),old)
        with self.assertRaises(ValueError):b.evaluate(np.zeros(12),np.ones(4))
        u=np.zeros(12);u[6]=100.
        with self.assertRaises(ValueError):b.evaluate(u,np.zeros(4))
        self.assertEqual(repr(old),before)
        # Straight compression above the continuum critical load has no accepted
        # positive supported tangent; do not return its zero lateral motion.
        critical=np.pi**2*EI/(4*H**2);c,f=column(8,1.1*critical)
        with self.assertRaisesRegex(ValueError,'stable'):c.solve(f)
