"""Serializable recipes for PyNite's concrete mesh generators (not a solver)."""
from dataclasses import asdict, dataclass, field, fields
import json
import math
from pathlib import Path

import numpy as np
from Pynite import FEModel3D
from Pynite.Mesh import AnnulusRingMesh, AnnulusTransRingMesh, CylinderRingMesh

from .model import Material, finite_number, unique_json_object
from .units import UNIT_SYSTEMS


MAX_MESH_ELEMENTS = 1024
# Parameter names are the upstream names. The direct ring helpers intentionally
# do not have a target mesh-size argument; they take a circumferential count.
GENERATORS = {
    "rectangle": ("Rectangle", {"width": 120., "height": 120.}),
    "annulus": ("Annulus", {"outer_radius": 60., "inner_radius": 30.}),
    "annulus_ring": ("Annular ring", {"outer_radius": 60., "inner_radius": 30., "num_quads": 16}),
    "annulus_transition": ("Annular transition ring", {"outer_radius": 60., "inner_radius": 30., "num_inner_quads": 8}),
    "cylinder": ("Cylinder", {"radius": 60., "height": 120., "num_elements": 0}),
    "cylinder_ring": ("Cylinder ring", {"radius": 60., "height": 30., "num_elements": 16}),
    "frustum": ("Conical frustum", {"large_radius": 60., "small_radius": 30., "height": 60.}),
}
RECT_FAMILIES = ("rectangle", "cylinder", "cylinder_ring")
COUNT_KEYS = ("num_quads", "num_inner_quads", "num_elements")


def rectangle_controls(width, height, mesh_size, x_control, y_control, openings):
    """Validate upstream rectangle options and bound the pre-opening grid."""
    controls = []
    for values, length in ((x_control, width), (y_control, height)):
        if not isinstance(values, list) or len(values) > 32 or any(
                not finite_number(value) or not 0 < value < length for value in values):
            raise ValueError("Control lines must be up to 32 finite coordinates strictly inside the rectangle.")
        controls.append([0., *values, length])
    if not isinstance(openings, list) or len(openings) > 16:
        raise ValueError("Use at most 16 rectangular openings.")
    boxes, names = [], set()
    for opening in openings:
        keys = {"name", "x_left", "y_bott", "width", "height"}
        if not isinstance(opening, dict) or set(opening) != keys:
            raise ValueError("Opening fields must be name, x_left, y_bott, width and height.")
        name = opening["name"]
        if not isinstance(name, str) or not name.strip() or name != name.strip() or name in names:
            raise ValueError("Opening names must be nonempty and unique.")
        names.add(name)
        if any(not finite_number(opening[key]) for key in keys - {"name"}):
            raise ValueError("Opening dimensions must be finite.")
        x, y, w, h = (opening[key] for key in ("x_left", "y_bott", "width", "height"))
        if min(w, h) < 1e-6 or x < 0 or y < 0 or x+w > width or y+h > height:
            raise ValueError("Openings must have positive size and lie within the rectangle.")
        if w >= width or h >= height:
            raise ValueError("An opening cannot cut completely across the rectangle.")
        for a, b, c, d in boxes:
            if x <= a+c and a <= x+w and y <= b+d and b <= y+h:
                raise ValueError("Openings must not overlap or touch.")
        boxes.append((x, y, w, h))
        controls[0].extend((x, x+w))
        controls[1].extend((y, y+h))
    divisions = []
    for values in controls:
        ordered = []
        for value in sorted(set(values)):
            if ordered and math.isclose(ordered[-1], value):
                continue
            ordered.append(value)
        spans = np.diff(ordered)
        if any(span < 1e-6 for span in spans):
            raise ValueError("Control lines/opening boundaries are too closely spaced.")
        divisions.append(sum(math.ceil(float(span)/mesh_size) for span in spans))
    count = divisions[0]*divisions[1]
    if count > MAX_MESH_ELEMENTS:
        raise ValueError(f"Pre-opening grid exceeds {MAX_MESH_ELEMENTS} elements; increase mesh size or simplify controls.")
    return count


