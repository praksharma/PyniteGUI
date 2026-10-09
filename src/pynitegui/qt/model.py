"""Serializable engineering data, independent of Qt and PyNite."""
from dataclasses import asdict, dataclass, field
import json
import math

from .units import UNIT_SYSTEMS


def finite_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def identifier(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field or identifier: {key}.")
        result[key] = value
    return result


@dataclass
class Material:
    name: str
    E: float = 29000.0
    nu: float = 0.3
    rho: float = 0.49 / 12**3
    preset: str | None = None

    @property
    def source_label(self):
        if self.preset is None:
            return "Custom"
        from .material_library import BY_KEY
        item = BY_KEY[self.preset]
        return f"Library | {item.name} | {item.source}"

    @property
    def G(self):
        return self.E / (2 * (1 + self.nu))

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip() or self.name != self.name.strip():
            raise ValueError("Material name must be nonempty with no leading or trailing spaces.")
        if not finite_number(self.E) or self.E <= 0:
            raise ValueError(f"Material {self.name}: E must be a positive finite number.")
        if not finite_number(self.nu) or not -1 < self.nu < 0.5:
            raise ValueError(f"Material {self.name}: Poisson ratio must be between -1 and 0.5.")
        if not finite_number(self.rho) or self.rho < 0:
            raise ValueError(f"Material {self.name}: density must be finite and nonnegative.")
        if self.preset is not None:
            from .material_library import BY_KEY
            if not isinstance(self.preset, str) or self.preset not in BY_KEY:
                raise ValueError(f"Material {self.name}: unknown library preset.")
            if any(getattr(self, key) != value for key, value in BY_KEY[self.preset].properties().items()):
                raise ValueError(f"Material {self.name}: library properties differ; save as a custom material.")


@dataclass
class Section:
    name: str
    A: float = 10.3
    Iy: float = 15.3
    Iz: float = 510.0
    J: float = 0.506
    catalog: str | None = None
    designation: str | None = None
    weak_axis: bool = False

    @property
    def source_label(self):
        if self.catalog is None:
            return "Custom"
        axis = "weak-axis" if self.weak_axis else "strong-axis"
        return f"{self.catalog} | {self.designation} | {axis}"

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip() or self.name != self.name.strip():
            raise ValueError("Section name must be nonempty with no leading or trailing spaces.")
        for key in ("A", "Iy", "Iz", "J"):
            value = getattr(self, key)
            if not finite_number(value) or value <= 0:
                raise ValueError(f"Section {self.name}: {key} must be a positive finite number.")
        if type(self.weak_axis) is not bool:
            raise ValueError(f"Section {self.name}: weak_axis must be a boolean.")
        if self.catalog is None:
            if self.designation is not None or self.weak_axis:
                raise ValueError(f"Section {self.name}: custom section has invalid catalog metadata.")
        else:
            from .section_library import BY_DESIGNATION, SOURCE
            if self.catalog != SOURCE or not isinstance(self.designation, str) or self.designation not in BY_DESIGNATION:
                raise ValueError(f"Section {self.name}: unknown catalog section.")
            properties = BY_DESIGNATION[self.designation].properties(self.weak_axis)
            if any(getattr(self, key) != value for key, value in properties.items()):
                raise ValueError(f"Section {self.name}: catalog properties differ; save as a custom section.")


@dataclass
class Node:
    name: str
    x: float
    y: float
    support: str = "free"
    restraint_x: bool = False
    restraint_y: bool = False
    restraint_rz: bool = False
    spring_x: float = 0.0
    spring_y: float = 0.0
    spring_rz: float = 0.0

    @property
    def springs(self):
        return self.spring_x, self.spring_y, self.spring_rz

    @property
    def restraints(self):
        if self.support == "custom":
            return self.restraint_x, self.restraint_y, self.restraint_rz
        return {"free": (False, False, False), "pin": (True, True, False),
                "roller": (False, True, False), "fixed": (True, True, True)}[self.support]


@dataclass
class Member:
    name: str
    start: str
    end: str
    material: str = "Steel_A992"
    section: str = "W18x35"
    release_start: bool = False
    release_end: bool = False
    kind: str = "frame"
    release_start_x: bool = False
    release_end_x: bool = False
    release_start_y: bool = False
    release_end_y: bool = False

    @property
    def end_releases(self):
        start, end = self.moment_releases
        return ((self.release_start_x, self.release_start_y, start),
                (self.release_end_x, self.release_end_y, end))

    @property
    def release_labels(self):
        return tuple(", ".join(label for label, released in zip(("DX", "DY", "RZ"), flags) if released) or "None"
                     for flags in self.end_releases)

    @property
    def moment_releases(self):
        return (True, True) if self.kind == "truss" else (self.release_start, self.release_end)


@dataclass
class Load:
    name: str
    target: str
    direction: str = "FY"
    magnitude: float = -10.0
    position: float = 0.5
    kind: str = "point"
    end_magnitude: float = 0.0
    end_position: float = 1.0
    case: str = "Case 1"
    angle: float = -90.0

    def resolved_angle(self, project=None):
        if self.direction.startswith("Local"):
            if project is None or self.target not in project.members:
                raise ValueError("Local forces require a member target.")
            member = project.members[self.target]
            a, b = project.nodes[member.start], project.nodes[member.end]
            base = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
            offset = 90 if self.direction == "Local y" else self.angle if self.direction == "Local angle" else 0
            return (base + offset + 180) % 360 - 180
        return self.angle if self.direction == "Angle" else 0 if self.direction == "FX" else 90

    def components(self, project=None, magnitude=None):
        magnitude = self.magnitude if magnitude is None else magnitude
        if self.direction != "Angle" and not self.direction.startswith("Local"):
            return [(self.direction, magnitude)]
        radians = math.radians(self.resolved_angle(project))
        return [(direction, magnitude * (0.0 if abs(factor) < 1e-14 else factor))
                for direction, factor in (("FX", math.cos(radians)), ("FY", math.sin(radians)))]


@dataclass
class Project:
    nodes: dict[str, Node] = field(default_factory=dict)
    members: dict[str, Member] = field(default_factory=dict)
    loads: dict[str, Load] = field(default_factory=dict)
    materials: dict[str, Material] = field(default_factory=lambda: {"Steel_A992": Material("Steel_A992")})
    default_material: str = "Steel_A992"
    sections: dict[str, Section] = field(default_factory=lambda: {"W18x35": Section("W18x35")})
    default_section: str = "W18x35"
    grid: float = 12.0
    unit_system: str = "imperial"
    load_cases: list[str] = field(default_factory=lambda: ["Case 1"])
    default_load_case: str = "Case 1"
    combinations: dict[str, dict[str, float]] = field(default_factory=lambda: {"Service": {"Case 1": 1.0}})
    self_weight_case: str | None = None
    self_weight_factor: float = 1.0

    @property
    def units(self):
        return UNIT_SYSTEMS[self.unit_system]

    def self_weight_loads(self):
        if self.self_weight_case is None:
            return []
        loads = []
        for member in self.members.values():
            magnitude = -self.materials[member.material].rho * self.sections[member.section].A * self.self_weight_factor
            if magnitude:
                if member.kind == "truss":
                    a, b = self.nodes[member.start], self.nodes[member.end]
                    half_weight = magnitude * math.hypot(b.x - a.x, b.y - a.y) / 2
                    for end, target in (("i", member.start), ("j", member.end)):
                        loads.append(Load(f"SW {member.name} {end}", target, "FY", half_weight, case=self.self_weight_case))
                else:
                    loads.append(Load(f"SW {member.name}", member.name, "FY", magnitude, 0, "distributed",
                                      magnitude, 1, self.self_weight_case))
        return loads

    def self_weight_total(self):
        total = 0.0
        for load in self.self_weight_loads():
            if load.target in self.nodes:
                total -= load.magnitude
            else:
                member = self.members[load.target]
                a, b = self.nodes[member.start], self.nodes[member.end]
                total -= load.magnitude * math.hypot(b.x - a.x, b.y - a.y)
        return total

    @staticmethod
    def validate_load_name(name):
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            raise ValueError("Load case/combination names must be nonempty with no surrounding spaces.")

    def set_load_case(self, name, previous=None):
        self.validate_load_name(name)
        if name in self.load_cases and name != previous:
            raise ValueError(f"Load case {name} already exists.")
        if previous is None:
            self.load_cases.append(name)
        else:
            if previous not in self.load_cases:
                raise ValueError(f"Load case {previous} does not exist.")
            self.load_cases[self.load_cases.index(previous)] = name
            for load in self.loads.values():
                if load.case == previous:
                    load.case = name
            for factors in self.combinations.values():
                if previous in factors:
                    factors[name] = factors.pop(previous)
            if self.default_load_case == previous:
                self.default_load_case = name
            if self.self_weight_case == previous:
                self.self_weight_case = name

    def delete_load_case(self, name):
        if name == self.self_weight_case:
            raise ValueError("Reassign or disable self-weight before deleting its load case.")
        if name == self.default_load_case:
            raise ValueError("Choose a different default load case first.")
        if any(load.case == name for load in self.loads.values()):
            raise ValueError("Reassign loads before deleting their load case.")
        if any(name in factors for factors in self.combinations.values()):
            raise ValueError("Remove the load case from combinations before deleting it.")
        self.load_cases.remove(name)

    def validate_combination(self, name, factors):
        self.validate_load_name(name)
        if not isinstance(factors, dict) or not factors:
            raise ValueError("A combination must include at least one load case.")
        for case, factor in factors.items():
            if case not in self.load_cases:
                raise ValueError(f"Combination {name}: load case {case} does not exist.")
            if not finite_number(factor):
                raise ValueError("Combination factors must be finite numbers.")

    def set_combination(self, name, factors, previous=None):
        self.validate_combination(name, factors)
        if name in self.combinations and name != previous:
            raise ValueError(f"Combination {name} already exists.")
        if previous is not None:
            if previous not in self.combinations:
                raise ValueError(f"Combination {previous} does not exist.")
            if previous != name:
                del self.combinations[previous]
        self.combinations[name] = dict(factors)

    def delete_combination(self, name):
        if len(self.combinations) == 1:
            raise ValueError("Keep at least one load combination.")
        del self.combinations[name]

    @property
    def E(self):
        return self.materials[self.default_material].E

    @property
    def nu(self):
        return self.materials[self.default_material].nu

    @property
    def rho(self):
        return self.materials[self.default_material].rho

    def set_material(self, material, previous=None):
        material.validate()
        if material.name in self.materials and material.name != previous:
            raise ValueError(f"Material {material.name} already exists.")
        if previous is not None and previous not in self.materials:
            raise ValueError(f"Material {previous} does not exist.")
        if previous and previous != material.name:
            for member in self.members.values():
                if member.material == previous:
                    member.material = material.name
            if self.default_material == previous:
                self.default_material = material.name
            del self.materials[previous]
        self.materials[material.name] = material

    def delete_material(self, name):
        used = [member.name for member in self.members.values() if member.material == name]
        if used:
            raise ValueError(f"Material {name} is assigned to: {', '.join(used)}. Reassign those members first.")
        if name == self.default_material:
            raise ValueError("Choose a different default material before deleting this definition.")
        del self.materials[name]

    @property
    def A(self):
        return self.sections[self.default_section].A

    @property
    def Iy(self):
        return self.sections[self.default_section].Iy

    @property
    def Iz(self):
        return self.sections[self.default_section].Iz

    @property
    def J(self):
        return self.sections[self.default_section].J

    def set_section(self, section, previous=None):
        section.validate()
        if section.name in self.sections and section.name != previous:
            raise ValueError(f"Section {section.name} already exists.")
        if previous is not None and previous not in self.sections:
            raise ValueError(f"Section {previous} does not exist.")
        if previous and previous != section.name:
            for member in self.members.values():
                if member.section == previous:
                    member.section = section.name
            if self.default_section == previous:
                self.default_section = section.name
            del self.sections[previous]
        self.sections[section.name] = section

    def delete_section(self, name):
        used = [member.name for member in self.members.values() if member.section == name]
        if used:
            raise ValueError(f"Section {name} is assigned to: {', '.join(used)}. Reassign those members first.")
        if name == self.default_section:
            raise ValueError("Choose a different default section before deleting this definition.")
        del self.sections[name]

    def to_dict(self):
        return {"version": 15, "units": "in-kip", **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Project document must be a JSON object.")
        if data.get("dimension") == "3D":
            from .spatial_model import SpatialProject
            return SpatialProject.from_dict(data)
        if "dimension" in data:
            raise ValueError("Unsupported project dimension.")
        version = data.get("version")
        if type(version) is not int or version not in range(1, 16) or data.get("units") != "in-kip":
            raise ValueError("Unsupported project version or units.")
        required = {"grid", "nodes", "members", "loads"}
        required.update({"E", "nu", "rho"} if version == 1 else {"materials", "default_material"})
        required.update({"A", "Iy", "Iz", "J"} if version < 3 else {"sections", "default_section"})
        if version >= 5:
            required.update({"load_cases", "default_load_case", "combinations"})
        if version >= 7:
            required.add("unit_system")
        if version >= 11:
            required.update({"self_weight_case", "self_weight_factor"})
        missing = required - data.keys()
        if missing:
            raise ValueError("Missing project fields: " + ", ".join(sorted(missing)) + ".")

        def entities(key, kind):
            if not isinstance(data[key], dict):
                raise ValueError(f"Project {key} must be an object keyed by identifiers.")
            result = {}
            for name, value in data[key].items():
                if not identifier(name) or not isinstance(value, dict):
                    raise ValueError(f"Invalid {key} entry: {name!r}. Expected an identifier and an object.")
                try:
                    result[name] = kind(**value)
                except TypeError as error:
                    raise ValueError(f"Invalid {key} entry {name}: {error}") from error
            return result

        result = cls(grid=data["grid"])
        if version >= 11:
            result.self_weight_case = data["self_weight_case"]
            result.self_weight_factor = data["self_weight_factor"]
        if data["version"] >= 7:
            result.unit_system = data["unit_system"]
        if data["version"] >= 5:
            if not isinstance(data["load_cases"], list):
                raise ValueError("Load cases must be a list of names.")
            result.load_cases = list(data["load_cases"])
            result.default_load_case = data["default_load_case"]
            if not isinstance(data["combinations"], dict):
                raise ValueError("Combinations must be an object keyed by names.")
            if any(not isinstance(factors, dict) for factors in data["combinations"].values()):
                raise ValueError("Each combination must be an object of load-case factors.")
            result.combinations = {name: dict(factors) for name, factors in data["combinations"].items()}
        if data["version"] < 3:
            result.default_section = "Project section"
            result.sections = {result.default_section: Section(result.default_section, data["A"], data["Iy"], data["Iz"], data["J"])}
        else:
            result.default_section = data["default_section"]
            result.sections = entities("sections", Section)
        if data["version"] == 1:
            result.default_material = "Project material"
            result.materials = {result.default_material: Material(result.default_material, data["E"], data["nu"], data["rho"])}
        else:
            result.default_material = data["default_material"]
            result.materials = entities("materials", Material)
        for key, kind in (("nodes", Node), ("members", Member), ("loads", Load)):
            setattr(result, key, entities(key, kind))
        if data["version"] == 1:
            for member in result.members.values():
                member.material = result.default_material
        if data["version"] < 3:
            for member in result.members.values():
                member.section = result.default_section
        result.validate()
        return result

    def clone(self):
        return self.from_dict(self.to_dict())

    def validate(self):
        for key in ("nodes", "members", "loads", "materials", "sections", "combinations"):
            if not isinstance(getattr(self, key), dict):
                raise ValueError(f"Project {key} must be an object keyed by identifiers.")
        for key in ("default_material", "default_section", "default_load_case"):
            if not identifier(getattr(self, key)):
                raise ValueError(f"Invalid {key} identifier.")
        if set(self.nodes) & set(self.members):
            raise ValueError("Node and member identifiers must be distinct to avoid ambiguous load targets.")
        if not isinstance(self.unit_system, str) or self.unit_system not in UNIT_SYSTEMS:
            raise ValueError("Unsupported unit system.")
        if not isinstance(self.load_cases, list) or not self.load_cases:
            raise ValueError("Load cases must be a nonempty list of names.")
        for case in self.load_cases:
            self.validate_load_name(case)
        if len(self.load_cases) != len(set(self.load_cases)):
            raise ValueError("Load cases must be unique.")
        if self.default_load_case not in self.load_cases:
            raise ValueError("Default load case does not exist.")
        if self.self_weight_case is not None and (not identifier(self.self_weight_case) or self.self_weight_case not in self.load_cases):
            raise ValueError("Self-weight load case does not exist.")
        if not finite_number(self.self_weight_factor) or self.self_weight_factor <= 0:
            raise ValueError("Self-weight factor must be a positive finite number.")
        if not self.combinations:
            raise ValueError("Keep at least one load combination.")
        for name, factors in self.combinations.items():
            self.validate_combination(name, factors)
        if self.default_material not in self.materials:
            raise ValueError("Default material does not exist.")
        for name, material in self.materials.items():
            if name != material.name:
                raise ValueError("Invalid material identifier.")
            material.validate()
        if self.default_section not in self.sections:
            raise ValueError("Default section does not exist.")
        for name, section in self.sections.items():
            if name != section.name:
                raise ValueError("Invalid section identifier.")
            section.validate()
        for key in ("grid",):
            value = getattr(self, key)
            if not finite_number(value) or value <= 0:
                raise ValueError(f"{key} must be a positive finite number.")
        coords = set()
        for name, node in self.nodes.items():
            if name != node.name or not identifier(name):
                raise ValueError("Invalid node identifier.")
            if not all(finite_number(value) for value in (node.x, node.y)):
                raise ValueError(f"Node {name}: coordinates must be finite numbers.")
            if (node.x, node.y) in coords:
                raise ValueError("Two nodes cannot occupy the same coordinates.")
            coords.add((node.x, node.y))
            if node.support not in ("free", "pin", "roller", "fixed", "custom"):
                raise ValueError("Unknown support type.")
            if any(type(value) is not bool for value in (node.restraint_x, node.restraint_y, node.restraint_rz)):
                raise ValueError("Support restraints must be boolean values.")
            for label, stiffness, fixed in zip(("DX", "DY", "RZ"), node.springs, node.restraints):
                if not finite_number(stiffness) or stiffness < 0:
                    raise ValueError(f"Node {name}: {label} spring stiffness must be finite and nonnegative; zero means no spring.")
                if stiffness and fixed:
                    raise ValueError(f"Node {name}: {label} cannot have both a rigid restraint and a spring. Set its spring stiffness to zero or free that direction.")
        connections = set()
        for name, member in self.members.items():
            references = (member.start, member.end, member.material, member.section)
            if (name != member.name or not identifier(name) or not all(identifier(value) for value in references)
                    or member.start not in self.nodes or member.end not in self.nodes):
                raise ValueError("Invalid member or endpoint reference.")
            if member.start == member.end:
                raise ValueError("A member needs two different nodes.")
            if any(type(value) is not bool for value in (member.release_start, member.release_end,
                    member.release_start_x, member.release_end_x, member.release_start_y, member.release_end_y)):
                raise ValueError(f"Member {name}: end releases must be true or false.")
            if member.kind not in ("frame", "truss"):
                raise ValueError(f"Member {name}: type must be frame or truss.")
            if member.kind == "truss" and any((member.release_start_x, member.release_end_x, member.release_start_y, member.release_end_y)):
                raise ValueError(f"Member {name}: truss bars cannot have axial/shear releases. Clear these frame releases before changing type.")
            if member.release_start_x and member.release_end_x:
                raise ValueError(f"Member {name}: axial DX cannot be released at both ends.")
            # The released bending block must remain invertible for static condensation.
            bending = (member.release_start_y, member.release_end_y, *member.moment_releases)
            if sum(bending) > 2 or (member.release_start_y and member.release_end_y):
                raise ValueError(f"Member {name}: incompatible DY/RZ releases leave the member internally unstable. Release at most two bending directions, and not DY at both ends.")
            if member.material not in self.materials:
                raise ValueError(f"Member {name}: material {member.material} does not exist.")
            if member.section not in self.sections:
                raise ValueError(f"Member {name}: section {member.section} does not exist.")
            if self.self_weight_case is not None and not finite_number(self.materials[member.material].rho * self.sections[member.section].A * self.self_weight_factor):
                raise ValueError(f"Member {name}: self-weight intensity is not finite.")
            connection = frozenset((member.start, member.end))
            if connection in connections:
                raise ValueError("Duplicate members connect the same nodes.")
            connections.add(connection)
        for name, load in self.loads.items():
            if (name != load.name or not identifier(name) or not identifier(load.target)
                    or load.target not in {*self.nodes, *self.members}):
                raise ValueError("Invalid load target.")
            if load.case not in self.load_cases:
                raise ValueError(f"Load {name}: load case {load.case} does not exist.")
            if load.target in self.members and self.members[load.target].kind == "truss":
                raise ValueError(f"Load {name}: truss member {load.target} accepts joint loads only. Apply the load to a node or use a frame member.")
            if load.direction not in ("FX", "FY", "MZ", "Angle", "Local x", "Local y", "Local angle"):
                raise ValueError("Unsupported 2D load direction.")
            if load.direction.startswith("Local") and load.target not in self.members:
                raise ValueError("Local forces require a member target.")
            if not finite_number(load.angle) or not -360 <= load.angle <= 360:
                raise ValueError("Load angle must be finite and between -360 and 360 degrees.")
            if not finite_number(load.magnitude) or not finite_number(load.position) or not 0 <= load.position <= 1:
                raise ValueError("Invalid load magnitude or position.")
            if not finite_number(load.end_magnitude) or not finite_number(load.end_position):
                raise ValueError(f"Load {name}: end intensity and position must be finite numbers.")
            if load.kind not in ("point", "distributed"):
                raise ValueError("Unknown load type.")
            if load.kind == "distributed":
                if load.target not in self.members or load.direction == "MZ":
                    raise ValueError("Distributed forces require a member and a force direction, not MZ.")
                if not load.position < load.end_position <= 1:
                    raise ValueError("Distributed load requires finite intensities and 0 <= start < end <= 1.")

    def next_name(self, prefix, collection):
        index = 1
        while f"{prefix}{index}" in collection:
            index += 1
        return f"{prefix}{index}"

    def node_at(self, x, y):
        for node in self.nodes.values():
            if math.isclose(node.x, x, rel_tol=0, abs_tol=1e-8) and math.isclose(node.y, y, rel_tol=0, abs_tol=1e-8):
                return node.name
        name = self.next_name("N", self.nodes)
        self.nodes[name] = Node(name, x, y)
        return name

    def add_member(self, start, end):
        if math.dist(start, end) < 1e-8:
            raise ValueError("A member needs two different points.")
        a, b = self.node_at(*start), self.node_at(*end)
        if any({m.start, m.end} == {a, b} for m in self.members.values()):
            raise ValueError("A member already connects these nodes.")
        name = self.next_name("M", self.members)
        self.members[name] = Member(name, a, b, self.default_material, self.default_section)
        return name

    def member_position(self, name, x, y):
        member = self.members[name]
        a, b = self.nodes[member.start], self.nodes[member.end]
        dx, dy = b.x - a.x, b.y - a.y
        length = math.hypot(dx, dy)
        if length <= 1e-8:
            raise ValueError(f"Member {name} is too short.")
        fraction = ((x - a.x) * dx + (y - a.y) * dy) / length**2
        distance = abs((x - a.x) * dy - (y - a.y) * dx) / length
        if distance <= 1e-8 and -1e-8 / length <= fraction <= 1 + 1e-8 / length:
            if fraction * length <= 1e-8:
                return 0.0
            if (1 - fraction) * length <= 1e-8:
                return 1.0
            return max(0.0, min(1.0, fraction))
        return None

    def member_intersection(self, first, second):
        one, two = self.members[first], self.members[second]
        a, b = self.nodes[one.start], self.nodes[one.end]
        c, d = self.nodes[two.start], self.nodes[two.end]
        rx, ry, sx, sy = b.x - a.x, b.y - a.y, d.x - c.x, d.y - c.y
        lr, ls = math.hypot(rx, ry), math.hypot(sx, sy)
        if min(lr, ls) <= 1e-8:
            raise ValueError(f"Members must be longer than {self.units.to_display(1e-8, 'length'):g} {self.units.length}.")
        qx, qy = c.x - a.x, c.y - a.y
        denominator = rx * sy - ry * sx
        if abs(denominator) <= 1e-12 * lr * ls:
            if abs(qx * ry - qy * rx) / lr > 1e-8:
                return None
            left = (qx * rx + qy * ry) / lr**2
            right = left + (sx * rx + sy * ry) / lr**2
            overlap = min(1, max(left, right)) - max(0, min(left, right))
            if overlap * lr > 1e-8:
                raise ValueError(f"Members {first} and {second} overlap. Remove or shorten the overlapping member.")
            return None
        t = (qx * sy - qy * sx) / denominator
        u = (qx * ry - qy * rx) / denominator
        if -1e-8 / lr <= t <= 1 + 1e-8 / lr and -1e-8 / ls <= u <= 1 + 1e-8 / ls:
            t = 0.0 if t * lr <= 1e-8 else 1.0 if (1 - t) * lr <= 1e-8 else t
            u = 0.0 if u * ls <= 1e-8 else 1.0 if (1 - u) * ls <= 1e-8 else u
            return max(0.0, min(1.0, t)), max(0.0, min(1.0, u))
        return None

    def split_member(self, name, fraction):
        if not math.isfinite(fraction) or not 0 < fraction < 1:
            raise ValueError("Split fraction must be strictly between 0 and 1.")
        return self._split_member(name, [fraction])

    def subdivide_members(self, names, count):
        """Atomically split selected members into equal physical segments."""
        if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 100:
            raise ValueError("Choose between 2 and 100 equal segments per member.")
        names = list(dict.fromkeys(names))
        if not names or any(name not in self.members for name in names):
            raise ValueError("Select existing members to subdivide.")
        candidate = self.clone()
        candidate.validate()
        segments = {}
        for name in names:
            member = candidate.members[name]
            if member.kind == "truss":
                raise ValueError(f"Member {name}: equal subdivision of axial-only trusses introduces unbraced joints. Use explicit split/connect operations with appropriate bracing instead.")
            a, b = candidate.nodes[member.start], candidate.nodes[member.end]
            spatial = getattr(candidate, "dimension", "2D") == "3D"
            length = math.dist(a.coords, b.coords) if spatial else math.hypot(b.x - a.x, b.y - a.y)
            if length / count <= 1e-8:
                raise ValueError(f"Member {name}: subdivisions are too close to the geometry tolerance.")
            segments[name] = candidate._split_member(name, [index / count for index in range(1, count)])
            if len(segments[name]) != count:
                raise ValueError(f"Member {name}: could not create all equal segments.")
        candidate.validate()
        self.nodes, self.members, self.loads = candidate.nodes, candidate.members, candidate.loads
        return segments

    def _split_member(self, name, fractions):
        from dataclasses import replace
        original = self.members[name]
        a, b = self.nodes[original.start], self.nodes[original.end]
        spatial = getattr(self, "dimension", "2D") == "3D"
        start_point, end_point = (a.coords, b.coords) if spatial else ((a.x, a.y), (b.x, b.y))
        length = math.dist(start_point, end_point)
        cuts = [0.0]
        for fraction in sorted(fractions):
            if (fraction - cuts[-1]) * length > 1e-8 and (1 - fraction) * length > 1e-8:
                cuts.append(fraction)
        if len(cuts) == 1:
            raise ValueError("Split point is too close to a member endpoint.")
        cuts.append(1.0)
        nodes = [original.start]
        nodes.extend(self.node_at(*(start + t * (end - start) for start, end in zip(start_point, end_point)))
                     for t in cuts[1:-1])
        nodes.append(original.end)
        segments = []
        for index, (start, end) in enumerate(zip(nodes, nodes[1:])):
            segment = name if index == 0 else self.next_name("M", self.members)
            self.members[segment] = replace(original, name=segment, start=start, end=end,
                                            release_start=original.release_start if index == 0 else False,
                                            release_end=original.release_end if index == len(nodes) - 2 else False,
                                            release_start_x=original.release_start_x if index == 0 else False,
                                            release_end_x=original.release_end_x if index == len(nodes) - 2 else False,
                                            release_start_y=original.release_start_y if index == 0 else False,
                                            release_end_y=original.release_end_y if index == len(nodes) - 2 else False)
            segments.append(segment)
        for load in list(self.loads.values()):
            if load.target != name:
                continue
            if load.kind == "distributed":
                pieces = []
                for index, (left, right) in enumerate(zip(cuts, cuts[1:])):
                    start, end = max(left, load.position), min(right, load.end_position)
                    if start >= end:
                        continue
                    slope = (load.end_magnitude - load.magnitude) / (load.end_position - load.position)
                    identifier = load.name if not pieces else self.next_name("L", self.loads)
                    piece = replace(load, name=identifier, target=segments[index],
                                    position=(start - left) / (right - left),
                                    end_position=(end - left) / (right - left),
                                    magnitude=load.magnitude + slope * (start - load.position),
                                    end_magnitude=load.magnitude + slope * (end - load.position))
                    self.loads[identifier] = piece
                    pieces.append(piece)
                continue
            position = load.position
            if spatial:
                # Keep rolled local forces/moments on a segment endpoint at cuts.
                for cut in cuts[1:-1]:
                    if abs(position - cut) * length <= 1e-8:
                        position = cut
                        break
                index = next(i for i, right in enumerate(cuts[1:]) if position <= right)
                load.target = segments[index]
                load.position = (position - cuts[index]) / (cuts[index + 1] - cuts[index])
                continue
            for index, cut in enumerate(cuts[1:-1], 1):
                if abs(position - cut) * length <= 1e-8:
                    if load.direction.startswith("Local"):
                        load.angle = load.resolved_angle(self)
                        load.direction = "Angle"
                    load.target = nodes[index]
                    break
            else:
                index = next(i for i, right in enumerate(cuts[1:]) if position <= right)
                load.target = segments[index]
                load.position = (position - cuts[index]) / (cuts[index + 1] - cuts[index])
        return segments

    def connect_intersections(self):
        names = list(self.members)
        cuts = {name: [] for name in names}
        # Collect every split first so IDs and original load fractions stay stable.
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                intersection = self.member_intersection(first, second)
                if intersection:
                    for name, fraction in zip((first, second), intersection):
                        if 0 < fraction < 1:
                            cuts[name].append(fraction)
        for name in names:
            member = self.members[name]
            for node in self.nodes.values():
                if node.name not in (member.start, member.end):
                    point = node.coords if getattr(self, "dimension", "2D") == "3D" else (node.x, node.y)
                    fraction = self.member_position(name, *point)
                    if fraction is not None and 0 < fraction < 1:
                        cuts[name].append(fraction)
        for name, fractions in cuts.items():
            if fractions:
                self._split_member(name, fractions)

    def inactive_rotations(self):
        connected = set()
        active = set()
        for member in self.members.values():
            connected.update((member.start, member.end))
            release_start, release_end = member.moment_releases
            if not release_start:
                active.add(member.start)
            if not release_end:
                active.add(member.end)
        return {name for name in connected - active if not self.nodes[name].restraints[2] and not self.nodes[name].spring_rz}

    def analysis_release_issues(self):
        issues = []
        for node in sorted(self.inactive_rotations()):
            for combination, factors in self.combinations.items():
                moments = [load.magnitude * factors.get(load.case, 0) for load in self.loads.values()
                           if load.target == node and load.direction == "MZ"]
                total = math.fsum(moments)
                if abs(total) > math.fsum(abs(value) for value in moments) * 1e-12:
                    issues.append(f"Node {node}: all connected member ends are hinged, so nodal moment MZ in {combination} has no rotational restraint. Remove the moment or provide a moment-resisting connection/support.")
        return issues

    def analysis_topology_issues(self):
        issues = []
        names = list(self.members)
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                try:
                    self.member_intersection(first, second)
                except ValueError as error:
                    issues.append(str(error))
        adjacency = {name: set() for name in self.nodes}
        for name, member in self.members.items():
            adjacency[member.start].add(member.end)
            adjacency[member.end].add(member.start)
            for node in self.nodes.values():
                if node.name not in (member.start, member.end):
                    fraction = self.member_position(name, node.x, node.y)
                    if fraction is not None and 0 < fraction < 1:
                        issues.append(f"{node.name} lies inside {name}. Use Edit > Connect Intersections to make this connection explicit.")
        remaining = set(self.nodes)
        components = []
        while remaining:
            todo, component = [min(remaining)], set()
            while todo:
                node = todo.pop()
                if node not in component:
                    component.add(node)
                    todo.extend(adjacency[node] - component)
            remaining -= component
            components.append(", ".join(sorted(component)))
        if len(components) > 1:
            issues.append("Disconnected node groups: " + "; ".join(components) + ". Connect or remove separate parts before analysis.")
        return issues

    def delete(self, kind, name):
        if kind == "nodes":
            attached = [m.name for m in self.members.values() if name in (m.start, m.end)]
            for member in attached:
                self.delete("members", member)
        if kind in ("nodes", "members"):
            self.loads = {key: load for key, load in self.loads.items() if load.target != name}
        getattr(self, kind).pop(name, None)

    def save(self, path):
        self.validate()
        # Replace only after the full document has been written successfully.
        from pathlib import Path
        import os
        import tempfile
        destination = Path(path)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as stream:
                temporary = stream.name
                json.dump(self.to_dict(), stream, indent=2, allow_nan=False)
                stream.write("\n")
            os.replace(temporary, destination)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def open(cls, path):
        with open(path, encoding="utf-8") as stream:
            try:
                data = json.load(stream, object_pairs_hook=unique_json_object)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid project JSON at line {error.lineno}, column {error.colno}: {error.msg}.") from error
            return cls.from_dict(data)
