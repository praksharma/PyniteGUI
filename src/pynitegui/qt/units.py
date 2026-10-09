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
        if quantity not in ("length", "force", "moment", "intensity", "stress", "density", "area", "inertia", "rotation", "stiffness", "rotational_stiffness"):
            raise ValueError(f"Unknown physical quantity: {quantity}")
        length, force = self.length_factor, self.force_factor
        return {"length": length, "force": force, "moment": force * length,
                "intensity": force / length, "stress": self.stress_factor,
                "density": force / length**3, "area": self.area_factor,
                "inertia": self.inertia_factor, "rotation": 1.0,
                "stiffness": force / length, "rotational_stiffness": force * length}[quantity]

    @property
    def stiffness(self):
        return self.intensity

    @property
    def rotational_stiffness(self):
        return self.moment + "/rad"

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

# Keep existing preset keys stable for saved projects. Additional combinations
# are deterministic registry entries, so they need no mutable global settings.
LENGTH_UNITS = {"mm": 25.4, "cm": 2.54, "m": INCH_TO_METRE,
                "in": 1.0, "ft": 1 / 12}
FORCE_UNITS = {"N": KIP_TO_KN * 1000, "kN": KIP_TO_KN,
               "lbf": 1000.0, "kip": 1.0}


def unit_key(length, force):
    """Resolve independent choices, retaining familiar preset identities."""
    if length not in LENGTH_UNITS or force not in FORCE_UNITS:
        raise ValueError("Unsupported length or force unit.")
    for key, units in UNIT_SYSTEMS.items():
        if (units.length, units.force) == (length, force):
            return key
    return f"custom_{length}_{force}"


for _length, _length_factor in LENGTH_UNITS.items():
    for _force, _force_factor in FORCE_UNITS.items():
        _key = unit_key(_length, _force)
        if _key in UNIT_SYSTEMS:
            continue
        # Section properties retain conventional mm or inch dimensions even
        # when geometry uses metres, centimetres, or feet.
        _metric = _length in ("mm", "cm", "m")
        _section = "mm" if _metric else "in"
        _section_factor = 25.4 if _metric else 1.0
        _stress = "MPa" if _metric else ("psi" if _force in ("N", "kN", "lbf") else "kip/in2")
        _stress_factor = KIP_TO_KN * 1000 / 25.4**2 if _metric else (1000.0 if _stress == "psi" else 1.0)
        UNIT_SYSTEMS[_key] = UnitSystem(
            _key, f"Custom ({_length}, {_force})", _length, _force,
            f"{_force}-{_length}", f"{_force}/{_length}", _stress,
            f"{_force}/{_length}3", f"{_section}2", f"{_section}4",
            _length_factor, _force_factor, _stress_factor,
            _section_factor**2, _section_factor**4,
        )


def units_dialog(parent, current):
    """Choose geometry length and force independently with derived-unit context."""
    from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel
    dialog = QDialog(parent)
    dialog.setWindowTitle("Units")
    form = QFormLayout(dialog)
    length, force = QComboBox(), QComboBox()
    length.setObjectName("unit_length")
    force.setObjectName("unit_force")
    length.addItems(list(LENGTH_UNITS))
    force.addItems(list(FORCE_UNITS))
    length.setCurrentText(current.length)
    force.setCurrentText(current.force)
    form.addRow("Length", length)
    form.addRow("Force", force)
    derived = QLabel()
    derived.setObjectName("unit_derived")

    def refresh():
        units = UNIT_SYSTEMS[unit_key(length.currentText(), force.currentText())]
        derived.setText(f"Moment: {units.moment}\nDistributed load: {units.intensity}\n"
                        f"Stress: {units.stress}\nSection area: {units.area}\n"
                        f"Section inertia: {units.inertia}\nWeight density: {units.density}")

    length.currentTextChanged.connect(refresh)
    force.currentTextChanged.connect(refresh)
    refresh()
    form.addRow("Derived units", derived)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    dialog.length, dialog.force = length, force
    return dialog
