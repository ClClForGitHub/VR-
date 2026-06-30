"""Thin Blender MCP bridge/status adapter and scene-state synchronizer."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import socket
import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - compatibility for Pydantic v1 environments
    from pydantic import BaseModel, Field

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.domain_tools import assert_tool_allowed
from agent_runtime.state import BlenderObjectRecord, BlenderSceneState, WorkflowPhase


CommandRunner = Callable[[list[str], float], subprocess.CompletedProcess[str]]
SendCodeFunc = Callable[[str, bool], dict[str, Any]]


class BlenderMCPStatus(BaseModel):
    ok: bool
    server_name: str = "blender_lab"
    bridge_host: str
    bridge_port: int
    status_script_path: str
    status_script_exists: bool
    blender_version: str | None = None
    bridge_running: bool | None = None
    socket_open: bool | None = None
    codex_command: str
    codex_cli_path: str | None = None
    codex_cli_found: bool = False
    configured_in_codex_mcp_list: bool | None = None
    mcp_list_servers: list[str] = Field(default_factory=list)
    status_output_tail: str | None = None
    issues: list[str] = Field(default_factory=list)


class BlenderSceneSyncResult(BaseModel):
    ok: bool
    blender_scene: BlenderSceneState | None = None
    scene_name: str | None = None
    active_object: str | None = None
    object_mode: str | None = None
    object_count: int = 0
    camera_object: str | None = None
    issues: list[str] = Field(default_factory=list)


class BlenderMCPDomainOperationPlan(BaseModel):
    ok: bool
    domain_tool_name: str
    phase: WorkflowPhase
    raw_tool_name: str | None = None
    raw_tool_arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_summary: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    issues: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class BlenderMCPAdapter:
    """Probe the existing Blender Lab MCP channel without reimplementing it."""

    def __init__(
        self,
        *,
        root: str | Path = "/home/team/zouzhiyuan/image23D_Agent",
        status_script: str | Path | None = None,
        bridge_host: str = "127.0.0.1",
        bridge_port: int = 9876,
        server_name: str = "blender_lab",
        codex_command: str = "codex",
        run_command: CommandRunner | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.status_script = (
            Path(status_script).expanduser().resolve()
            if status_script is not None
            else self.root / "scripts" / "status_blender51_lab_mcp_bridge.sh"
        )
        self.bridge_host = bridge_host
        self.bridge_port = bridge_port
        self.server_name = server_name
        self.codex_command = codex_command
        self._run_command = run_command or _run_command

    def status(self, *, timeout_seconds: float = 30) -> BlenderMCPStatus:
        issues = []
        status_script_exists = self.status_script.is_file()
        if not status_script_exists:
            issues.append("missing_status_script")

        blender_version = None
        bridge_running = None
        socket_open = _socket_open(self.bridge_host, self.bridge_port)
        status_output_tail = None

        if status_script_exists:
            status_result = self._run_command(["bash", str(self.status_script)], timeout_seconds)
            status_output = (status_result.stdout or "") + ("\n" + status_result.stderr if status_result.stderr else "")
            status_output_tail = _tail_text(status_output)
            blender_version = _parse_blender_version(status_output)
            bridge_running = "Blender 5.1 Lab MCP bridge running" in status_output
            socket_open = "Blender Lab MCP bridge socket: open" in status_output or socket_open
            if status_result.returncode != 0:
                issues.append("status_script_failed")
        if not bridge_running:
            issues.append("bridge_not_running")
        if not socket_open:
            issues.append("bridge_socket_closed")

        codex_cli_path = shutil.which(self.codex_command)
        codex_cli_found = codex_cli_path is not None
        configured_in_codex_mcp_list = None
        mcp_list_servers: list[str] = []
        if not codex_cli_found:
            issues.append("missing_codex_cli")
        else:
            mcp_list_result = self._run_command([self.codex_command, "mcp", "list"], timeout_seconds)
            if mcp_list_result.returncode == 0:
                mcp_list_servers = _parse_mcp_list_names(mcp_list_result.stdout)
                configured_in_codex_mcp_list = self.server_name in mcp_list_servers
                if not configured_in_codex_mcp_list:
                    issues.append("blender_lab_not_configured_in_codex_mcp_list")
            else:
                issues.append("codex_mcp_list_failed")

        ok = (
            status_script_exists
            and bool(bridge_running)
            and bool(socket_open)
            and codex_cli_found
            and bool(configured_in_codex_mcp_list)
        )
        return BlenderMCPStatus(
            ok=ok,
            server_name=self.server_name,
            bridge_host=self.bridge_host,
            bridge_port=self.bridge_port,
            status_script_path=str(self.status_script),
            status_script_exists=status_script_exists,
            blender_version=blender_version,
            bridge_running=bridge_running,
            socket_open=socket_open,
            codex_command=self.codex_command,
            codex_cli_path=codex_cli_path,
            codex_cli_found=codex_cli_found,
            configured_in_codex_mcp_list=configured_in_codex_mcp_list,
            mcp_list_servers=mcp_list_servers,
            status_output_tail=status_output_tail,
            issues=issues,
        )


class BlenderLabSocketRawToolCaller:
    """Call selected raw tools through the existing Blender Lab socket bridge."""

    def __init__(
        self,
        *,
        root: str | Path = "/home/team/zouzhiyuan/image23D_Agent",
        bridge_host: str = "127.0.0.1",
        bridge_port: int = 9876,
        send_code_func: SendCodeFunc | None = None,
        toolcode_format_call: Callable[[str, object], str] | None = None,
        toolcode_load_from_filepath: Callable[[str], str] | None = None,
        toolcode_wrap_with_calling_convention: Callable[[str], str] | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.bridge_host = bridge_host
        self.bridge_port = bridge_port
        self._send_code_func = send_code_func
        self._toolcode_format_call = toolcode_format_call
        self._toolcode_load_from_filepath = toolcode_load_from_filepath
        self._toolcode_wrap_with_calling_convention = toolcode_wrap_with_calling_convention

    def __call__(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        if tool_name == "get_objects_summary":
            return self._get_objects_summary()
        if tool_name == "execute_blender_code":
            code = arguments.get("code")
            if not isinstance(code, str) or not code.strip():
                raise ValueError("execute_blender_code requires a non-empty string code argument")
            return self._send_code(code, strict_json=False)
        raise ValueError(f"unsupported Blender Lab socket raw tool: {tool_name}")

    def _get_objects_summary(self) -> dict[str, Any]:
        helpers = self._helpers()
        tool_path = self._tools_dir() / "get_objects_summary.py"
        tool_call = helpers["wrap"](helpers["load"](str(tool_path)))
        code = helpers["format"](tool_call, None)
        return self._send_code(code, strict_json=True)

    def _send_code(self, code: str, *, strict_json: bool) -> dict[str, Any]:
        send_code = self._send_code_func or self._load_send_code_func()
        with _temporary_env(
            {
                "BLENDER_MCP_HOST": self.bridge_host,
                "BLENDER_MCP_PORT": str(self.bridge_port),
            }
        ):
            result = send_code(code, strict_json)
        if not isinstance(result, dict):
            raise TypeError(f"Blender Lab socket caller expected dict response, got {type(result)!r}")
        return result

    def _helpers(self) -> dict[str, Callable[..., Any]]:
        return {
            "format": self._toolcode_format_call or self._load_toolcode_helper("toolcode_format_call"),
            "load": self._toolcode_load_from_filepath or self._load_toolcode_helper("toolcode_load_from_filepath"),
            "wrap": self._toolcode_wrap_with_calling_convention
            or self._load_toolcode_helper("toolcode_wrap_with_calling_convention"),
        }

    def _load_toolcode_helper(self, name: str) -> Callable[..., Any]:
        module = _load_module_from_path(
            "_agent_runtime_blmcp_tools_helpers",
            self._blmcp_dir() / "tools_helpers" / "__init__.py",
        )
        return getattr(module, name)

    def _load_send_code_func(self) -> SendCodeFunc:
        module = _load_module_from_path(
            "_agent_runtime_blmcp_connection",
            self._blmcp_dir() / "tools_helpers" / "connection.py",
        )
        return getattr(module, "send_code")

    def _blmcp_dir(self) -> Path:
        path = self.root / "third_party" / "blender_lab_mcp" / "mcp" / "blmcp"
        if not path.is_dir():
            raise FileNotFoundError(f"Blender Lab MCP source not found: {path}")
        return path

    def _tools_dir(self) -> Path:
        path = self._blmcp_dir() / "tools"
        if not path.is_dir():
            raise FileNotFoundError(f"Blender Lab MCP tools directory not found: {path}")
        return path


def build_safe_blender_mcp_operation_plan(
    *,
    phase: WorkflowPhase,
    domain_tool_name: str,
    arguments: dict[str, Any] | None = None,
    blender_scene: BlenderSceneState | None = None,
) -> BlenderMCPDomainOperationPlan:
    """Map a V1 Blender domain tool into a constrained raw MCP call plan."""

    args = arguments or {}
    assert_tool_allowed(phase, domain_tool_name)
    if domain_tool_name == "get_blender_scene_summary":
        return BlenderMCPDomainOperationPlan(
            ok=True,
            domain_tool_name=domain_tool_name,
            phase=phase,
            raw_tool_name="get_objects_summary",
            arguments_summary={},
            safety_notes=["read_only_scene_summary"],
        )
    if domain_tool_name in {"move_subject", "place_subject"}:
        return _build_transform_plan(
            phase=phase,
            domain_tool_name=domain_tool_name,
            arguments=args,
            blender_scene=blender_scene,
            transform_field="location",
            code_template=_LOCATION_CODE,
        )
    if domain_tool_name == "rotate_subject":
        return _build_transform_plan(
            phase=phase,
            domain_tool_name=domain_tool_name,
            arguments=args,
            blender_scene=blender_scene,
            transform_field="rotation_euler",
            code_template=_ROTATION_CODE,
        )
    if domain_tool_name == "scale_subject":
        scale = _validate_vector(args.get("scale"), "scale")
        if scale is not None and any(value <= 0 for value in scale):
            return _invalid_plan(phase, domain_tool_name, "scale values must be positive")
        return _build_transform_plan(
            phase=phase,
            domain_tool_name=domain_tool_name,
            arguments=args,
            blender_scene=blender_scene,
            transform_field="scale",
            code_template=_SCALE_CODE,
        )
    if domain_tool_name in {"setup_camera", "update_camera"}:
        return _build_camera_plan(phase=phase, domain_tool_name=domain_tool_name, arguments=args)
    if domain_tool_name in {"setup_lighting", "update_lighting"}:
        return _build_light_plan(phase=phase, domain_tool_name=domain_tool_name, arguments=args)
    if domain_tool_name == "set_simple_material":
        return _build_material_plan(phase=phase, domain_tool_name=domain_tool_name, arguments=args, blender_scene=blender_scene)
    if domain_tool_name == "delete_subject":
        return _build_delete_plan(phase=phase, domain_tool_name=domain_tool_name, arguments=args, blender_scene=blender_scene)
    return _invalid_plan(phase, domain_tool_name, f"unsupported Blender MCP domain tool: {domain_tool_name}")


def sync_blender_scene_state_from_objects_summary(
    objects_summary: dict[str, Any],
    *,
    scene_id: str | None = None,
    blend_file_artifact_id: str | None = None,
    preview_image_id: str | None = None,
    scene_asset_id: str | None = None,
) -> BlenderSceneSyncResult:
    payload = _unwrap_mcp_result(objects_summary)
    if payload.get("status") != "ok":
        return BlenderSceneSyncResult(
            ok=False,
            issues=[payload.get("message") or "objects_summary_not_ok"],
        )

    objects = []
    seen_ids: set[str] = set()
    for item in _iter_collection_objects(payload.get("collections", [])):
        object_id = _unique_object_id(_safe_object_id(item.get("name") or "object"), seen_ids)
        objects.append(
            BlenderObjectRecord(
                object_id=object_id,
                blender_name=item.get("name") or object_id,
                object_type=_map_blender_object_type(item.get("type")),
                visible=bool(item.get("visible", True)) and not bool(item.get("hide_viewport", False)),
                semantic_role=_semantic_role_for_item(item),
                notes=_object_notes(item),
            )
        )

    blender_scene = BlenderSceneState(
        blender_scene_id=scene_id or payload.get("scene_name") or "blender_scene",
        blend_file_artifact_id=blend_file_artifact_id,
        preview_image_id=preview_image_id,
        objects=objects,
        scene_asset_id=scene_asset_id,
        last_synced_at=utc_now_iso(),
    )
    return BlenderSceneSyncResult(
        ok=True,
        blender_scene=blender_scene,
        scene_name=payload.get("scene_name"),
        active_object=payload.get("active_object"),
        object_mode=payload.get("object_mode"),
        object_count=len(objects),
        camera_object=payload.get("camera_object"),
        issues=[],
        )


_LOCATION_CODE = """
import bpy
obj = bpy.data.objects.get({object_name!r})
if obj is None:
    raise ValueError("object not found: {object_name}")
