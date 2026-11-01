"""Compatible recovery identities and independently checked thin-plate fields."""
from math import factorial
import unittest
import numpy as np
from equilibrated_quad_shear import recover,FreeEdge
from equilibrated_quad_shear_cases import recovered
from quad_shear_boundaries import solve_case,relative_l2,FACTORS,CASES,SIZES
from plate_energy_reference import OpeningEnergyReference
from functools import lru_cache


def rectangles(xs,ys):return np.array([[a,c,b,d] for c,d in zip(ys,ys[1:]) for a,b in zip(xs,xs[1:])],float)



@lru_cache(maxsize=2)
def opening_reference(n=96):return OpeningEnergyReference(nx=n)


class EquilibratedPatchTests(unittest.TestCase):
    def test_free_edge_compatible_uniform_pressure_identity_including_zero_and_unit_scaling(self):
        for nu in (0.,.2,.3):
            cells=rectangles([0,1,2.4,4,6,8],[0,1.2,2,3.5,5,7]);points=(cells[:,:2]+cells[:,2:])/2;x,y=points.T
            xx=(cells[:,0]**2+cells[:,0]*cells[:,2]+cells[:,2]**2)/3
            yy=(cells[:,1]**2+cells[:,1]*cells[:,3]+cells[:,3]**2)/3
            moments=np.column_stack((-(1+nu)*xx/4,-(1+nu)*yy/4,nu*x*y/2))
            expected=-points/2
            for length_scale,force_scale,origin in ((1.,1.,[0.,0.]),(.01,1000.,[17.,-31.])):
                actual_cells=cells*np.tile([length_scale,length_scale],2)+np.tile(origin,2)
                edges=[FreeEdge(0,origin[0],origin[1],origin[1]+7*length_scale),FreeEdge(1,origin[1],origin[0],origin[0]+8*length_scale)]
                for factor in FACTORS.values():
                    # M (force), q (force/length²), Q (force/length).
                    result=recover(actual_cells,factor*force_scale*moments,['Owner/Material']*len(cells),
                        np.full(len(cells),factor*force_scale/length_scale**2),nu,edges)
                    self.assertTrue(result['valid'].all(),result['status'])
                    np.testing.assert_allclose(result['shear'],factor*force_scale/length_scale*expected,rtol=1e-8,atol=1e-7)
                    self.assertLess(max(result['constraint_backward_error']),1e-9)
                    self.assertEqual(set(result['method']),{'polynomial_exact'})
                    self.assertTrue((result['free_edge_count']==0).all())

    def test_quintic_potential_and_affine_pressure_are_exact_on_graded_grid(self):
        cells=rectangles([0,1,2.4,4,6,8],[0,1.2,2,3.5,5,7]);points=(cells[:,:2]+cells[:,2:])/2;x,y=points.T;nu=.2
        terms={(2,0):.2,(0,2):.3,(1,1):.04,(3,0):2.,(0,3):-1.,(4,0):1.,(3,1):2.,(2,2):3.,(1,3):4.,(0,4):2.,(5,0):.1,(4,1):-.2,(3,2):.3,(2,3):-.4,(1,4):.5,(0,5):-.6}
        def derivative(dx,dy):
            return sum(c*factorial(a)/factorial(a-dx)*factorial(b)/factorial(b-dy)*x**(a-dx)*y**(b-dy)
                       for (a,b),c in terms.items() if a>=dx and b>=dy)
        def mean_derivative(dx,dy):
            return sum(c*factorial(a)/factorial(a-dx)*factorial(b)/factorial(b-dy)
                *(cells[:,2]**(a-dx+1)-cells[:,0]**(a-dx+1))/((a-dx+1)*(cells[:,2]-cells[:,0]))
                *(cells[:,3]**(b-dy+1)-cells[:,1]**(b-dy+1))/((b-dy+1)*(cells[:,3]-cells[:,1]))
                for (a,b),c in terms.items() if a>=dx and b>=dy)
        moments=-np.column_stack((mean_derivative(2,0)+nu*mean_derivative(0,2),mean_derivative(0,2)+nu*mean_derivative(2,0),(1-nu)*mean_derivative(1,1)))
        expected=-np.column_stack((derivative(3,0)+derivative(1,2),derivative(2,1)+derivative(0,3)))
        pressures=96+31.2*x-86.4*y
        before=cells.copy();result=recover(cells,moments,['One']*len(cells),pressures,nu)
        self.assertTrue(result['valid'].all());np.testing.assert_allclose(result['shear'],expected,rtol=1e-8,atol=1e-8)
        np.testing.assert_array_equal(cells,before)
        self.assertTrue(np.any(result['status']=='centered'));self.assertTrue(np.any(result['status']=='one_sided'))

    def test_biharmonic_quintic_uses_true_free_edge_constraints(self):
        nu=.2;cells=rectangles([0,1,2.4,4,6,8],[0,1.2,2,3.5,5,7]);points=(cells[:,:2]+cells[:,2:])/2;x,y=points.T
        base=1/(48*(1-nu));terms={(4,0):base,(0,4):base,(2,2):-6*nu*base,
            (5,0):.01,(3,2):-.1*(2-nu)/(3-2*nu),(1,4):.05/(3-2*nu)}
        def derivative(dx,dy,mean=False):
            result=np.zeros(len(cells))
            for (a,b),c in terms.items():
                if a<dx or b<dy:continue
                factor=c*factorial(a)/factorial(a-dx)*factorial(b)/factorial(b-dy)
                if mean:
                    result+=factor*(cells[:,2]**(a-dx+1)-cells[:,0]**(a-dx+1))/((a-dx+1)*(cells[:,2]-cells[:,0]))*(cells[:,3]**(b-dy+1)-cells[:,1]**(b-dy+1))/((b-dy+1)*(cells[:,3]-cells[:,1]))
                else:result+=factor*x**(a-dx)*y**(b-dy)
            return result
        moments=-np.column_stack((derivative(2,0,True)+nu*derivative(0,2,True),derivative(0,2,True)+nu*derivative(2,0,True),(1-nu)*derivative(1,1,True)))
        expected=-np.column_stack((derivative(3,0)+derivative(1,2),derivative(0,3)+derivative(2,1)))
        result=recover(cells,moments,['P']*len(cells),np.ones(len(cells)),nu,[FreeEdge(0,0.,0.,7.)])
        self.assertTrue(result['valid'].all());self.assertEqual(set(result['method']),{'equilibrated_quintic'})
        self.assertTrue(np.any(result['free_edge_count']>0))
        np.testing.assert_allclose(result['shear'],expected,rtol=1e-8,atol=1e-9)

    def test_no_bridging_holes_or_material_jumps_and_missing_thin_regions(self):
        cells=rectangles(np.arange(9.),np.arange(8.));cells=cells[~np.all(cells[:,:2]==[3.,3.],axis=1)]
        points=(cells[:,:2]+cells[:,2:])/2;x,y=points.T;regions=['L' if c[0]<4 else 'R' for c in cells]
        xx=(cells[:,0]**2+cells[:,0]*cells[:,2]+cells[:,2]**2)/3;yy=(cells[:,1]**2+cells[:,1]*cells[:,3]+cells[:,3]**2)/3
        moments=np.column_stack((-.3*xx,-.3*yy,.1*x*y));moments[np.array(regions)=='R'] += [500.,-200.,100.]
        result=recover(cells,moments,regions,np.ones(len(cells)),.2)
        self.assertTrue(result['valid'].any())
        for i in np.where(result['valid'])[0]:
            ids=result['stencils'][i];patch=cells[ids]
            self.assertEqual({regions[j] for j in ids},{regions[i]});self.assertIn(i,ids)
            self.assertAlmostEqual(np.prod(patch[:,2:]-patch[:,:2],axis=1).sum(),np.prod(patch[:,2:].max(axis=0)-patch[:,:2].min(axis=0)))
        np.testing.assert_allclose(result['shear'][result['valid']],-points[result['valid']]/2,atol=1e-8)
        cells=rectangles(np.arange(5.),np.arange(6.));regions=['L' if c[0]<2 else 'R' for c in cells]
        result=recover(cells,np.zeros((len(cells),3)),regions,np.zeros(len(cells)),0.)
        self.assertFalse(result['valid'].any());self.assertTrue(np.isnan(result['shear']).all());self.assertTrue((result['stencils']==-1).all())

    def test_non_affine_pressure_excessive_grading_and_coordinate_roundoff(self):
        cells=rectangles(np.arange(4.),np.arange(4.));points=(cells[:,:2]+cells[:,2:])/2
        result=recover(cells,np.zeros((9,3)),['P']*9,points[:,0]**2,.2)
        self.assertFalse(result['valid'].any());self.assertEqual(set(result['status']),{'non_affine_pressure'})
        alias=cells.copy();alias[-1,2]=np.nextafter(alias[-1,2],np.inf)
        result=recover(alias,np.zeros((9,3)),['P']*9,np.zeros(9),0.)
        self.assertTrue(result['valid'].all());np.testing.assert_array_equal(result['shear'],0.)
        cells=rectangles([0,1,2,20],np.arange(4.))
        result=recover(cells,np.zeros((9,3)),['P']*9,np.zeros(9),.2)
        self.assertFalse(result['valid'].any());self.assertEqual(set(result['status']),{'excessive_grading'})

    def test_quad_centre_moment_is_its_bilinear_cell_mean_in_all_planes(self):
        from pynitegui.qt.plate_model import PlateDefinition,build_plate
        point=1/np.sqrt(3.)
        for plane in ('XY','XZ','YZ'):
            definition=PlateDefinition(plane=plane,mesh_size=30.,thickness=.6,pressure=-1e-7,
                pressure_profiles={'Case 1':{'axis':'x','end_pressure':-3e-7}})
            model=build_plate(definition);model.analyze_linear(check_statics=False)
            for element in model.quads.values():
                centre=element.moment(combo_name='Plate').ravel()
                mean=np.mean([element.moment(x,y,combo_name='Plate').ravel() for x in (-point,point) for y in (-point,point)],axis=0)
                np.testing.assert_allclose(centre,mean,rtol=1e-12,atol=1e-14)

    def test_false_free_edges_invalid_geometry_and_constitutive_mismatch_are_rejected(self):
        cells=rectangles(np.arange(4.),np.arange(4.));moments=np.zeros((9,3));q=np.zeros(9)
        for edge in (FreeEdge(0,1.,0.,3.),FreeEdge(0,0.,.5,3.),FreeEdge(0,0.,0.,4.),FreeEdge(2,0.,0.,3.),FreeEdge(0,0.,1.,0.)):
            with self.assertRaises(ValueError):recover(cells,moments,['P']*9,q,.2,[edge])
        with self.assertRaises(ValueError):recover(cells,moments,['P']*9,q,np.linspace(.1,.2,9))
        for c,m,p in ((cells,moments[:8],q),(cells,np.full((9,3),np.nan),q),(cells,moments,np.full(9,np.inf)),(np.vstack((cells,cells[:1])),np.zeros((10,3)),np.zeros(10))):
            with self.assertRaises(ValueError):recover(c,m,['P']*len(c),p,.2)


