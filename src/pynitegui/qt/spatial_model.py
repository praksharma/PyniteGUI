"""Spatial frame definitions; legacy planar projects remain unchanged."""
from dataclasses import asdict, dataclass, fields
import math

import numpy as np

from .model import Project, Node, Member, Load, identifier, finite_number


DOFS = ("DX", "DY", "DZ", "RX", "RY", "RZ")
FORCES = ("FX", "FY", "FZ", "MX", "MY", "MZ")
MEMBER_DIRECTIONS = (*FORCES, "Fx", "Fy", "Fz", "Mx", "My", "Mz")
RESTRAINT_FIELDS = ("restraint_x", "restraint_y", "restraint_z", "restraint_rx", "restraint_ry", "restraint_rz")
SPRING_FIELDS = ("spring_x", "spring_y", "spring_z", "spring_rx", "spring_ry", "spring_rz")


@dataclass
class SpatialNode(Node):
    z: float = 0.0
    restraint_z: bool = False
    restraint_rx: bool = False
    restraint_ry: bool = False
    spring_z: float = 0.0
    spring_rx: float = 0.0
    spring_ry: float = 0.0

    @property
    def coords(self):
        return self.x, self.y, self.z

    @property
    def restraints(self):
        if self.support == "custom":
            return tuple(getattr(self, key) for key in RESTRAINT_FIELDS)
        return {"free": (False,) * 6, "pin": (True, True, True, False, False, False),
                "roller": (False, True, False, False, False, False), "fixed": (True,) * 6}[self.support]

    @property
    def springs(self):
        return tuple(getattr(self, key) for key in SPRING_FIELDS)


@dataclass
class SpatialMember(Member):
    roll: float = 0.0


@dataclass
class SpatialLoad(Load):
    elevation: float = 0.0

    @property
    def is_moment(self):
        return self.direction.upper().startswith("M")

    def components(self, project=None, magnitude=None):
        magnitude = self.magnitude if magnitude is None else magnitude
        if self.direction != "Angle":
            return [(self.direction, magnitude)]
        azimuth, elevation = math.radians(self.angle), math.radians(self.elevation)
        factors = (math.cos(elevation)*math.cos(azimuth), math.sin(elevation), math.cos(elevation)*math.sin(azimuth))
        return [(direction, magnitude*(0. if abs(factor)<1e-14 else factor))
                for direction, factor in zip(FORCES[:3], factors)]


