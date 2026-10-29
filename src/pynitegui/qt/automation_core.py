"""GUI-thread automation commands; no optional server dependencies are imported."""
from concurrent.futures import Future
from dataclasses import asdict, dataclass, fields
import json
from threading import Lock

from PySide6.QtCore import QObject, Signal, Slot, Qt
from .model import Load, Material, Member, Node, Project, Section


TOOLS = {
    "read_model": ("Model reads", "Read the current model, project/session revisions and exact entity schema, including empty collections. include_schema defaults true; set false after learning the schema to reduce response size. No session_id is needed for this discovery call. Read this before edits; do not guess node/support/load fields."),
    "read_schema": ("Model reads", "Read the exact 2D/3D entity fields, types, defaults, support presets/custom restraints, units, validation rules and valid batch examples for the current project. Call before constructing edits, especially for an empty model."),
    "read_units": ("Model reads", "Read display units and canonical conversion factors."),
    "read_results": ("Result reads", "Read paginated snapshot-labelled results: kind=nodes|members|surface_elements. Spatial members with translational releases include a released_end_translations table (member-side local DX/DY/DZ, distinct from joint motion) for members on the page. surface_elements requires surface_id from read_model.model.surfaces and returns unsmoothed local Quad element-centre Mx,My,Mxy (moment/length), Sx,Sy,Txy (membrane stresses, tension positive). Quad transverse shear is unavailable pending independent validation. Output units follow headers. Use analysis_status.available_combinations for solved names; omit combination to use the snapshot default. Only the active snapshot is retained."),
    "apply_batch": ("Model edits", "Apply a validated model batch as one undoable edit."),
    "run_analysis": ("Analysis", "Start background analysis using settings.analysis_method (linear|p_delta) and return a job_id immediately. Poll analysis_status with that job_id until running=false, then check state/error before read_results. phase is human-readable progress text, not a fixed enum."),
    "analysis_status": ("Analysis", "Read job progress, failures, the active snapshot and available_combinations (solved names). Poll after run_analysis until running=false; check state/error. Only one active result snapshot is retained; job_id rejects replaced jobs."),
    "cancel_analysis": ("Analysis", "Cancel the identified running analysis job."),
}


class AutomationError(Exception):
    def __init__(self, code, message, operation_index=None):
        self.code, self.message = code, message
        self.operation_index = operation_index
        super().__init__(message)


class Permissions:
    def __init__(self):
        self.lock = Lock()
        self.groups = {group: group.endswith("reads") for group, _ in TOOLS.values()}
        self.tools = {name: True for name in TOOLS}

    def allows(self, name):
        with self.lock:
            return name in TOOLS and self.groups[TOOLS[name][0]] and self.tools[name]

    def set_group(self, name, enabled):
        with self.lock:
            self.groups[name] = bool(enabled)

    def set_tool(self, name, enabled):
        with self.lock:
            self.tools[name] = bool(enabled)


def safe_json(value):
    # Convert numpy scalars and tuples to transportable values; never accept NaN.
    return json.loads(json.dumps(value, allow_nan=False, default=lambda item: item.item()))


