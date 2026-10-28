"""A bounded rectangular DKMQ plate pilot, independent of frame projects."""
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
import hashlib
import json
import math
import uuid
from pathlib import Path

import numpy as np

from .model import Material, Project, finite_number, identifier, unique_json_object
from .units import UNIT_SYSTEMS
from .mesh_model import MeshDefinition, generate_mesh


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
    element_type: str = "Quad"
    origin: list = field(default_factory=lambda: [0., 0., 0.])
    x_control: list = field(default_factory=list)
    y_control: list = field(default_factory=list)
    openings: list = field(default_factory=list)
    kx_mod: float = 1.
    ky_mod: float = 1.
    node_start: int = 1
    element_start: int = 1
    mesh_name: str = "Surface"
    additional_pressures: dict = field(default_factory=dict)
    combinations: dict = field(default_factory=dict)
    self_weight_case: str | None = None
    self_weight_factor: float = 1.

    @property
    def case_pressures(self):
        return {self.load_case: self.pressure, **self.additional_pressures}

    @property
    def load_cases(self):
        return list(self.case_pressures)

    @property
    def load_combinations(self):
        # Preserve the original one-case Plate combination as a useful baseline.
        return {"Plate": {self.load_case: self.load_factor}, **self.combinations}

    def validate_combination(self, name, factors):
        Project.validate_combination(self, name, factors)
        if name == "Plate":
            raise ValueError("Plate is the primary-case combination; edit its factor in the main controls.")
        if len(name) > 80 or any(abs(factor) > 1e6 for factor in factors.values()):
            raise ValueError("Use combination names up to 80 characters and factors within +/-1e6.")

    validate_load_name = staticmethod(Project.validate_load_name)

    def pressure_for_case(self, case):
        pressure = self.case_pressures[case]
        if case == self.self_weight_case:
            # Only horizontal XZ plates can carry the complete global -Y weight
            # as transverse pressure. Never silently discard a tangent component.
            pressure += self.material.rho * self.thickness * self.self_weight_factor
        return pressure

    def rename_case(self, previous, name):
        self.validate_load_name(name)
        if name in self.load_cases and previous != name:
            raise ValueError("A pressure case with that name already exists.")
        if previous == self.load_case:
            self.load_case = name
        else:
            self.additional_pressures[name] = self.additional_pressures.pop(previous)
        for factors in self.combinations.values():
            if previous in factors:
                factors[name] = factors.pop(previous)
        if self.self_weight_case == previous:
            self.self_weight_case = name

    def mesh_definition(self):
        return MeshDefinition(name=self.mesh_name, parameters={"width": self.width, "height": self.height},
            mesh_size=self.mesh_size, thickness=self.thickness, material=self.material,
            element_type=self.element_type, origin=list(self.origin), plane=self.plane,
            x_control=list(self.x_control), y_control=list(self.y_control), openings=list(self.openings),
            kx_mod=self.kx_mod, ky_mod=self.ky_mod, node_start=self.node_start,
            element_start=self.element_start, unit_system=self.unit_system)

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
        if abs(self.load_factor) > 1e6:
            raise ValueError("The primary Plate factor must be within +/-1e6.")
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
        self.mesh_definition().validate()
        if not isinstance(self.additional_pressures, dict) or len(self.additional_pressures) > 31:
            raise ValueError("Use at most 32 plate pressure cases including the primary case.")
        if self.load_case in self.additional_pressures:
            raise ValueError("An additional pressure case cannot duplicate the primary case.")
        for name, pressure in self.case_pressures.items():
            if not identifier(name) or len(name) > 80 or not finite_number(pressure) or abs(pressure) > 1e6:
                raise ValueError("Pressure cases need names up to 80 characters and finite pressures within +/-1e6 kip/in2.")
        if not isinstance(self.combinations, dict) or len(self.combinations) > 31:
            raise ValueError("Use at most 32 plate combinations including Plate.")
        for name, factors in self.combinations.items():
            self.validate_combination(name, factors)
        if not finite_number(self.self_weight_factor) or not 0 < self.self_weight_factor <= 1e6:
            raise ValueError("Plate self-weight factor must be positive and at most 1e6.")
        if self.self_weight_case is not None:
            if not isinstance(self.self_weight_case, str) or self.self_weight_case not in self.load_cases:
                raise ValueError("Plate self-weight requires an existing pressure case.")
            if self.plane != "XZ":
                raise ValueError("Plate self-weight requires the horizontal XZ plane. Vertical plate membrane gravity is not supported.")
        for factors in self.load_combinations.values():
            value = math.fsum(self.pressure_for_case(case)*factor for case, factor in factors.items())
            if not math.isfinite(value*self.width*self.height):
                raise ValueError("Combined plate pressure resultant is not finite.")

    def to_dict(self):
        self.validate()
        data = {"format": "pynitegui-rectangular-plate", "version": 3, "units": "in-kip", **asdict(self)}
        data["material"].pop("shear_modulus")  # Plate formulation derives G.
        return data

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("format") != "pynitegui-rectangular-plate" or type(data.get("version")) is not int or data["version"] not in (1, 2, 3) or data.get("units") != "in-kip":
            raise ValueError("Unsupported rectangular plate file.")
        values = {key: value for key, value in data.items() if key not in ("format", "version", "units")}
        added = {"element_type", "origin", "x_control", "y_control", "openings", "kx_mod", "ky_mod", "node_start", "element_start", "mesh_name"}
        loading = {"additional_pressures", "combinations", "self_weight_case", "self_weight_factor"}
        expected = {item.name for item in fields(cls)} - (added if data["version"] == 1 else set()) - (loading if data["version"] < 3 else set())
        if set(values) != expected:
            raise ValueError("Plate file fields do not match the declared version schema.")
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
    model = generate_mesh(definition.mesh_definition())
    u, v, normal, _ = PLANES[definition.plane]
    # This transverse plate pilot explicitly restrains all in-plane motions and
    # drilling rotation. It does not model membrane loading or mixed frames.
    for node in model.nodes.values():
        coords = tuple(value-origin for value, origin in zip((node.X, node.Y, node.Z), definition.origin))
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
    for element in model.meshes[definition.mesh_name].elements.values():
        add_pressure = model.add_plate_surface_pressure if definition.element_type == "Rect" else model.add_quad_surface_pressure
        for case in definition.load_cases:
            add_pressure(element.name, definition.pressure_for_case(case), case)
    for name, factors in definition.load_combinations.items():
        model.add_load_combo(name, dict(factors))
    return model