@dataclass
class SpatialProject(Project):
    dimension: str = "3D"

    def to_dict(self):
        return {"version": 17, "units": "in-kip", **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] not in (16, 17) or data.get("dimension") != "3D" or data.get("units") != "in-kip":
            raise ValueError("Unsupported spatial project version, dimension, or units.")
        unknown = data.keys() - {f.name for f in fields(cls)} - {"version", "units"}
        if unknown:
            raise ValueError("Unknown spatial project fields: " + ", ".join(sorted(unknown)) + ".")
        # Reuse the established metadata migrations/validation, without projecting geometry.
        metadata = {**data, "version": 15, "nodes": {}, "members": {}, "loads": {}}
        metadata.pop("dimension")
        shared = Project.from_dict(metadata)
        result = cls(**{f.name: getattr(shared, f.name) for f in fields(Project)})
        for key, constructor in (("nodes", SpatialNode), ("members", SpatialMember), ("loads", SpatialLoad)):
            if not isinstance(data.get(key), dict):
                raise ValueError(f"Spatial project {key} must be an object keyed by identifiers.")
            entities = {}
            for name, value in data[key].items():
                if not identifier(name) or not isinstance(value, dict):
                    raise ValueError(f"Invalid spatial {key} entry: {name!r}.")
                if key == "loads" and data["version"] == 16 and ("elevation" in value or value.get("direction") == "Angle"):
                    raise ValueError("Spatial angle forces require project version 17.")
                try:
                    entities[name] = constructor(**value)
                except TypeError as error:
                    raise ValueError(f"Invalid spatial {key} entry {name}: {error}") from error
            setattr(result, key, entities)
        result.validate()
        return result

    def validate(self):
        Project(**{f.name: getattr(self, f.name) for f in fields(Project)
                   if f.name not in ("nodes", "members", "loads")}).validate()
        if self.dimension != "3D":
            raise ValueError("Spatial project dimension must be 3D.")
        if any(not isinstance(getattr(self, key), dict) for key in ("nodes", "members", "loads")):
            raise ValueError("Spatial entities must be objects keyed by identifiers.")
        if set(self.nodes) & set(self.members):
            raise ValueError("Node and member identifiers must be distinct.")
        coordinates, connections = set(), set()
        for name, node in self.nodes.items():
            if not isinstance(node, SpatialNode) or name != node.name or not identifier(name):
                raise ValueError("Invalid spatial node identifier or type.")
            if not all(finite_number(value) for value in node.coords):
                raise ValueError(f"Node {name}: coordinates must be finite numbers.")
            if node.coords in coordinates:
                raise ValueError("Two nodes cannot occupy the same coordinates.")
            coordinates.add(node.coords)
            if node.support not in ("free", "pin", "roller", "fixed", "custom"):
                raise ValueError("Unknown spatial support type.")
            if any(type(getattr(node, key)) is not bool for key in RESTRAINT_FIELDS):
                raise ValueError("Support restraints must be boolean values.")
            for dof, stiffness, fixed in zip(DOFS, node.springs, node.restraints):
                if not finite_number(stiffness) or stiffness < 0:
                    raise ValueError(f"Node {name}: {dof} spring stiffness must be finite and nonnegative.")
                if stiffness and fixed:
                    raise ValueError(f"Node {name}: {dof} cannot have both a rigid restraint and a spring.")
        for name, member in self.members.items():
            if not isinstance(member, SpatialMember) or name != member.name or not identifier(name):
                raise ValueError("Invalid spatial member identifier or type.")
            if not identifier(member.start) or not identifier(member.end) or member.start not in self.nodes or member.end not in self.nodes or member.start == member.end:
                raise ValueError(f"Member {name}: invalid endpoint reference.")
            length = math.dist(self.nodes[member.start].coords, self.nodes[member.end].coords)
            if not math.isfinite(length) or length <= 1e-8:
                raise ValueError(f"Member {name}: length must be finite and endpoints must be distinct.")
            if not identifier(member.material) or not identifier(member.section) or member.material not in self.materials or member.section not in self.sections:
                raise ValueError(f"Member {name}: invalid material or section reference.")
            if member.kind != "frame" or any(flag is not False for end in member.end_releases for flag in end):
                raise ValueError(f"Member {name}: this 3D milestone supports unreleased frame members only.")
            if not finite_number(member.roll) or not -360 <= member.roll <= 360:
                raise ValueError(f"Member {name}: roll must be between -360 and 360 degrees.")
            if self.self_weight_case is not None and not finite_number(self.materials[member.material].rho * self.sections[member.section].A * self.self_weight_factor):
                raise ValueError(f"Member {name}: self-weight intensity is not finite.")
            pair = frozenset((member.start, member.end))
            if pair in connections:
                raise ValueError("Duplicate members connect the same nodes.")
            connections.add(pair)
        for name, load in self.loads.items():
            if not isinstance(load, SpatialLoad) or name != load.name or not identifier(name) or not identifier(load.target) or load.target not in {*self.nodes, *self.members}:
                raise ValueError("Invalid spatial load identifier or target.")
            directions = MEMBER_DIRECTIONS if load.target in self.members else FORCES
            if load.direction not in (*directions, "Angle"):
                raise ValueError(f"Load {name}: unsupported direction for this target.")
            if load.case not in self.load_cases or load.kind not in ("point", "distributed"):
                raise ValueError(f"Load {name}: invalid case or load type.")
            if not all(finite_number(value) for value in (load.magnitude, load.end_magnitude, load.position, load.end_position, load.angle, load.elevation)):
                raise ValueError(f"Load {name}: magnitudes and positions must be finite numbers.")
            if not -360 <= load.angle <= 360 or not -90 <= load.elevation <= 90:
                raise ValueError(f"Load {name}: azimuth must be between -360 and 360 and elevation between -90 and 90 degrees.")
            if not 0 <= load.position <= 1:
                raise ValueError(f"Load {name}: position must be between zero and one.")
            if load.kind == "distributed" and (load.target not in self.members or load.is_moment or not 0 <= load.position < load.end_position <= 1):
                raise ValueError(f"Load {name}: distributed forces require a member and 0 <= start < end <= 1; distributed moments are not supported.")

    def node_at(self, x, y, z=0):
        for name, node in self.nodes.items():
            if math.dist(node.coords, (x, y, z)) <= 1e-8:
                return name
        name = self.next_name("N", self.nodes)
        self.nodes[name] = SpatialNode(name, x, y, z=z)
        return name

    def add_member(self, start, end):
        if len(start) != 3 or len(end) != 3 or math.dist(start, end) <= 1e-8:
            raise ValueError("A spatial member needs two distinct XYZ points.")
        a, b = self.node_at(*start), self.node_at(*end)
        if any({member.start, member.end} == {a, b} for member in self.members.values()):
            raise ValueError("A member already connects these nodes.")
        name = self.next_name("M", self.members)
        self.members[name] = SpatialMember(name, a, b, self.default_material, self.default_section)
        return name

    def self_weight_loads(self):
        if self.self_weight_case is None:
            return []
        return [SpatialLoad(f"SW {member.name}", member.name, "FY", magnitude, 0, "distributed", magnitude, 1, self.self_weight_case)
                for member in self.members.values()
                if (magnitude := -self.materials[member.material].rho * self.sections[member.section].A * self.self_weight_factor)]

    def self_weight_total(self):
        return -sum(load.magnitude * math.dist(self.nodes[self.members[load.target].start].coords,
                                              self.nodes[self.members[load.target].end].coords) for load in self.self_weight_loads())

    def inactive_rotations(self):
        return set()

    def analysis_release_issues(self):
        return []

    def member_position(self, name, x, y, z):
        member = self.members[name]
        a, b = np.array(self.nodes[member.start].coords), np.array(self.nodes[member.end].coords)
        vector, point = b - a, np.array([x, y, z]) - a
        length = np.linalg.norm(vector)
        if length <= 1e-8:
            raise ValueError(f"Member {name} is too short.")
        fraction = float(np.dot(point, vector) / length**2)
        if np.linalg.norm(point - fraction * vector) <= 1e-8 and -1e-8 / length <= fraction <= 1 + 1e-8 / length:
            if fraction * length <= 1e-8:
                return 0.0
            if (1 - fraction) * length <= 1e-8:
                return 1.0
            return max(0.0, min(1.0, fraction))
        return None

    def member_intersection(self, first, second):
        one, two = self.members[first], self.members[second]
        a, b, c, d = (np.array(self.nodes[name].coords) for name in (one.start, one.end, two.start, two.end))
        r, s, q = b - a, d - c, c - a
        lr, ls = np.linalg.norm(r), np.linalg.norm(s)
        if min(lr, ls) <= 1e-8:
            raise ValueError("Spatial members must be longer than the geometry tolerance.")
        if np.linalg.norm(np.cross(r, s)) <= 1e-12 * lr * ls:
            if np.linalg.norm(np.cross(q, r)) / lr > 1e-8:
                return None
            left, right = float(q @ r / lr**2), float((d - a) @ r / lr**2)
            if (min(1, max(left, right)) - max(0, min(left, right))) * lr > 1e-8:
                raise ValueError(f"Members {first} and {second} overlap.")
            return None
        t, u = np.linalg.lstsq(np.column_stack((r, -s)), q, rcond=None)[0]
        if (np.linalg.norm(a + t * r - c - u * s) <= 1e-8
                and -1e-8 / lr <= t <= 1 + 1e-8 / lr and -1e-8 / ls <= u <= 1 + 1e-8 / ls):
            t = 0.0 if t * lr <= 1e-8 else 1.0 if (1 - t) * lr <= 1e-8 else t
            u = 0.0 if u * ls <= 1e-8 else 1.0 if (1 - u) * ls <= 1e-8 else u
            return float(max(0, min(1, t))), float(max(0, min(1, u)))
        return None

    def split_member(self, name, fraction):
        if not finite_number(fraction) or not 0 < fraction < 1:
            raise ValueError("Split fraction must be strictly between 0 and 1.")
        candidate = self.clone()
        candidate.validate()
        if name not in candidate.members:
            raise ValueError("Unknown spatial member.")
        segments = candidate._split_member(name, [fraction])
        candidate.validate()
        self.nodes, self.members, self.loads = candidate.nodes, candidate.members, candidate.loads
        return segments

    def connect_intersections(self):
        candidate = self.clone()
        candidate.validate()
        Project.connect_intersections(candidate)
        candidate.validate()
        self.nodes, self.members, self.loads = candidate.nodes, candidate.members, candidate.loads

    def analysis_topology_issues(self):
        issues = []
        for name, member in self.members.items():
            for node in self.nodes.values():
                if node.name not in (member.start, member.end) and self.member_position(name, *node.coords) is not None:
                    issues.append(f"{node.name} lies inside {name}. Use Edit > Connect Intersections or define explicit segments in Model Tables.")
        names = list(self.members)
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                try:
                    intersection = self.member_intersection(first, second)
                    if intersection and any(0 < fraction < 1 for fraction in intersection):
                        issues.append(f"Members {first} and {second} cross or meet without an explicit shared joint. Use Edit > Connect Intersections.")
                except ValueError as error:
                    issues.append(str(error))
        adjacency = {name: set() for name in self.nodes}
        for member in self.members.values():
            adjacency[member.start].add(member.end)
            adjacency[member.end].add(member.start)
        remaining, groups = set(self.nodes), []
        while remaining:
            pending, group = [min(remaining)], set()
            while pending:
                node = pending.pop()
                if node not in group:
                    group.add(node)
                    pending.extend(adjacency[node] - group)
            remaining -= group
            groups.append(", ".join(sorted(group)))
        if len(groups) > 1:
            issues.append("Disconnected node groups: " + "; ".join(groups) + ".")
        return issues
