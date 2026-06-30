"""Thin MCP client manager boundary for existing runtime channels.

The manager does not implement a new MCP transport. It registers existing
channels, caches the raw tool surface that the backend is allowed to call, and
provides a deterministic injection point for runtime-owned MCP tool callers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - compatibility for Pydantic v1 environments
    from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso


RawMCPToolCaller = Callable[[str, dict[str, Any]], dict[str, Any]]
MCPStatusChecker = Callable[[], Any]
MCPTransport = Literal["injected", "socket", "stdio", "http", "codex_session"]
MCPServerRole = Literal["primary", "fallback", "sub_agent", "utility"]


class RawToolSpec(BaseModel):
    server_name: str
    tool_name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPServerConfig(BaseModel):
    server_name: str
    role: MCPServerRole = "primary"
    transport: MCPTransport = "injected"
    enabled: bool = True
    notes: str | None = None


class MCPHealthStatus(BaseModel):
    ok: bool
    server_name: str
    enabled: bool
    transport: MCPTransport
    role: MCPServerRole
    raw_tool_caller_registered: bool = False
    tool_count: int = 0
    issues: list[str] = Field(default_factory=list)
    adapter_status: dict[str, Any] | None = None


class MCPRawToolCallRecord(BaseModel):
    call_id: str
    server_name: str
    tool_name: str
    status: Literal["succeeded", "failed"]
    arguments_summary: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    started_at: str
    finished_at: str


class MCPClientManager:
    """Registry and call boundary for runtime-owned MCP clients."""

    def __init__(self, servers: list[MCPServerConfig] | None = None) -> None:
        self._servers: dict[str, MCPServerConfig] = {}
        self._tools: dict[str, dict[str, RawToolSpec]] = {}
        self._callers: dict[str, RawMCPToolCaller] = {}
        self._status_checkers: dict[str, MCPStatusChecker] = {}
        self.raw_call_log: list[MCPRawToolCallRecord] = []
        for server in servers or []:
            self.register_server(server)

    def register_server(
        self,
        config: MCPServerConfig,
        *,
        tools: list[RawToolSpec] | None = None,
        raw_tool_caller: RawMCPToolCaller | None = None,
        status_checker: MCPStatusChecker | None = None,
    ) -> None:
        self._servers[config.server_name] = config
        self._tools.setdefault(config.server_name, {})
        for spec in tools or []:
            if spec.server_name != config.server_name:
                raise ValueError(
                    f"tool spec server_name {spec.server_name!r} does not match {config.server_name!r}"
                )
            self._tools[config.server_name][spec.tool_name] = spec
        if raw_tool_caller is not None:
            self._callers[config.server_name] = raw_tool_caller
        if status_checker is not None:
            self._status_checkers[config.server_name] = status_checker

    def register_raw_tool_caller(self, server_name: str, raw_tool_caller: RawMCPToolCaller) -> None:
        self._require_server(server_name)
        self._callers[server_name] = raw_tool_caller

    def list_servers(self) -> list[MCPServerConfig]:
        return list(self._servers.values())

    def list_tools(self, server_name: str) -> list[RawToolSpec]:
        server = self._require_server(server_name)
        if not server.enabled:
            return []
        return list(self._tools.get(server_name, {}).values())

    def raw_tool_caller_for(self, server_name: str) -> RawMCPToolCaller:
        self._require_server(server_name)

        def _call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return self.call_tool(server_name, tool_name, arguments)

        return _call

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        server = self._require_server(server_name)
        arguments = arguments or {}
        if not server.enabled:
            raise ValueError(f"MCP server is disabled: {server_name}")
        if tool_name not in self._tools.get(server_name, {}):
            raise ValueError(f"raw MCP tool {tool_name!r} is not registered for server {server_name!r}")

        started_at = utc_now_iso()
        result: dict[str, Any]
        error_message = None
        caller = self._callers.get(server_name)
        if caller is None:
            result = {
                "status": "error",
                "message": f"no raw MCP tool caller registered for server {server_name}",
            }
            status: Literal["succeeded", "failed"] = "failed"
            error_message = result["message"]
        else:
            try:
                result = caller(tool_name, arguments)
                status = "succeeded" if _raw_mcp_result_ok(result) else "failed"
                if status == "failed":
                    error_message = _raw_mcp_error_message(result)
            except Exception as exc:  # pragma: no cover - defensive boundary
                result = {"status": "error", "message": str(exc)}
                status = "failed"
                error_message = str(exc)

        self.raw_call_log.append(
            MCPRawToolCallRecord(
                call_id=f"mcp_call_{uuid4().hex[:12]}",
                server_name=server_name,
                tool_name=tool_name,
                status=status,
                arguments_summary=_summarize_arguments(arguments),
                result_summary=_summarize_result(result),
                error_message=error_message,
                started_at=started_at,
                finished_at=utc_now_iso(),
            )
        )
        return result

    def health_check(self, server_name: str) -> MCPHealthStatus:
        server = self._require_server(server_name)
        issues = []
        adapter_status = None
        checker = self._status_checkers.get(server_name)
        if checker is not None:
            adapter_status = _to_plain_dict(checker())
            if adapter_status.get("ok") is False:
                issues.append("adapter_status_not_ok")
            issues.extend(str(item) for item in adapter_status.get("issues", []) if item)
        if server.enabled and server_name not in self._callers and server.transport == "injected":
            issues.append("missing_raw_tool_caller")
        if not server.enabled:
            issues.append("server_disabled")
        return MCPHealthStatus(
            ok=server.enabled and not issues,
            server_name=server_name,
            enabled=server.enabled,
            transport=server.transport,
            role=server.role,
            raw_tool_caller_registered=server_name in self._callers,
            tool_count=len(self._tools.get(server_name, {})),
            issues=issues,
            adapter_status=adapter_status,
        )

    def _require_server(self, server_name: str) -> MCPServerConfig:
        try:
            return self._servers[server_name]
        except KeyError as exc:
            raise ValueError(f"unknown MCP server: {server_name}") from exc


def build_default_mcp_client_manager(
    *,
    blender_raw_tool_caller: RawMCPToolCaller | None = None,
    blender_status_checker: MCPStatusChecker | None = None,
    codex_self_status_checker: MCPStatusChecker | None = None,
) -> MCPClientManager:
    """Build the default V1 MCP registry without creating new transports."""

    manager = MCPClientManager()
    manager.register_server(
        MCPServerConfig(
            server_name="blender_lab",
            role="primary",
            transport="injected",
            notes="Existing Blender Lab MCP channel behind BlenderMCPAdapter.",
        ),
        tools=blender_lab_tool_specs(),
        raw_tool_caller=blender_raw_tool_caller,
        status_checker=blender_status_checker,
    )
    manager.register_server(
        MCPServerConfig(
            server_name="codex_self_mcp",
            role="sub_agent",
            transport="stdio",
            notes="Existing /home/team/zouzhiyuan/codex-self-mcp sub-agent channel.",
        ),
        tools=[
            RawToolSpec(
                server_name="codex_self_mcp",
                tool_name="codex_subagent_call_plan",
                description="Build an explicit codex-self-mcp helper command plan.",
            ),
            RawToolSpec(
                server_name="codex_self_mcp",
                tool_name="codex_subagent_smoke",
                description="Run the explicit codex-self-mcp smoke path when requested.",
            ),
        ],
        status_checker=codex_self_status_checker,
    )
    return manager


def blender_lab_tool_specs(server_name: str = "blender_lab") -> list[RawToolSpec]:
    return [
        RawToolSpec(
            server_name=server_name,
            tool_name="get_objects_summary",
            description="Read the current Blender scene object hierarchy.",
            input_schema={},
        ),
        RawToolSpec(
            server_name=server_name,
            tool_name="execute_blender_code",
            description="Execute fixed-template Blender Python emitted by safe domain planners.",
            input_schema={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        ),
    ]


def _raw_mcp_result_ok(result: dict[str, Any]) -> bool:
    if result.get("status") == "error":
        return False
    inner = result.get("result")
    if isinstance(inner, dict) and inner.get("status") == "error":
        return False
    return result.get("ok", True) is not False


def _raw_mcp_error_message(result: dict[str, Any]) -> str:
    if isinstance(result.get("message"), str):
        return result["message"]
    inner = result.get("result")
    if isinstance(inner, dict) and isinstance(inner.get("message"), str):
        return inner["message"]
    if isinstance(result.get("error"), str):
        return result["error"]
    return "raw MCP tool failed"


def _summarize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    summary = {}
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > 160:
            summary[key] = f"<string:{len(value)} chars>"
        else:
            summary[key] = value
    return summary


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("status", "ok", "message", "error"):
        if key in result:
            summary[key] = result[key]
    inner = result.get("result")
    if isinstance(inner, dict):
        for key in ("status", "ok", "message", "scene_name", "active_object"):
            if key in inner:
                summary[f"result.{key}"] = inner[key]
        if "collections" in inner and isinstance(inner["collections"], list):
            summary["result.collection_count"] = len(inner["collections"])
    return summary or {"keys": sorted(result.keys())}


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return dict(value)
    return {"value": value}
