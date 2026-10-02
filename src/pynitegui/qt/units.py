"""Display/input units over the canonical inch-kip engineering model."""
from dataclasses import dataclass


# Exact inch and pound-force definitions: NIST SP 811, Appendix B.
# https://pml.nist.gov/cuu/pdf/sp811.pdf
INCH_TO_METRE = 0.0254
KIP_TO_KN = 4.4482216152605


@dataclass(frozen=True)
class UnitSystem:
    key: str
    label: str
    length: str
    force: str
    moment: str
    intensity: str
    stress: str
    density: str
    area: str
    inertia: str

    def factor(self, quantity):
        if quantity not in ("length", "force", "moment", "intensity", "stress", "density", "area", "inertia", "rotation"):
            raise ValueError(f"Unknown physical quantity: {quantity}")
        if self.key == "imperial":
            return 1.0
        length, force = INCH_TO_METRE, KIP_TO_KN
        return {"length": length, "force": force, "moment": force * length,
                "intensity": force / length, "stress": force / length**2 / 1000,
                "density": force / length**3, "area": 25.4**2,
                "inertia": 25.4**4, "rotation": 1.0}[quantity]

    def to_display(self, value, quantity):
        return value * self.factor(quantity)

    def from_display(self, value, quantity):
        return value / self.factor(quantity)

    @property
    def summary(self):
        return f"{self.length}, {self.force}"


UNIT_SYSTEMS = {
    "imperial": UnitSystem("imperial", "Imperial (in, kip)", "in", "kip", "kip-in", "kip/in", "kip/in2", "kip/in3", "in2", "in4"),
    "si": UnitSystem("si", "SI (m, kN)", "m", "kN", "kN-m", "kN/m", "MPa", "kN/m3", "mm2", "mm4"),
}
