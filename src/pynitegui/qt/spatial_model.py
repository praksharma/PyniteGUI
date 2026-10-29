"""Spatial frame definitions; legacy planar projects remain unchanged."""
from dataclasses import asdict, dataclass, field, fields
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
    release_start_rx: bool = False
    release_end_rx: bool = False
    release_start_ry: bool = False
    release_end_ry: bool = False
    release_start_z: bool = False
    release_end_z: bool = False

    @property
    def spatial_releases(self):
        return tuple((*(getattr(self, f"release_{end}_{axis}") for axis in ("x", "y", "z", "rx", "ry")),
                      getattr(self, f"release_{end}")) for end in ("start", "end"))

    @property
    def rotation_releases(self):
        return ((self.release_start_rx, self.release_start_ry, self.release_start),
                (self.release_end_rx, self.release_end_ry, self.release_end))

    @property
    def release_labels(self):
        if self.kind == "truss":
            return ("Axial-only", "Axial-only")
        return tuple(", ".join(axis for axis, value in zip(DOFS, flags) if value) or "None"
                     for flags in self.spatial_releases)


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
    surfaces: dict = field(default_factory=dict)
    surface_analysis_enabled: bool = False
    surface_pressures: dict = field(default_factory=dict)
    surface_supports: dict = field(default_factory=dict)

    def to_dict(self):
        data = {"version": 32, "units": "in-kip", **asdict(self),
                "surfaces": {name: mesh.to_dict() for name, mesh in self.surfaces.items()}}
        for node in data["nodes"].values():
            if finite_number(node["support_angle"]) and node["support_angle"] == 0.:
                node.pop("support_angle")
        return data

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] not in (16, 17, 18, 19, 20, 22, 24, 26, 28, 30, 32) or data.get("dimension") != "3D" or data.get("units") != "in-kip":
            raise ValueError("Unsupported spatial project version, dimension, or units.")
        if data["version"] < 28 and data.get("surface_supports", {}):
            raise ValueError("Surface edge supports require spatial version 28.")
        if data["version"] >= 28 and "surface_supports" not in data:
            raise ValueError("Missing surface_supports field.")
        if (data["version"] < 19 and "surfaces" in data) or (data["version"] >= 19 and not isinstance(data.get("surfaces"), dict)):
            raise ValueError("Surface geometry requires the version 19 spatial schema.")
        if data["version"] < 20 and (data.get("surface_analysis_enabled", False) is not False or data.get("surface_pressures", {})):
            raise ValueError("Coupled surface analysis requires spatial version 20.")
        if data["version"] >= 20 and not {"surface_analysis_enabled", "surface_pressures"} <= data.keys():
            raise ValueError("Missing coupled surface analysis fields.")
        if data["version"] >= 22 and "analysis_method" not in data:
            raise ValueError("Missing analysis_method setting.")
        if data["version"] < 22 and data.get("analysis_method", "linear") != "linear":
            raise ValueError("Analysis method settings require spatial version 22.")
        unknown = data.keys() - {f.name for f in fields(cls)} - {"version", "units"}
        if unknown:
            raise ValueError("Unknown spatial project fields: " + ", ".join(sorted(unknown)) + ".")
        # Reuse the established metadata migrations/validation, without projecting geometry.
        if data["version"] < 24 and (data.get("groups", {}) or data.get("levels", {}) or data.get("snap_levels", False) is not False):
            raise ValueError("Groups and levels require spatial version 24.")
        if data["version"] >= 24 and not {"groups", "levels", "snap_levels"} <= data.keys():
            raise ValueError("Missing groups or levels metadata.")
        metadata = {**data, "version": 25 if data["version"] >= 26 else 23, "analysis_method": data.get("analysis_method", "linear"), "nodes": {}, "members": {}, "loads": {},
                    "groups": {}, "levels": data.get("levels", {}), "snap_levels": data.get("snap_levels", False)}
        metadata.pop("dimension")
        metadata.pop("surfaces", None)
        metadata.pop("surface_analysis_enabled", None)
        metadata.pop("surface_pressures", None)
        metadata.pop("surface_supports", None)
        shared = Project.from_dict(metadata)
        result = cls(**{f.name: getattr(shared, f.name) for f in fields(Project)})
        from copy import deepcopy
        result.groups = deepcopy(data.get("groups", {}))
        for key, constructor in (("nodes", SpatialNode), ("members", SpatialMember), ("loads", SpatialLoad)):
            if not isinstance(data.get(key), dict):
                raise ValueError(f"Spatial project {key} must be an object keyed by identifiers.")
            entities = {}
            for name, value in data[key].items():
                if not identifier(name) or not isinstance(value, dict):
                    raise ValueError(f"Invalid spatial {key} entry: {name!r}.")
                if key == "loads" and data["version"] == 16 and ("elevation" in value or value.get("direction") == "Angle"):
                    raise ValueError("Spatial angle forces require project version 17.")
                if key == "members" and data["version"] < 18 and value.get("kind", "frame") != "frame":
                    raise ValueError("Spatial trusses require project version 18.")
                if key == "members":
                    from .spatial_releases import ROTATION_FIELDS, TRANSLATION_FIELDS
                    if data["version"] < 30 and any(value.get(field, False) is not False for field in ROTATION_FIELDS):
                        raise ValueError("Spatial rotational releases require project version 30.")
                    if data["version"] >= 30 and not set(ROTATION_FIELDS) <= value.keys():
                        raise ValueError("Missing spatial rotational release fields.")
                    if data["version"] < 32 and any(value.get(field, False) is not False for field in TRANSLATION_FIELDS):
                        raise ValueError("Spatial translational releases require project version 32.")
                    if data["version"] >= 32 and not set(TRANSLATION_FIELDS) <= value.keys():
                        raise ValueError("Missing spatial translational release fields.")
                try:
                    entities[name] = constructor(**value)
                except TypeError as error:
                    raise ValueError(f"Invalid spatial {key} entry {name}: {error}") from error
            setattr(result, key, entities)
        from .mesh_model import MeshDefinition
        result.surfaces = {name: MeshDefinition.from_dict(value) for name, value in data.get("surfaces", {}).items()}
        result.surface_analysis_enabled = data.get("surface_analysis_enabled", False)
        result.surface_pressures = data.get("surface_pressures", {})
        result.surface_supports = data.get("surface_supports", {})
        result.validate()
        return result

    def validate(self):
        Project(**{f.name: getattr(self, f.name) for f in fields(Project)
                   if f.name not in ("nodes", "members", "loads", "groups")}).validate()
        from .organization import validate_organization
        validate_organization(self)
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
            if not finite_number(node.support_angle) or node.support_angle != 0.:
                raise ValueError("Inclined support angles are not supported in spatial projects.")
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
            from .spatial_releases import RELEASE_FIELDS
            if member.kind not in ("frame", "truss") or any(type(getattr(member, key)) is not bool for key in RELEASE_FIELDS):
                raise ValueError(f"Member {name}: release flags must be boolean; choose frame or truss.")
            if member.kind == "truss" and any(getattr(member, key) for key in RELEASE_FIELDS):
                raise ValueError(f"Member {name}: trusses are axial-only; clear manual frame releases before changing type.")
            if member.release_start_rx and member.release_end_rx:
                raise ValueError(f"Member {name}: RX cannot be released at both ends. One RX release already removes torsion transfer.")
            if member.release_start_x and member.release_end_x:
                raise ValueError(f"Member {name}: axial DX cannot be released at both ends.")
            for translation, rotation in (("y", ""), ("z", "_ry")):
                first, last = (getattr(member, f"release_{end}_{translation}") for end in ("start", "end"))
                bends = (getattr(member, "release_start"+rotation), getattr(member, "release_end"+rotation))
                if (first and last) or sum((first, last, *bends)) > 2:
                    raise ValueError(f"Member {name}: incompatible D{translation.upper()}/R{'Z' if translation=='y' else 'Y'} releases leave the member internally unstable. "
                                     "Release at most two directions in each bending plane, and not both end translations.")
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
            if load.target in self.members and self.members[load.target].kind == "truss":
                raise ValueError(f"Load {name}: truss members accept joint loads only.")
        from .spatial_surfaces import validate_surfaces
        validate_surfaces(self)

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
        loads = []
        for member in self.members.values():
            magnitude = -self.materials[member.material].rho * self.sections[member.section].A * self.self_weight_factor
            if not magnitude:
                continue
            if member.kind == "truss":
                half = magnitude * math.dist(self.nodes[member.start].coords, self.nodes[member.end].coords) / 2
                loads.extend(SpatialLoad(f"SW {member.name} {end}", target, "FY", half, case=self.self_weight_case)
                             for end, target in (("i", member.start), ("j", member.end)))
            else:
                loads.append(SpatialLoad(f"SW {member.name}", member.name, "FY", magnitude, 0, "distributed", magnitude, 1, self.self_weight_case))
        return loads

    def self_weight_total(self):
        total = -sum(load.magnitude if load.target in self.nodes else load.magnitude *
                    math.dist(self.nodes[self.members[load.target].start].coords,
                              self.nodes[self.members[load.target].end].coords) for load in self.self_weight_loads())
        if self.surfaces and self.surface_analysis_enabled and self.self_weight_case is not None:
            from .surface_solver import face_weights
            from .spatial_surfaces import surface_geometry
            for definition in self.surfaces.values():
                _, _, points, cells = surface_geometry(definition)
                area = math.fsum(face_weights(np.asarray(points)[list(cell)])[0] for cell in cells)
                total += area*definition.thickness*definition.material.rho*self.self_weight_factor
        return total

    def inactive_rotations(self):
        from .spatial_releases import has_releases, unused_rotation_axes, inactive_components
        if has_releases(self):
            return inactive_components(unused_rotation_axes(self))
        frame_nodes = {node for member in self.members.values() if member.kind == "frame" for node in (member.start, member.end)}
        if self.surfaces and self.surface_analysis_enabled:
            from .spatial_surfaces import surface_geometry
            points = [point for mesh in self.surfaces.values() for point in surface_geometry(mesh)[2]]
            frame_nodes.update(name for name, node in self.nodes.items()
                               if any(math.dist(node.coords, point) <= 1e-8 for point in points))
        connected = {node for member in self.members.values() for node in (member.start, member.end)}
        return {(name, dof) for name in connected - frame_nodes for index, dof in enumerate(DOFS[3:], 3)
                if not self.nodes[name].restraints[index] and not self.nodes[name].springs[index]}

    def analysis_release_issues(self):
        from .spatial_releases import has_releases
        if has_releases(self):
            # Oblique moments can be several global component loads. Check the
            # assembled P-FER for each combination, including member moments,
            # rather than incorrectly rejecting individual vector components.
            return []
        inactive = self.inactive_rotations()
        return [f"Load {load.name}: {load.direction} has no rotational stiffness at truss-only joint {load.target}."
                for load in self.loads.values() if load.target in self.nodes and load.is_moment
                and (load.target, 'R' + load.direction[-1]) in inactive and load.magnitude]

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
        self.nodes, self.members, self.loads, self.groups = candidate.nodes, candidate.members, candidate.loads, candidate.groups
        return segments

    def _split_member(self, name, fractions):
        original = self.members[name]
        segments = super()._split_member(name, fractions)
        for index, segment in enumerate(segments):
            for end, keep in (("start", index == 0), ("end", index == len(segments)-1)):
                for axis in ("rx", "ry", "z"):
                    key = f"release_{end}_{axis}"
                    setattr(self.members[segment], key, getattr(original, key) if keep else False)
        return segments

    def connect_intersections(self):
        candidate = self.clone()
        candidate.validate()
        Project.connect_intersections(candidate)
        candidate.validate()
        self.nodes, self.members, self.loads, self.groups = candidate.nodes, candidate.members, candidate.loads, candidate.groups

    def analysis_topology_issues(self):
        issues = []
        if self.surfaces:
            from .spatial_surfaces import surface_analysis_issue
            issue = surface_analysis_issue(self)
            if issue:
                issues.append(issue)
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
        # Coupled connectivity includes shell edges and physical-member mesh
        # nodes, and is checked by attach_surfaces before any solver call.
        if len(groups) > 1 and not (self.surfaces and self.surface_analysis_enabled):
            issues.append("Disconnected node groups: " + "; ".join(groups) + ".")
        return issues

    def delete(self, kind, name):
        super().delete(kind, name)
        if kind == "surfaces":
            self.surface_pressures.pop(name, None)
            self.surface_supports.pop(name, None)

    def set_load_case(self, name, previous=None):
        super().set_load_case(name, previous)
        if previous is not None and previous != name:
            for pressures in self.surface_pressures.values():
                if previous in pressures:
                    pressures[name] = pressures.pop(previous)

    def delete_load_case(self, name):
        if any(name in pressures for pressures in self.surface_pressures.values()):
            raise ValueError("Reassign surface pressures before deleting their load case.")
        super().delete_load_case(name)
