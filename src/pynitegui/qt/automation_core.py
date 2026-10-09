"""GUI-thread automation commands; no optional server dependencies are imported."""
from concurrent.futures import Future
from dataclasses import asdict, dataclass, fields
import json
from threading import Lock

from PySide6.QtCore import QObject, Signal, Slot, Qt
from .model import Load, Material, Member, Node, Project, Section


TOOLS = {
    "read_model": ("Model reads", "Read the current model, project/session revisions and exact entity schema, including empty collections. Read this before edits; do not guess node/support/load fields."),
    "read_schema": ("Model reads", "Read the exact 2D/3D entity fields, types, defaults, support presets/custom restraints, units, validation rules and valid batch examples for the current project. Call before constructing edits, especially for an empty model."),
    "read_units": ("Model reads", "Read display units and canonical conversion factors."),
    "read_results": ("Result reads", "Read paginated snapshot-labelled node or member results."),
    "apply_batch": ("Model edits", "Apply a validated model batch as one undoable edit."),
    "run_analysis": ("Analysis", "Start the existing background analysis workflow."),
    "analysis_status": ("Analysis", "Read analysis job progress, failures and snapshot identity."),
    "cancel_analysis": ("Analysis", "Cancel the identified running analysis job."),
}


class AutomationError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
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
    if len(json.dumps(operations, allow_nan=False).encode()) > 512*1024:
        raise AutomationError("invalid_batch", "Batch exceeds 512 KiB.")
    data = project.to_dict()
    constructors = {"nodes": Node, "members": Member, "loads": Load, "materials": Material, "sections": Section}
    if getattr(project, "dimension", "2D") == "3D":
        from .spatial_model import SpatialNode, SpatialMember, SpatialLoad
        constructors.update(nodes=SpatialNode, members=SpatialMember, loads=SpatialLoad)
    settings = {"unit_system", "grid", "default_material", "default_section", "default_load_case",
                "self_weight_case", "self_weight_factor"}
    for operation in operations:
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
        if collection in constructors:
            entities = data[collection]
            if action == "put":
                allowed = {field.name for field in fields(constructors[collection])}
                if not isinstance(value, dict) or set(value)-allowed or value.get("name", key) != key:
                    raise AutomationError("invalid_batch", "Unsupported entity field or inconsistent name.")
                values = {**entities.get(key, {}), **value, "name": key}
                if collection == "materials" and "preset" not in value and any(
                        field in value and value[field] != entities.get(key, {}).get(field) for field in ("E", "nu", "rho")):
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
    return Project.from_dict(data)


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
            return {**self.identity(), "model": window.project.to_dict(), "schema": model_reference(getattr(window.project, "dimension", "2D")), "input_units": "Canonical inch-kip; positions are member fractions; angles are degrees."}
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
            if kind not in ("nodes", "members"):
                raise AutomationError("invalid_query", "Choose nodes or members.")
            offset, limit = arguments.get("offset", 0), arguments.get("limit", 100)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
                raise AutomationError("invalid_query", "Use a nonnegative offset and a limit from 1 to 1000.")
            from .reports import result_table
            headers, rows = result_table(window.project, result.for_combination(combination), kind)
            return {**self.identity(), **self.snapshot(), "combination": combination,
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
                                           "model_signature": result.model_signature}

    def status(self):
        window = self.window
        return {**self.identity(), "job_id": window.analysis_job_id, "running": window.thread is not None,
                "job_session_id": window.analysis_job_session, "job_model_revision": getattr(window, "analysis_revision", None),
                "phase": window.analysis_phase.text() if window.thread is not None else "",
                "state": window.results_panel.analysis_state, "error": window.analysis_error,
                "snapshot": self.snapshot()}


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
            response, status = {"ok": False, "error": {"code": error.code, "message": error.message}}, error.code
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            response, status = {"ok": False, "error": {"code": "invalid_arguments", "message": str(error)}}, "invalid_arguments"
        except Exception:
            response, status = {"ok": False, "error": {"code": "internal_error", "message": "The command failed without a complete response."}}, "internal_error"
        # Fixed names/codes only: no arguments, model values, credentials or paths.
        self.logged.emit(f"{request.name if request.name in TOOLS else 'unknown_tool'} | {status}")
        if not request.future.done():
            request.future.set_result(response)
