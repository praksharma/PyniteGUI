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
    length_factor: float = 1.0
    force_factor: float = 1.0
    stress_factor: float = 1.0
    area_factor: float = 1.0
    inertia_factor: float = 1.0

    def factor(self, quantity):
        if quantity not in ("length", "force", "moment", "intensity", "stress", "density", "area", "inertia", "rotation"):
            raise ValueError(f"Unknown physical quantity: {quantity}")
        length, force = self.length_factor, self.force_factor
        return {"length": length, "force": force, "moment": force * length,
                "intensity": force / length, "stress": self.stress_factor,
                "density": force / length**3, "area": self.area_factor,
                "inertia": self.inertia_factor, "rotation": 1.0}[quantity]

    def to_display(self, value, quantity):
        return value * self.factor(quantity)

    def from_display(self, value, quantity):
        return value / self.factor(quantity)

    @property
    def summary(self):
        return f"{self.length}, {self.force}"


UNIT_SYSTEMS = {
    "imperial": UnitSystem("imperial", "Imperial (in, kip)", "in", "kip", "kip-in", "kip/in", "kip/in2", "kip/in3", "in2", "in4"),
    "si": UnitSystem("si", "SI (m, kN)", "m", "kN", "kN-m", "kN/m", "MPa", "kN/m3", "mm2", "mm4",
                     INCH_TO_METRE, KIP_TO_KN, KIP_TO_KN / INCH_TO_METRE**2 / 1000, 25.4**2, 25.4**4),
    "si_mm": UnitSystem("si_mm", "SI (mm, N)", "mm", "N", "N-mm", "N/mm", "MPa", "N/mm3", "mm2", "mm4",
                        25.4, KIP_TO_KN * 1000, KIP_TO_KN * 1000 / 25.4**2, 25.4**2, 25.4**4),
    "imperial_ft": UnitSystem("imperial_ft", "Imperial (ft, kip)", "ft", "kip", "kip-ft", "kip/ft", "kip/in2", "kip/ft3", "in2", "in4",
                              length_factor=1 / 12),
}