def plate_geometry(model, definition):
    names = list(model.nodes)
    indices = {name: i for i, name in enumerate(names)}
    u, v, _, _ = PLANES[definition.plane]
    points = (np.array([(node.X, node.Y, node.Z) for node in model.nodes.values()])-definition.origin)[:, [u, v]]
    cells = np.array([[indices[node.name] for node in (quad.i_node, quad.j_node, quad.m_node, quad.n_node)]
                      for quad in model.meshes[definition.mesh_name].elements.values()], dtype=int)
    return names, points, cells


def plate_signature(definition):
    data = definition.to_dict()
    data.pop("unit_system")
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()


def plate_equilibrium(model, definition, combination, pressure):
    """Integrate recipe loads independently of the element reaction recovery."""
    from .equilibrium import FORCE_TOLERANCE, MOMENT_TOLERANCE, RELATIVE_TOLERANCE
    u, v, _, _ = PLANES[definition.plane]
    area = definition.width*definition.height
    first = np.array((area*definition.width/2, area*definition.height/2))
    for opening in definition.openings:
        removed = opening["width"]*opening["height"]
        area -= removed
        first -= removed*np.array((opening["x_left"]+opening["width"]/2,
                                    opening["y_bott"]+opening["height"]/2))
    centroid = np.zeros(3)
    centroid[[u, v]] = first/area
    force = definition.normal*pressure*area
    applied = np.r_[force, np.cross(centroid, force)]
    contributions = []
    for node in model.nodes.values():
        reaction = np.array([getattr(node, key)[combination] for key in
                             ("RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ")])
        point = np.array((node.X, node.Y, node.Z))-definition.origin
        contributions.append(np.r_[reaction[:3], reaction[3:]+np.cross(point, reaction[:3])])
    contributions = np.array(contributions)
    rows = []
    for index, component in enumerate(("FX", "FY", "FZ", "MX", "MY", "MZ")):
        total = math.fsum(contributions[:, index])
        residual = math.fsum((applied[index], total))
        tolerance = (FORCE_TOLERANCE if index < 3 else MOMENT_TOLERANCE) + RELATIVE_TOLERANCE*math.fsum(
            [abs(applied[index]), *abs(contributions[:, index])])
        if not all(math.isfinite(value) for value in (total, residual, tolerance)) or abs(residual) > tolerance:
            raise ValueError(f"Plate equilibrium failed for {combination}: {component} residual {residual:.6g} (limit {tolerance:.6g}), canonical kip/in units.")
        rows.append(dict(component=component, applied=float(applied[index]), reaction=total, residual=residual, tolerance=tolerance))
    return pressure*area, rows


