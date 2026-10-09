"""Explicit conversion of a planar definition, without changing the source."""
from copy import deepcopy
from dataclasses import asdict, fields
import math

from .model import Project, finite_number
from .spatial_model import SpatialProject, SpatialNode, SpatialMember, SpatialLoad


def to_spatial(project, support_mode="planar", offset=0.0):
    if getattr(project, "dimension", "2D") != "2D":
        raise ValueError("Only a 2D project can be converted to 3D.")
    if support_mode not in ("planar", "spatial"):
        raise ValueError("Choose planar constraints or spatial supports.")
    if not finite_number(offset):
        raise ValueError("The global Z offset must be finite.")
    project.validate()
    released = [member.name for member in project.members.values() if member.kind == "frame"
                and any(flag for end in member.end_releases for flag in end)]
    if released:
        raise ValueError("Cannot convert released frame members: " + ", ".join(released) +
                         ". General 3D frame releases are not supported yet; no releases were removed.")
    result = SpatialProject(**{field.name: deepcopy(getattr(project, field.name))
                              for field in fields(Project) if field.name not in ("nodes", "members", "loads")})
    for name, node in project.nodes.items():
        converted = SpatialNode(**asdict(node), z=offset)
        if support_mode == "planar":
            converted.support = "custom"
            converted.restraint_x, converted.restraint_y, converted.restraint_rz = node.restraints
            converted.restraint_z = converted.restraint_rx = converted.restraint_ry = True
        result.nodes[name] = converted
    for name, member in project.members.items():
        data = asdict(member)
        # Truss moment flags are redundant; the spatial type releases both planes.
        if member.kind == "truss":
            data["release_start"] = data["release_end"] = False
        result.members[name] = SpatialMember(**data)
    for name, load in project.loads.items():
        data = asdict(load)
        # Preserve the actual planar force direction, including reversed members.
        if load.direction == "Angle" or load.direction.startswith("Local"):
            angle = math.radians(load.resolved_angle(project))
            x, y = math.cos(angle), math.sin(angle)
            data.update(direction="Angle", angle=0.0 if x >= 0 else 180.0,
                        elevation=math.degrees(math.atan2(y, abs(x))))
        result.loads[name] = SpatialLoad(**data)
    result.validate()
    return result


def conversion_dialog(parent, project):
    from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout
    from .app import unit_number
    dialog = QDialog(parent)
    dialog.setWindowTitle("Create 3D Copy")
    form = QFormLayout(dialog)
    mode = QComboBox()
    mode.setObjectName("conversion_support_mode")
    mode.addItem("Preserve planar constraints", "planar")
    mode.addItem("Use spatial supports", "spatial")
    mode.setToolTip("Planar: fix DZ/RX/RY at every node and preserve DX/DY/RZ. "
                    "Spatial: retain support presets (pin fixes XYZ; fixed fixes all six), "
                    "custom in-plane restraints and springs; other directions are free. "
                    "A planar truss may then be unstable out of plane.")
    offset = unit_number(0, project.units, "length")
    offset.setObjectName("conversion_offset")
    form.addRow("Supports", mode)
    form.addRow(f"Global Z ({project.units.length})", offset)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create Copy")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    dialog.mode, dialog.offset = mode, offset
    return dialog
