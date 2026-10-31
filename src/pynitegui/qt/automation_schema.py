"""Discoverable model reference derived from the actual desktop dataclasses."""
from dataclasses import MISSING, asdict, fields
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
            if field.name.startswith("spring_") and not field.name.endswith('_mode'):
                schema.update(minimum=0, description="Bilateral stiffness: kip/in for translations, kip-in/rad for rotations; cannot coexist with a rigid restraint on that DOF.")
            if field.name.startswith("settlement_"):
                schema["description"] = ("Signed model-level prescribed support motion: canonical inches for translations/normal, radians for rotations. Same value in every combination, including zero-factor combinations; do not scale with loads. Nonzero global fields require explicit rigid global restraints; settlement_normal requires inclined. Duplicate global/normal prescriptions must agree. Linear, iterative elastic and supported frame-only P-Delta; solve P-Delta combinations independently, never superpose. Springs keep zero rest positions.")
            if field.name in ("position", "end_position"):
                schema.update(minimum=0, maximum=1, description="Fraction of member length, not a coordinate or percentage.")
            properties[field.name] = schema
        entities[collection] = {"type": "object", "additionalProperties": False,
                                "properties": properties, "required_on_create": required,
                                "update": "Existing put merges fields; omit unchanged fields. Required-on-create fields need not be repeated for updates."}
    entities["materials"]["properties"]["shear_modulus"].update(type=["number", "null"], exclusiveMinimum=0,
        description="Optional independent frame/truss G in ksi. null (default) derives E/[2(1+nu)]. Positive finite numbers only; independent G requires custom provenance.")
    nodes = entities["nodes"]["properties"]
    from .unilateral import MEMBER_BEHAVIORS, SPRING_BEHAVIORS, ITERATIVE_DEFAULTS
    for name, schema in nodes.items():
        if name.startswith('spring_') and name.endswith('_mode'):
            schema.update(enum=list(SPRING_BEHAVIORS), description='Global spring action: bilateral, positive displacement only, or negative displacement only. One-way action requires positive stiffness and Iterative elastic. Reaction opposes displacement; zero rest position.')
    entities['members']['properties']['behavior'].update(enum=list(MEMBER_BEHAVIORS),
        description='Bilateral or tension_only/compression_only axial bar. Unilateral requires kind=truss and Iterative elastic; states are solved independently for every complete combination, with reactivation. No material yielding.')
    nodes["support"]["enum"] = ["free", "pin", "roller", "fixed", "custom", "inclined"]
    nodes["support"]["description"] = ("Supports are node fields, not a supports collection/object. restraint_* flags apply to custom and, in 3D, as additional global restraints for inclined. An inclined support fixes translation along its normal; other translations/rotations remain free unless separately restrained. Springs retain global axes.")
    if spatial:
        nodes["support_angle"].update(minimum=-180, maximum=180,
            description="Inclined support NORMAL azimuth, degrees from global +X toward +Z. Use with support_elevation; normal=(cos(el)cos(az),sin(el),cos(el)sin(az)). Other presets require both angles 0. Additional restraint_* flags constrain global DOFs; exact redundant normal is assigned zero separate normal force.")
        nodes["support_elevation"].update(minimum=-90, maximum=90,
            description="Inclined support NORMAL elevation toward global +Y, degrees. Azimuth 0/elevation 90 equals the global-Y roller. Linear frames/trusses, released frames and existing frame P-Delta restrictions apply. Imposed rigid-support movements stay unchanged in every combination.")
    else:
        nodes["support_angle"].update(minimum=-180, maximum=180,
            description="For support='inclined': roller TANGENT angle in degrees CCW from global +X. Normal (-sin a, cos a) translation fixed; tangent and RZ free. Other support presets require 0. Linear frames/trusses/releases and existing frame P-Delta restrictions apply. Springs retain global axes. Reactions are global total rigid+spring forces. Imposed rigid-support movements stay unchanged in every combination.")
    members = entities["members"]["properties"]
    members["kind"]["enum"] = ["frame", "truss"]
    members["start"]["description"] = members["end"]["description"] = "Existing node identifier; start/end, not i_node/j_node."
    for field in ("material", "section"):
        members[field]["description"] = "Existing identifier in the corresponding model collection; specify explicitly using read_model's defaults."
    if spatial:
        from .spatial_releases import RELEASE_FIELDS
        for field in members:
            if field.startswith("release_"):
                if field in RELEASE_FIELDS:
                    members[field]["description"] = "Member-local end release, including roll; *_x/y/z mean DX/DY/DZ, *_rx/ry mean RX/RY, release_start/end mean RZ. Linear frame-only; no surfaces or P-Delta. Manual flags must be false for trusses. DX/RX cannot be released at both ends. Each DY/RZ or DZ/RY plane accepts at most two releases and not both translations. Joint translations must remain restrained or connected; no translation gauges are added. Member-side motion can differ from joint motion."
    loads = entities["loads"]["properties"]
    loads["kind"]["enum"] = ["point", "distributed"]
    loads["target"]["description"] = "Existing node or member identifier. Node loads must be point loads; truss members accept joint loads only."
    loads["direction"]["enum"] = (["FX", "FY", "FZ", "MX", "MY", "MZ", "Fx", "Fy", "Fz", "Mx", "My", "Mz", "Angle"] if spatial else
                                      ["FX", "FY", "MZ", "Angle", "Local x", "Local y", "Local angle"])
    loads["direction"]["description"] = ("Uppercase=global, mixed case=member-local (member targets only). Angle uses azimuth angle and elevation." if spatial else
                                               "FX/FY/MZ are global; Local x/y/angle require a member. Angle is a global force angle measured from +X.")
    loads["magnitude"]["description"] = "Signed kip for point forces, kip-in for point moments, kip/in for distributed forces."
    loads["case"]["description"] = "Existing load_cases identifier; specify read_model's default_load_case explicitly."
    surface_info = None
    settings = {"unit_system": {"enum": list(UNIT_SYSTEMS)}, "grid": "positive inches",
                "default_material": "existing material ID", "default_section": "existing section ID",
                "default_load_case": "existing case ID", "self_weight_case": "existing case ID or null",
                "self_weight_factor": "positive finite multiplier",
                "analysis_method": {"enum": ["linear", "p_delta", "iterative"], "default": "linear",
                    "description": "Elastic analysis. p_delta: geometric stiffness, frame-only restrictions. iterative: first-order unilateral axial bars/global support springs with activation and reactivation; no surfaces or spatial frame releases. Solve every combination independently. Not plastic yielding."}}
    for key, default in ITERATIVE_DEFAULTS.items():
        settings[key] = {'type':'integer' if type(default) is int else 'number', 'default':default,
                         'minimum':1 if type(default) is int else 0,
                         'maximum':500 if key == 'iteration_limit' else 100 if key == 'load_steps' else 1000}
    settings['member_tolerance']['description'] = 'Axial switch tolerance in canonical kip; not residual strength.'
    settings['translation_tolerance']['description'] = 'One-way spring translation switch tolerance in canonical inches.'
    settings['rotation_tolerance']['description'] = 'One-way rotational spring switch tolerance in radians.'
    if spatial:
        entities["surfaces"] = surface_reference(entities["materials"])
        entities["surface_pressures"] = {"type": "object", "additionalProperties": {"type": "number", "minimum": -1e6, "maximum": 1e6},
            "description": "Collection key is an existing surface ID. put replaces its entire case -> signed pressure map (kip/in2); delete removes the map. Cases must exist. Remove assignments explicitly when deleting a surface/case."}
        entities["surface_supports"] = {"type": "object", "additionalProperties": False,
            "properties": {edge: {"type": "array", "minItems": 1, "uniqueItems": True,
                "items": {"enum": ["DX", "DY", "DZ", "RX", "RY", "RZ"]}} for edge in ("left", "right", "bottom", "top")},
            "description": "Key is a rectangular Quad surface ID. put replaces its entire outer-edge -> global rigid DOF list map. Omit free edges. Geometry-owned, reapplied on remesh. Shared joints use the union of restraints; spring conflicts are rejected. Remove explicitly when deleting a surface. Opening rims are excluded."}
        settings["surface_analysis_enabled"] = {"type": "boolean", "default": False,
            "description": "Experimental coupled analysis opt-in. When true, the complete candidate must contain only conforming, connected rectangular Quad surfaces. No solve occurs during editing."}
        surface_info = "Spatial v38: surfaces, surface_pressures and surface_supports are editable via put/delete; surface_analysis_enabled via settings/set. Recipes use canonical inches/kip, pressure kip/in2. Geometry-only surfaces block analysis. Frame releases cannot be combined with surfaces. Coupled candidate topology is checked once after all operations; stability and independent equilibrium remain analysis gates."
    return {
        "dimension": dimension, "input_units": "Canonical inch-kip regardless of display units; angles in degrees, rotations in radians.",
        "entities": entities,
        "surface_geometry": surface_info,
        "supports": {
            "dof_order": ["DX", "DY", "DZ", "RX", "RY", "RZ"] if spatial else ["DX", "DY", "RZ"],
            "presets": {"free": [False]*(6 if spatial else 3), "pin": [True, True, True, False, False, False] if spatial else [True, True, False],
                        "roller": [False, True, False, False, False, False] if spatial else [False, True, False], "fixed": [True]*(6 if spatial else 3)},
            "custom": "Set support='custom' and the corresponding restraint_x/y/rz (2D) or restraint_x/y/z/rx/ry/rz (3D) booleans. True fixes that global DOF. In 3D inclined supports also use these flags as additional global constraints; other presets ignore them.",
            "inclined": ("Set support='inclined', support_angle=normal azimuth +X toward +Z, support_elevation=normal elevation toward +Y (degrees). Fixes n dot u=settlement_normal (default 0). Optional restraint_* flags add global constraints; explicitly clear them if changing an existing custom support to a freely sliding roller." if spatial else
                         "Set support='inclined' and support_angle=roller tangent CCW from +X (degrees). Fixes (-sin a,cos a) dot (DX,DY)=settlement_normal (default 0); tangent/RZ stay free. Cannot be represented by a global restraint boolean list."),
        },
        "operations": {"put": "op,collection,key,value; merge/create entity or replace combination case-factor map.",
                       "delete": "op,collection,key; no value. Fix all dependent references explicitly in the same batch.",
                       "load_cases": "put/delete with key and no value.",
                       "settings": "op='set',collection='settings',value=partial settings; no key."},
        "settings": settings,
        "editing_metadata": "groups (named node/member ID lists), levels (named global-Y inch elevations) and snap_levels are editing-only metadata in read_model. They do not change analysis. This API does not edit these fields. Geometry deletion prunes group references automatically.",
        "validation": ["All operations validate together and create one undo step; errors make no changes.",
                       "Material E, optional independent shear_modulus and section A/Iy/Iz/J must be positive; rho nonnegative; nu between -1 and 0.5 (exclusive).",
                       "Distributed loads require a frame member, force direction and 0 <= position < end_position <= 1; end_magnitude is the intensity at the end, so set both magnitudes equal for a uniform load.",
                       "Names must be nonempty identifiers; node/member names must be distinct; no zero-length or duplicate members.",
                       "Use read_model for the current session/revision and existing material, section and case identifiers. Do not guess fields from another PyNite API."]}


