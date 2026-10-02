"""Serializable engineering data, independent of Qt and PyNite."""
from dataclasses import asdict, dataclass, field
import json
import math


@dataclass
class Material:
    name: str
    E: float = 29000.0
    nu: float = 0.3
    rho: float = 0.49 / 12**3

    @property
    def G(self):
        return self.E / (2 * (1 + self.nu))

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip() or self.name != self.name.strip():
            raise ValueError("Material name must be nonempty with no leading or trailing spaces.")
        if not isinstance(self.E, (int, float)) or not math.isfinite(self.E) or self.E <= 0:
            raise ValueError(f"Material {self.name}: E must be a positive finite number.")
        if not isinstance(self.nu, (int, float)) or not math.isfinite(self.nu) or not -1 < self.nu < 0.5:
            raise ValueError(f"Material {self.name}: Poisson ratio must be between -1 and 0.5.")
        if not isinstance(self.rho, (int, float)) or not math.isfinite(self.rho) or self.rho < 0:
            raise ValueError(f"Material {self.name}: density must be finite and nonnegative.")


@dataclass
class Section:
    name: str
    A: float = 10.3
    Iy: float = 15.3
    Iz: float = 510.0
    J: float = 0.506

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip() or self.name != self.name.strip():
            raise ValueError("Section name must be nonempty with no leading or trailing spaces.")
        for key in ("A", "Iy", "Iz", "J"):
            value = getattr(self, key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Section {self.name}: {key} must be a positive finite number.")


@dataclass
class Node:
    name: str
    x: float
    y: float
    support: str = "free"


@dataclass
class Member:
    name: str
    start: str
    end: str
    material: str = "Steel_A992"
    section: str = "W18x35"


@dataclass
class Load:
    name: str
    target: str
    direction: str = "FY"
    magnitude: float = -10.0
    position: float = 0.5


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
        return {"version": 3, "units": "in-kip", **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if data.get("version") not in (1, 2, 3) or data.get("units") != "in-kip":
            raise ValueError("Unsupported project version or units.")
        result = cls(grid=data["grid"])
        if data["version"] < 3:
            result.default_section = "Project section"
            result.sections = {result.default_section: Section(result.default_section, data["A"], data["Iy"], data["Iz"], data["J"])}
        else:
            result.default_section = data["default_section"]
            result.sections = {name: Section(**value) for name, value in data["sections"].items()}
        if data["version"] == 1:
            result.default_material = "Project material"
            result.materials = {result.default_material: Material(result.default_material, data["E"], data["nu"], data["rho"])}
        else:
            result.default_material = data["default_material"]
            result.materials = {name: Material(**value) for name, value in data["materials"].items()}
        for key, kind in (("nodes", Node), ("members", Member), ("loads", Load)):
            setattr(result, key, {name: kind(**value) for name, value in data[key].items()})
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
            if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be a positive finite number.")
        coords = set()
        for name, node in self.nodes.items():
            if name != node.name or not name:
                raise ValueError("Invalid node identifier.")
            if not all(math.isfinite(value) for value in (node.x, node.y)):
                raise ValueError("Node coordinates must be finite.")
            if (node.x, node.y) in coords:
                raise ValueError("Two nodes cannot occupy the same coordinates.")
            coords.add((node.x, node.y))
            if node.support not in ("free", "pin", "roller", "fixed"):
                raise ValueError("Unknown support type.")
        connections = set()
        for name, member in self.members.items():
            if name != member.name or not name or member.start not in self.nodes or member.end not in self.nodes:
                raise ValueError("Invalid member or endpoint reference.")
            if member.start == member.end:
                raise ValueError("A member needs two different nodes.")
            if member.material not in self.materials:
                raise ValueError(f"Member {name}: material {member.material} does not exist.")
            if member.section not in self.sections:
                raise ValueError(f"Member {name}: section {member.section} does not exist.")
            connection = frozenset((member.start, member.end))
            if connection in connections:
                raise ValueError("Duplicate members connect the same nodes.")
            connections.add(connection)
        for name, load in self.loads.items():
            if name != load.name or not name or load.target not in {*self.nodes, *self.members}:
                raise ValueError("Invalid load target.")
            if load.direction not in ("FX", "FY", "MZ"):
                raise ValueError("Unsupported 2D load direction.")
            if not math.isfinite(load.magnitude) or not math.isfinite(load.position) or not 0 <= load.position <= 1:
                raise ValueError("Invalid load magnitude or position.")

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
            raise ValueError("Members must be longer than 1e-8 in.")
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

    def _split_member(self, name, fractions):
        from dataclasses import replace
        original = self.members[name]
        a, b = self.nodes[original.start], self.nodes[original.end]
        length = math.hypot(b.x - a.x, b.y - a.y)
        cuts = [0.0]
        for fraction in sorted(fractions):
            if (fraction - cuts[-1]) * length > 1e-8 and (1 - fraction) * length > 1e-8:
                cuts.append(fraction)
        if len(cuts) == 1:
            raise ValueError("Split point is too close to a member endpoint.")
        cuts.append(1.0)
        nodes = [original.start]
        nodes.extend(self.node_at(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y)) for t in cuts[1:-1])
        nodes.append(original.end)
        segments = []
        for index, (start, end) in enumerate(zip(nodes, nodes[1:])):
            segment = name if index == 0 else self.next_name("M", self.members)
            self.members[segment] = replace(original, name=segment, start=start, end=end)
            segments.append(segment)
        for load in self.loads.values():
            if load.target != name:
                continue
            position = load.position
            for index, cut in enumerate(cuts[1:-1], 1):
                if abs(position - cut) * length <= 1e-8:
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
                    fraction = self.member_position(name, node.x, node.y)
                    if fraction is not None and 0 < fraction < 1:
                        cuts[name].append(fraction)
        for name, fractions in cuts.items():
            if fractions:
                self._split_member(name, fractions)

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
            return cls.from_dict(json.load(stream))