def select_plate_combination(result, combination):
    if combination not in result["solutions"]:
        raise ValueError("Unknown solved plate combination.")
    return {**result, **result["solutions"][combination], "combination": combination}


def analyze_plate(definition, progress=None):
    if definition.element_type == "Rect" and (definition.kx_mod != 1 or definition.ky_mod != 1):
        raise ValueError("Rect transverse bending does not support stiffness modifiers; use unmodified Rect or Quad elements.")
    phase = progress or (lambda message: None)
    phase(f"Generating {definition.element_type} mesh")
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
    phase(f"Solving {len(cells)} plate elements in {len(definition.load_combinations)} combination(s)")
    model.analyze_linear(check_stability=True, check_statics=False)
    phase("Sampling plate results")
    if any(not math.isfinite(value) for node in model.nodes.values()
           for key in ("DX", "DY", "DZ", "RX", "RY", "RZ", "RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ")
           for value in getattr(node, key).values()):
        raise ValueError("Plate analysis returned nonfinite nodal results.")
    elements = list(model.meshes[definition.mesh_name].elements.values())
    stations = [(element.width()/2, element.height()/2) if definition.element_type == "Rect" else (0, 0) for element in elements]
    solutions = {}
    for combination, factors in definition.load_combinations.items():
        phase(f"Recovering and checking plate combination {combination}")
        displacement = np.array([getattr(model.nodes[name], ("DX", "DY", "DZ")[normal_axis])[combination] * sign for name in names])
        reactions = np.array([getattr(model.nodes[name], ("RxnFX", "RxnFY", "RxnFZ")[normal_axis])[combination] * sign for name in names])
        if definition.element_type == "Rect":
            from .plate_recovery import rectangular_resultants
            recovered = [rectangular_resultants(element, definition.material.E, definition.material.nu,
                                               definition.thickness, combination) for element in elements]
            moments = np.array([moment for moment, shear in recovered])
            shears = np.array([shear for moment, shear in recovered])
        else:
            moments = np.array([element.moment(*station, combo_name=combination).ravel() for element, station in zip(elements, stations)])
            # Raw DKMQ shear fails the independent Navier refinement check.
            shears = None
        if any(not np.isfinite(values).all() for values in (displacement, reactions, moments, shears) if values is not None):
            raise ValueError(f"Plate analysis returned nonfinite results for {combination}.")
        pressure = math.fsum(definition.pressure_for_case(case)*factor for case, factor in factors.items())
        applied, equilibrium = plate_equilibrium(model, definition, combination, pressure)
        solutions[combination] = dict(displacement=displacement, reactions=reactions, moments=moments, shears=shears,
                                      applied=applied, pressure=pressure, factors=dict(factors), equilibrium=equilibrium)
    result = {"names": names, "points": points, "cells": cells, "solutions": solutions,
              "snapshot_id": uuid.uuid4().hex[:12], "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "model_signature": plate_signature(definition), "definition": definition.to_dict()}
    return select_plate_combination(result, "Plate")


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
