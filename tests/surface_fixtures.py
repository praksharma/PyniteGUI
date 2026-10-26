"""Small multistorey fixtures; not a published example or a design model."""
from pynitegui.qt.mesh_model import MeshDefinition
from pynitegui.qt.spatial_model import SpatialProject, SpatialNode, SpatialMember


def two_storey_slabs():
    project = SpatialProject(load_cases=["Dead", "Live"], default_load_case="Dead",
        combinations={"Gravity":{"Dead":1.,"Live":1.}, "Factored":{"Dead":1.2,"Live":1.6}})
    corners = ((0.,0.), (240.,0.), (240.,180.), (0.,180.))
    for level in range(3):
        for corner, (x,z) in enumerate(corners):
            name = f"N{level}_{corner}"
            project.nodes[name] = SpatialNode(name, x, level*120., z=z, support="fixed" if level==0 else "free")
            if level:
                name = f"C{level}_{corner}"
                project.members[name] = SpatialMember(name, f"N{level-1}_{corner}", f"N{level}_{corner}")
        if level:
            for corner in range(4):
                name = f"B{level}_{corner}"
                project.members[name] = SpatialMember(name, f"N{level}_{corner}", f"N{level}_{(corner+1)%4}")
            name = f"Floor{level}"
            project.surfaces[name] = MeshDefinition(name=name, plane="XZ", origin=[0.,level*120.,0.],
                parameters={"width":240.,"height":180.}, mesh_size=60., thickness=6.)
            project.surface_pressures[name] = {"Dead":.001 if level==1 else .0015, "Live":.0005 if level==1 else .00025}
    project.surface_analysis_enabled = True
    project.validate()
    return project