obj.location = ({x}, {y}, {z})
bpy.context.view_layer.update()
result = {{"ok": True, "object": obj.name, "location": [float(v) for v in obj.location]}}
""".strip()

_ROTATION_CODE = """
import bpy
obj = bpy.data.objects.get({object_name!r})
if obj is None:
    raise ValueError("object not found: {object_name}")
obj.rotation_mode = "XYZ"
obj.rotation_euler = ({x}, {y}, {z})
bpy.context.view_layer.update()
result = {{"ok": True, "object": obj.name, "rotation_euler": [float(v) for v in obj.rotation_euler]}}
""".strip()

_SCALE_CODE = """
import bpy
obj = bpy.data.objects.get({object_name!r})
if obj is None:
    raise ValueError("object not found: {object_name}")
obj.scale = ({x}, {y}, {z})
bpy.context.view_layer.update()
result = {{"ok": True, "object": obj.name, "scale": [float(v) for v in obj.scale]}}
""".strip()


def _build_transform_plan(
    *,
    phase: WorkflowPhase,
    domain_tool_name: str,
    arguments: dict[str, Any],
    blender_scene: BlenderSceneState | None,
    transform_field: str,
    code_template: str,
) -> BlenderMCPDomainOperationPlan:
    object_name, issue = _resolve_object_name(arguments, blender_scene)
    if issue:
        return _invalid_plan(phase, domain_tool_name, issue)
    vector = _validate_vector(arguments.get(transform_field), transform_field)
    if vector is None:
        return _invalid_plan(phase, domain_tool_name, f"{transform_field} must be a 3-number list or tuple")
    code = code_template.format(object_name=object_name, x=vector[0], y=vector[1], z=vector[2])
    return BlenderMCPDomainOperationPlan(
        ok=True,
        domain_tool_name=domain_tool_name,
        phase=phase,
        raw_tool_name="execute_blender_code",
        raw_tool_arguments={"code": code},
        arguments_summary={
            "blender_name": object_name,
            transform_field: vector,
        },
        safety_notes=[
            "object_resolved_from_blender_scene_state",
            "fixed_python_template",
            "view_layer_update_after_transform",
        ],
    )


def _build_camera_plan(
    *,
    phase: WorkflowPhase,
    domain_tool_name: str,
    arguments: dict[str, Any],
) -> BlenderMCPDomainOperationPlan:
    camera_name = arguments.get("camera_name") or "Camera"
    location = _validate_optional_vector(arguments.get("location"), "location")
    rotation = _validate_optional_vector(arguments.get("rotation_euler"), "rotation_euler")
    focal_length = arguments.get("focal_length")
    if location is None and arguments.get("location") is not None:
        return _invalid_plan(phase, domain_tool_name, "location must be a 3-number list or tuple")
    if rotation is None and arguments.get("rotation_euler") is not None:
        return _invalid_plan(phase, domain_tool_name, "rotation_euler must be a 3-number list or tuple")
    if focal_length is not None and (not isinstance(focal_length, (int, float)) or focal_length <= 0):
        return _invalid_plan(phase, domain_tool_name, "focal_length must be a positive number")
    code = _camera_code(camera_name=camera_name, location=location, rotation_euler=rotation, focal_length=focal_length)
    return BlenderMCPDomainOperationPlan(
        ok=True,
        domain_tool_name=domain_tool_name,
        phase=phase,
        raw_tool_name="execute_blender_code",
        raw_tool_arguments={"code": code},
        arguments_summary={
            "camera_name": camera_name,
            "location": location,
            "rotation_euler": rotation,
            "focal_length": focal_length,
        },
        safety_notes=["fixed_python_template", "updates_existing_or_creates_camera"],
    )


def _build_light_plan(
    *,
    phase: WorkflowPhase,
    domain_tool_name: str,
    arguments: dict[str, Any],
) -> BlenderMCPDomainOperationPlan:
    light_name = arguments.get("light_name") or "Key_Light"
    energy = arguments.get("energy", 500.0)
    color = _validate_optional_vector(arguments.get("color"), "color", length=3)
    if not isinstance(energy, (int, float)) or energy < 0:
        return _invalid_plan(phase, domain_tool_name, "energy must be a non-negative number")
    if color is None and arguments.get("color") is not None:
        return _invalid_plan(phase, domain_tool_name, "color must be a 3-number RGB list or tuple")
    location = _validate_optional_vector(arguments.get("location"), "location")
    if location is None and arguments.get("location") is not None:
        return _invalid_plan(phase, domain_tool_name, "location must be a 3-number list or tuple")
    code = _light_code(light_name=light_name, energy=float(energy), color=color, location=location)
    return BlenderMCPDomainOperationPlan(
        ok=True,
        domain_tool_name=domain_tool_name,
        phase=phase,
        raw_tool_name="execute_blender_code",
        raw_tool_arguments={"code": code},
        arguments_summary={"light_name": light_name, "energy": float(energy), "color": color, "location": location},
        safety_notes=["fixed_python_template", "updates_existing_or_creates_area_light"],
    )


def _build_material_plan(
    *,
    phase: WorkflowPhase,
    domain_tool_name: str,
    arguments: dict[str, Any],
    blender_scene: BlenderSceneState | None,
) -> BlenderMCPDomainOperationPlan:
    object_name, issue = _resolve_object_name(arguments, blender_scene)
    if issue:
        return _invalid_plan(phase, domain_tool_name, issue)
    color = _validate_optional_vector(arguments.get("base_color"), "base_color", length=4)
    if color is None:
        return _invalid_plan(phase, domain_tool_name, "base_color must be a 4-number RGBA list or tuple")
    if any(value < 0 or value > 1 for value in color):
        return _invalid_plan(phase, domain_tool_name, "base_color values must be between 0 and 1")
    material_name = arguments.get("material_name") or f"{object_name}_simple_material"
    code = _material_code(object_name=object_name, material_name=material_name, base_color=color)
    return BlenderMCPDomainOperationPlan(
        ok=True,
        domain_tool_name=domain_tool_name,
        phase=phase,
        raw_tool_name="execute_blender_code",
        raw_tool_arguments={"code": code},
        arguments_summary={"blender_name": object_name, "material_name": material_name, "base_color": color},
        safety_notes=["object_resolved_from_blender_scene_state", "fixed_python_template"],
    )


def _build_delete_plan(
    *,
    phase: WorkflowPhase,
    domain_tool_name: str,
    arguments: dict[str, Any],
    blender_scene: BlenderSceneState | None,
) -> BlenderMCPDomainOperationPlan:
    if arguments.get("confirm_delete") is not True:
        return BlenderMCPDomainOperationPlan(
            ok=False,
            domain_tool_name=domain_tool_name,
            phase=phase,
            requires_confirmation=True,
            issues=["delete_subject requires confirm_delete=true"],
            safety_notes=["destructive_operation_requires_explicit_confirmation"],
        )
    object_name, issue = _resolve_object_name(arguments, blender_scene)
    if issue:
        return _invalid_plan(phase, domain_tool_name, issue, requires_confirmation=True)
    code = """
