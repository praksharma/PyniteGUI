"""Independent boundary/graded/interface evidence, with unresolved rim gates."""
import unittest
import numpy as np
from plate_reference import OpeningRitz,navier
from quad_shear_boundaries import recover,solve_case,relative_l2,opening_mean_shear,FACTORS,SIZES


def rectangles(xs,ys):
    return np.array([[a,c,b,d] for c,d in zip(ys,ys[1:]) for a,b in zip(xs,xs[1:])],float)


class QuadBoundaryPatchTests(unittest.TestCase):
    def test_quadratic_tensor_is_exact_on_one_sided_graded_scaled_patches(self):
        for scale,origin in (([1.,1.],[0.,0.]),([.01,100.],[17.,-31.])):
            cells=rectangles([0,1,2.4,4,6,8],[0,1.2,2,3.5,5,7])*np.tile(scale,2)+np.tile(origin,2)
            points=(cells[:,:2]+cells[:,2:])/2;x,y=(points-origin).T
            moments=np.column_stack((2*x*x+3*x*y-y,-x*y+4*y*y+x,x*x-y*y+2*x*y))
            expected=np.column_stack((6*x+y,x+10*y));before=cells.copy()
            for factor in FACTORS.values():
                data=recover(cells,factor*moments,['Owner/Material']*len(cells))
                self.assertTrue(data['valid'].all());self.assertIn('one_sided',data['status'])
                np.testing.assert_allclose(data['shear'],factor*expected,rtol=1e-9,atol=1e-5)
            np.testing.assert_array_equal(cells,before)

    def test_stencils_are_complete_connected_and_never_mix_regions_or_cross_holes(self):
        cells=rectangles(np.arange(9.),np.arange(8.))
        cells=cells[~np.all(cells[:,:2]==[3.,3.],axis=1)]
        regions=['L' if cell[0]<4 else 'R' for cell in cells]
        points=(cells[:,:2]+cells[:,2:])/2;x,y=points.T
        jumps=np.array([0 if r=='L' else 500 for r in regions])
        moments=np.column_stack((2*x*x+jumps,3*y*y-jumps,x*y+2*jumps))
        data=recover(cells,moments,regions)
        self.assertTrue(data['valid'].any())
        for i in np.where(data['valid'])[0]:
            indices=data['stencils'][i];patch=cells[indices]
            self.assertEqual({regions[j] for j in indices},{regions[i]})
            self.assertIn(i,indices);self.assertEqual(len(set(indices)),9)
            area=np.prod(patch[:,2:]-patch[:,:2],axis=1).sum()
            self.assertAlmostEqual(area,np.prod(patch[:,2:].max(axis=0)-patch[:,:2].min(axis=0)))
        np.testing.assert_allclose(data['shear'][data['valid']],np.column_stack((5*x,7*y))[data['valid']],atol=1e-10)
        self.assertTrue(np.isnan(data['shear'][~data['valid']]).all())
        self.assertTrue((data['stencils'][~data['valid']]==-1).all())

    def test_insufficient_thin_regions_and_excessive_grading_return_explicit_missing_values(self):
        cells=rectangles(np.arange(5.),np.arange(6.));regions=['L' if c[0]<2 else 'R' for c in cells]
        data=recover(cells,np.zeros((len(cells),3)),regions)
        self.assertFalse(data['valid'].any());self.assertTrue(np.isnan(data['shear']).all())
        self.assertEqual(set(data['status']),{'incomplete_or_mixed_region'})
        cells=rectangles([0.,1.,2.,20.],np.arange(4.))
        data=recover(cells,np.zeros((9,3)),['Plate']*9)
        self.assertFalse(data['valid'].any());self.assertEqual(set(data['status']),{'excessive_grading'})

    def test_invalid_duplicate_nonconforming_or_nonfinite_inputs_are_rejected(self):
        cells=rectangles(np.arange(4.),np.arange(4.));moments=np.zeros((9,3))
        bad=cells.copy();bad[0,2]=2.
        for c,m,r in ((cells,moments[:8],['P']*9),(cells,np.full((9,3),np.nan),['P']*9),
                      (cells,moments,['P']*8),(cells,moments,['']*9),(cells[:,[2,1,0,3]],moments,['P']*9),
                      (np.vstack((cells,cells[:1])),np.zeros((10,3)),['P']*10),(bad,moments,['P']*9)):
            with self.assertRaises(ValueError):recover(c,m,r)

    def test_coordinate_roundoff_is_merged_but_a_real_gap_is_not(self):
        cells=rectangles(np.arange(4.),np.arange(4.));moments=np.ones((9,3));alias=cells.copy()
        alias[-1,2]=np.nextafter(alias[-1,2],np.inf)
        data=recover(alias,moments,['P']*9);self.assertTrue(data['valid'].all())
        np.testing.assert_allclose(data['shear'],0.,atol=1e-14)
        separated=cells.copy();separated[-1,2]+=1e-7
        with self.assertRaisesRegex(ValueError,'conforming'):recover(separated,moments,['P']*9)

    def test_analytic_ritz_mean_shear_matches_intact_navier_quadrature(self):
        box=(0.,20.,30.,70.);r=OpeningRitz(120.,180.,.2,terms=9)
        g,w=np.polynomial.legendre.leggauss(40)
        xx,yy=np.meshgrid(10*(g+1),20*g+50);weights=np.outer(w,w).ravel()/4
        expected=weights@navier(np.column_stack((xx.ravel(),yy.ravel())),120.,180.,.2,1.,1.,terms=18)[2]
        np.testing.assert_allclose(r.mean_shears(box),expected,rtol=1e-11)

    def test_clipped_material_patch_means_and_missing_area_guard(self):
        sample={'cells':np.array([[0,0,1,1],[1,0,3,1]],float),'valid':np.array([True,True]),'shear':np.array([[2,4],[8,10]],float)}
        np.testing.assert_allclose(opening_mean_shear(sample,(.5,2.,0.,1.)),[6.,8.])
        with self.assertRaisesRegex(ValueError,'covered'):opening_mean_shear(sample,(0,4,0,1))
        sample['valid'][1]=False
        with self.assertRaisesRegex(ValueError,'valid material'):opening_mean_shear(sample,(0,3,0,1))


