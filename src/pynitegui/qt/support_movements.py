"""Model-level prescribed support motion, independent of load combinations."""
import numpy as np

from .model import finite_number
from .support_axes import support_normal, translation_spaces


def movement_fields(node):
    axes = ("x", "y", "z", "rx", "ry", "rz") if hasattr(node, "z") else ("x", "y", "rz")
    return tuple("settlement_"+axis for axis in axes)+("settlement_normal",)


def movement_label(key):
    axis = key.removeprefix("settlement_")
    return "normal" if axis == "normal" else ("D"+axis.upper() if len(axis) == 1 else axis.upper())


def has_movements(project):
    return any(any(getattr(node, key) != 0. for key in movement_fields(node)) for node in project.nodes.values())


def validate_movements(node):
    keys = movement_fields(node)
    for key in keys:
        value = getattr(node, key)
        if not finite_number(value):
            raise ValueError(f"Node {node.name}: {key} must be a finite number.")
    for key, fixed in zip(keys[:-1], node.restraints):
        if getattr(node, key) and not fixed:
            raise ValueError(f"Node {node.name}: {key} requires an explicit rigid global restraint. Use normal movement for an inclined roller.")
    if node.settlement_normal and node.support != "inclined":
        raise ValueError(f"Node {node.name}: normal settlement requires an inclined support.")
    movement_lift(node)


def movement_lift(node, fixed=None):
    """A particular physical motion satisfying all rigid constraints.

    Extra fixed flags may come from shared shell edges or inactive-coordinate
    gauges. Their prescribed motion is zero unless explicitly defined here.
    Exact redundant constraints must prescribe the same motion.
    """
    fixed = node.restraints if fixed is None else fixed
    count = 3 if hasattr(node, "z") else 2
    values = np.array([getattr(node, key) for key in movement_fields(node)[:-1]])
    rows = [axis for axis, restrained in zip(np.eye(count), fixed[:count]) if restrained]
    targets = [value for value, restrained in zip(values[:count], fixed[:count]) if restrained]
    if node.support == "inclined":
        normal = support_normal(node)
        translation_spaces(fixed[:count], normal)  # Reject nearly dependent axes.
        rows.append(normal)
        targets.append(node.settlement_normal)
    displacement = np.zeros(len(fixed))
    if rows:
        matrix = np.array(rows)
        targets = np.array(targets)
        translation = np.linalg.lstsq(matrix, targets, rcond=1e-13)[0]
        if np.any(abs(matrix @ translation-targets) > 1e-11*max(1., float(np.max(abs(targets))))):
            raise ValueError(f"Node {node.name}: incompatible prescribed global/normal support movements.")
        displacement[:count] = translation
    displacement[count:] = values[count:]
    return displacement


def movement_summary(node, units):
    entries = []
    for key in movement_fields(node):
        value = getattr(node, key)
        if value:
            quantity = "rotation" if key.startswith("settlement_r") else "length"
            unit = "rad" if quantity == "rotation" else units.length
            label = movement_label(key)
            entries.append(f"{label} {units.to_display(value, quantity):.8g} {unit}")
    return "; ".join(entries) or "None"


def clear_inapplicable_movements(node):
    for key, fixed in zip(movement_fields(node)[:-1], node.restraints):
        if not fixed:
            setattr(node, key, 0.)
    if node.support != "inclined":
        node.settlement_normal = 0.


def add_movement_controls(form, fields, node, units):
    """Staged native controls; callers clear values whose restraints are removed."""
    from PySide6.QtWidgets import QLabel
    from .app import unit_number
    note = QLabel("Imposed support movements apply unchanged to every combination. Rotations use the right-hand rule, in radians.")
    note.setWordWrap(True)
    form.addRow(note)
    keys = movement_fields(node)
    for key in keys:
        rotation = key.startswith("settlement_r")
        label = movement_label(key)
        widget = unit_number(getattr(node, key), units, "rotation" if rotation else "length", decimals=9)
        widget.setObjectName(key)
        widget.setToolTip(note.text()+" Signed global direction, or the listed inclined normal. Requires a rigid support; spring rest positions remain zero.")
        fields[key] = widget
        form.addRow(f"Imposed {label} ({'rad' if rotation else units.length})", widget)

    def refresh():
        enabled = False
        for key in keys:
            applicable = (fields["support"].currentText() == "inclined" if key == "settlement_normal" else
                          fields["restraint_"+key.removeprefix("settlement_")].isChecked())
            fields[key].setEnabled(applicable)
            form.setRowVisible(fields[key], applicable)
            enabled = enabled or applicable
        form.setRowVisible(note, enabled)
    for key in keys[:-1]:
        fields["restraint_"+key.removeprefix("settlement_")].toggled.connect(refresh)
    return refresh
