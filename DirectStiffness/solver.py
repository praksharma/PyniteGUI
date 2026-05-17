import numpy as np
np.set_printoptions(precision=3, suppress=True)
np.set_printoptions(linewidth=np.inf)
float_type = np.float64

class Solver():
    def __init__(self, node, conn) -> None:
        self.NN= len(node)        #number of nodes
        self.NE= len(conn)        #number of elements
        self.ndof= 3*self.NN           #total dof (axial, shear, moment)
        # Formation of Displacement Matrix
        d = np.zeros([self.ndof, 1], dtype=float_type) 
        f = np.zeros([self.ndof, 1], dtype=float_type)
        K = np.zeros([self.ndof, self.ndof], dtype=float_type)     #size of assembled stiffness matrix is ndof x ndof
        f[4]=-1.0
    def __repr__(self):
        "Give more information about the object for development purpose."
        return f"Solver init: No. of Nodes= {self.NN}, No. of Elems= {self.NE})"