def batch_examples(project):
    # Separate examples avoid suggesting that a custom support is needed for a preset.
    examples = {"note": "Example identifiers must be changed if they already exist. Use the current session/revision from read_model.",
            "create_cantilever": [
                {"op": "put", "collection": "nodes", "key": "ExampleA", "value": {"x": 0, "y": 0, "support": "fixed"}},
                {"op": "put", "collection": "nodes", "key": "ExampleB", "value": {"x": 120, "y": 0}},
                {"op": "put", "collection": "members", "key": "ExampleBeam", "value": {"start": "ExampleA", "end": "ExampleB", "material": project.default_material, "section": project.default_section}},
                {"op": "put", "collection": "loads", "key": "ExampleForce", "value": {"target": "ExampleB", "kind": "point", "direction": "FY", "magnitude": -1, "case": project.default_load_case}}],
            "update_custom_support": {"op": "put", "collection": "nodes", "key": "ExampleA", "value": {"support": "custom", "restraint_x": True, "restraint_y": True, "restraint_rz": False}}}

    if getattr(project, "dimension", "2D") == "3D":
        examples["create_surface_geometry"] = [
            {"op":"put", "collection":"surfaces", "key":"ExampleFloor", "value":{
                "plane":"XZ", "origin":[0,144,0], "parameters":{"width":240,"height":180}, "mesh_size":60, "thickness":6}},
            {"op":"put", "collection":"surface_pressures", "key":"ExampleFloor", "value":{project.default_load_case:.001}}]
        examples["surface_note"] = "ExampleFloor is geometry-only until settings.surface_analysis_enabled is true. Positive XZ pressure acts in -Y. Enabling requires a conforming connected frame/interface; include matching frame/surface edits together."
    spatial = getattr(project, "dimension", "2D") == "3D"
    examples["update_inclined_roller"] = {"op": "put", "collection": "nodes", "key": "ExampleB", "value": {
        "support": "inclined", "support_angle": 60. if spatial else 30.,
        **({"support_elevation": 30., **{key: False for key in
            ("restraint_x", "restraint_y", "restraint_z", "restraint_rx", "restraint_ry", "restraint_rz")}} if spatial else {})}}
    examples["impose_support_settlement"] = {"op": "put", "collection": "nodes", "key": "ExampleA", "value": {"settlement_y": -0.1}}
    return examples


