"""Serializable engineering data, independent of Qt and PyNite."""
from dataclasses import asdict, dataclass, field
import json
import math


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
    E: float = 29000.0
    nu: float = 0.3
    rho: float = 0.49 / 12**3
    A: float = 10.3
    Iy: float = 15.3
    Iz: float = 510.0
    J: float = 0.506
    grid: float = 12.0

    def to_dict(self):
        return {"version": 1, "units": "in-kip", **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        if data.get("version") != 1 or data.get("units") != "in-kip":
            raise ValueError("Unsupported project version or units.")
        properties = {key: data[key] for key in ("E", "nu", "rho", "A", "Iy", "Iz", "J", "grid")}
        result = cls(**properties)
        for key, kind in (("nodes", Node), ("members", Member), ("loads", Load)):
            setattr(result, key, {name: kind(**value) for name, value in data[key].items()})
        result.validate()
        return result

    def clone(self):
        return self.from_dict(self.to_dict())

    def validate(self):
        for key in ("E", "A", "Iy", "Iz", "J", "grid"):
            value = getattr(self, key)
            if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be a positive finite number.")
        if not math.isfinite(self.nu) or not -1 < self.nu < 0.5:
            raise ValueError("Poisson's ratio must be between -1 and 0.5.")
        if not math.isfinite(self.rho) or self.rho < 0:
            raise ValueError("Density must be finite and nonnegative.")
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
            if math.isclose(node.x, x, abs_tol=1e-8) and math.isclose(node.y, y, abs_tol=1e-8):
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
        self.members[name] = Member(name, a, b)
        return name

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
