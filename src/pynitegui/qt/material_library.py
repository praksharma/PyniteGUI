"""Reference linear-elastic presets, not certified grade/strength models."""
from dataclasses import dataclass

from .units import UNIT_SYSTEMS


@dataclass(frozen=True)
class MaterialPreset:
    key: str
    name: str
    E: float
    nu: float
    rho: float
    source: str
    note: str

    def properties(self):
        return {"E": self.E, "nu": self.nu, "rho": self.rho}


def metric(key, name, E, nu, weight, source, note):
    units = UNIT_SYSTEMS["si"]
    return MaterialPreset(key, name, units.from_display(E, "stress"), nu,
                          units.from_display(weight, "density"), source, note)


# Mass densities are converted to weight density using standard g = 9.80665 m/s2.
PRESETS = (
    MaterialPreset("steel_us", "Steel - US typical", 29000, 0.3, 2.836e-4,
                   "PyNite Quickstart", "Typical structural steel; no yield strength or grade certification."),
    metric("steel_eu", "Steel - EU typical", 210000, 0.3, 7850 * 9.80665 / 1000,
           "JRC Handbook 3", "Nominal elastic steel properties; no strength or code-compliance checks."),
    metric("aluminum", "Aluminum - typical", 70000, 0.33, 2700 * 9.80665 / 1000,
           "MIT material database", "Generic isotropic aluminum; alloy and temper must be verified separately."),
    metric("concrete_plain", "Concrete C30/37 - plain", 33000, 0.2, 24,
           "JRC Handbook 3", "Uncracked, short-term stiffness; no cracking, creep, or shrinkage."),
    metric("concrete_rc", "Concrete C30/37 - RC weight", 33000, 0.2, 25,
           "JRC Handbook 3", "Uncracked concrete stiffness with reinforced-concrete weight; reinforcement stiffness is not modeled."),
)
BY_KEY = {item.key: item for item in PRESETS}