import bpy
obj = bpy.data.objects.get({object_name!r})
if obj is None:
    raise ValueError("object not found: {object_name}")
bpy.data.objects.remove(obj, do_unlink=True)
bpy.context.view_layer.update()
result = {{"ok": True, "deleted_object": {object_name!r}}}
""".strip().format(object_name=object_name)
    return BlenderMCPDomainOperationPlan(
        ok=True,
        domain_tool_name=domain_tool_name,
        phase=phase,
        raw_tool_name="execute_blender_code",
        raw_tool_arguments={"code": code},
        arguments_summary={"blender_name": object_name},
        requires_confirmation=True,
        safety_notes=[
            "destructive_operation_confirmed",
            "object_resolved_from_blender_scene_state",
            "fixed_python_template",
        ],
    )


def _camera_code(
    *,
    camera_name: str,
    location: list[float] | None,
    rotation_euler: list[float] | None,
    focal_length: float | None,
) -> str:
    lines = [
        "import bpy",
        f"camera = bpy.data.objects.get({camera_name!r})",
        "if camera is None:",
        f"    data = bpy.data.cameras.new({camera_name!r})",
        f"    camera = bpy.data.objects.new({camera_name!r}, data)",
        "    bpy.context.scene.collection.objects.link(camera)",
        "if camera.type != 'CAMERA':",
        f"    raise ValueError('object is not a camera: {camera_name}')",
    ]
    if location is not None:
        lines.append(f"camera.location = ({location[0]}, {location[1]}, {location[2]})")
    if rotation_euler is not None:
        lines.append("camera.rotation_mode = 'XYZ'")
        lines.append(f"camera.rotation_euler = ({rotation_euler[0]}, {rotation_euler[1]}, {rotation_euler[2]})")
    if focal_length is not None:
        lines.append(f"camera.data.lens = {float(focal_length)}")
    lines.extend(
        [
            "bpy.context.scene.camera = camera",
            "bpy.context.view_layer.update()",
            "result = {'ok': True, 'camera': camera.name, 'location': [float(v) for v in camera.location], 'rotation_euler': [float(v) for v in camera.rotation_euler], 'focal_length': float(camera.data.lens)}",
        ]
    )
    return "\n".join(lines)


def _light_code(
    *,
    light_name: str,
    energy: float,
    color: list[float] | None,
    location: list[float] | None,
) -> str:
    lines = [
        "import bpy",
        f"light = bpy.data.objects.get({light_name!r})",
        "if light is None:",
        f"    data = bpy.data.lights.new({light_name!r}, type='AREA')",
        f"    light = bpy.data.objects.new({light_name!r}, data)",
        "    bpy.context.scene.collection.objects.link(light)",
        "if light.type != 'LIGHT':",
        f"    raise ValueError('object is not a light: {light_name}')",
        f"light.data.energy = {energy}",
    ]
    if color is not None:
        lines.append(f"light.data.color = ({color[0]}, {color[1]}, {color[2]})")
    if location is not None:
        lines.append(f"light.location = ({location[0]}, {location[1]}, {location[2]})")
    lines.extend(
        [
            "bpy.context.view_layer.update()",
            "result = {'ok': True, 'light': light.name, 'energy': float(light.data.energy), 'color': [float(v) for v in light.data.color]}",
        ]
    )
    return "\n".join(lines)


def _material_code(*, object_name: str, material_name: str, base_color: list[float]) -> str:
    return """