def annulus_count(inner, outer, size):
    """Bound the exact locked-generator subdivision loop before allocation."""
    n = int(2*math.pi*inner/size)
    if n < 3:
        raise ValueError("Mesh size is too large for the inner circumference (at least 3 divisions required).")
    radius, count = inner, 0
    while round(radius, 10) < round(outer, 10):
        arc = 2*math.pi*radius/n
        radial = int((outer-radius)/min(size, 3*arc))
        if radial < 1:
            raise ValueError("Mesh size is too large for the radial width; reduce it.")
        step = (outer-radius)/radial
        transition = arc > 3*size
        count += n*(4 if transition else 1)
        if count > MAX_MESH_ELEMENTS:
            raise ValueError(f"Annular mesh exceeds {MAX_MESH_ELEMENTS} elements.")
        if transition:
            n *= 3
        radius += step
    return count


@dataclass
class MeshDefinition:
    name: str = "Surface"
    generator: str = "rectangle"
    parameters: dict = field(default_factory=lambda: dict(GENERATORS["rectangle"][1]))
    mesh_size: float = 15.
    thickness: float = 1.
    material: Material = field(default_factory=lambda: Material("Surface", E=3600, nu=.2, rho=0))
    kx_mod: float = 1.
    ky_mod: float = 1.
    origin: list = field(default_factory=lambda: [0., 0., 0.])
    plane: str = "XY"
    axis: str = "Y"
    element_type: str = "Quad"
    node_start: int = 1
    element_start: int = 1
    x_control: list = field(default_factory=list)
    y_control: list = field(default_factory=list)
    openings: list = field(default_factory=list)
    unit_system: str = "imperial"

    @property
    def units(self):
        return UNIT_SYSTEMS[self.unit_system]

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip() or self.name != self.name.strip():
            raise ValueError("Mesh name must be nonempty without surrounding spaces.")
        if not isinstance(self.generator, str) or self.generator not in GENERATORS:
            raise ValueError("Unknown PyNite mesh generator.")
        if not isinstance(self.parameters, dict) or set(self.parameters) != set(GENERATORS[self.generator][1]):
            raise ValueError("Mesh parameters do not match the selected generator.")
        if not isinstance(self.material, Material):
            raise ValueError("Invalid mesh material.")
        self.material.validate()
        for key in ("mesh_size", "thickness", "kx_mod", "ky_mod"):
            if not finite_number(getattr(self, key)) or not 1e-6 <= getattr(self, key) <= 1e6:
                raise ValueError(f"{key} must be finite and between 1e-6 and 1e6.")
        if not isinstance(self.origin, list) or len(self.origin) != 3 or any(
                not finite_number(value) or abs(value) > 1e6 for value in self.origin):
            raise ValueError("Origin must contain three finite coordinates within +/-1e6 inches.")
        if not isinstance(self.unit_system, str) or self.unit_system not in UNIT_SYSTEMS or self.plane not in ("XY", "XZ", "YZ") or self.axis not in ("X", "Y", "Z"):
            raise ValueError("Unknown units, plane or axis.")
        if self.element_type not in ("Quad", "Rect") or (self.element_type == "Rect" and self.generator not in RECT_FAMILIES):
            raise ValueError("This generator supports Quad elements only.")
        for key in ("node_start", "element_start"):
            if type(getattr(self, key)) is not int or not 1 <= getattr(self, key) <= 100000000:
                raise ValueError("Numbering starts must be positive integers up to 100000000.")
        for key, value in self.parameters.items():
            if key in COUNT_KEYS:
                if type(value) is not int or not (value == 0 and self.generator == "cylinder") and not 3 <= value <= MAX_MESH_ELEMENTS:
                    raise ValueError("Circumferential divisions must be integers >=3 (0 is automatic for Cylinder only).")
            elif not finite_number(value) or not 1e-6 <= value <= 1e6:
                raise ValueError(f"{key} must be a positive finite length between 1e-6 and 1e6 inches.")
        p = self.parameters
        if self.generator == "rectangle":
            return rectangle_controls(p["width"], p["height"], self.mesh_size, self.x_control, self.y_control, self.openings)
        if self.x_control or self.y_control or self.openings:
            raise ValueError("Control lines/openings are available only on rectangular meshes.")
        if self.generator.startswith("annulus") or self.generator == "frustum":
            inner, outer = (p["small_radius"], p["large_radius"]) if self.generator == "frustum" else (p["inner_radius"], p["outer_radius"])
            if outer-inner < 1e-6:
                raise ValueError("Outer/large radius must be larger than inner/small radius.")
            if self.generator in ("annulus", "frustum"):
                return annulus_count(inner, outer, self.mesh_size)
            count = p["num_quads"] if self.generator == "annulus_ring" else 4*p["num_inner_quads"]
        else:
            n = p["num_elements"] or int(round(2*math.pi*p["radius"]/self.mesh_size))
            if n < 3:
                raise ValueError("Automatic cylinder divisions are below 3; reduce the mesh size.")
            count = n*(max(int(p["height"]/self.mesh_size), 1) if self.generator == "cylinder" else 1)
        if count > MAX_MESH_ELEMENTS:
            raise ValueError(f"Mesh exceeds {MAX_MESH_ELEMENTS} elements; reduce divisions or increase mesh size.")
        return count

    def to_dict(self):
        self.validate()
        return {"format": "pynitegui-mesh", "version": 1, "units": "in-kip", **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("format") != "pynitegui-mesh" or type(data.get("version")) is not int or data["version"] != 1 or data.get("units") != "in-kip":
            raise ValueError("Unsupported mesh recipe file.")
        values = {key: value for key, value in data.items() if key not in ("format", "version", "units")}
        if set(values) != {item.name for item in fields(cls)}:
            raise ValueError("Mesh recipe fields do not match the version 1 schema.")
        try:
            values["material"] = Material(**values["material"])
            result = cls(**values)
            result.validate()
            return result
        except (TypeError, KeyError) as error:
            raise ValueError(f"Invalid mesh recipe: {error}") from error

    @classmethod
    def open(cls, path):
        if Path(path).stat().st_size > 100000:
            raise ValueError("Mesh recipe is too large.")
        return cls.from_dict(json.loads(Path(path).read_text(), object_pairs_hook=unique_json_object))


def generate_mesh(definition):
    definition.validate()
    model = FEModel3D()
    mat = definition.material
    model.add_material(mat.name, mat.E, mat.G, mat.nu, mat.rho)
    common = dict(thickness=definition.thickness, material_name=mat.name, kx_mod=definition.kx_mod,
                  ky_mod=definition.ky_mod, origin=[0., 0., 0.])
    p, kind = dict(definition.parameters), definition.generator
    if kind == "rectangle":
        model.add_rectangle_mesh(definition.name, definition.mesh_size, **p, **common, plane=definition.plane,
                                 x_control=list(definition.x_control), y_control=list(definition.y_control),
                                 element_type=definition.element_type)
        mesh = model.meshes[definition.name]
        for opening in definition.openings:
            mesh.add_rect_opening(**opening)
    elif kind == "annulus":
        model.add_annulus_mesh(definition.name, definition.mesh_size, **p, **common, axis=definition.axis)
        mesh = model.meshes[definition.name]
    elif kind == "frustum":
        model.add_frustrum_mesh(definition.name, definition.mesh_size, **p, **common, axis=definition.axis)
        mesh = model.meshes[definition.name]
    elif kind == "cylinder":
        p["num_elements"] = p["num_elements"] or None
        model.add_cylinder_mesh(definition.name, definition.mesh_size, **p, **common, axis=definition.axis,
                                element_type=definition.element_type)
        mesh = model.meshes[definition.name]
    else:
        constructor = {"annulus_ring": AnnulusRingMesh, "annulus_transition": AnnulusTransRingMesh,
                       "cylinder_ring": CylinderRingMesh}[kind]
        if kind == "cylinder_ring":
            common["element_type"] = definition.element_type
        # Ring helper constructors generate immediately.
        mesh = constructor(**p, **common, model=model, axis=definition.axis)
        model.meshes[definition.name] = mesh
    if not mesh.is_generated:
        mesh.generate()
    elements = list(mesh.elements.values())
    if not elements or len(elements) > MAX_MESH_ELEMENTS:
        raise ValueError("Generator produced an empty or oversized mesh.")
    # Generate at zero then translate: locked CylinderMesh otherwise ignores
    # transverse origin components and interprets axial origin as an end height.
    nodes = list(mesh.nodes.values())
    for index, node in enumerate(nodes, definition.node_start):
        node.name = f"N{index}"
        node.X += definition.origin[0]
        node.Y += definition.origin[1]
        node.Z += definition.origin[2]
    model.nodes = {node.name: node for node in nodes}
    mesh.nodes = dict(model.nodes)
    # Locked cylinder courses also omit requested membrane modifiers. Preserve
    # the user's values explicitly on every generated element, before solving.
    for index, element in enumerate(elements, definition.element_start):
        element.name = ("R" if definition.element_type == "Rect" else "Q") + str(index)
        element.kx_mod, element.ky_mod = definition.kx_mod, definition.ky_mod
    mesh.elements = {element.name: element for element in elements}
    model.quads = {} if definition.element_type == "Rect" else dict(mesh.elements)
    model.plates = dict(mesh.elements) if definition.element_type == "Rect" else {}
    mesh.origin = list(definition.origin)
    mesh_quality(model)
    return model


def mesh_geometry(model):
    nodes = list(model.nodes.values())
    indices = {node.name: index for index, node in enumerate(nodes)}
    elements = list(next(iter(model.meshes.values())).elements.values())
    points = np.array([(node.X, node.Y, node.Z) for node in nodes])
    cells = np.array([[indices[node.name] for node in (element.i_node, element.j_node, element.m_node, element.n_node)]
                      for element in elements], dtype=int)
    return [node.name for node in nodes], [element.name for element in elements], points, cells


def mesh_quality(model):
    _, _, points, cells = mesh_geometry(model)
    if not np.isfinite(points).all():
        raise ValueError("Mesh coordinates are not finite.")
    polygons = points[cells]
    edges = np.linalg.norm(np.roll(polygons, -1, axis=1)-polygons, axis=2)
    if np.any(edges.min(axis=1) < 1e-8):
        raise ValueError("Mesh contains a degenerate edge.")
    ratio = edges.max(axis=1)/edges.min(axis=1)
    if np.any(ratio > 20):
        raise ValueError("Generated element edge ratio exceeds 20; revise the mesh options.")
    for poly in polygons:
        x = poly[1]-poly[0]
        x /= np.linalg.norm(x)
        normal = np.cross(x, poly[3]-poly[0])
        norm = np.linalg.norm(normal)
        if norm < 1e-12:
            raise ValueError("Mesh contains a degenerate face.")
        normal /= norm
        if max(abs((poly-poly[0]) @ normal)) > 1e-7*max(np.linalg.norm(poly-poly[0], axis=1)):
            raise ValueError("Generated face is not planar.")
        local = np.column_stack(((poly-poly[0]) @ x, (poly-poly[0]) @ np.cross(normal, x)))
        for xi in (-1/math.sqrt(3), 1/math.sqrt(3)):
            for eta in (-1/math.sqrt(3), 1/math.sqrt(3)):
                derivatives = np.array([[-(1-eta), 1-eta, 1+eta, -(1+eta)],
                                        [-(1-xi), -(1+xi), 1+xi, 1-xi]])/4
                if np.linalg.det(derivatives @ local) <= 1e-14:
                    raise ValueError("Generated face has a nonpositive Jacobian.")
    return {"elements": len(cells), "nodes": len(points), "max_edge_ratio": float(ratio.max())}


def mesh_export(definition, model):
    names, elements, points, cells = mesh_geometry(model)
    return {"format": "pynitegui-generated-mesh", "version": 1, "units": "in-kip",
            "recipe": definition.to_dict(), "nodes": dict(zip(names, points.tolist())),
            "elements": {name: {"type": definition.element_type, "nodes": [names[i] for i in cell],
                                "material": definition.material.name, "thickness": definition.thickness,
                                "kx_mod": definition.kx_mod, "ky_mod": definition.ky_mod}
                         for name, cell in zip(elements, cells)}}
