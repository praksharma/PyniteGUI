"""First-order unilateral axial bars/global ground springs with exact supports.

Use PyNite's physical elastic matrices, not its deactivate-only member loop.
Reconsider both activation directions after every solve. Refuse cycles, missing
stiffness, unresolved neutral-contact mechanisms and unbalanced accepted states.
"""
import numpy as np
from Pynite import Analysis
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, diags

from .inclined_supports import free_basis, factor_stiffness, store_displacements, recover_reactions
from .support_movements import movement_lift, movement_fields
from .unilateral import spring_mode_fields


def contacts(model, project):
    result = []
    size = 6*len(model.nodes)
    for name, member in project.members.items():
        if member.behavior == 'bilateral':
            continue
        start, end = model.nodes[member.start], model.nodes[member.end]
        axis = np.array((end.X-start.X, end.Y-start.Y, end.Z-start.Z))
        length = np.linalg.norm(axis)
        axis /= length
        indices = np.r_[6*start.ID+np.arange(3), 6*end.ID+np.arange(3)]
        row = csr_matrix((np.r_[-axis, axis], (np.zeros(6, dtype=int), indices)), shape=(1, size))
        stiffness = project.materials[member.material].E*project.sections[member.section].A/length
        result.append(dict(key=('members', name), row=row, stiffness=stiffness,
                           sign=1 if member.behavior == 'tension_only' else -1,
                           tolerance=project.member_tolerance, behavior=member.behavior))
    dofs = ('DX', 'DY', 'DZ', 'RX', 'RY', 'RZ') if getattr(project, 'dimension', '2D') == '3D' else ('DX', 'DY', 'RZ')
    for name, node in project.nodes.items():
        for index, (field, dof, stiffness) in enumerate(zip(spring_mode_fields(node), dofs, node.springs)):
            mode = getattr(node, field)
            if mode == 'bilateral':
                continue
            index = model.nodes[name].ID*6+('DX','DY','DZ','RX','RY','RZ').index(dof)
            row = csr_matrix(([1.], ([0], [index])), shape=(1, size))
            result.append(dict(key=('springs', name, dof), row=row, stiffness=stiffness,
                sign=1 if mode == 'positive' else -1, behavior=mode,
                tolerance=project.translation_tolerance if dof.startswith('D') else project.rotation_tolerance))
    return result


def apply_states(model, combination, items, states):
    for item, active in zip(items, states):
        key = item['key']
        if key[0] == 'members':
            member = model.members[key[1]]
            member.active[combination] = bool(active)
            for sub in member.sub_members.values():
                sub.active[combination] = bool(active)
        else:
            getattr(model.nodes[key[1]], 'spring_'+key[2])[2] = bool(active)


def neutral_stability(model, combination, items, states, neutral, transform, matrix):
    """No zero-energy direction may leave every neutral contact open.

    Removing all neutral contacts is too strict for opposing tension braces;
    keeping them all is unsafe for a single unloaded one-way support. On the
    bilateral nullspace, test the actual slack half-spaces by bounded LPs.
    """
    if not any(neutral) or transform.shape[1] == 0:
        return
    try:
        apply_states(model, combination, items, [active and not off for active, off in zip(states, neutral)])
        without = model.Ke(combination, check_stability=False, sparse=True).tocsr()
    finally:
        apply_states(model, combination, items, states)
    full = (transform.T @ matrix @ transform).tocsr()
    scale = 1/np.sqrt(full.diagonal())
    normalized_basis = transform @ diags(scale)
    bilateral = (normalized_basis.T @ without @ normalized_basis).tocsr()
    # Do not silently assume zero-load stability on a large unresolved cone.
    if bilateral.shape[0] > 600:
        # The production factorization can still certify an independently
        # stable bilateral structure without any contact-cone calculation.
        try:
            factor_stiffness(without, transform, ['neutral check']*transform.shape[1], [False]*transform.shape[1], 1.)
            return
        except ValueError as error:
            raise ValueError('Neutral-contact stability with mechanisms is limited to 600 free coordinates; reduce the model before accepting this zero-contact state.') from error
    values, vectors = np.linalg.eigh(((bilateral+bilateral.T)*.5).toarray())
    cancellation = abs(normalized_basis).T @ abs(without) @ abs(normalized_basis)
    limit = 10*np.finfo(float).eps*max(
        len(values)*max(1., float(abs(values).max())),
        without.shape[0]*float(np.asarray(cancellation.sum(axis=1)).max()))
    null = vectors[:, values <= limit]
    if null.shape[1] == 0:
        return
    rows = np.array([item['sign']*np.asarray(item['row'] @ normalized_basis @ null).ravel()
                     for item, off in zip(items, neutral) if off])
    norms = np.linalg.norm(rows, axis=1)
    rows = rows[norms > 1e-12]/norms[norms > 1e-12, None]
    if not len(rows):
        raise ValueError('Unilateral mechanism: unloaded contacts do not restrain a free motion.')
    for index in range(null.shape[1]):
        for sign in (-1., 1.):
            bounds = [(-1., 1.)]*null.shape[1]
            bounds[index] = (sign, sign)
            result = linprog(np.zeros(null.shape[1]), A_ub=rows, b_ub=np.zeros(len(rows)), bounds=bounds, method='highs')
            if result.status == 0:
                raise ValueError('Unilateral mechanism: a free zero-energy motion can open all unloaded contacts; no results were accepted.')
            if result.status != 2:
                raise ValueError('Neutral-contact stability could not be certified; no results were accepted.')


