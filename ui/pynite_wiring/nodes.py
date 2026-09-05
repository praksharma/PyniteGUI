def add_node(model,
            node_name: str, 
            x: float, 
            y: float):
    """
    Add a node to a FEModel3D() model.
    """
    model.add_node(node_name, x, y, 0)
    print("DEBUG: Node created: ", model.nodes[node_name])


node_number = 0

def get_or_create_nodes(model, x, y):
    """
    Check whether a node exist.
    If not then create one with a new name
    Returns the name of the node.
    """
    global node_number

    # Look for already created node
    for name, node in model.nodes.items():
        if (node.X, node.Y) == (x,y):
            return name
        
    # if node not found, increment the node number and create a new node
    node_number += 1
    node_name = f"N{node_number}"
    # create a node
    add_node(model, node_name, x, y)
    return node_name