def batch_candidate(project, operations):
    if not isinstance(operations, list) or not 1 <= len(operations) <= 500:
        raise AutomationError("invalid_batch", "Supply between 1 and 500 operations.")
    for index, operation in enumerate(operations):
        try:
            json.dumps(operation, allow_nan=False)
        except (ValueError, TypeError, OverflowError) as error:
            raise AutomationError("invalid_batch", str(error), index) from error
    if len(json.dumps(operations, allow_nan=False).encode()) > 512*1024:
        raise AutomationError("invalid_batch", "Batch exceeds 512 KiB.")
    data = project.to_dict()
    constructors = {"nodes": Node, "members": Member, "loads": Load, "materials": Material, "sections": Section}
    spatial = getattr(project, "dimension", "2D") == "3D"
    if spatial:
        from .spatial_model import SpatialNode, SpatialMember, SpatialLoad
        constructors.update(nodes=SpatialNode, members=SpatialMember, loads=SpatialLoad)
    settings = {"unit_system", "grid", "default_material", "default_section", "default_load_case",
                "self_weight_case", "self_weight_factor", "analysis_method"}
    if spatial:
        settings.add("surface_analysis_enabled")
    for index, operation in enumerate(operations):
        try:
            if not isinstance(operation, dict) or set(operation)-{"op", "collection", "key", "value"}:
                raise AutomationError("invalid_batch", "Each operation must contain only op, collection, key and value.")
            action, collection, key, value = (operation.get(name) for name in ("op", "collection", "key", "value"))
            if collection == "settings" and action == "set":
                if not isinstance(value, dict) or not value or set(value)-settings or key is not None:
                    raise AutomationError("invalid_batch", "Unsupported settings field.")
                data.update(value)
                continue
            if not isinstance(key, str) or not key.strip() or key != key.strip():
                raise AutomationError("invalid_batch", "Entity keys must be nonempty identifiers.")
            if spatial and collection == "surfaces":
                from .mesh_model import MeshDefinition
                entities = data[collection]
                if action == "put":
                    allowed = {field.name for field in fields(MeshDefinition)} | {"format", "version", "units"}
                    if not isinstance(value, dict) or set(value)-allowed or value.get("name", key) != key:
                        raise AutomationError("invalid_batch", "Unsupported surface field or inconsistent name.")
                    previous = entities.get(key) or MeshDefinition(name=key).to_dict()
                    values = {**previous, **value, "name": key}
                    if "material" in value and isinstance(value["material"], dict):
                        material = value["material"]
                        values["material"] = {**previous["material"], **material}
                        if "preset" not in material and any(field in material and material[field] != previous["material"].get(field)
                                                            for field in ("E", "nu", "rho", "shear_modulus")):
                            values["material"]["preset"] = None
                    entities[key] = values
                elif action == "delete" and value is None and key in entities:
                    del entities[key]
                else:
                    raise AutomationError("invalid_batch", "Invalid surface operation.")
            elif spatial and collection in ("surface_pressures", "surface_supports"):
                if action == "put" and isinstance(value, dict):
                    data[collection][key] = value
                elif action == "delete" and value is None and key in data[collection]:
                    del data[collection][key]
                else:
                    raise AutomationError("invalid_batch", "Use put with a complete surface assignment map, or delete an existing map.")
            elif collection in constructors:
                entities = data[collection]
                if action == "put":
                    allowed = {field.name for field in fields(constructors[collection])}
                    if not isinstance(value, dict) or set(value)-allowed or value.get("name", key) != key:
                        raise AutomationError("invalid_batch", "Unsupported entity field or inconsistent name.")
                    values = {**entities.get(key, {}), **value, "name": key}
                    if collection == "materials" and "preset" not in value and any(
                            field in value and value[field] != entities.get(key, {}).get(field) for field in ("E", "nu", "rho", "shear_modulus")):
                        values["preset"] = None
                    if collection == "sections" and "catalog" not in value and any(
                            field in value and value[field] != entities.get(key, {}).get(field) for field in ("A", "Iy", "Iz", "J")):
                        values.update(catalog=None, designation=None, weak_axis=False)
                    entities[key] = asdict(constructors[collection](**values))
                elif action == "delete" and value is None:
                    if key not in entities:
                        raise AutomationError("invalid_batch", "Cannot delete an unknown entity.")
                    del entities[key]
                else:
                    raise AutomationError("invalid_batch", "Use put or delete for entity collections.")
            elif collection == "combinations":
                if action == "put" and isinstance(value, dict):
                    data[collection][key] = value
                elif action == "delete" and value is None and key in data[collection]:
                    del data[collection][key]
                else:
                    raise AutomationError("invalid_batch", "Invalid combination operation.")
            elif collection == "load_cases":
                if action == "put" and value is None and key not in data[collection]:
                    data[collection].append(key)
                elif action == "delete" and value is None and key in data[collection]:
                    data[collection].remove(key)
                else:
                    raise AutomationError("invalid_batch", "Invalid load-case operation.")
            else:
                raise AutomationError("invalid_batch", "Unsupported collection.")
        except AutomationError as error:
            raise AutomationError(error.code, error.message, index) from error
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            raise AutomationError("invalid_batch", str(error), index) from error
    try:
        # Selection groups are editing metadata: geometry deletion prunes their
        # references, while engineering dependencies still require explicit edits.
        for group in data["groups"].values():
            for kind in ("nodes", "members"):
                group[kind] = [key for key in group[kind] if key in data[kind]]
        candidate = Project.from_dict(data)
        if spatial:
            from .surface_solver import validate_coupled_topology
            validate_coupled_topology(candidate)
        return candidate
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        # Cross-entity constraints apply to the completed batch; do not blame an
        # operation when several cooperating changes can cause or fix the issue.
        raise AutomationError("invalid_batch", str(error)) from error


