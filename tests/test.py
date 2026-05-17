import sys
sys.path.append('.') 
import DirectStiffness as DS

problem = {
    "materials": {
        "E": [2e8, 2e8],
        "I": [4e-6, 4e-6],
        "A": [0.0, 0.0],
    },
    "nodes": [
        [0.0, 0.0],
        [5.0, 0.0],
        [10.0, 0.0],
    ],
    "connectivity": [
        [0, 1],
        [1, 2],
    ],
    "free_dofs": [4, 5],
    "loads": {
        4: -1.0,
    },
}

structure = DS.Structure()
structure.read_variables(problem)

print(structure.nodes[0]) ## __repr__


print(structure.nodes[0]) ## __str__

