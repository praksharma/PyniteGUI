"""Independent pre-yield beam-column fields and energy discretization.

No application or PyNite imports. Compression N is positive. Euler–Bernoulli
cantilever: EI*w'''' + N*w'' = 0, tip shear H, free tip moment. Global RZ=-w'.
These elastic prerequisites cannot validate a plastic or post-critical path.
"""
import math
import numpy as np


def column_field(stations,length,rigidity,compression,force):
    parameters=np.asarray((length,rigidity,compression,force),float)
    y=np.asarray(stations,float)
    if not np.isfinite(parameters).all() or length<=0 or rigidity<=0:
        raise ValueError('Finite positive length and bending rigidity are required.')
    if not np.isfinite(y).all() or np.any((y<0)|(y>length)):
        raise ValueError('Stations must lie on the finite cantilever.')
    load= compression*length**2/rigidity
    if load>=math.pi**2/4:raise ValueError('The elastic cantilever is at or above its first buckling load.')
    if abs(load)<1e-5:
        w=force/rigidity*(y*y*(3*length-y)/6+compression/rigidity*(length**3*y*y/6-length*y**4/24+y**5/120))
        slope=force/rigidity*(y*(2*length-y)/2+compression/rigidity*(length**3*y/3-length*y**3/6+y**4/24))
    else:
        k=math.sqrt(abs(compression)/rigidity);a=k*length
        if a>30:raise ValueError('Reference tension parameter exceeds the bounded hyperbolic range.')
        z=k*y
        if compression>0:
            w=force/(compression*k)*(math.tan(a)*(1-np.cos(z))+np.sin(z)-z)
            slope=force/compression*(math.tan(a)*np.sin(z)+np.cos(z)-1)
        else:
            tension=-compression
            w=force/(tension*k)*(math.tanh(a)*(np.cosh(z)-1)-np.sinh(z)+z)
            slope=force/tension*(math.tanh(a)*np.sinh(z)-np.cosh(z)+1)
    return np.column_stack((w,-slope))


def energy_column(segments,length,rigidity,compression,force):
    """Integrate EI curvature² - N slope² with cubic C1 Hermite traces.

    Solve lateral displacement/slope directly; no engine matrix or forces are
    reused. Transform slope to global-Z rotation only in the returned field.
    """
    if type(segments) is not int or not 1<=segments<=128:raise ValueError('Choose 1–128 reference segments.')
    column_field([0.],length,rigidity,compression,force)  # Parameter/branch guards.
    size=2*(segments+1);K=np.zeros((size,size));l=length/segments
    gauss,weights=np.polynomial.legendre.leggauss(4)
    for s,weight in zip((gauss+1)/2,weights*l/2):
        slope=np.array(((-6*s+6*s*s)/l,1-4*s+3*s*s,(6*s-6*s*s)/l,-2*s+3*s*s))
        curvature=np.array(((-6+12*s)/l**2,(-4+6*s)/l,(6-12*s)/l**2,(-2+6*s)/l))
        local=weight*(rigidity*np.outer(curvature,curvature)-compression*np.outer(slope,slope))
        for i in range(segments):
            indices=np.arange(2*i,2*i+4);K[np.ix_(indices,indices)]+=local
    force_vector=np.zeros(size);force_vector[-2]=force;motion=np.zeros(size)
    reduced=K[2:,2:]
    np.linalg.cholesky(reduced)
    motion[2:]=np.linalg.solve(reduced,force_vector[2:])
    residual=K@motion-force_vector
    bound=abs(K)@abs(motion)+abs(force_vector)
    backward=float(np.max(abs(residual[2:])/np.maximum(bound[2:],np.finfo(float).tiny)))
    if backward>1e-11:raise ValueError('Independent reference equilibrium failed.')
    field=motion.reshape(-1,2)*[1.,-1.]
    return field,backward


def compliance_path_integral(length,rigidity,compression,force,terms=64):
    """Diagnostic of integrating compliance without restoring equilibrium.

    The correct static tip is H*C(N). An increment-only path with changing
    axial load instead tends to integral_0^1 H*C(lambda*N) d lambda, omitting
    the lambda*H*N*C'(lambda*N) contribution. This is deliberately NOT a solver.
    """
    if type(terms) is not int or not 8<=terms<=256:raise ValueError('Use 8–256 diagnostic quadrature terms.')
    gauss,weights=np.polynomial.legendre.leggauss(terms)
    return float(sum(weight*column_field([length],length,rigidity,compression*factor,force)[0,0]
        for factor,weight in zip((gauss+1)/2,weights/2)))
