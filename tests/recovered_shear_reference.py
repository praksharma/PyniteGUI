"""Independent sine/Levy thin-plate shear; no application or engine imports."""
import numpy as np


def triangular_shear(points,width,height,pressure,axis='y',terms=160):
    if axis=='x':return triangular_shear(np.asarray(points)[:,::-1],height,width,pressure,'y',terms)[:,::-1]
    m=np.arange(1,terms+1,2)[:,None];n=np.arange(1,terms+1)[None,:]
    a=m*np.pi/width;b=n*np.pi/height
    coefficient=8*pressure/(np.pi**2*m*n)/(a*a+b*b)**2
    x,y=np.asarray(points).T;sx,cx=np.sin(x[:,None]*a.T),np.cos(x[:,None]*a.T)
    sy,cy=np.sin(y[:,None]*b),np.cos(y[:,None]*b)
    def field(c,l,r):return np.einsum('pm,mn,pn->p',l,c,r,optimize=True)
    return np.column_stack((field(coefficient*a*(a*a+b*b),cx,sy),field(coefficient*b*(a*a+b*b),sx,cy)))


def torsional_edge_shear(points,width,height,pressure,rigidity,GJ,terms=160):
    """SS rectangle with a torsional beam on y=0, w=0 on every edge.

    Each sine-x Levy mode solves D(dy²-alpha²)² f=q_m. At y=H: f=f''=0;
    at y=0: f=0 and D f''=GJ alpha² f'. This follows directly from adding
    GJ/2 integral(w,xy²) along the edge to the Kirchhoff bending energy.
    Exponential endpoint bases avoid overflow and differentiated Fourier jumps.
    """
    x,y=np.asarray(points,float).T;result=np.zeros((len(x),2))
    for m in range(1,terms+1,2):
        a=m*np.pi/width;q=4*pressure/(m*np.pi);particular=q/(rigidity*a**4)
        def basis(y,derivative):
            y=np.asarray(y);left=np.exp(-a*y);right=np.exp(-a*(height-y))
            values=[(-a)**derivative*left,a**derivative*right]
            values += [(a*y*(-a)**derivative+(derivative*a*(-a)**(derivative-1) if derivative else 0.))*left,
                       (a*(height-y)*a**derivative-(derivative*a*a**(derivative-1) if derivative else 0.))*right]
            return np.array(values).T
        matrix=np.array([basis(0.,0),basis(height,0),basis(height,2),basis(0.,2)-GJ*a*a/rigidity*basis(0.,1)])
        rhs=np.array([-particular,-particular,0.,0.]);scale=np.linalg.norm(matrix,axis=1)
        coefficients=np.linalg.solve(matrix/scale[:,None],rhs/scale)
        f=basis(y,0)@coefficients+particular;f1=basis(y,1)@coefficients
        f2=basis(y,2)@coefficients;f3=basis(y,3)@coefficients
        result[:,0]+=rigidity*a*np.cos(a*x)*(a*a*f-f2)
        result[:,1]+=-rigidity*np.sin(a*x)*(f3-a*a*f1)
    return result
