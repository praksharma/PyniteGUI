"""Serializable unilateral elastic behaviour; no solver or Qt imports."""
from .model import finite_number

MEMBER_BEHAVIORS = {"bilateral": "Bilateral", "tension_only": "Tension only", "compression_only": "Compression only"}
SPRING_BEHAVIORS = {"bilateral": "Both directions", "positive": "Positive displacement only", "negative": "Negative displacement only"}
ITERATIVE_DEFAULTS = {"iteration_limit": 30, "load_steps": 1,
                      "member_tolerance": 1e-9, "translation_tolerance": 1e-10,
                      "rotation_tolerance": 1e-12}


def spring_mode_fields(node):
    axes = ("x", "y", "z", "rx", "ry", "rz") if hasattr(node, "z") else ("x", "y", "rz")
    return tuple("spring_"+axis+"_mode" for axis in axes)


def has_unilateral(project):
    return (any(member.behavior != "bilateral" for member in project.members.values()) or
            any(getattr(node, key) != "bilateral" for node in project.nodes.values() for key in spring_mode_fields(node)))


def validate_node(node):
    for key in spring_mode_fields(node):
        mode = getattr(node, key)
        if not isinstance(mode, str) or mode not in SPRING_BEHAVIORS:
            raise ValueError(f"Node {node.name}: {key} must be bilateral, positive or negative.")
        if mode != "bilateral" and (not finite_number(getattr(node,key.removesuffix('_mode'))) or getattr(node, key.removesuffix('_mode')) <= 0):
            raise ValueError(f"Node {node.name}: one-way behaviour requires a positive spring stiffness.")


def validate_member(member):
    if not isinstance(member.behavior, str) or member.behavior not in MEMBER_BEHAVIORS:
        raise ValueError(f"Member {member.name}: behaviour must be bilateral, tension_only or compression_only.")
    if member.behavior != "bilateral" and member.kind != "truss":
        raise ValueError(f"Member {member.name}: unilateral behaviour requires the axial-only truss type. Frame members remain bilateral.")


def validate_settings(project):
    for key in ("iteration_limit", "load_steps"):
        value = getattr(project, key)
        if type(value) is not int or not 1 <= value <= (500 if key == "iteration_limit" else 100):
            raise ValueError(f"{key} must be an integer from 1 to {500 if key == 'iteration_limit' else 100}.")
    for key in ("member_tolerance", "translation_tolerance", "rotation_tolerance"):
        value = getattr(project, key)
        if not finite_number(value) or not 0 <= value <= 1e3:
            raise ValueError(f"{key} must be finite, nonnegative and at most 1000 in its canonical units.")


def check_schema(values, version, required_version, defaults, label):
    if version >= required_version:
        if not defaults.keys() <= values.keys():
            raise ValueError(f"Missing unilateral {label} fields for version {required_version}.")
    elif any(values.get(key, default) != default for key, default in defaults.items()):
        raise ValueError(f"Unilateral {label} fields require version {required_version}.")


def spring_mode_text(node):
    return "; ".join(key.removeprefix("spring_").removesuffix("_mode").upper()+": "+SPRING_BEHAVIORS[getattr(node, key)]
                     for key in spring_mode_fields(node) if getattr(node, key) != "bilateral")


def enum_widget(options, value, name):
    from PySide6.QtWidgets import QComboBox
    box = QComboBox()
    box.setObjectName(name)
    box.setProperty('enum_data', True)
    for key, label in options.items():
        box.addItem(label, key)
    box.setCurrentIndex(box.findData(value))
    return box


def add_node_controls(form, fields, node):
    for key in spring_mode_fields(node):
        box = enum_widget(SPRING_BEHAVIORS, getattr(node,key), key)
        fields[key] = box
        stiffness = fields[key.removesuffix('_mode')]
        def update(value=None, box=box, stiffness=stiffness):
            enabled = stiffness.value() > 0
            if not enabled:
                box.setCurrentIndex(box.findData('bilateral'))
            box.setEnabled(enabled)
            form.setRowVisible(box, enabled)
        stiffness.valueChanged.connect(update)
        form.addRow(key.removeprefix('spring_').removesuffix('_mode').upper()+' spring action', box)
        box.setToolTip('Global direction of allowed displacement; reaction opposes it. One-way action requires Iterative elastic. Zero rest position.')
        update()


def add_member_control(form, fields, member):
    box = enum_widget(MEMBER_BEHAVIORS, member.behavior, 'member_behavior')
    fields['behavior'] = box
    form.addRow('Axial behaviour', box)
    box.setToolTip('Use the axial-only truss type for unilateral bars. Iterative elastic determines their active state separately for every combination.')
    def update():
        enabled = fields['kind'].currentText() == 'truss'
        box.setEnabled(enabled)
        if not enabled:
            box.setCurrentIndex(box.findData('bilateral'))
    fields['kind'].currentTextChanged.connect(update)
    update()


def active_state_table(project, result):
    data = getattr(result.solver, '_brecon_iterations', {}).get(result.combination)
    headers = ['Kind','ID','Direction','Behaviour','Active','Neutral','Trial value','Units']
    if data is None:
        return headers, []
    rows = []
    for item in data['contacts']:
        quantity = 'force' if item['kind'] == 'members' else 'rotation' if item['dof'].startswith('R') else 'length'
        unit = 'rad' if quantity == 'rotation' else getattr(project.units,quantity)
        rows.append(['Member' if item['kind'] == 'members' else 'Ground spring', item['name'],item['dof'] or 'Axial',
                     (MEMBER_BEHAVIORS if item['kind'] == 'members' else SPRING_BEHAVIORS)[item['behavior']],
                     'Yes' if item['active'] else 'No','Yes' if item['neutral'] else 'No',
                     project.units.to_display(item['trial'],quantity),unit])
    return headers, rows


def planar_bar_motion(result, name, distance):
    import numpy as np
    member = result.solver.members[name]
    a = np.r_[result.displacements[member.i_node.name][:2],0.]
    b = np.r_[result.displacements[member.j_node.name][:2],0.]
    return member.T()[:3,:3] @ (a+distance/member.L()*(b-a))


def iteration_table(result):
    data = getattr(result.solver,'_brecon_iterations',{}).get(result.combination)
    headers = ['Load step','Iteration','Active contacts','Total contacts','Activated','Deactivated']
    if data is None:
        return headers, []
    def labels(keys):
        return '; '.join(key.replace('members:','Bar ',1).replace('springs:','Spring ',1) for key in keys)
    return headers, [[row['step'],row['iteration'],row['active'],row['total'],labels(row['activated']),labels(row['deactivated'])] for row in data['history']]
