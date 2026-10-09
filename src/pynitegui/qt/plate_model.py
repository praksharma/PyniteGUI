"""A bounded rectangular DKMQ plate pilot, independent of frame projects."""
from dataclasses import asdict, dataclass, field, fields
import json
import math
from pathlib import Path

import numpy as np
from Pynite import FEModel3D

from .model import Material, finite_number, unique_json_object
from .units import UNIT_SYSTEMS


PLANES = {"XY": (0, 1, 2, 1), "XZ": (0, 2, 1, -1), "YZ": (2, 1, 0, -1)}
EDGES = ("Left", "Right", "Bottom", "Top")
MAX_ELEMENTS = 1024


@dataclass
class PlateDefinition:
    width: float = 120.0
    height: float = 120.0
    thickness: float = 1.0
    mesh_size: float = 15.0
    plane: str = "XY"
    material: Material = field(default_factory=lambda: Material("Plate", E=3600, nu=0.2, rho=0))
    pressure: float = -0.00001
    load_case: str = "Case 1"
    load_factor: float = 1.0
    edges: dict = field(default_factory=lambda: dict.fromkeys(EDGES, "Simply supported"))
    unit_system: str = "imperial"

    def validate(self):
        for key in ("width", "height", "thickness", "mesh_size"):
            value = getattr(self, key)
            if not finite_number(value) or not 1e-6 <= value <= 1e6:
                raise ValueError(f"{key}: enter a finite length between 1e-6 and 1e6 inches.")
        if not isinstance(self.material, Material):
            raise ValueError("Invalid plate material.")
        self.material.validate()
        if not isinstance(self.plane, str) or not isinstance(self.unit_system, str) or self.plane not in PLANES or self.unit_system not in UNIT_SYSTEMS:
            raise ValueError("Unknown plane or units.")
        if not finite_number(self.pressure) or not finite_number(self.load_factor):
            raise ValueError("Pressure and load factor must be finite.")
        if not math.isfinite(self.pressure * self.load_factor * self.width * self.height):
            raise ValueError("Resultant pressure load is not finite.")
        if not isinstance(self.load_case, str) or not self.load_case.strip() or self.load_case != self.load_case.strip():
            raise ValueError("Enter a nonempty load case without surrounding spaces.")
        if not isinstance(self.edges, dict) or set(self.edges) != set(EDGES) or any(
                support not in ("Free", "Simply supported", "Clamped") for support in self.edges.values()):
            raise ValueError("Invalid plate edge supports.")
        nx, ny = math.ceil(self.width / self.mesh_size), math.ceil(self.height / self.mesh_size)
        if nx * ny > MAX_ELEMENTS:
            raise ValueError(f"Plate pilot is limited to {MAX_ELEMENTS} quads; increase the mesh size.")
        ratio = (self.width / nx) / (self.height / ny)
        if max(ratio, 1 / ratio) > 20:
            raise ValueError("Element aspect ratio exceeds 20; use a smaller mesh size or revise the geometry.")
        if not finite_number(self.width / self.height) or max(self.width / self.height, self.height / self.width) > 1e6:
            raise ValueError("Plate dimensions are too disproportionate.")

    def to_dict(self):
        self.validate()
        return {"format": "pynitegui-rectangular-plate", "version": 1, "units": "in-kip", **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("format") != "pynitegui-rectangular-plate" or type(data.get("version")) is not int or data["version"] != 1 or data.get("units") != "in-kip":
            raise ValueError("Unsupported rectangular plate file.")
        values = {key: value for key, value in data.items() if key not in ("format", "version", "units")}
        if set(values) != {item.name for item in fields(cls)}:
            raise ValueError("Plate file fields do not match the version 1 schema.")
        try:
            values["material"] = Material(**values["material"])
            result = cls(**values)
            result.validate()
        except (TypeError, KeyError) as error:
            raise ValueError(f"Invalid plate file: {error}") from error
        return result

    @classmethod
    def open(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(), object_pairs_hook=unique_json_object))

    @property
    def units(self):
        return UNIT_SYSTEMS[self.unit_system]

    @property
    def normal(self):
        _, _, axis, sign = PLANES[self.plane]
        vector = np.zeros(3)
        vector[axis] = sign
        return vector


