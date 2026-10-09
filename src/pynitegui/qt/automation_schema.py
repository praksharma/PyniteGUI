"""Discoverable model reference derived from the actual desktop dataclasses."""
from dataclasses import MISSING, fields
from .model import Node, Member, Load, Material, Section
from .spatial_model import SpatialNode, SpatialMember, SpatialLoad
from .units import UNIT_SYSTEMS


def model_reference(dimension="2D"):
    spatial = dimension == "3D"
    constructors = {"nodes": SpatialNode if spatial else Node,
                    "members": SpatialMember if spatial else Member,
                    "loads": SpatialLoad if spatial else Load,
                    "materials": Material, "sections": Section}
    entities = {}
    for collection, constructor in constructors.items():
        properties, required = {}, []
        for field in fields(constructor):
            schema = ({"type": "number"} if field.type is float else
                      {"type": "boolean"} if field.type is bool else
                      {"type": "string"} if field.type is str else {"type": ["string", "null"]})
            if field.default is not MISSING:
                schema["default"] = field.default
            elif field.name != "name":
                required.append(field.name)
            if field.name == "name":
                schema["description"] = "Normally omit: the operation key supplies name; if supplied it must equal key."
            if field.name.startswith("spring_"):
                schema.update(minimum=0, description="Bilateral stiffness: kip/in for translations, kip-in/rad for rotations; cannot coexist with a rigid restraint on that DOF.")
            if field.name in ("position", "end_position"):
                schema.update(minimum=0, maximum=1, description="Fraction of member length, not a coordinate or percentage.")
            properties[field.name] = schema
        entities[collection] = {"type": "object", "additionalProperties": False,
                                "properties": properties, "required_on_create": required,
                                "update": "Existing put merges fields; omit unchanged fields. Required-on-create fields need not be repeated for updates."}
    nodes = entities["nodes"]["properties"]
    nodes["support"]["enum"] = ["free", "pin", "roller", "fixed", "custom"]
    nodes["support"]["description"] = "Supports are node fields, not a supports collection/object. restraint_* flags are used only when support='custom'."
    members = entities["members"]["properties"]
    members["kind"]["enum"] = ["frame", "truss"]
    members["start"]["description"] = members["end"]["description"] = "Existing node identifier; start/end, not i_node/j_node."
    for field in ("material", "section"):
        members[field]["description"] = "Existing identifier in the corresponding model collection; specify explicitly using read_model's defaults."
    if spatial:
        for field in members:
            if field.startswith("release_"):
                members[field]["const"] = False
    loads = entities["loads"]["properties"]
    loads["kind"]["enum"] = ["point", "distributed"]
    loads["target"]["description"] = "Existing node or member identifier. Node loads must be point loads; truss members accept joint loads only."
    loads["direction"]["enum"] = (["FX", "FY", "FZ", "MX", "MY", "MZ", "Fx", "Fy", "Fz", "Mx", "My", "Mz", "Angle"] if spatial else
                                      ["FX", "FY", "MZ", "Angle", "Local x", "Local y", "Local angle"])
    loads["direction"]["description"] = ("Uppercase=global, mixed case=member-local (member targets only). Angle uses azimuth angle and elevation." if spatial else
                                               "FX/FY/MZ are global; Local x/y/angle require a member. Angle is a global force angle measured from +X.")
    loads["magnitude"]["description"] = "Signed kip for point forces, kip-in for point moments, kip/in for distributed forces."
    loads["case"]["description"] = "Existing load_cases identifier; specify read_model's default_load_case explicitly."
    return {
        "dimension": dimension, "input_units": "Canonical inch-kip regardless of display units; angles in degrees, rotations in radians.",
        "entities": entities,
        "supports": {
            "dof_order": ["DX", "DY", "DZ", "RX", "RY", "RZ"] if spatial else ["DX", "DY", "RZ"],
            "presets": {"free": [False]*(6 if spatial else 3), "pin": [True, True, True, False, False, False] if spatial else [True, True, False],
                        "roller": [False, True, False, False, False, False] if spatial else [False, True, False], "fixed": [True]*(6 if spatial else 3)},
            "custom": "Set support='custom' and the corresponding restraint_x/y/rz (2D) or restraint_x/y/z/rx/ry/rz (3D) booleans. True fixes that global DOF. Presets ignore these booleans.",
        },
        "operations": {"put": "op,collection,key,value; merge/create entity or replace combination case-factor map.",
                       "delete": "op,collection,key; no value. Fix all dependent references explicitly in the same batch.",
                       "load_cases": "put/delete with key and no value.",
                       "settings": "op='set',collection='settings',value=partial settings; no key."},
        "settings": {"unit_system": {"enum": list(UNIT_SYSTEMS)}, "grid": "positive inches",
                     "default_material": "existing material ID", "default_section": "existing section ID",
                     "default_load_case": "existing case ID", "self_weight_case": "existing case ID or null",
                     "self_weight_factor": "finite signed multiplier"},
        "validation": ["All operations validate together and create one undo step; errors make no changes.",
                       "Material E and section A/Iy/Iz/J must be positive; rho nonnegative; nu between -1 and 0.5 (exclusive).",
                       "Distributed loads require a frame member, force direction and 0 <= position < end_position <= 1; end_magnitude is the intensity at the end, so set both magnitudes equal for a uniform load.",
                       "Names must be nonempty identifiers; node/member names must be distinct; no zero-length or duplicate members.",
                       "Use read_model for the current session/revision and existing material, section and case identifiers. Do not guess fields from another PyNite API."]}


def batch_examples(project):
    # Separate examples avoid suggesting that a custom support is needed for a preset.
    return {"note": "Example identifiers must be changed if they already exist. Use the current session/revision from read_model.",
            "create_cantilever": [
                {"op": "put", "collection": "nodes", "key": "ExampleA", "value": {"x": 0, "y": 0, "support": "fixed"}},
                {"op": "put", "collection": "nodes", "key": "ExampleB", "value": {"x": 120, "y": 0}},
                {"op": "put", "collection": "members", "key": "ExampleBeam", "value": {"start": "ExampleA", "end": "ExampleB", "material": project.default_material, "section": project.default_section}},
                {"op": "put", "collection": "loads", "key": "ExampleForce", "value": {"target": "ExampleB", "kind": "point", "direction": "FY", "magnitude": -1, "case": project.default_load_case}}],
            "update_custom_support": {"op": "put", "collection": "nodes", "key": "ExampleA", "value": {"support": "custom", "restraint_x": True, "restraint_y": True, "restraint_rz": False}}}