import bpy
obj = bpy.data.objects.get({object_name!r})
if obj is None:
    raise ValueError("object not found: {object_name}")
mat = bpy.data.materials.get({material_name!r}) or bpy.data.materials.new({material_name!r})
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf is not None:
    bsdf.inputs["Base Color"].default_value = ({r}, {g}, {b}, {a})
if obj.data and hasattr(obj.data, "materials"):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
bpy.context.view_layer.update()
result = {{"ok": True, "object": obj.name, "material": mat.name}}
""".strip().format(
        object_name=object_name,
        material_name=material_name,
        r=base_color[0],
        g=base_color[1],
        b=base_color[2],
        a=base_color[3],
    )


def _resolve_object_name(arguments: dict[str, Any], blender_scene: BlenderSceneState | None) -> tuple[str | None, str | None]:
    explicit_name = arguments.get("blender_name")
    object_id = arguments.get("blender_object_id") or arguments.get("object_id")
    subject_id = arguments.get("subject_id")
    if blender_scene is None:
        if explicit_name:
            return str(explicit_name), None
        return None, "blender_scene is required unless blender_name is provided"

    object_match = None
    name_match = None
    subject_match = None
    for item in blender_scene.objects:
        if object_id and (item.object_id == object_id or item.blender_name == object_id):
            object_match = item
        if explicit_name and item.blender_name == explicit_name:
            name_match = item
        if subject_id and item.subject_id == subject_id:
            subject_match = item

    resolved = object_match or name_match
    if resolved is not None:
        if subject_match is not None and subject_match.object_id != resolved.object_id:
            return None, (
                "object_id/blender_name and subject_id resolve to different Blender objects: "
                f"{resolved.object_id} != {subject_match.object_id}"
            )
        return resolved.blender_name, None

    if subject_match is not None:
        return subject_match.blender_name, None
    if object_id:
        if subject_id:
            return None, f"object_id/subject_id not found in BlenderSceneState: {object_id} / {subject_id}"
        return None, f"object_id not found in BlenderSceneState: {object_id}"
    if explicit_name:
        return None, f"blender_name not found in BlenderSceneState: {explicit_name}"
    if subject_id:
        return None, f"subject_id not found in BlenderSceneState: {subject_id}"
    return None, "blender_object_id/object_id, subject_id, or blender_name is required"


def _validate_optional_vector(value: Any, field_name: str, *, length: int = 3) -> list[float] | None:
    if value is None:
        return None
    return _validate_vector(value, field_name, length=length)


def _validate_vector(value: Any, field_name: str, *, length: int = 3) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        return None
    if not all(isinstance(item, (int, float)) for item in value):
        return None
    return [float(item) for item in value]


def _invalid_plan(
    phase: WorkflowPhase,
    domain_tool_name: str,
    issue: str,
    *,
    requires_confirmation: bool = False,
) -> BlenderMCPDomainOperationPlan:
    return BlenderMCPDomainOperationPlan(
        ok=False,
        domain_tool_name=domain_tool_name,
        phase=phase,
        requires_confirmation=requires_confirmation,
        issues=[issue],
    )


def _run_command(args: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


def _socket_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _unwrap_mcp_result(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") == "ok" and isinstance(payload.get("result"), dict):
        return payload["result"]
    return payload


def _iter_collection_objects(collections: list[dict[str, Any]]):
    for collection in collections:
        for item in collection.get("objects", []) or []:
            yield item
        yield from _iter_collection_objects(collection.get("children", []) or [])


def _safe_object_id(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")
    return token or "object"


def _unique_object_id(value: str, seen: set[str]) -> str:
    candidate = value
    counter = 2
    while candidate in seen:
        candidate = f"{value}_{counter}"
        counter += 1
    seen.add(candidate)
    return candidate


def _map_blender_object_type(raw_type: str | None) -> str:
    return {
        "CAMERA": "camera",
        "LIGHT": "light",
        "EMPTY": "helper",
        "MESH": "unknown",
    }.get((raw_type or "").upper(), "unknown")


def _semantic_role_for_item(item: dict[str, Any]) -> str | None:
    raw_type = (item.get("type") or "").upper()
    if raw_type == "CAMERA":
        return "camera"
    if raw_type == "LIGHT":
        return "light"
    if raw_type == "EMPTY":
        return "helper"
    return None


def _object_notes(item: dict[str, Any]) -> str | None:
    notes = []
    if item.get("parent"):
        notes.append(f"parent={item['parent']}")
    if item.get("data_name"):
        notes.append(f"data_name={item['data_name']}")
    if item.get("selected"):
        notes.append("selected=true")
    return "; ".join(notes) or None


def _parse_blender_version(output: str) -> str | None:
    for line in output.splitlines():
        if line.startswith("Blender "):
            return line.strip()
    return None


def _parse_mcp_list_names(output: str) -> list[str]:
    names = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Name "):
            continue
        names.append(stripped.split()[0])
    return names


def _tail_text(text: str, *, lines: int = 20) -> str:
    return "\n".join(text.splitlines()[-lines:])


def _load_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _temporary_env(values: dict[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
