"""Persisted frame analysis choices and their supported modelling boundary."""

METHODS = {"linear": "Linear elastic", "p_delta": "P-Delta elastic", "iterative": "Iterative elastic (unilateral)"}


def analysis_method_issue(project):
    from .unilateral import has_unilateral
    if has_unilateral(project) and project.analysis_method != "iterative":
        return "Unilateral members/support springs require Iterative elastic analysis. Linear and P-Delta do not silently treat them as bilateral."
    if project.analysis_method == "iterative":
        if getattr(project, "surfaces", {}):
            return "Iterative elastic is available for frame/truss models only; coupled surfaces are not validated for unilateral activation."
        if getattr(project, "dimension", "2D") == "3D":
            from .spatial_releases import has_releases
            if has_releases(project):
                return "Spatial frame end releases require Linear elastic analysis; iterative release recovery is not validated."
        return None
    if project.analysis_method != "p_delta":
        return None
    if getattr(project, "dimension", "2D") == "3D":
        from .spatial_releases import has_releases
        if has_releases(project):
            return "Spatial end releases currently require Linear elastic analysis; P-Delta release recovery is not validated."
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
    from PySide6.QtWidgets import QSpinBox
    from .app import unit_number, unit_value
    from .unilateral import ITERATIVE_DEFAULTS
    iterative_fields = {}
    for key, label, limit in (('iteration_limit', 'Maximum active-set iterations', 500), ('load_steps', 'Load steps', 100)):
        field = QSpinBox()
        field.setObjectName('analysis_'+key)
        field.setRange(1, limit)
        field.setValue(getattr(project,key))
        form.addRow(label, field)
        iterative_fields[key] = field
    quantities = {'member_tolerance':'force', 'translation_tolerance':'length', 'rotation_tolerance':'rotation'}
    for key, label in (('member_tolerance','Axial force switch tolerance'), ('translation_tolerance','Spring translation switch tolerance'), ('rotation_tolerance','Spring rotation switch tolerance')):
        quantity = quantities[key]
        unit = 'rad' if quantity == 'rotation' else getattr(project.units,quantity)
        field = unit_number(getattr(project,key), project.units, quantity, 0., decimals=12)
        field.setObjectName('analysis_'+key)
        form.addRow(label+f' ({unit})',field)
        iterative_fields[key] = field
    def update():
        for field in iterative_fields.values():
            form.setRowVisible(field, method.currentData() == 'iterative')
    method.currentIndexChanged.connect(update)
    update()
    help_text = QLabel("P-Delta includes geometric stiffness from axial loads and solves each combination separately. "
                       "Materials remain elastic. Frame-only models; no coupled slabs, trusses, released translations or spatial rotational releases. "
                       "Imposed rigid-support movements stay unchanged in every combination; each combination is solved independently. "
                       "Add intermediate joints to resolve member curvature and compare mesh refinement. "
                       "Iterative elastic adds tension/compression-only axial bars and one-way global support springs, with activation and reactivation. "
                       "Each full combination starts independently; support motions remain unchanged during load steps. "
                       "Switch tolerances define neutral contact, not artificial residual stiffness. Cycles, mechanisms and failed convergence reject results. "
                       "Steel plastic pushover and reinforced-concrete plasticity are separate capabilities and are not enabled here.")
    help_text.setWordWrap(True)
    help_text.setMinimumWidth(420)
    form.addRow(help_text)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    dialog.method = method
    dialog.iterative_fields = iterative_fields
    def settings_values():
        result = {'analysis_method': method.currentData()}
        for key, field in iterative_fields.items():
            field.interpretText()
            result[key] = unit_value(field, project.units, quantities[key]) if key in quantities else field.value()
        return result
    dialog.settings_values = settings_values
    return dialog
