"""Editing-only selection sets and global-Y elevations; no solver constraints."""
from copy import deepcopy

from .model import finite_number, identifier

FIELDS = ("groups", "levels", "snap_levels")


def validate_organization(project):
    if not isinstance(project.groups, dict) or not isinstance(project.levels, dict) or type(project.snap_levels) is not bool:
        raise ValueError("Groups/levels must be objects and snap_levels must be boolean.")
    for name, group in project.groups.items():
        if not identifier(name) or not isinstance(group, dict) or set(group) != {"nodes", "members"}:
            raise ValueError("Each named group needs nodes and members lists.")
        for kind, values in group.items():
            if (not isinstance(values, list) or any(not identifier(v) or v not in getattr(project, kind) for v in values)
                    or len(values) != len(set(values))):
                raise ValueError(f"Group {name}: {kind} must contain unique existing identifiers.")
    for name, elevation in project.levels.items():
        if not identifier(name) or not finite_number(elevation):
            raise ValueError("Each level needs a name and finite global Y elevation.")


def prune_groups(project):
    for group in project.groups.values():
        for kind in ("nodes", "members"):
            group[kind] = [name for name in group[kind] if name in getattr(project, kind)]


def set_group(project, name, selections):
    if not identifier(name):
        raise ValueError("Enter a group name without leading or trailing spaces.")
    group = {kind: list(dict.fromkeys(n for k, n in selections if k == kind)) for kind in ("nodes", "members")}
    if not any(group.values()):
        raise ValueError("Select at least one node or member first.")
    candidate = deepcopy(project.groups)
    candidate[name] = group
    previous, project.groups = project.groups, candidate
    try:
        validate_organization(project)
    except ValueError:
        project.groups = previous
        raise


def rename_entry(project, collection, old, new):
    entries = getattr(project, collection)
    if collection not in ("groups", "levels") or old not in entries or not identifier(new):
        raise ValueError("Choose an existing item and enter a valid name.")
    if new != old and new in entries:
        raise ValueError("That name already exists.")
    setattr(project, collection, {new if key == old else key: value for key, value in entries.items()})


def level_selections(project, elevation):
    nodes = {name for name, node in project.nodes.items() if abs(node.y-elevation) <= 1e-8}
    return [("nodes", name) for name in project.nodes if name in nodes] + [
        ("members", name) for name, m in project.members.items() if m.start in nodes and m.end in nodes]


def snap_elevation(project, value):
    if project.snap_levels and project.levels:
        nearest = min(project.levels.values(), key=lambda level: (abs(level-value), level))
        if abs(nearest-value) <= project.grid*.2:
            return nearest
    return round(value/project.grid)*project.grid


def visible_ids(window):
    """Member endpoints are visible context, without changing saved membership."""
    p = window.project
    name = getattr(window, "isolated_group", None)
    if name not in p.groups:
        return None
    group = p.groups[name]
    members, nodes = set(group["members"]), set(group["nodes"])
    for member in members:
        nodes.update((p.members[member].start, p.members[member].end))
    return {"nodes": nodes, "members": members, "surfaces": set(),
            "loads": {name for name, load in p.loads.items() if load.target in nodes | members}}


def entity_visible(window, kind, name):
    visible = getattr(window, "visible_ids", None)
    return visible is None or name in visible.get(kind, ())


def show_group(window, name, isolate=False):
    if window.mcp_mode or name not in window.project.groups:
        return
    window.isolated_group = name if isolate else None
    window.refresh()
    group = window.project.groups[name]
    window.select_many([(kind, key) for kind in ("nodes", "members") for key in group[kind]])
    if window.selections:
        window.fit_selection()


def show_all(window):
    if window.mcp_mode:
        return
    window.isolated_group = None
    window.refresh()