def surface_reference(material_schema):
    from copy import deepcopy
    from .mesh_model import MeshDefinition, GENERATORS
    defaults = asdict(MeshDefinition())
    properties = {}
    for field in fields(MeshDefinition):
        kind = {str:"string", float:"number", int:"integer", dict:"object", list:"array", Material:"object"}[field.type]
        properties[field.name] = {"type":kind, "default":defaults[field.name]}
    material = deepcopy(material_schema)
    material.pop("required_on_create", None)
    for name, value in defaults["material"].items():
        material["properties"][name]["default"] = value
    material["properties"]["name"]["description"] = "Recipe-local material name; independent of the surface ID and project material library."
    material["update"] = "Nested material fields merge during a surface put."
    material["description"] = "Recipe-local material object, not a project-material ID. put merges its fields; numeric changes clear preset provenance unless explicitly supplied."
    material["properties"]["shear_modulus"] = {"type":"null", "default":None,
        "description":"Surface/plate formulations derive G from E and nu; independent G is not supported in recipes."}
    properties["material"].update(material)
    properties["name"]["description"] = "Omit to use the operation key, or supply the identical name."
    for name, values in (("generator",list(GENERATORS)), ("plane",["XY","XZ","YZ"]), ("axis",["X","Y","Z"]), ("element_type",["Quad","Rect"]), ("unit_system",list(UNIT_SYSTEMS))):
        properties[name]["enum"] = values
    properties["parameters"]["description"] = "Replace the complete generator-specific parameter map; see generator_parameters. Lengths are inches; num_* values are integer counts. Changing generator requires matching parameters in the final batch."
    properties["origin"].update(items={"type":"number"}, minItems=3, maxItems=3)
    for name in ("x_control","y_control"):
        properties[name].update(items={"type":"number"}, maxItems=32,
            description="Replace the list of local rectangle coordinates, strictly inside its bounds (inches).")
    properties["openings"].update(maxItems=16, items={"type":"object", "additionalProperties":False,
        "required":["name","x_left","y_bott","width","height"], "properties":{
            key:{"type":"string" if key=="name" else "number"} for key in ("name","x_left","y_bott","width","height")}},
        description="Replace all rectangular openings; inches in local recipe coordinates. Openings must lie within the rectangle and cannot overlap/touch.")
    for name, value in (("format","pynitegui-mesh"),("version",1),("units","in-kip")):
        properties[name] = {"const":value, "description":"Optional fixed metadata when copying a read_model recipe."}
    return {"type":"object", "properties":properties, "additionalProperties":False, "required_on_create":[],
        "update":"put merges recipe fields; material merges nested fields; parameters, lists and openings replace whole values. delete needs explicit pressure-map cleanup. All final recipe and coupled interface checks are atomic.",
        "generator_parameters":{name:dict(parameters) for name,(_,parameters) in GENERATORS.items()},
        "limits":"16 project meshes; 1024 elements/mesh; 4096 total before openings. Analysis supports rectangle/Quad only; other families are geometry-only.",
        "positive_pressure_normal":{"XY":"+Z", "XZ":"-Y", "YZ":"+X"}}
