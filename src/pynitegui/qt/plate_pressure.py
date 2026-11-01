"""Geometry-owned affine pressure and independent centroid-load resultants."""
import math
import numpy as np


def pressure_coefficients(definition,factors):
    """q = constant + gx*local_x + gy*local_y, including selected gravity."""
    constant=[];gx=[];gy=[]
    for case,factor in factors.items():
        start=definition.case_pressures[case]
        constant.append(start*factor)
        profile=definition.pressure_profiles.get(case)
        if profile:
            change=(profile['end_pressure']-start)*factor
            (gx if profile['axis']=='x' else gy).append(change/(definition.width if profile['axis']=='x' else definition.height))
        if case==definition.self_weight_case:
            constant.append(definition.material.rho*definition.thickness*definition.self_weight_factor*factor)
    return tuple(math.fsum(values) for values in (constant,gx,gy))


def element_pressures(definition,points,cells,factors):
    q,gx,gy=pressure_coefficients(definition,factors)
    centres=points[cells].mean(axis=1)
    return q+gx*centres[:,0]+gy*centres[:,1]


def geometric_integrals(definition):
    """Area and first/second moments from the rectangle-minus-openings recipe."""
    values=[]
    rectangles=[(1.,0.,0.,definition.width,definition.height)]
    rectangles += [(-1.,o['x_left'],o['y_bott'],o['width'],o['height']) for o in definition.openings]
    for sign,x,y,width,height in rectangles:
        area=sign*width*height;cx=x+width/2;cy=y+height/2
        values.append((area,area*cx,area*cy,area*(cx*cx+width*width/12),area*(cy*cy+height*height/12),area*cx*cy))
    return np.array([math.fsum(row[i] for row in values) for i in range(6)])


def pressure_resultants(definition,points,cells,factors):
    """Integrate recipe q independently of stored engine pressures/reactions.

    Engines accept constant pressure per element. Centroid sampling preserves an
    affine field's force exactly, but changes its first moments. Subtract the
    within-cell variance to check the actual discretization, without hiding that
    difference from the continuously varying target field.
    """
    area,ix,iy,ixx,iyy,ixy=geometric_integrals(definition)
    q,gx,gy=pressure_coefficients(definition,factors)
    continuous=np.array((q*area+gx*ix+gy*iy,q*ix+gx*ixx+gy*ixy,q*iy+gx*ixy+gy*iyy))
    sizes=np.ptp(points[cells],axis=1);areas=sizes[:,0]*sizes[:,1]
    variance=np.array((0.,gx*math.fsum(areas*sizes[:,0]**2)/12,gy*math.fsum(areas*sizes[:,1]**2)/12))
    return continuous-variance,continuous,float(area)