class AutomationCommands:
    def __init__(self, window):
        self.window = window

    def identity(self):
        window = self.window
        return {"session_id": window.project_session, "revision": window.automation_revision,
                "model_revision": window.revision, "mcp_mode": window.mcp_mode}

    def guard(self, arguments, revision=False):
        if arguments.get("session_id") != self.window.project_session:
            raise AutomationError("stale_session", "Read the current model session before continuing.")
        if revision and (type(arguments.get("expected_revision")) is not int or
                         arguments["expected_revision"] != self.window.automation_revision):
            raise AutomationError("stale_revision", "The model or units changed. Read the current revision and retry.")

    def execute(self, name, arguments, cancelled=lambda: False):
        window = self.window
        if name == "read_model":
            from .automation_schema import model_reference
            include_schema = arguments.get("include_schema", True)
            if type(include_schema) is not bool:
                raise AutomationError("invalid_arguments", "include_schema must be a boolean.")
            response = {**self.identity(), "model": window.project.to_dict(),
                        "input_units": "Canonical inch-kip; positions are member fractions; angles are degrees."}
            if include_schema:
                response["schema"] = model_reference(getattr(window.project, "dimension", "2D"))
            return response
        self.guard(arguments, revision=name in ("apply_batch", "run_analysis"))
        if name == "read_schema":
            from .automation_schema import model_reference, batch_examples
            return {**self.identity(), "schema": model_reference(getattr(window.project, "dimension", "2D")), "examples": batch_examples(window.project)}
        if name == "read_units":
            return {**self.identity(), "units": asdict(window.project.units), "canonical": "in-kip"}
        if name == "apply_batch":
            self.require_idle_editor()
            candidate = batch_candidate(window.project, arguments["operations"])
            self.guard(arguments, revision=True)
            if cancelled():
                raise AutomationError("request_cancelled", "The request was cancelled before applying.")
            changed = window.project.to_dict() != candidate.to_dict()
            if changed:
                from .app import Edit
                window.undo.push(Edit(window, "Automation batch edit", window.project.clone(), candidate))
            return {**self.identity(), "changed": changed, "result_snapshot": self.snapshot()}
        if name == "run_analysis":
            self.require_idle_editor()
            from .analysis_method import analysis_method_issue
            method_issue = analysis_method_issue(window.project)
            if method_issue:
                raise AutomationError("unsupported_analysis", method_issue)
            from .spatial_surfaces import surface_analysis_issue
            surface_issue = surface_analysis_issue(window.project)
            if surface_issue:
                raise AutomationError("surface_geometry_only", surface_issue)
            if window.thread is not None:
                raise AutomationError("analysis_busy", "An analysis is already running.")
            if cancelled():
                raise AutomationError("request_cancelled", "The request was cancelled before starting.")
            window.run_analysis(automation=True)
            return self.status()
        if name == "analysis_status":
            if arguments.get("job_id") and arguments["job_id"] != window.analysis_job_id:
                raise AutomationError("unknown_job", "The job is no longer the current analysis job.")
            return self.status()
        if name == "cancel_analysis":
            if arguments["job_id"] != window.analysis_job_id:
                raise AutomationError("unknown_job", "The job is no longer the current analysis job.")
            if window.thread is None:
                raise AutomationError("job_finished", "The analysis job has already stopped.")
            if cancelled():
                raise AutomationError("request_cancelled", "The request was cancelled before cancelling analysis.")
            window.cancel_analysis()
            return self.status()
        if name == "read_results":
            result = window.result
            if result is None:
                raise AutomationError("no_results", "Analyze the current model before reading results.")
            if arguments.get("snapshot_id") and arguments["snapshot_id"] != result.snapshot_id:
                raise AutomationError("stale_snapshot", "The result snapshot changed. Read the current analysis status.")
            combination = arguments.get("combination") or result.combination
            if combination not in result.solver.load_combos:
                raise AutomationError("invalid_combination", "Unknown solved combination.")
            kind = arguments.get("kind", "nodes")
            if kind not in ("nodes", "members", "surface_elements"):
                raise AutomationError("invalid_query", "Choose nodes, members or surface_elements.")
            offset, limit = arguments.get("offset", 0), arguments.get("limit", 100)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
                raise AutomationError("invalid_query", "Use a nonnegative offset and a limit from 1 to 1000.")
            from .reports import result_table
            local_metadata = {}
            if kind == "surface_elements":
                from .surface_results import surface_table, centre_results
                surface = arguments.get("surface_id")
                if not isinstance(surface, str) or surface not in getattr(result.solver, "_pynitegui_surfaces", {}):
                    raise AutomationError("invalid_query", "surface_elements requires a surface_id present in the solved snapshot.")
                selected = result.for_combination(combination)
                headers, rows = surface_table(window.project, selected, surface)
                local_metadata = {"surface_id": surface, "sample": "Element centres, xi=eta=0; unsmoothed",
                                  "local_axes": centre_results(selected, surface)[0]["axes"],
                                  "convention": "Local x=i->j, y=i->n, z=x cross y. Membrane tension positive. Quad transverse shear unavailable pending validation; no combined face stresses or design checks."}
            else:
                headers, rows = result_table(window.project, result.for_combination(combination), kind)
                directions = getattr(result.solver, "rotation_nullspaces", None)
                if kind == "nodes" and directions is not None:
                    names = {row[0] for row in rows[offset:offset+limit]}
                    local_metadata = {"inactive_rotation_directions": {name: basis.T.tolist() for name, basis in directions.items() if name in names},
                        "rotation_note": "Undefined global joint-rotation components are n/a, not measured zero. Listed global unit vectors span unused rotations. Recovered member-end bending slopes are separate from the shared joint rotation."}
                if kind == "members" and result.spatial:
                    from .spatial_results import released_translation_table
                    motion_headers, motion_rows = released_translation_table(window.project, result.for_combination(combination))
                    names = {row[0] for row in rows[offset:offset+limit]}
                    motion_rows = [row for row in motion_rows if row[0] in names]
                    if motion_rows:
                        local_metadata = {"released_end_translations": {"headers": motion_headers, "rows": motion_rows},
                            "translation_note": "Recovered member-side DX/DY/DZ use rolled local axes and the header length units; they can differ from the global joint motions. Includes only members present on this result page."}
            return {**self.identity(), **self.snapshot(), "combination": combination,
                    **local_metadata,
                    "unit_system": window.project.unit_system, "headers": headers, "rows": rows[offset:offset+limit],
                    "total_rows": len(rows), "offset": offset, "analysis_state": window.results_panel.analysis_state}
        raise AutomationError("unknown_tool", "Unknown automation tool.")

    def require_idle_editor(self):
        if self.window.live_analysis.is_editing():
            raise AutomationError("editor_busy", self.window.live_analysis.editing_blocker() or
                                  "Finish the current input, gesture or dialog before automation edits/analysis.")

    def snapshot(self):
        result = self.window.result
        return None if result is None else {"snapshot_id": result.snapshot_id, "analyzed_at": result.analyzed_at,
                                           "model_signature": result.model_signature,
                                           "analysis_method": result.analysis_method, "method_label": result.method_label}

    def status(self):
        window = self.window
        return {**self.identity(), "job_id": window.analysis_job_id, "running": window.thread is not None,
                "job_session_id": window.analysis_job_session, "job_model_revision": getattr(window, "analysis_revision", None),
                "phase": window.analysis_phase.text() if window.thread is not None else "",
                "state": window.results_panel.analysis_state, "error": window.analysis_error,
                "snapshot": self.snapshot(),
                "available_combinations": list(window.result.solver.load_combos) if window.result is not None else []}