class EquilibratedShearBenchmarkTests(unittest.TestCase):
    def test_navier_boundary_and_graded_refinement_does_not_regress(self):
        for case in ('boundary','graded','coupled_boundary','coupled_graded'):
            history=[]
            for size in (30.,15.,7.5):
                sample,result=recovered(case,size);valid=result['valid'];self.assertTrue(valid.all(),result['status'])
                history.append([relative_l2(result['shear'],sample['reference'],sample['areas'],selected) for selected in (valid,valid&sample['outer'],valid&~sample['outer'])])
            history=np.array(history);self.assertTrue(np.all(np.diff(history,axis=0)<0),history)
            self.assertTrue(np.all(history[-1]<[.005,.01,.003]),history)

    def test_interface_cantilevers_keep_exact_cut_equilibrium_and_no_cross_region_stencil(self):
        for case in ('stiffness_x','stiffness_y'):
            for size in (30.,15.,7.5):
                sample,result=recovered(case,size);valid=result['valid']
                if case=='stiffness_x' and size==30.:
                    self.assertFalse(valid.any());continue
                self.assertTrue(valid.all(),result['status'])
                self.assertLess(relative_l2(result['shear'],sample['reference'],sample['areas'],valid),1e-6)
                for i,ids in enumerate(result['stencils']):self.assertEqual({sample['regions'][j] for j in ids},{sample['regions'][i]})

    def test_free_rim_accuracy_is_fixed_against_independent_converged_reference(self):
        coarse,fine=opening_reference(72),opening_reference(96);history=[]
        corners=np.array([[40,40],[40,80],[80,40],[80,80]])
        for size in (10.,5.,4.):
            sample,result=recovered('opening',size);points=sample['points'];x,y=points.T
            distance=np.min(np.linalg.norm(points[:,None]-corners[None],axis=2),axis=1)
            away=result['valid']&(distance>=10.);rim=away&(x>=20)&(x<=40)&(y>=48)&(y<=72)
            a,b=-1e-7*coarse.shears(points),-1e-7*fine.shears(points)
            self.assertLess(relative_l2(a,b,sample['areas'],rim),.005)
            old_error=relative_l2(sample['shear'],b,sample['areas'],rim)
            error=relative_l2(result['shear'],b,sample['areas'],rim);history.append(error)
            self.assertTrue(np.any(result['free_edge_count'][rim]>0))
            self.assertLess(error,old_error)
            if size<=5.:self.assertLess(error,.05)
        self.assertTrue(all(b<a for a,b in zip(history,history[1:])),history)
        self.assertLess(history[-1],.035)
        self.assertLess(relative_l2(result['shear'],b,sample['areas'],away),.01)

    def test_signed_zero_and_all_plane_results_preserve_physical_local_axes(self):
        for case,size in (('boundary',15.),('graded',15.),('opening',5.),('stiffness_x',15.),('stiffness_y',15.)):
            _,base=recovered(case,size)
            for plane in ('XY','XZ','YZ'):
                for combination,factor in FACTORS.items():
                    sample,result=recovered(case,size,plane,combination)
                    np.testing.assert_array_equal(result['valid'],base['valid'])
                    np.testing.assert_allclose(result['shear'],factor*base['shear'],rtol=1e-7,atol=1e-12,equal_nan=True)