def solve_iterative(model, project, phase):
    from .analysis import AnalysisResult, model_signature
    from .equilibrium import check_equilibrium
    spatial = getattr(project, 'dimension', '2D') == '3D'
    Analysis._prepare_model(model)
    model._brecon_iterating = True
    basis, labels, translations = free_basis(model, project)
    lift = np.zeros((6*len(model.nodes), 1))
    offsets, dofs = (np.arange(6), ('DX','DY','DZ','RX','RY','RZ')) if spatial else (np.array((0,1,5)), ('DX','DY','RZ'))
    for name, definition in project.nodes.items():
        node = model.nodes[name]
        lift[6*node.ID+offsets, 0] = movement_lift(definition, [getattr(node, 'support_'+dof) for dof in dofs])
    model._pynitegui_support_movements = {name: {key: getattr(node, key) for key in movement_fields(node) if getattr(node, key)}
        for name, node in project.nodes.items() if any(getattr(node, key) for key in movement_fields(node))}
    model._pynitegui_support_reactions, model._brecon_iterations, model._brecon_spring_states = {}, {}, {}
    coordinates = np.array([(node.X,node.Y,node.Z) for node in model.nodes.values()])
    length = max(1., float(np.linalg.norm(np.ptp(coordinates, axis=0))))
    items = contacts(model, project)
    try:
        for combination in model.load_combos:
            states = [True]*len(items)  # Every complete combination starts afresh.
            history = []
            full_force, full_fixed = model.P(combination), model.FER(combination)
            for step in range(1, project.load_steps+1):
                seen = set()
                fraction = step/project.load_steps
                force, fixed = fraction*full_force, fraction*full_fixed
                for iteration in range(1, project.iteration_limit+1):
                    phase(f'Iterative elastic | {combination}: load step {step}/{project.load_steps}, active-set iteration {iteration}/{project.iteration_limit}')
                    key = tuple(states)
                    if key in seen:
                        raise ValueError(f'Active-set cycle in {combination}, step {step}; no results were accepted.')
                    seen.add(key)
                    apply_states(model, combination, items, states)
                    matrix = model.Ke(combination, check_stability=False, sparse=True).tocsr()
                    transform, factor, scale = factor_stiffness(matrix, basis, labels, translations, length)
                    rhs = np.asarray(transform.T @ (force-fixed-matrix @ lift)).ravel()
                    free = scale*factor.solve(scale*rhs) if factor is not None else np.empty(0)
                    displacement = lift+np.asarray(transform @ free).reshape(-1,1)
                    if not np.isfinite(displacement).all():
                        raise ValueError(f'Nonfinite iterative displacement in {combination}.')
                    store_displacements(model, combination, displacement)
                    next_states, neutral, trial = [], [], []
                    for item, active in zip(items, states):
                        value = float((item['row'] @ displacement[:,0])[0])
                        if item['key'][0] == 'members':
                            value *= item['stiffness']
                        signed = item['sign']*value
                        next_states.append(True if signed > item['tolerance'] else False if signed < -item['tolerance'] else active)
                        neutral.append(abs(value) <= item['tolerance'])
                        trial.append(float(value))
                    changes = [':'.join(item['key']) for item, a, b in zip(items,states,next_states) if a != b]
                    history.append(dict(step=step, iteration=iteration, active=sum(states), total=len(states), changed=changes,
                        activated=[':'.join(item['key']) for item,a,b in zip(items,states,next_states) if not a and b],
                        deactivated=[':'.join(item['key']) for item,a,b in zip(items,states,next_states) if a and not b]))
                    if next_states != states:
                        states = next_states
                        continue
                    # Certification is needed only for the final complete state;
                    # intermediate load steps are not published as results.
                    if step == project.load_steps:
                        neutral_stability(model, combination, items, states, neutral, transform, matrix)
                    records = recover_reactions(model, project, combination, matrix, force, fixed, displacement)
                    break
                else:
                    raise ValueError(f'Iterative elastic did not converge in {combination}, step {step}, after {project.iteration_limit} iterations; no results were accepted.')
            model._pynitegui_support_reactions[combination] = records
            model._brecon_spring_states[combination] = {(item['key'][1],item['key'][2]):bool(active)
                for item, active in zip(items,states) if item['key'][0] == 'springs'}
            model._brecon_iterations[combination] = dict(converged=True, load_steps=project.load_steps,
                iterations=len(history), history=history,
                contacts=[dict(kind=item['key'][0], name=item['key'][1],
                    dof=item['key'][2] if len(item['key']) == 3 else None,
                    behavior=item['behavior'], active=bool(active), neutral=bool(zero), trial=value)
                    for item, active, zero, value in zip(items,states,neutral,trial)])
            model.solution = 'Nonlinear TC'
            result = AnalysisResult.from_solver(model, combination, spatial=spatial)
            result.analysis_method, result.model_signature = 'iterative', model_signature(project)
            if not check_equilibrium(project, result).passed:
                raise ValueError(f'Iterative elastic global force/moment equilibrium failed in {combination}; no results were accepted.')
    finally:
        model._brecon_iterating = False
    model.solution = 'Nonlinear TC'