@dataclass
class CommandRequest:
    name: str
    arguments: dict
    generation: int
    future: Future


class QtCommandBridge(QObject):
    requested = Signal(object)
    logged = Signal(str)

    def __init__(self, window, permissions):
        super().__init__(window)
        self.commands = AutomationCommands(window)
        self.permissions = permissions
        self.lock = Lock()
        self.active = False
        self.generation = 0
        self.queued = 0
        self.requested.connect(self.dispatch, Qt.ConnectionType.QueuedConnection)

    def set_active(self, active):
        with self.lock:
            self.active = active
            self.generation += 1

    def submit(self, name, arguments):
        future = Future()
        with self.lock:
            if not self.active or self.queued >= 64:
                future.set_result({"ok": False, "error": {"code": "server_unavailable", "message": "Server stopped or command queue full."}})
                return future
            request = CommandRequest(name, arguments, self.generation, future)
            self.queued += 1
        self.requested.emit(request)
        return future

    @Slot(object)
    def dispatch(self, request):
        with self.lock:
            active = self.active and request.generation == self.generation
            self.queued -= 1
        if request.future.cancelled():
            return
        try:
            if not active:
                raise AutomationError("server_stopped", "The server stopped before dispatch.")
            if not self.permissions.allows(request.name):
                raise AutomationError("permission_denied", "This tool or its permission group is disabled.")
            data = safe_json(self.commands.execute(request.name, request.arguments, request.future.cancelled))
            response, status = {"ok": True, "data": data}, "ok"
        except AutomationError as error:
            error_data = {"code": error.code, "message": error.message}
            if error.operation_index is not None:
                error_data["operation_index"] = error.operation_index
            response, status = {"ok": False, "error": error_data}, error.code
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            response, status = {"ok": False, "error": {"code": "invalid_arguments", "message": str(error)}}, "invalid_arguments"
        except Exception:
            response, status = {"ok": False, "error": {"code": "internal_error", "message": "The command failed without a complete response."}}, "internal_error"
        # Fixed names/codes only: no arguments, model values, credentials or paths.
        self.logged.emit(f"{request.name if request.name in TOOLS else 'unknown_tool'} | {status}")
        if not request.future.done():
            request.future.set_result(response)
