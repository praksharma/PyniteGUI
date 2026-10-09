"""Optional official MCP Streamable HTTP transport, imported only on Start."""
import asyncio
import hmac
import ipaddress
import json
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import StrictInt, StrictBool, ValidationError
from .automation_core import TOOLS
from .automation_schema import model_reference
from pynitegui import __version__


def build_application(bridge, permissions, token, port, network_event, *, require_token=True):
    class PermissionServer(MCPServer):
        async def list_tools(self):
            return [tool for tool in await super().list_tools() if permissions.allows(tool.name)]

        async def call_tool(self, name, arguments, context=None):
            code = ""
            operation_index = None
            if not permissions.allows(name):
                code = "permission_denied" if name in TOOLS else "unknown_tool"
            else:
                try:
                    result = await super().call_tool(name, arguments, context)
                    if result.structured_content and result.structured_content.get("ok") is False:
                        result.is_error = True
                    return result
                except Exception as error:
                    code = "invalid_arguments"
                    cause = error.__cause__
                    if name == "apply_batch" and isinstance(cause, ValidationError):
                        for issue in cause.errors(include_input=False, include_url=False):
                            location = issue["loc"]
                            if len(location) > 1 and location[0] == "operations" and type(location[1]) is int:
                                operation_index = location[1]
                                break
            bridge.logged.emit(f"{name if name in TOOLS else 'unknown_tool'} | {code}")
            response = {"ok": False, "error": {"code": code, "message": "Tool disabled, unknown, or arguments rejected. See its schema and desktop permissions."}}
            if operation_index is not None:
                response["error"]["operation_index"] = operation_index
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(response))],
                                  structured_content=response, is_error=True)

    server = PermissionServer("PyniteGUI", version=__version__, log_level="CRITICAL",
        instructions="Controls one attached desktop project window. The GUI owns its session, not the client or chat. "
                     "Call read_model without session_id to discover it; reuse that ID. Opening a project changes it. "
                     "Unknown/old IDs return stale_session; read_model again rather than minting IDs. "
                     "Inputs use canonical inch-kip; result outputs use the units named in their headers. "
                     "Angles are degrees and load positions are member fractions. "
                     "Read read_model.schema or call read_schema before constructing edits; never guess fields. "
                     "Supports are node fields: support=free/pin/roller/fixed/custom, and restraint_* flags for custom. "
                     "Edits require enabled desktop permissions and expected_revision. Files are opened/saved by the user.")

    async def call(name, arguments):
        if not permissions.allows(name):
            return {"ok": False, "error": {"code": "permission_denied", "message": "Tool or permission group disabled."}}
        future = bridge.submit(name, arguments)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(future), 30)
        except TimeoutError:
            bridge.logged.emit(f"{name} | request_timeout")
            return {"ok": False, "error": {"code": "request_timeout", "message": "GUI command timed out; read state before retrying a mutation."}}

    @server.tool(description=TOOLS["read_model"][1], annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    async def read_model(include_schema: StrictBool = True) -> dict[str, Any]:
        return await call("read_model", {"include_schema": include_schema})

    @server.resource("pynitegui://automation/reference", mime_type="application/json",
                     description="Exact 2D and 3D model fields, supports, units and batch operation reference.")
    def automation_reference() -> str:
        return json.dumps({dimension: model_reference(dimension) for dimension in ("2D", "3D")})

    @server.tool(description=TOOLS["read_schema"][1], annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    async def read_schema(session_id: str) -> dict[str, Any]:
        return await call("read_schema", {"session_id": session_id})

    @server.tool(description=TOOLS["read_units"][1], annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    async def read_units(session_id: str) -> dict[str, Any]:
        return await call("read_units", {"session_id": session_id})

    @server.tool(description=TOOLS["read_results"][1], annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    async def read_results(session_id: str, kind: Literal["nodes", "members"] = "nodes", combination: str | None = None,
                           snapshot_id: str | None = None, offset: StrictInt = 0, limit: StrictInt = 100) -> dict[str, Any]:
        return await call("read_results", dict(session_id=session_id, kind=kind, combination=combination,
                                               snapshot_id=snapshot_id, offset=offset, limit=limit))

    @server.tool(description=TOOLS["apply_batch"][1] + " Canonical inch-kip inputs. Operations: "
                 "put/delete on nodes,members,loads,materials,sections,combinations; put/delete key on load_cases; "
                 "set value on settings. Each operation has op,collection,key,value. Entity put merges fields; "
                 "deletion requires explicit dependent-reference updates in the same batch. All operations validate together. "
                 "REQUIRED WORKFLOW: read_model then inspect its schema or call read_schema; do not guess fields. "
                 "Nodes: x,y (+z in 3D), support=free/pin/roller/fixed/custom; custom uses restraint_x/y/rz "
                 "(+z/rx/ry in 3D) booleans. There is no supports object or fixX field. "
                 "Members: start/end node IDs, material/section IDs, kind=frame/truss. "
                 "Loads: target node/member ID, direction, magnitude, kind=point/distributed, case, position/end_position fractions. "
                 "Distributed loads use magnitude and end_magnitude; equal for uniform. See read_schema for allowed directions and all fields. "
                 "2D directions: FX,FY,MZ,Angle,Local x,Local y,Local angle. "
                 "3D directions: FX,FY,FZ,MX,MY,MZ,Angle; members also accept Fx,Fy,Fz,Mx,My,Mz. "
                 "Local operation errors include a zero-based error.operation_index. Whole-batch reference/constraint errors omit it; no changes apply.")
    async def apply_batch(session_id: str, expected_revision: StrictInt, operations: list[dict]) -> dict[str, Any]:
        return await call("apply_batch", dict(session_id=session_id, expected_revision=expected_revision, operations=operations))

    @server.tool(description=TOOLS["run_analysis"][1])
    async def run_analysis(session_id: str, expected_revision: StrictInt) -> dict[str, Any]:
        return await call("run_analysis", dict(session_id=session_id, expected_revision=expected_revision))

    @server.tool(description=TOOLS["analysis_status"][1], annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    async def analysis_status(session_id: str, job_id: str | None = None) -> dict[str, Any]:
        return await call("analysis_status", dict(session_id=session_id, job_id=job_id))

    @server.tool(description=TOOLS["cancel_analysis"][1])
    async def cancel_analysis(session_id: str, job_id: str) -> dict[str, Any]:
        return await call("cancel_analysis", dict(session_id=session_id, job_id=job_id))

    hosts = [f"127.0.0.1:{port}", f"localhost:{port}"]
    origins = [f"http://{host}" for host in hosts]
    app = server.streamable_http_app(stateless_http=True, json_response=True, max_request_body_size=1024*1024,
        transport_security=TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins))

    class LocalAuthentication:
        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await app(scope, receive, send)
            headers = {}
            for key, value in scope.get("headers", []):
                headers.setdefault(key.lower(), []).append(value)
            status, reason = 0, ""
            try:
                local = ipaddress.ip_address(scope["client"][0]).is_loopback
            except (ValueError, TypeError, KeyError):
                local = False
            if not bridge.active:
                status, reason = 503, "server_stopped"
            elif not local or headers.get(b"host") not in ([host.encode()] for host in hosts):
                status, reason = 403, "invalid_host"
            elif b"origin" in headers and headers[b"origin"] not in ([origin.encode()] for origin in origins):
                status, reason = 403, "invalid_origin"
            elif require_token and (len(headers.get(b"authorization", [])) != 1 or not hmac.compare_digest(
                    headers[b"authorization"][0], b"Bearer "+token.encode())):
                status, reason = 401, "unauthorized"
            if status:
                network_event.emit(f"HTTP | {reason}")
                body = json.dumps({"error": reason}).encode()
                response_headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
                if status == 401:
                    response_headers.append((b"www-authenticate", b"Bearer"))
                await send({"type": "http.response.start", "status": status, "headers": response_headers})
                await send({"type": "http.response.body", "body": body})
                return
            network_event.emit("HTTP | authenticated" if require_token else "HTTP | accepted")
            await app(scope, receive, send)

    return LocalAuthentication()
