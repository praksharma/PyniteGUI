"""Small, offline AISC v16.0 subset; canonical area/inertias are in2/in4.

Source columns: C (designation), F (A), AQ (Iy), AM (Ix), AX (J).
Catalog Ix maps to PyNite Iz for the XY frame, not the database's AU column.
See GUIDE.md for provenance and scope. Material is deliberately independent.
"""
from dataclasses import dataclass


SOURCE = "AISC v16.0"
SOURCE_URL = "https://www.aisc.org/aisc/publications/steel-construction-manual/aisc-shapes-database-v160/"


@dataclass(frozen=True)
class CatalogSection:
    designation: str
    family: str
    A: float
    Iy: float
    Ix: float
    J: float

    def properties(self, weak_axis=False):
        return {"A": self.A, "Iy": self.Ix if weak_axis else self.Iy,
                "Iz": self.Iy if weak_axis else self.Ix, "J": self.J}


CATALOG = tuple(CatalogSection(*row) for row in (
    ("W8X10", "Wide flange", 2.96, 2.09, 30.8, 0.0426),
    ("W10X12", "Wide flange", 3.54, 2.18, 53.8, 0.0547),
    ("W12X26", "Wide flange", 7.65, 17.3, 204, 0.3),
    ("W14X30", "Wide flange", 8.85, 19.6, 291, 0.38),
    ("W16X26", "Wide flange", 7.68, 9.59, 301, 0.262),
    ("W18X35", "Wide flange", 10.3, 15.3, 510, 0.506),
    ("W21X44", "Wide flange", 13, 20.7, 843, 0.77),
    ("W24X55", "Wide flange", 16.2, 29.1, 1350, 1.18),
    ("HSS4X4X1/4", "Square HSS", 3.37, 7.8, 7.8, 12.8),
    ("HSS6X6X3/8", "Square HSS", 7.58, 39.5, 39.5, 64.6),
    ("HSS8X8X1/2", "Square HSS", 13.5, 125, 125, 204),
    ("HSS8X4X1/4", "Rectangular HSS", 5.24, 14.4, 42.5, 35.3),
    ("HSS10X6X3/8", "Rectangular HSS", 10.4, 61.8, 137, 139),
    ("HSS6.625X0.280", "Round HSS", 5.2, 26.4, 26.4, 52.7),
    ("HSS8.625X0.322", "Round HSS", 7.85, 68.1, 68.1, 136),
))
BY_DESIGNATION = {section.designation: section for section in CATALOG}
