"""Persisted frame analysis choices and their supported modelling boundary."""

METHODS = {"linear": "Linear elastic", "p_delta": "P-Delta elastic"}


def analysis_method_issue(project):
    if project.analysis_method != "p_delta":
        return None
    if getattr(project, "dimension", "2D") == "3D":
        from .spatial_releases import has_rotational_releases
        if has_rotational_releases(project):
            return "Spatial rotational end releases currently require Linear elastic analysis; P-Delta release recovery is not validated."
    if getattr(project, "surfaces", {}):
        return "P-Delta is available for frame-only models. PyNite does not include second-order shell effects; use Linear elastic for coupled slabs."
    if any(member.kind != "frame" for member in project.members.values()):
        return "P-Delta currently requires frame members only. Bilateral truss second-order behaviour has not been validated in this adapter."
    if any(any(getattr(member, key, False) for key in
               ("release_start_x", "release_end_x", "release_start_y", "release_end_y"))
           for member in project.members.values()):
        return "P-Delta does not support released member translations. Their displacement recovery is linear-only; use Linear elastic or revise the connection."
    return None


def settings_dialog(parent, project):
    from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel
    dialog = QDialog(parent)
    dialog.setWindowTitle("Analysis Method")
    form = QFormLayout(dialog)
    method = QComboBox()
    method.setObjectName("analysis_method")
    for key, label in METHODS.items():
        method.addItem(label, key)
    method.setCurrentIndex(method.findData(project.analysis_method))
    form.addRow("Method", method)
    help_text = QLabel("P-Delta includes geometric stiffness from axial loads and solves each combination separately. "
                       "Materials remain elastic. Frame-only models; no coupled slabs, trusses, released translations or spatial rotational releases. "
                       "Add intermediate joints to resolve member curvature and compare mesh refinement. "
                       "Steel plastic pushover and reinforced-concrete plasticity are separate capabilities and are not enabled here.")
    help_text.setWordWrap(True)
    help_text.setMinimumWidth(420)
    form.addRow(help_text)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    dialog.method = method
    return dialog
