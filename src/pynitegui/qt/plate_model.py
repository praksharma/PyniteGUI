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
SUBGRADE_MODES = ("compression_only", "bilateral")
MAX_ELEMENTS = 1600


def plate_point_load_directions(plane, analysis_mode="transverse"):
    u, v, normal, _ = PLANES[plane]
    forces = ("FX", "FY", "FZ")
    if analysis_mode == "shear_wall":
        return (forces[u], forces[v])
    moments = ("MX", "MY", "MZ")
    return (forces[normal], *(moments[i] for i in sorted((u, v))))


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
    pressure_profiles: dict = field(default_factory=dict)
    subgrade_modulus: float = 0.0
    subgrade_mode: str = "compression_only"
    point_loads: list = field(default_factory=list)
    analysis_mode: str = "transverse"
    wall_supports: list = field(default_factory=list)
    wall_stories: list = field(default_factory=list)
    wall_loads: list = field(default_factory=list)

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

    def pressure_for_case(self, case, x=0., y=0.):
        pressure = self.case_pressures[case]
        profile=self.pressure_profiles.get(case)
        if profile:
            ratio=x/self.width if profile['axis']=='x' else y/self.height
            pressure+=(profile['end_pressure']-pressure)*ratio
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
        if previous in self.pressure_profiles:
            self.pressure_profiles[name]=self.pressure_profiles.pop(previous)
        for factors in self.combinations.values():
            if previous in factors:
                factors[name] = factors.pop(previous)
        if self.self_weight_case == previous:
            self.self_weight_case = name
        for load in self.point_loads:
            if isinstance(load, dict) and load.get("case") == previous:
                load["case"] = name
        for load in self.wall_loads:
            if isinstance(load, dict) and load.get("case") == previous:
                load["case"] = name

    def mesh_definition(self, include_point_loads=False):
        x_control = list(self.x_control)
        y_control = list(self.y_control)
        if include_point_loads:
            extra_x, extra_y = [], []
            if isinstance(self.point_loads, list):
                for load in self.point_loads:
                    if isinstance(load, dict):
                        extra_x.append(load.get("x"))
                        extra_y.append(load.get("y"))
            from .shear_wall_model import wall_control_coordinates
            wx, wy = wall_control_coordinates(self)
            extra_x.extend(wx)
            extra_y.extend(wy)
            for x in extra_x:
                if finite_number(x) and 0. < x < self.width and not any(math.isclose(x, c, rel_tol=1e-9, abs_tol=1e-9) for c in x_control):
                    x_control.append(float(x))
            for y in extra_y:
                if finite_number(y) and 0. < y < self.height and not any(math.isclose(y, c, rel_tol=1e-9, abs_tol=1e-9) for c in y_control):
                    y_control.append(float(y))
        return MeshDefinition(name=self.mesh_name, parameters={"width": self.width, "height": self.height},
            mesh_size=self.mesh_size, thickness=self.thickness, material=self.material,
            element_type=self.element_type, origin=list(self.origin), plane=self.plane,
            x_control=x_control, y_control=y_control, openings=list(self.openings),
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
        if not finite_number(self.width / self.height) or max(self.width / self.height, self.height / self.width) > 1e6:
            raise ValueError("Plate dimensions are too disproportionate.")
        if not finite_number(self.subgrade_modulus) or not 0. <= self.subgrade_modulus <= 1e6:
            raise ValueError("Subgrade modulus must be finite and between 0 and 1e6 kip/in3.")
        if not isinstance(self.subgrade_mode, str) or self.subgrade_mode not in SUBGRADE_MODES:
            raise ValueError("Subgrade mode must be compression_only or bilateral.")
        if not isinstance(self.additional_pressures, dict) or len(self.additional_pressures) > 31:
            raise ValueError("Use at most 32 plate pressure cases including the primary case.")
        if self.load_case in self.additional_pressures:
            raise ValueError("An additional pressure case cannot duplicate the primary case.")
        for name, pressure in self.case_pressures.items():
            if not identifier(name) or len(name) > 80 or not finite_number(pressure) or abs(pressure) > 1e6:
                raise ValueError("Pressure cases need names up to 80 characters and finite pressures within +/-1e6 kip/in2.")
        if not isinstance(self.point_loads, list) or len(self.point_loads) > 64:
            raise ValueError("Use at most 64 concentrated plate point loads.")
        from .shear_wall_model import validate_shear_wall_fields
        validate_shear_wall_fields(self)
        count = self.mesh_definition().validate()
        if count > MAX_ELEMENTS or self.mesh_definition(include_point_loads=True).validate() > MAX_ELEMENTS:
            raise ValueError(f"Plate pilot is limited to {MAX_ELEMENTS} quads; increase the mesh size.")
        allowed_directions = plate_point_load_directions(self.plane, self.analysis_mode)
        for load in self.point_loads:
            if not isinstance(load, dict) or set(load) != {"case", "x", "y", "direction", "magnitude"}:
                raise ValueError("Point load fields must be case, x, y, direction and magnitude.")
            if not isinstance(load["case"], str) or load["case"] not in self.load_cases:
                raise ValueError("Point loads require an existing load case.")
            if not isinstance(load["direction"], str) or load["direction"] not in allowed_directions:
                raise ValueError(f"Point load direction for {self.plane} plates must be one of {', '.join(allowed_directions)}.")
            if any(not finite_number(load[key]) for key in ("x", "y", "magnitude")) or abs(load["magnitude"]) > 1e6:
                raise ValueError("Point load coordinates and magnitude must be finite and within +/-1e6.")
            if not (0. <= load["x"] <= self.width and 0. <= load["y"] <= self.height):
                raise ValueError("Point load coordinates must lie on or inside the plate rectangle.")
            for opening in self.openings:
                if (opening["x_left"] < load["x"] < opening["x_left"] + opening["width"] and
                        opening["y_bott"] < load["y"] < opening["y_bott"] + opening["height"]):
                    raise ValueError("Point load coordinates cannot lie inside an opening.")
        mesh = self.mesh_definition(include_point_loads=True)
        x_points = [0., *mesh.x_control, self.width]
        y_points = [0., *mesh.y_control, self.height]
        for opening in self.openings:
            x_points.extend((opening["x_left"], opening["x_left"] + opening["width"]))
            y_points.extend((opening["y_bott"], opening["y_bott"] + opening["height"]))
        def cell_sizes(points):
            ordered = []
            for value in sorted(set(points)):
                if not ordered or not math.isclose(ordered[-1], value):
                    ordered.append(value)
            return [float(span) / math.ceil(float(span) / self.mesh_size) for span in np.diff(ordered)]
        widths, heights = cell_sizes(x_points), cell_sizes(y_points)
        if max(max(w / h, h / w) for w in widths for h in heights) > 20:
            raise ValueError("Element aspect ratio exceeds 20; use a smaller mesh size or revise the geometry.")
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
        if not isinstance(self.pressure_profiles,dict):
            raise ValueError('Pressure profiles must be a case-to-profile map.')
        for case,profile in self.pressure_profiles.items():
            if (case not in self.load_cases or not isinstance(profile,dict) or set(profile)!={'axis','end_pressure'} or
                    profile['axis'] not in ('x','y') or not finite_number(profile['end_pressure']) or abs(profile['end_pressure'])>1e6):
                raise ValueError('Pressure profiles require an existing case, local axis x/y and finite end_pressure within +/-1e6 kip/in2.')
        from .plate_pressure import pressure_coefficients
        for factors in self.load_combinations.values():
            q,gx,gy=pressure_coefficients(self,factors)
            for x,y in ((0.,0.),(self.width,0.),(0.,self.height),(self.width,self.height)):
                if not math.isfinite((q+gx*x+gy*y)*self.width*self.height):
                    raise ValueError('Combined plate pressure resultant is not finite.')

    def to_dict(self):
        self.validate()
        data = {"format": "pynitegui-rectangular-plate", "version": 5, "units": "in-kip", **asdict(self)}
        data["material"].pop("fy")  # Steel yield data belongs to frame profiles.
        data["material"].pop("shear_modulus")  # Plate formulation derives G.
        return data

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("format") != "pynitegui-rectangular-plate" or type(data.get("version")) is not int or data["version"] not in (1, 2, 3, 4, 5) or data.get("units") != "in-kip":
            raise ValueError("Unsupported rectangular plate file.")
        values = {key: value for key, value in data.items() if key not in ("format", "version", "units")}
        added = {"element_type", "origin", "x_control", "y_control", "openings", "kx_mod", "ky_mod", "node_start", "element_start", "mesh_name"}
        loading = {"additional_pressures", "combinations", "self_weight_case", "self_weight_factor"}
        subgrade = {"subgrade_modulus", "subgrade_mode", "point_loads", "analysis_mode", "wall_supports", "wall_stories", "wall_loads"}
        expected = {item.name for item in fields(cls)} - (added if data["version"] == 1 else set()) - (loading if data["version"] < 3 else set()) - ({"pressure_profiles"} if data["version"] < 4 else set()) - (subgrade if data["version"] < 5 else set())
        if set(values) != expected:
            raise ValueError("Plate file fields do not match the declared version schema.")
        try:
            values["material"] = Material(**values["material"])
            for list_key in ("point_loads", "wall_supports", "wall_stories", "wall_loads"):
                if list_key in values and isinstance(values[list_key], list):
                    values[list_key] = [dict(item) if isinstance(item, dict) else item for item in values[list_key]]
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
    model = generate_mesh(definition.mesh_definition(include_point_loads=True))
    u, v, normal, _ = PLANES[definition.plane]
    tributary_areas = dict.fromkeys(model.nodes, 0.0)
    for element in model.meshes[definition.mesh_name].elements.values():
        corners = (element.i_node, element.j_node, element.m_node, element.n_node)
        coords = [(n.X, n.Y, n.Z) for n in corners]
        elem_area = abs(coords[0][u] - coords[2][u]) * abs(coords[0][v] - coords[2][v])
        for corner in corners:
            tributary_areas[corner.name] += elem_area / 4.0
    model._pynitegui_tributary_areas = tributary_areas
    if definition.analysis_mode == "shear_wall":
        from .shear_wall_model import apply_shear_wall_supports_and_loads
        apply_shear_wall_supports_and_loads(model, definition)
        for name, factors in definition.load_combinations.items():
            model.add_load_combo(name, dict(factors))
        return model
    # Transverse plate mode explicitly restrains all in-plane motions and
    # drilling rotation.
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
        corners = (element.i_node, element.j_node, element.m_node, element.n_node)
        coords = [(n.X, n.Y, n.Z) for n in corners]
        add_pressure = model.add_plate_surface_pressure if definition.element_type == "Rect" else model.add_quad_surface_pressure
        for case in definition.load_cases:
            center=np.mean(coords,axis=0)-definition.origin
            add_pressure(element.name, definition.pressure_for_case(case,center[u],center[v]), case)
    if definition.subgrade_modulus > 0:
        normal_dof = ("DX", "DY", "DZ")[normal]
        spring_direction = "-" if definition.subgrade_mode == "compression_only" else None
        for node_name, trib in tributary_areas.items():
            if trib > 0 and not getattr(model.nodes[node_name], f"support_{normal_dof}"):
                model.def_support_spring(node_name, normal_dof, definition.subgrade_modulus * trib, spring_direction)
    for load in definition.point_loads:
        target = next((node.name for node in model.nodes.values()
                       if math.isclose((node.X, node.Y, node.Z)[u] - definition.origin[u], load["x"], rel_tol=1e-9, abs_tol=1e-7)
                       and math.isclose((node.X, node.Y, node.Z)[v] - definition.origin[v], load["y"], rel_tol=1e-9, abs_tol=1e-7)), None)
        if target is None:
            raise ValueError(f"No generated plate node matches point load at ({load['x']:g}, {load['y']:g}).")
        model.add_node_load(target, load["direction"], load["magnitude"], load["case"])
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


def plate_equilibrium(model, definition, combination):
    """Integrate recipe loads independently of the element reaction recovery."""
    if definition.analysis_mode == "shear_wall":
        from .shear_wall_model import shear_wall_equilibrium
        return shear_wall_equilibrium(model, definition, combination)
    from .equilibrium import FORCE_TOLERANCE, MOMENT_TOLERANCE, RELATIVE_TOLERANCE
    u, v, _, _ = PLANES[definition.plane]
    from .plate_pressure import pressure_resultants
    _,points,cells=plate_geometry(model,definition)
    factors = definition.load_combinations[combination]
    loads,continuous,area=pressure_resultants(definition,points,cells,factors)
    force=definition.normal*loads[0]
    first=np.zeros(3);first[[u,v]]=loads[1:]
    applied=np.r_[force,np.cross(first,definition.normal)]
    normal_force = float(loads[0])
    for load in definition.point_loads:
        factor = factors.get(load["case"], 0.)
        if not factor:
            continue
        value = float(load["magnitude"]) * factor
        arm = np.zeros(3)
        arm[u], arm[v] = load["x"], load["y"]
        if load["direction"].startswith("F"):
            f_vec = np.zeros(3)
            f_vec[("FX", "FY", "FZ").index(load["direction"])] = value
            applied[:3] += f_vec
            applied[3:] += np.cross(arm, f_vec)
            normal_force += float(f_vec @ definition.normal)
        else:
            m_vec = np.zeros(3)
            m_vec[("MX", "MY", "MZ").index(load["direction"])] = value
            applied[3:] += m_vec
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
    return normal_force, rows, continuous, area


def select_plate_combination(result, combination):
    if combination not in result["solutions"]:
        raise ValueError("Unknown solved plate combination.")
    return {**result, **result["solutions"][combination], "combination": combination}


def _transverse_stable(definition, support_points):
    if not support_points:
        return False
    if "Clamped" in definition.edges.values():
        return True
    if len(support_points) < 3:
        return False
    scale = max(definition.width, definition.height)
    return np.linalg.matrix_rank(np.column_stack((np.ones(len(support_points)), np.asarray(support_points) / scale))) >= 3


def _solve_subgrade_plate(model, definition, names, points, normal_axis, phase):
    from Pynite import Analysis
    from scipy.sparse.linalg import spsolve
    normal_dof = ("DX", "DY", "DZ")[normal_axis]
    Analysis._prepare_model(model)
    for element in (*model.quads.values(), *model.plates.values()):
        ke = element.Ke()
        element.Ke = lambda ke=ke: ke
    D1_indices, D2_indices, D2 = Analysis._partition_D(model)
    has_springs = np.array([getattr(model.nodes[name], f"spring_{normal_dof}")[0] is not None for name in names], dtype=bool)
    for name in names:
        getattr(model.nodes[name], f"spring_{normal_dof}")[2] = False
    K_elem = model.Ke(next(iter(model.load_combos)), False, False, True).tocsr()
    spring_states = {}
    solved_by_factors = {}
    for combination, factors in definition.load_combinations.items():
        factor_key = tuple(sorted((case, float(val)) for case, val in factors.items() if val))
        if factor_key in solved_by_factors:
            prev = solved_by_factors[factor_key]
            model._D[combination] = model._D[prev].copy()
            for node in model.nodes.values():
                for key in ("DX", "DY", "DZ", "RX", "RY", "RZ", "RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ"):
                    getattr(node, key)[combination] = getattr(node, key)[prev]
            spring_states[combination] = spring_states[prev].copy()
            continue
        phase(f"Solving subgrade springs for {combination}")
        for name, has_sp in zip(names, has_springs):
            if has_sp:
                getattr(model.nodes[name], f"spring_{normal_dof}")[2] = True
        P = model.P(combination)
        FER = model.FER(combination)
        P1, _ = Analysis._partition(model, P, D1_indices, D2_indices)
        FER1, _ = Analysis._partition(model, FER, D1_indices, D2_indices)
        seen = set()
        for _ in range(30):
            active = np.array([bool(getattr(model.nodes[name], f"spring_{normal_dof}")[2]) and has_sp
                               for name, has_sp in zip(names, has_springs)], dtype=bool)
            active_points = [point for name, point, is_act in zip(names, points, active)
                             if is_act or getattr(model.nodes[name], f"support_{normal_dof}")]
            if not _transverse_stable(definition, active_points):
                raise ValueError(f"Unstable plate/subgrade supports in {combination}: uplift leaves fewer than three non-collinear active supports.")
            state_key = tuple(active.tolist())
            if state_key in seen:
                raise ValueError(f"Subgrade spring active-set cycle in {combination}; no results were accepted.")
            seen.add(state_key)
            K11, K12, _, _ = Analysis._partition(model, model.Ke(combination, False, False, True).tocsr(), D1_indices, D2_indices)
            if K11.shape == (0, 0):
                D1 = np.empty((0, 1))
            else:
                D1 = spsolve(K11, (P1 - FER1) - K12 @ D2).reshape(len(D1_indices), 1)
            if not np.isfinite(D1).all():
                raise ValueError(f"Unstable plate/subgrade supports in {combination}: singular stiffness matrix.")
            Analysis._store_displacements(model, D1, D2, D1_indices, D2_indices, model.load_combos[combination])
            if definition.subgrade_mode == "bilateral" or Analysis._check_TC_convergence(model, combination, log=False):
                break
        else:
            raise ValueError(f"Subgrade spring analysis did not converge in {combination} after 30 iterations.")
        D = model._D[combination]
        R_elem = (K_elem @ D + FER - P).ravel()
        for node in model.nodes.values():
            for idx, (sup, rxn_key, sp) in enumerate((
                (node.support_DX, "RxnFX", node.spring_DX),
                (node.support_DY, "RxnFY", node.spring_DY),
                (node.support_DZ, "RxnFZ", node.spring_DZ),
                (node.support_RX, "RxnMX", node.spring_RX),
                (node.support_RY, "RxnMY", node.spring_RY),
                (node.support_RZ, "RxnMZ", node.spring_RZ),
            )):
                m = node.ID * 6 + idx
                val = float(R_elem[m]) if sup else 0.0
                if sp[0] is not None and sp[2]:
                    val -= float(sp[0]) * float(D[m, 0])
                getattr(node, rxn_key)[combination] = val
        spring_states[combination] = active
        solved_by_factors[factor_key] = combination
    return spring_states, has_springs


def _solve_shear_wall(model, definition, names, points, phase):
    from Pynite import Analysis
    from scipy.sparse.linalg import spsolve
    from .shear_wall_model import recover_story_stiffnesses
    u, v, _, _ = PLANES[definition.plane]
    u_dof, v_dof = ("DX", "DY", "DZ")[u], ("DX", "DY", "DZ")[v]
    supported = [point for name, point in zip(names, points)
                 if getattr(model.nodes[name], f"support_{u_dof}") and getattr(model.nodes[name], f"support_{v_dof}")]
    if len(supported) < 2:
        raise ValueError("Unstable shear wall supports: restrain in-plane translations at two or more distinct nodes.")
    Analysis._prepare_model(model)
    for element in (*model.quads.values(), *model.plates.values()):
        k_loc = element.ke()
        element.ke = lambda k_loc=k_loc: k_loc
        ke_glob = element.Ke()
        element.Ke = lambda ke_glob=ke_glob: ke_glob
    D1_indices, D2_indices, D2 = Analysis._partition_D(model)
    K_elem = model.Ke(next(iter(model.load_combos)), False, False, True).tocsr()
    K11, K12, _, _ = Analysis._partition(model, K_elem, D1_indices, D2_indices)
    solved_by_factors = {}
    for combination, factors in definition.load_combinations.items():
        factor_key = tuple(sorted((case, float(val)) for case, val in factors.items() if val))
        if factor_key in solved_by_factors:
            prev = solved_by_factors[factor_key]
            model._D[combination] = model._D[prev].copy()
            for node in model.nodes.values():
                for key in ("DX", "DY", "DZ", "RX", "RY", "RZ", "RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ"):
                    getattr(node, key)[combination] = getattr(node, key)[prev]
            continue
        phase(f"Solving shear wall combination {combination}")
        P = model.P(combination)
        FER = model.FER(combination)
        P1, _ = Analysis._partition(model, P, D1_indices, D2_indices)
        FER1, _ = Analysis._partition(model, FER, D1_indices, D2_indices)
        if K11.shape == (0, 0):
            D1 = np.empty((0, 1))
        else:
            D1 = spsolve(K11, (P1 - FER1) - K12 @ D2).reshape(len(D1_indices), 1)
        if not np.isfinite(D1).all():
            raise ValueError(f"Unstable shear wall supports in {combination}: singular stiffness matrix.")
        Analysis._store_displacements(model, D1, D2, D1_indices, D2_indices, model.load_combos[combination])
        D = model._D[combination]
        R_elem = (K_elem @ D + FER - P).ravel()
        for node in model.nodes.values():
            for idx, (sup, rxn_key) in enumerate((
                (node.support_DX, "RxnFX"),
                (node.support_DY, "RxnFY"),
                (node.support_DZ, "RxnFZ"),
                (node.support_RX, "RxnMX"),
                (node.support_RY, "RxnMY"),
                (node.support_RZ, "RxnMZ"),
            )):
                m = node.ID * 6 + idx
                getattr(node, rxn_key)[combination] = float(R_elem[m]) if sup else 0.0
        solved_by_factors[factor_key] = combination
    return recover_story_stiffnesses(model, definition, K11, D1_indices)


def analyze_plate(definition, progress=None):
    if definition.analysis_mode == "transverse" and definition.element_type == "Rect" and (definition.kx_mod != 1 or definition.ky_mod != 1):
        raise ValueError("Rect transverse bending does not support stiffness modifiers; use unmodified Rect or Quad elements.")
    phase = progress or (lambda message: None)
    phase(f"Generating {definition.element_type} mesh")
    model = build_plate(definition)
    names, points, cells = plate_geometry(model, definition)
    u, v, normal_axis, sign = PLANES[definition.plane]
    normal_dof = ("DX", "DY", "DZ")[normal_axis]
    u_dof, v_dof = ("DX", "DY", "DZ")[u], ("DX", "DY", "DZ")[v]
    u_rxn, v_rxn = ("RxnFX", "RxnFY", "RxnFZ")[u], ("RxnFX", "RxnFY", "RxnFZ")[v]
    is_wall = definition.analysis_mode == "shear_wall"
    if is_wall:
        phase(f"Solving {len(cells)} shear wall elements in {len(definition.load_combinations)} combination(s)")
        story_stiffnesses = _solve_shear_wall(model, definition, names, points, phase)
        has_springs = np.zeros(len(names), dtype=bool)
        spring_states = {combination: np.zeros(len(names), dtype=bool) for combination in definition.load_combinations}
    else:
        constrained = [point for name, point in zip(names, points)
                       if getattr(model.nodes[name], f"support_{normal_dof}")]
        spring_points = [point for name, point in zip(names, points)
                         if getattr(model.nodes[name], f"spring_{normal_dof}")[0] is not None]
        # Transverse rigid motion w=a+b*u+c*v needs three independent constraints,
        # unless a clamped edge additionally fixes its slope.
        if not _transverse_stable(definition, constrained + spring_points):
            raise ValueError("Unstable plate supports: restrain transverse translation and both rigid slopes.")
        phase(f"Solving {len(cells)} plate elements in {len(definition.load_combinations)} combination(s)")
        if definition.subgrade_modulus > 0:
            spring_states, has_springs = _solve_subgrade_plate(model, definition, names, points, normal_axis, phase)
        else:
            model.analyze_linear(check_stability=True, check_statics=False)
            has_springs = np.zeros(len(names), dtype=bool)
            spring_states = {combination: np.zeros(len(names), dtype=bool) for combination in definition.load_combinations}
        story_stiffnesses = {}
    phase("Sampling plate results")
    if any(not math.isfinite(value) for node in model.nodes.values()
           for key in ("DX", "DY", "DZ", "RX", "RY", "RZ", "RxnFX", "RxnFY", "RxnFZ", "RxnMX", "RxnMY", "RxnMZ")
           for value in getattr(node, key).values()):
        raise ValueError("Plate analysis returned nonfinite nodal results.")
    tributary_areas = np.array([model._pynitegui_tributary_areas[name] for name in names], dtype=float)
    elements = list(model.meshes[definition.mesh_name].elements.values())
    stations = [(element.width()/2, element.height()/2) if definition.element_type == "Rect" else (0, 0) for element in elements]
    solutions = {}
    for combination, factors in definition.load_combinations.items():
        phase(f"Recovering and checking plate combination {combination}")
        displacement_u = np.array([getattr(model.nodes[name], u_dof)[combination] for name in names])
        displacement_v = np.array([getattr(model.nodes[name], v_dof)[combination] for name in names])
        reactions_u = np.array([getattr(model.nodes[name], u_rxn)[combination] for name in names])
        reactions_v = np.array([getattr(model.nodes[name], v_rxn)[combination] for name in names])
        if is_wall:
            displacement = displacement_u
            reactions = reactions_u
        else:
            displacement = np.array([getattr(model.nodes[name], normal_dof)[combination] * sign for name in names])
            reactions = np.array([getattr(model.nodes[name], ("RxnFX", "RxnFY", "RxnFZ")[normal_axis])[combination] * sign for name in names])
        active_springs = spring_states[combination]
        if definition.subgrade_modulus > 0:
            nodal_bearing_pressure = np.array([
                (-definition.subgrade_modulus * getattr(model.nodes[name], normal_dof)[combination])
                if is_active else 0.0
                for name, is_active in zip(names, active_springs)
            ], dtype=float)
            element_bearing_pressures = nodal_bearing_pressure[cells].mean(axis=1)
        else:
            nodal_bearing_pressure = np.zeros(len(names), dtype=float)
            element_bearing_pressures = np.zeros(len(cells), dtype=float)
        if definition.element_type == "Rect":
            from .plate_recovery import rectangular_resultants, rectangular_coefficients
            recovered = [rectangular_resultants(element, definition.material.E, definition.material.nu,
                                               definition.thickness, combination) for element in elements]
            moments = np.array([moment for moment, shear in recovered])
            shears = np.array([shear for moment, shear in recovered])
            inspection = np.array([rectangular_coefficients(element, combination) for element in elements])
        else:
            moments = np.array([element.moment(*station, combo_name=combination).ravel() for element, station in zip(elements, stations)])
            # Raw DKMQ shear fails the independent Navier refinement check.
            shears = None
            # Quad's public moment recovery is bilinear extrapolation of four
            # Gauss-point values. Four corner values retain that exact field,
            # without shipping a live solver or solving again on each probe.
            inspection = np.array([[element.moment(xi, eta, combo_name=combination).ravel()
                for xi, eta in ((-1., -1.), (1., -1.), (1., 1.), (-1., 1.))] for element in elements])
        if is_wall:
            from .shear_wall_model import recover_piers_and_beams
            membrane = np.array([element.membrane(*station, combo_name=combination).ravel() for element, station in zip(elements, stations)])
            membrane_inspection = np.array([[
                element.membrane(*(((xi + 1.) * element.width() / 2., (eta + 1.) * element.height() / 2.)
                                   if definition.element_type == "Rect" else (xi, eta)), combo_name=combination).ravel()
                for xi, eta in ((-1., -1.), (1., -1.), (1., 1.), (-1., 1.))
            ] for element in elements])
            piers, coupling_beams = recover_piers_and_beams(definition, elements, combination)
        else:
            membrane = np.zeros((len(elements), 3), dtype=float)
            membrane_inspection = np.zeros((len(elements), 4, 3), dtype=float)
            piers, coupling_beams = [], []
        if any(not np.isfinite(values).all() for values in (displacement, reactions, moments, shears, inspection, nodal_bearing_pressure, element_bearing_pressures, membrane, membrane_inspection) if values is not None):
            raise ValueError(f"Plate analysis returned nonfinite results for {combination}.")
        from .plate_pressure import pressure_coefficients,element_pressures
        q,gx,gy=pressure_coefficients(definition,factors)
        pressures=element_pressures(definition,points,cells,factors)
        applied,equilibrium,continuous,area=plate_equilibrium(model,definition,combination)
        from .quad_shear_snapshot import plate_recovery
        recovered_shear=plate_recovery(definition,points,cells,moments,pressures)
        pressure=q if gx==0. and gy==0. else None
        d_max = float(np.max(np.abs(displacement_u))) if len(displacement_u) else 0.
        wall_rigidity = float(abs(applied) / d_max) if is_wall and abs(applied) > 0 and d_max > 1e-15 else 0.
        solutions[combination] = dict(displacement=displacement, displacement_u=displacement_u, displacement_v=displacement_v,
                                      reactions=reactions, reactions_u=reactions_u, reactions_v=reactions_v,
                                      moments=moments, shears=shears, recovered_shear=recovered_shear,
                                      membrane=membrane, membrane_stresses=membrane, membrane_inspection=membrane_inspection,
                                      piers=piers, coupling_beams=coupling_beams, wall_rigidity=wall_rigidity,
                                      applied=applied, pressure=pressure, mean_pressure=applied/area, element_pressures=pressures, pressure_coefficients=np.array((q,gx,gy)),
                                      continuous_pressure_resultants=dict(zip(("normal_force_kip","first_moment_local_x_kip_in","first_moment_local_y_kip_in"),continuous.tolist())),
                                      pressure_representation='Uniform per element, sampled at its geometry centroid; refine varying profiles.',
                                      nodal_bearing_pressure=nodal_bearing_pressure, element_bearing_pressures=element_bearing_pressures,
                                      soil_spring_active=active_springs, active_soil_springs=int(np.sum(active_springs)),
                                      total_soil_springs=int(np.sum(has_springs)),
                                      uplift_nodes=[name for name, has_sp, is_act in zip(names, has_springs, active_springs) if has_sp and not is_act],
                                      factors=dict(factors), equilibrium=equilibrium,
                                      inspection=inspection)
    result = {"names": names, "points": points, "cells": cells, "tributary_areas": tributary_areas,
              "story_stiffnesses": story_stiffnesses,
              "element_names": [element.name for element in elements], "solutions": solutions,
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