def build_plate(definition):
    """Always regenerate from geometry; mesh node IDs never own assignments."""
    definition.validate()
    model = FEModel3D()
    material = definition.material
    model.add_material(material.name, material.E, material.G, material.nu, material.rho)
    model.add_rectangle_mesh("Surface", definition.mesh_size, definition.width, definition.height,
                             definition.thickness, material.name, plane=definition.plane, element_type="Quad")
    model.meshes["Surface"].generate()
    u, v, normal, _ = PLANES[definition.plane]
    # This transverse plate pilot explicitly restrains all in-plane motions and
    # drilling rotation. It does not model membrane loading or mixed frames.
    for node in model.nodes.values():
        coords = (node.X, node.Y, node.Z)
        on_edges = (math.isclose(coords[u], 0, abs_tol=1e-8),
                    math.isclose(coords[u], definition.width, rel_tol=1e-10, abs_tol=1e-8),
                    math.isclose(coords[v], 0, abs_tol=1e-8),
                    math.isclose(coords[v], definition.height, rel_tol=1e-10, abs_tol=1e-8))
        supports = [definition.edges[edge] for edge, on in zip(EDGES, on_edges) if on]
        fixed = [False] * 6
        fixed[u] = fixed[v] = fixed[normal + 3] = True
        fixed[normal] = any(support != "Free" for support in supports)
        if "Clamped" in supports:
            fixed[u + 3] = fixed[v + 3] = True
        model.def_support(node.name, **dict(zip(("support_DX", "support_DY", "support_DZ",
                                               "support_RX", "support_RY", "support_RZ"), fixed)))
    for quad in model.quads.values():
        model.add_quad_surface_pressure(quad.name, definition.pressure, definition.load_case)
    model.add_load_combo("Plate", {definition.load_case: definition.load_factor})
    return model


def plate_geometry(model, definition):
    names = list(model.nodes)
    indices = {name: i for i, name in enumerate(names)}
    u, v, _, _ = PLANES[definition.plane]
    points = np.array([(node.X, node.Y, node.Z) for node in model.nodes.values()])[:, [u, v]]
    cells = np.array([[indices[node.name] for node in (quad.i_node, quad.j_node, quad.m_node, quad.n_node)]
                      for quad in model.quads.values()], dtype=int)
    return names, points, cells


def analyze_plate(definition, progress=None):
    phase = progress or (lambda message: None)
    phase("Generating DKMQ mesh")
    model = build_plate(definition)
    names, points, cells = plate_geometry(model, definition)
    _, _, normal_axis, sign = PLANES[definition.plane]
    constrained = [point for name, point in zip(names, points)
                   if getattr(model.nodes[name], ("support_DX", "support_DY", "support_DZ")[normal_axis])]
    # Transverse rigid motion w=a+b*u+c*v needs three independent constraints,
    # unless a clamped edge additionally fixes its slope.
    if not constrained or ("Clamped" not in definition.edges.values() and
            np.linalg.matrix_rank(np.column_stack((np.ones(len(constrained)), np.array(constrained) / max(definition.width, definition.height)))) < 3):
        raise ValueError("Unstable plate supports: restrain transverse translation and both rigid slopes.")
    phase(f"Solving {len(cells)} plate elements")
    model.analyze_linear(check_stability=True, check_statics=False)
    phase("Sampling plate results")
    if any(not math.isfinite(value) for node in model.nodes.values()
           for key in ("DX", "DY", "DZ", "RX", "RY", "RZ", "RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ")
           for value in getattr(node, key).values()):
        raise ValueError("Plate analysis returned nonfinite nodal results.")
    displacement = np.array([getattr(model.nodes[name], ("DX", "DY", "DZ")[normal_axis])["Plate"] * sign for name in names])
    reactions = np.array([getattr(model.nodes[name], ("RxnFX", "RxnFY", "RxnFZ")[normal_axis])["Plate"] * sign for name in names])
    moments = np.array([quad.moment(0, 0, combo_name="Plate").ravel() for quad in model.quads.values()])
    shears = np.array([quad.shear(0, 0, combo_name="Plate").ravel() for quad in model.quads.values()])
    if any(not np.isfinite(values).all() for values in (displacement, reactions, moments, shears)):
        raise ValueError("Plate analysis returned nonfinite results.")
    applied = definition.pressure * definition.load_factor * definition.width * definition.height
    if abs(reactions.sum() + applied) > 1e-7 * max(1, abs(applied)):
        raise ValueError("Plate normal-force equilibrium check failed.")
    return {"names": names, "points": points, "cells": cells, "displacement": displacement,
            "reactions": reactions, "moments": moments, "shears": shears,
            "applied": applied, "definition": definition.to_dict()}


def plate_analysis_child(connection, definition):
    import contextlib
    import io
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze_plate(definition, lambda message: connection.send(("progress", message)))
        connection.send(("finished", result, ""))
    except Exception as error:
        with contextlib.suppress(BrokenPipeError, EOFError, OSError):
            connection.send(("finished", None, str(error)))
    finally:
        connection.close()