class QuadBoundaryBenchmarkTests(unittest.TestCase):
    def test_outer_boundaries_and_graded_navier_refinement_signed_zero_and_reference_truncation(self):
        for case in ('boundary','graded','coupled_boundary','coupled_graded'):
            history=[]
            for size in (30.,15.,7.5):
                samples=solve_case(case,size);s=samples['Service'];valid=s['valid']
                self.assertTrue(valid.all())
                masks=(valid,valid&s['outer'],valid&~s['outer'])
                history.append([relative_l2(s['shear'],s['reference'],s['areas'],mask) for mask in masks])
                for name,factor in FACTORS.items():
                    sample=samples[name]
                    for key in ('moments','raw','shear','reference'):
                        np.testing.assert_allclose(sample[key],factor*s[key],atol=1e-12,rtol=1e-7,equal_nan=True)
                if size==7.5:
                    q=-1e-7;D=3600*.6**3/(12*(1-.2**2))
                    lower=navier(s['points'],120.,180.,.2,q,D,terms=160)[2]
                    self.assertLess(relative_l2(lower,s['reference'],s['areas'],s['outer']),.0005)
            history=np.array(history)
            self.assertTrue(np.all(np.diff(history,axis=0)<0),history)
            self.assertTrue(np.all(history[-1]<[.02,.03,.003]),history)

    def test_E_and_thickness_interfaces_match_two_direction_cut_equilibrium_without_mixed_stencils(self):
        for case in ('stiffness_x','stiffness_y'):
            for size in (30.,15.,7.5):
                samples=solve_case(case,size);s=samples['Service'];valid=s['valid']
                self.assertEqual(len(set(s['regions'])),2)
                self.assertTrue(any('14400.0' in region and '0.9' in region for region in s['regions']))
                if case=='stiffness_x' and size==30.:
                    self.assertFalse(valid.any());self.assertTrue(np.isnan(s['shear']).all());continue
                self.assertTrue(valid.all())
                for i,patch in enumerate(s['stencils']):self.assertEqual({s['regions'][j] for j in patch},{s['regions'][i]})
                self.assertLess(relative_l2(s['shear'],s['reference'],s['areas'],valid),1e-6)
                for name,factor in FACTORS.items():
                    np.testing.assert_allclose(samples[name]['shear'],factor*s['shear'],atol=1e-12,rtol=1e-7)

    def test_plane_permutation_preserves_local_boundary_opening_and_interface_results(self):
        for case,size in (('boundary',15.),('graded',15.),('coupled_boundary',15.),('opening',10.),('stiffness_x',15.),('stiffness_y',15.)):
            base=solve_case(case,size)['Service']
            for plane in ('XZ','YZ'):
                sample=solve_case(case,size,plane)['Service']
                np.testing.assert_allclose(sample['cells'],base['cells'],atol=1e-10)
                np.testing.assert_array_equal(sample['valid'],base['valid'])
                np.testing.assert_allclose(sample['shear'],base['shear'],atol=1e-12,rtol=1e-7)

    def test_opening_corner_mean_is_bounded_but_rim_and_outer_strip_references_remain_unresolved(self):
        boxes=((0.,20.,0.,20.),);rim=(20.,40.,48.,72.)
        refs=[OpeningRitz(120,120,.2,40,40,terms=n) for n in (9,11,13)]
        q=-1e-7
        for box in boxes:
            last=q*refs[-1].mean_shears(box);previous=q*refs[-2].mean_shears(box)
            self.assertLess(np.linalg.norm(last-previous)/np.linalg.norm(last),.005)
            for size in SIZES['opening']:
                samples=solve_case('opening',size);s=samples['Service']
                actual=opening_mean_shear(s,box)
                self.assertLess(np.linalg.norm(actual-last)/np.linalg.norm(last),.04 if size==10. else .01)
                for name,factor in FACTORS.items():
                    np.testing.assert_allclose(opening_mean_shear(samples[name],box),factor*actual,atol=1e-12,rtol=1e-7)
        strip=[q*r.mean_shears((0.,20.,40.,80.)) for r in refs]
        self.assertGreater(np.linalg.norm(strip[-1]-strip[-2])/np.linalg.norm(strip[-1]),.005)
        near=[q*r.mean_shears(rim) for r in refs]
        self.assertGreater(np.linalg.norm(near[-1]-near[-2])/np.linalg.norm(near[-1]),.2)
        # Keep the original independent-reference conditioning guard. Better
        # displacement/moment agreement cannot certify a third derivative.
        with self.assertRaisesRegex(ValueError,'ill-conditioned'):OpeningRitz(120,120,.2,40,40,terms=17)
