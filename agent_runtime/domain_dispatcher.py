"""DOC-006 domain-tool dispatchers over existing local infrastructure.

Script-backed tools deliberately delegate execution to ToolExecutor so phase
guards, tool-call logging, stdout/stderr capture, and dry-run behavior stay in
one place. Service-backed tools wrap existing runtime adapters instead of
creating parallel service clients.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.artifacts import FileArtifactStore, utc_now_iso
from agent_runtime.blender_mcp import (
    build_safe_blender_mcp_operation_plan,
    sync_blender_scene_state_from_objects_summary,
)
from agent_runtime.domain_tools import assert_tool_allowed
from agent_runtime.mcp_client_manager import MCPClientManager
from agent_runtime.script_adapters import (
    build_compose_blender_scene_command,
    build_export_viewer_scene_command,
    build_render_glb_preview_command,
)
from agent_runtime.scene_assets import inspect_worldmirror_output, register_worldmirror_output
from agent_runtime.service_adapters import (
    Hunyuan3DServiceAdapter,
    WorldMirrorGenerationRequest,
    WorldMirrorServiceAdapter,
)
from agent_runtime.state import (
    AgentProjectState,
    ArtifactType,
    Asset3DRecord,
    BlenderSceneState,
    ToolCallRecord,
    ToolCallStatus,
    WorkflowError,
)
from agent_runtime.state_views import apply_state_updates
from agent_runtime.tool_executor import CommandExecutionOptions, ToolExecutor


class DomainToolDispatchResult(BaseModel):
    domain_tool_name: str
    ok: bool
    dry_run: bool
    tool_call_id: str
    tool_call_status: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    tool_call_record: ToolCallRecord


RawBlenderMCPToolCaller = Callable[[str, dict[str, Any]], dict[str, Any]]


class ScriptDomainToolDispatcher:
    """Dispatch supported domain tools to existing script adapters."""

    def __init__(
        self,
        *,
        state: AgentProjectState,
        root: str | Path,
        blender_path: str | Path | None = None,
    ) -> None:
        self.state = state
        self.root = Path(root).expanduser().resolve()
        self.blender_path = blender_path

    def dispatch(
        self,
        domain_tool_name: str,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None = None,
    ) -> DomainToolDispatchResult:
        if domain_tool_name == "import_scene_asset":
            return self._dispatch_import_scene_asset(arguments, options=options)
        if domain_tool_name == "export_viewer_scene":
            return self._dispatch_export_viewer_scene(arguments, options=options)
        if domain_tool_name == "render_preview":
            return self._dispatch_render_preview(arguments, options=options)
        raise NotImplementedError(f"domain tool is not script-backed yet: {domain_tool_name}")

    def _dispatch_import_scene_asset(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        args = _require_args(arguments, ["scene_glb", "asset_glb", "preview_png", "output_blend"])
        if arguments.get("assembly_plan_json"):
            args["assembly_plan_json"] = arguments["assembly_plan_json"]
        command = build_compose_blender_scene_command(
            self.root,
            args["scene_glb"],
            args["asset_glb"],
            args["preview_png"],
            args["output_blend"],
            assembly_plan_json=args.get("assembly_plan_json"),
            **self._blender_kwargs(),
        )
        record = ToolExecutor(self.state).run_command(
            "import_scene_asset",
            command,
            arguments=args,
            options=options,
        )
        return self._result(
            "import_scene_asset",
            record,
            args,
            outputs={
                "preview_png": str(Path(args["preview_png"]).expanduser().resolve()),
                "output_blend": str(Path(args["output_blend"]).expanduser().resolve()),
            },
            options=options,
        )

    def _dispatch_export_viewer_scene(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        args = _require_args(arguments, ["input_blend", "viewer_glb", "scene_state_json"])
        command = build_export_viewer_scene_command(
            self.root,
            args["input_blend"],
            args["viewer_glb"],
            args["scene_state_json"],
            **self._blender_kwargs(),
        )
        record = ToolExecutor(self.state).run_command(
            "export_viewer_scene",
            command,
            arguments=args,
            options=options,
        )
        return self._result(
            "export_viewer_scene",
            record,
            args,
            outputs={
                "viewer_glb": str(Path(args["viewer_glb"]).expanduser().resolve()),
                "scene_state_json": str(Path(args["scene_state_json"]).expanduser().resolve()),
            },
            options=options,
        )

    def _dispatch_render_preview(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        args = _require_args(arguments, ["input_glb", "preview_png", "preview_blend"])
        command = build_render_glb_preview_command(
            self.root,
            args["input_glb"],
            args["preview_png"],
            args["preview_blend"],
            **self._blender_kwargs(),
        )
        record = ToolExecutor(self.state).run_command(
            "render_preview",
            command,
            arguments=args,
            options=options,
        )
        return self._result(
            "render_preview",
            record,
            args,
            outputs={
                "preview_png": str(Path(args["preview_png"]).expanduser().resolve()),
                "preview_blend": str(Path(args["preview_blend"]).expanduser().resolve()),
            },
            options=options,
        )

    def _blender_kwargs(self) -> dict[str, str | Path]:
        if self.blender_path is None:
            return {}
        return {"blender_path": self.blender_path}

    @staticmethod
    def _result(
        domain_tool_name: str,
        record: ToolCallRecord,
        arguments: dict[str, Any],
        *,
        outputs: dict[str, Any],
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        return DomainToolDispatchResult(
            domain_tool_name=domain_tool_name,
            ok=record.status.value == "succeeded",
            dry_run=bool(options and options.dry_run),
            tool_call_id=record.tool_call_id,
            tool_call_status=record.status.value,
            arguments=arguments,
            outputs=outputs,
            tool_call_record=record,
        )


class BlenderMCPDomainToolDispatcher:
    """Dispatch safe Blender domain tools through an injected raw MCP caller."""

    def __init__(
        self,
        *,
        state: AgentProjectState,
        raw_tool_caller: RawBlenderMCPToolCaller,
        server_name: str = "blender_lab",
        ensure_blend_loaded: bool = False,
    ) -> None:
        self.state = state
        self.raw_tool_caller = raw_tool_caller
        self.server_name = server_name
        self.ensure_blend_loaded = ensure_blend_loaded

    @classmethod
    def from_mcp_client_manager(
        cls,
        *,
        state: AgentProjectState,
        manager: MCPClientManager,
        server_name: str = "blender_lab",
        ensure_blend_loaded: bool = False,
    ) -> "BlenderMCPDomainToolDispatcher":
        """Build a dispatcher from the shared MCP manager call boundary."""

        return cls(
            state=state,
            raw_tool_caller=manager.raw_tool_caller_for(server_name),
            server_name=server_name,
            ensure_blend_loaded=ensure_blend_loaded,
        )

    def dispatch(
        self,
        domain_tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        options: CommandExecutionOptions | None = None,
    ) -> DomainToolDispatchResult:
        assert_tool_allowed(self.state.phase, domain_tool_name)
        options = options or CommandExecutionOptions()
        arguments = arguments or {}
        plan = build_safe_blender_mcp_operation_plan(
            phase=self.state.phase,
            domain_tool_name=domain_tool_name,
            arguments=arguments,
            blender_scene=self.state.blender_scene,
        )
        if not plan.ok:
            outputs = {"planned": False, "issues": plan.issues, "requires_confirmation": plan.requires_confirmation}
            record = self._record_mcp_call(
                domain_tool_name=domain_tool_name,
                arguments=arguments,
                plan=plan,
                outputs=outputs,
                ok=False,
                dry_run=options.dry_run,
                error_code="BLENDER_MCP_PLAN_REJECTED",
                error_message="; ".join(plan.issues) or "Blender MCP operation plan rejected",
            )
            return self._result(domain_tool_name, record, arguments, outputs=outputs, dry_run=options.dry_run)

        if options.dry_run:
            outputs = {
                "planned": True,
                "raw_tool_name": plan.raw_tool_name,
                "arguments_summary": plan.arguments_summary,
                "safety_notes": plan.safety_notes,
                "requires_confirmation": plan.requires_confirmation,
            }
            record = self._record_mcp_call(
                domain_tool_name=domain_tool_name,
                arguments=arguments,
                plan=plan,
                outputs=outputs,
                ok=True,
                dry_run=True,
            )
            return self._result(domain_tool_name, record, arguments, outputs=outputs, dry_run=True)

        raw_calls = []
        if self.ensure_blend_loaded and plan.raw_tool_name != "get_objects_summary":
            blend_path = _blend_file_path_for_state(self.state)
            if blend_path is not None:
                load_arguments = {"code": _load_blend_python(blend_path)}
                load_raw = self.raw_tool_caller("execute_blender_code", load_arguments)
                raw_calls.append(
                    {
                        "kind": "blender_mcp",
                        "server": self.server_name,
                        "tool_name": "execute_blender_code",
                        "arguments": load_arguments,
                        "purpose": "load_blend_before_edit",
                    }
                )
                if not _raw_mcp_result_ok(load_raw):
                    outputs = {
                        "planned": True,
                        "raw_tool_name": plan.raw_tool_name,
                        "blend_load_raw_result": _summarize_raw_mcp_result(load_raw),
                        "arguments_summary": plan.arguments_summary,
                        "safety_notes": [*plan.safety_notes, "run_local_blend_load_failed"],
                    }
                    record = self._record_mcp_call(
                        domain_tool_name=domain_tool_name,
                        arguments=arguments,
                        plan=plan,
                        outputs=outputs,
                        ok=False,
                        dry_run=False,
                        raw_calls=raw_calls,
                        error_code="BLENDER_MCP_BLEND_LOAD_FAILED",
                        error_message=_raw_mcp_error_message(load_raw),
                    )
                    return self._result(domain_tool_name, record, arguments, outputs=outputs, dry_run=False)
                outputs_prefix = {"blend_load_raw_result": _summarize_raw_mcp_result(load_raw)}
            else:
                outputs_prefix = {"blend_load_skipped": "no_blend_file_artifact"}
        else:
            outputs_prefix = {}

        raw_result = self.raw_tool_caller(plan.raw_tool_name, plan.raw_tool_arguments)
        raw_ok = _raw_mcp_result_ok(raw_result)
        outputs = {
            "planned": True,
            "raw_tool_name": plan.raw_tool_name,
            "raw_result": _summarize_raw_mcp_result(raw_result),
            "arguments_summary": plan.arguments_summary,
            "safety_notes": plan.safety_notes,
            **outputs_prefix,
        }
        raw_calls.append(
            {
                "kind": "blender_mcp",
                "server": self.server_name,
                "tool_name": plan.raw_tool_name,
                "arguments": plan.raw_tool_arguments,
            }
        )
        ok = raw_ok
        error_code = None
        error_message = None
        if raw_ok:
            sync_result = None
            existing_scene = self.state.blender_scene
            sync_context = {
                "scene_id": existing_scene.blender_scene_id if existing_scene is not None else None,
                "blend_file_artifact_id": existing_scene.blend_file_artifact_id if existing_scene is not None else None,
                "preview_image_id": existing_scene.preview_image_id if existing_scene is not None else None,
                "scene_asset_id": existing_scene.scene_asset_id if existing_scene is not None else None,
            }
            if plan.raw_tool_name == "get_objects_summary":
                sync_result = sync_blender_scene_state_from_objects_summary(raw_result, **sync_context)
            else:
                sync_raw = self.raw_tool_caller("get_objects_summary", {})
                raw_calls.append(
                    {
                        "kind": "blender_mcp",
                        "server": self.server_name,
                        "tool_name": "get_objects_summary",
                        "arguments": {},
                    }
                )
                outputs["sync_raw_result"] = _summarize_raw_mcp_result(sync_raw)
                sync_result = sync_blender_scene_state_from_objects_summary(sync_raw, **sync_context)
            outputs["scene_sync"] = _model_to_dict(sync_result)
            if sync_result.ok and sync_result.blender_scene is not None:
                self.state = apply_state_updates(
                    self.state,
                    node_name="SceneStateSynchronizer",
                    updates={"blender_scene": sync_result.blender_scene},
                )
                self.state = _apply_planned_transform_to_state(
                    self.state,
                    domain_tool_name=domain_tool_name,
                    arguments=arguments,
                    arguments_summary=plan.arguments_summary,
                    previous_scene=existing_scene,
                )
                outputs["blender_scene_object_count"] = sync_result.object_count
                blend_path = _blend_file_path_for_state(self.state)
                if blend_path is not None:
                    save_code = _save_blend_python(blend_path)
                    save_raw = self.raw_tool_caller("execute_blender_code", {"code": save_code})
                    raw_calls.append(
                        {
                            "kind": "blender_mcp",
                            "server": self.server_name,
                            "tool_name": "execute_blender_code",
                            "arguments": {"code": save_code},
                            "purpose": "save_blend_after_edit",
                        }
                    )
                    outputs["save_raw_result"] = _summarize_raw_mcp_result(save_raw)
                    outputs["saved_blend_path"] = str(blend_path)
                    ok = ok and _raw_mcp_result_ok(save_raw)
            else:
                ok = False
                error_code = "BLENDER_MCP_SYNC_FAILED"
                error_message = "; ".join(sync_result.issues) or "Blender scene synchronization failed"
        else:
            error_code = "BLENDER_MCP_RAW_TOOL_FAILED"
            error_message = _raw_mcp_error_message(raw_result)

        record = self._record_mcp_call(
            domain_tool_name=domain_tool_name,
            arguments=arguments,
            plan=plan,
            outputs=outputs,
            ok=ok,
            dry_run=False,
            raw_calls=raw_calls,
            error_code=error_code,
            error_message=error_message,
        )
        return self._result(domain_tool_name, record, arguments, outputs=outputs, dry_run=False)

    def _record_mcp_call(
        self,
        *,
        domain_tool_name: str,
        arguments: dict[str, Any],
        plan,
        outputs: dict[str, Any],
        ok: bool,
        dry_run: bool,
        raw_calls: list[dict[str, Any]] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ToolCallRecord:
        ended_at = utc_now_iso()
        raw_calls = raw_calls or [
            {
                "kind": "blender_mcp",
                "server": self.server_name,
                "tool_name": plan.raw_tool_name,
                "arguments": plan.raw_tool_arguments,
                "planned_only": dry_run or not plan.ok,
            }
        ]
        record = ToolCallRecord(
            tool_call_id=f"tool_call_{uuid4().hex[:12]}",
            project_id=self.state.project_id,
            phase=self.state.phase,
            domain_tool_name=domain_tool_name,
            tool_name=plan.raw_tool_name or domain_tool_name,
            raw_tool_calls=raw_calls,
            arguments=arguments,
            arguments_summary=plan.arguments_summary,
            result_summary={"dry_run": dry_run, **outputs},
            status=ToolCallStatus.SUCCEEDED if ok else ToolCallStatus.FAILED,
            error=None if ok else {"code": error_code or "BLENDER_MCP_FAILED", "message": error_message},
            error_message=None if ok else error_message,
            started_at=ended_at,
            ended_at=ended_at,
            finished_at=ended_at,
        )
        if not ok:
            self.state.last_error = WorkflowError(
                error_id=f"error_{uuid4().hex[:12]}",
                phase=self.state.phase,
                message=error_message or "Blender MCP dispatch failed",
                node_name="BlenderCommandExecutor",
                code=error_code or "BLENDER_MCP_FAILED",
                recoverable=True,
                retriable=error_code != "BLENDER_MCP_PLAN_REJECTED",
                details={
                    "tool_call_id": record.tool_call_id,
                    "domain_tool_name": domain_tool_name,
                    "issues": plan.issues,
                },
                created_at=ended_at,
            )
        else:
            self.state.last_error = None
        self.state.tool_call_log.append(record)
        return record

    @staticmethod
    def _result(
        domain_tool_name: str,
        record: ToolCallRecord,
        arguments: dict[str, Any],
        *,
        outputs: dict[str, Any],
        dry_run: bool,
    ) -> DomainToolDispatchResult:
        return DomainToolDispatchResult(
            domain_tool_name=domain_tool_name,
            ok=record.status == ToolCallStatus.SUCCEEDED,
            dry_run=dry_run,
            tool_call_id=record.tool_call_id,
            tool_call_status=record.status.value,
            arguments=arguments,
            outputs=outputs,
            tool_call_record=record,
        )


def _apply_planned_transform_to_state(
    state: AgentProjectState,
    *,
    domain_tool_name: str,
    arguments: dict[str, Any],
    arguments_summary: dict[str, Any],
    previous_scene: BlenderSceneState | None = None,
) -> AgentProjectState:
    scene = state.blender_scene
    if scene is None:
        return state
    previous_by_name = {
        item.blender_name: item
        for item in (previous_scene.objects if previous_scene is not None else [])
    }
    field_by_tool = {
        "move_subject": "location",
        "rotate_subject": "rotation_euler",
        "scale_subject": "scale",
    }
    transform_field = field_by_tool.get(domain_tool_name)
    object_name = arguments_summary.get("blender_name")
    value = arguments_summary.get(transform_field) if transform_field else None
    if not transform_field or not object_name or not isinstance(value, list) or len(value) != 3:
        value = None
    updated_objects = []
    changed = False
    for item in scene.objects:
        updates: dict[str, Any] = {}
        previous = previous_by_name.get(item.blender_name)
        if previous is not None:
            for field_name in ("subject_id", "asset_id", "scene_asset_id", "semantic_role"):
                if getattr(item, field_name) is None and getattr(previous, field_name) is not None:
                    updates[field_name] = getattr(previous, field_name)
            if item.object_type == "unknown" and previous.object_type != "unknown":
                updates["object_type"] = previous.object_type
        if (
            item.blender_name == object_name
            and transform_field
            and isinstance(value, list)
            and len(value) == 3
        ):
            updates["transform"] = item.transform.model_copy(
                update={transform_field: tuple(float(component) for component in value)}
            )
            if arguments.get("subject_id") and item.subject_id is None and "subject_id" not in updates:
                updates["subject_id"] = str(arguments["subject_id"])
            if domain_tool_name in {"move_subject", "rotate_subject", "scale_subject"}:
                if item.object_type == "unknown" and "object_type" not in updates:
                    updates["object_type"] = "subject_asset"
                if item.semantic_role is None and "semantic_role" not in updates:
                    updates["semantic_role"] = "hero subject"
        if updates:
            updated_objects.append(item.model_copy(update=updates))
            changed = True
        else:
            updated_objects.append(item)
    if not changed:
        return state
    updated_scene = scene.model_copy(update={"objects": updated_objects})
    return apply_state_updates(
        state,
        node_name="SceneStateSynchronizer",
        updates={"blender_scene": updated_scene},
    )


def _require_args(arguments: dict[str, Any], required: list[str]) -> dict[str, Any]:
    missing = [name for name in required if name not in arguments or arguments[name] in (None, "")]
    if missing:
        raise ValueError(f"missing required domain tool arguments: {missing}")
    return {name: arguments[name] for name in required}


def _blend_file_path_for_state(state: AgentProjectState) -> Path | None:
    scene = state.blender_scene
    if scene is None or not scene.blend_file_artifact_id:
        return None
    for artifact in state.artifacts:
        if artifact.artifact_id != scene.blend_file_artifact_id:
            continue
        if artifact.artifact_type != ArtifactType.BLENDER_FILE:
            continue
        if not artifact.uri:
            return None
        return Path(artifact.uri).expanduser().resolve()
    return None


def _save_blend_python(path: Path) -> str:
    return (
        "import bpy\n"
        f"target_path = {str(path)!r}\n"
        "bpy.ops.wm.save_as_mainfile(filepath=target_path)\n"
        "result = {\"ok\": True, \"saved_to\": target_path, \"filepath\": bpy.data.filepath}\n"
    )


def _load_blend_python(path: Path) -> str:
    return (
        "import bpy\n"
        "import os\n"
        f"target_path = {str(path)!r}\n"
        "if not os.path.exists(target_path):\n"
        "    raise FileNotFoundError(target_path)\n"
        "if os.path.abspath(bpy.data.filepath or '') != os.path.abspath(target_path):\n"
        "    bpy.ops.wm.open_mainfile(filepath=target_path)\n"
        "result = {\"ok\": True, \"loaded_blend\": target_path, \"filepath\": bpy.data.filepath}\n"
    )


class Hunyuan3DDomainToolDispatcher:
    """Dispatch `build_subject_asset` to the existing Hunyuan3D FastAPI service."""

    def __init__(
        self,
        *,
        state: AgentProjectState,
        service_adapter: Hunyuan3DServiceAdapter | None = None,
        artifact_store: FileArtifactStore | None = None,
    ) -> None:
        self.state = state
        self.service_adapter = service_adapter or Hunyuan3DServiceAdapter()
        self.artifact_store = artifact_store

    def dispatch(
        self,
        domain_tool_name: str,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None = None,
    ) -> DomainToolDispatchResult:
        if domain_tool_name != "build_subject_asset":
            raise NotImplementedError(f"domain tool is not Hunyuan3D-backed: {domain_tool_name}")
        assert_tool_allowed(self.state.phase, domain_tool_name)
        operation = arguments.get("operation", "submit_async")
        if operation == "submit_async":
            return self._submit_async(arguments, options=options)
        if operation == "check_status":
            return self._check_status(arguments, options=options)
        if operation == "save_completed":
            return self._save_completed(arguments, options=options)
        raise ValueError(f"unsupported build_subject_asset operation: {operation}")

    def _submit_async(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        args = _require_args(arguments, ["subject_id", "source_image_id"])
        payload = self.service_adapter.build_payload(
            image_base64=arguments.get("image_base64"),
            image_path=arguments.get("image_path"),
            remove_background=arguments.get("remove_background", True),
            texture=arguments.get("texture", True),
            seed=arguments.get("seed", 1234),
            randomize_seed=arguments.get("randomize_seed", True),
            octree_resolution=arguments.get("octree_resolution", 768),
            num_inference_steps=arguments.get("num_inference_steps", 50),
            guidance_scale=arguments.get("guidance_scale", 5.0),
            num_chunks=arguments.get("num_chunks", 200000),
            face_count=arguments.get("face_count", 1000000),
        )
        payload_dict = _model_to_dict(payload)
        dry_run = bool(options and options.dry_run)
        if dry_run:
            outputs = {
                "operation": "submit_async",
                "submitted": False,
                "payload_fields": sorted(payload_dict),
            }
            record = self._record_service_call(
                operation="submit_async",
                arguments=arguments,
                outputs=outputs,
                ok=True,
                dry_run=True,
            )
            return self._result(record, arguments, outputs=outputs, dry_run=True)

        response = self.service_adapter.submit_async(payload)
        ok = bool(response.get("ok"))
        uid = response.get("uid")
        outputs = {"operation": "submit_async", "submitted": ok, "uid": uid, "response": response}
        if ok:
            self.state = apply_state_updates(
                self.state,
                node_name="SubjectAssetGenerationExecutor",
                updates={
                    "subject_assets": _upsert_subject_asset(
                        self.state.subject_assets,
                        Asset3DRecord(
                            asset_id=arguments.get("asset_id") or f"asset_{args['subject_id']}",
                            subject_id=args["subject_id"],
                            source_image_id=args["source_image_id"],
                            job_id=uid,
                            status="running",
                            generation_params=_redact_generation_payload(payload_dict),
                        ),
                    )
                },
            )
        record = self._record_service_call(
            operation="submit_async",
            arguments=arguments,
            outputs=outputs,
            ok=ok,
            dry_run=False,
        )
        return self._result(record, arguments, outputs=outputs, dry_run=False)

    def _check_status(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        args = _require_args(arguments, ["uid"])
        dry_run = bool(options and options.dry_run)
        if dry_run:
            outputs = {"operation": "check_status", "uid": args["uid"], "checked": False}
            record = self._record_service_call(
                operation="check_status",
                arguments=arguments,
                outputs=outputs,
                ok=True,
                dry_run=True,
            )
            return self._result(record, arguments, outputs=outputs, dry_run=True)

        status = self.service_adapter.task_status(args["uid"])
        ok = bool(status.get("ok"))
        outputs = {"operation": "check_status", "uid": args["uid"], "status": status}
        record = self._record_service_call(
            operation="check_status",
            arguments=arguments,
            outputs=outputs,
            ok=ok,
            dry_run=False,
        )
        return self._result(record, arguments, outputs=outputs, dry_run=False)

    def _save_completed(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        args = _require_args(arguments, ["subject_id", "source_image_id", "status_payload", "output_glb"])
        if self.artifact_store is None:
            raise ValueError("artifact_store is required for save_completed")
        dry_run = bool(options and options.dry_run)
        output_glb = Path(args["output_glb"]).expanduser().resolve()
        asset_id = arguments.get("asset_id") or f"asset_{args['subject_id']}"
        if dry_run:
            outputs = {
                "operation": "save_completed",
                "saved": False,
                "output_glb": str(output_glb),
                "asset_id": asset_id,
            }
            record = self._record_service_call(
                operation="save_completed",
                arguments=arguments,
                outputs=outputs,
                ok=True,
                dry_run=True,
            )
            return self._result(record, arguments, outputs=outputs, dry_run=True)

        saved_path = self.service_adapter.save_status_model(args["status_payload"], output_glb)
        artifact = self.artifact_store.register_file(
            saved_path,
            ArtifactType.SUBJECT_3D_ASSET,
            artifact_id=asset_id,
            semantic_role="hunyuan3d_subject_asset",
            metadata={
                "stage": "subject_asset_generation",
                "subject_id": args["subject_id"],
                "source_image_id": args["source_image_id"],
                "service": "hunyuan3d_2_1",
            },
        )
        self.state.artifacts.append(artifact)
        self.state = apply_state_updates(
            self.state,
            node_name="SubjectAssetGenerationExecutor",
            updates={
                "subject_assets": _upsert_subject_asset(
                    self.state.subject_assets,
                    Asset3DRecord(
                        asset_id=asset_id,
                        subject_id=args["subject_id"],
                        source_image_id=args["source_image_id"],
                        service="hunyuan3d_2_1",
                        job_id=arguments.get("uid"),
                        glb_uri=str(saved_path),
                        status="succeeded",
                        generation_params={"saved_from_status": True},
                    ),
                )
            },
        )
        outputs = {
            "operation": "save_completed",
            "saved": True,
            "output_glb": str(saved_path),
            "artifact_id": artifact.artifact_id,
            "asset_id": asset_id,
        }
        record = self._record_service_call(
            operation="save_completed",
            arguments=arguments,
            outputs=outputs,
            ok=True,
            dry_run=False,
        )
        return self._result(record, arguments, outputs=outputs, dry_run=False)

    def _record_service_call(
        self,
        *,
        operation: str,
        arguments: dict[str, Any],
        outputs: dict[str, Any],
        ok: bool,
        dry_run: bool,
    ) -> ToolCallRecord:
        ended_at = utc_now_iso()
        record = ToolCallRecord(
            tool_call_id=f"tool_call_{uuid4().hex[:12]}",
            project_id=self.state.project_id,
            phase=self.state.phase,
            domain_tool_name="build_subject_asset",
            tool_name="build_subject_asset",
            raw_tool_calls=[
                {
                    "kind": "service_adapter",
                    "service": "hunyuan3d_2_1",
                    "operation": operation,
                    "base_url": self.service_adapter.base_url,
                }
            ],
            arguments=_redact_generation_payload(arguments),
            arguments_summary=_redact_generation_payload(arguments),
            result_summary={"dry_run": dry_run, **_redact_outputs(outputs)},
            status=ToolCallStatus.SUCCEEDED if ok else ToolCallStatus.FAILED,
            error=None if ok else {"code": "SERVICE_CALL_FAILED", "message": f"{operation} failed"},
            error_message=None if ok else f"{operation} failed",
            started_at=ended_at,
            ended_at=ended_at,
            finished_at=ended_at,
        )
        self.state.tool_call_log.append(record)
        return record

    @staticmethod
    def _result(
        record: ToolCallRecord,
        arguments: dict[str, Any],
        *,
        outputs: dict[str, Any],
        dry_run: bool,
    ) -> DomainToolDispatchResult:
        return DomainToolDispatchResult(
            domain_tool_name="build_subject_asset",
            ok=record.status == ToolCallStatus.SUCCEEDED,
            dry_run=dry_run,
            tool_call_id=record.tool_call_id,
            tool_call_status=record.status.value,
            arguments=_redact_generation_payload(arguments),
            outputs=_redact_outputs(outputs),
            tool_call_record=record,
        )


class WorldMirrorDomainToolDispatcher:
    """Dispatch scene-asset tools to the existing HY-World/WorldMirror surface."""

    def __init__(
        self,
        *,
        state: AgentProjectState,
        service_adapter: WorldMirrorServiceAdapter | None = None,
        artifact_store: FileArtifactStore | None = None,
    ) -> None:
        self.state = state
        self.service_adapter = service_adapter or WorldMirrorServiceAdapter()
        self.artifact_store = artifact_store

    def dispatch(
        self,
        domain_tool_name: str,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None = None,
    ) -> DomainToolDispatchResult:
        if domain_tool_name not in {"build_scene_asset", "adapt_scene_asset"}:
            raise NotImplementedError(f"domain tool is not WorldMirror-backed: {domain_tool_name}")
        assert_tool_allowed(self.state.phase, domain_tool_name)
        operation = arguments.get("operation")
        if domain_tool_name == "build_scene_asset":
            operation = operation or "runtime_status"
            if operation == "runtime_status":
                return self._runtime_status(arguments, options=options)
            if operation == "prepare_generation":
                return self._prepare_generation(arguments, options=options)
            if operation == "upload_inputs":
                return self._upload_inputs(arguments, options=options)
            if operation == "poll_upload":
                return self._poll_upload(arguments, options=options)
            if operation == "submit_generation":
                return self._submit_generation(arguments, options=options)
            if operation == "poll_generation":
                return self._poll_generation(arguments, options=options)
        if domain_tool_name == "adapt_scene_asset":
            operation = operation or "register_existing_output"
            if operation == "inspect_output":
                return self._inspect_output(arguments, options=options)
            if operation == "register_existing_output":
                return self._register_existing_output(arguments, options=options)
        raise ValueError(f"unsupported {domain_tool_name} operation: {operation}")

    def _runtime_status(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        dry_run = bool(options and options.dry_run)
        if dry_run:
            outputs = {
                "operation": "runtime_status",
                "checked": False,
                "base_url": self.service_adapter.base_url,
            }
            record = self._record_service_call(
                domain_tool_name="build_scene_asset",
                operation="runtime_status",
                arguments=arguments,
                outputs=outputs,
                ok=True,
                dry_run=True,
            )
            return self._result("build_scene_asset", record, arguments, outputs=outputs, dry_run=True)

        status = self.service_adapter.runtime_status()
        ok = bool(status.get("ok"))
        outputs = {"operation": "runtime_status", "checked": True, "status": status}
        record = self._record_service_call(
            domain_tool_name="build_scene_asset",
            operation="runtime_status",
            arguments=arguments,
            outputs=outputs,
            ok=ok,
            dry_run=False,
        )
        return self._result("build_scene_asset", record, arguments, outputs=outputs, dry_run=False)

    def _prepare_generation(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        request = WorldMirrorGenerationRequest(
            input_files=[str(item) for item in arguments.get("input_files", [])],
            workspace_dir=arguments.get("workspace_dir"),
            time_interval=arguments.get("time_interval", 1.0),
            frame_selector=arguments.get("frame_selector", "All"),
            show_camera=arguments.get("show_camera", True),
            filter_sky_bg=arguments.get("filter_sky_bg", False),
            show_mesh=arguments.get("show_mesh", True),
            filter_ambiguous=arguments.get("filter_ambiguous", True),
        )
        plan = self.service_adapter.build_generation_call_plan(request)
        outputs = {
            "operation": "prepare_generation",
            "prepared": plan.ok,
            "submits_long_running_job": False,
            "call_plan": _model_to_dict(plan),
        }
        record = self._record_service_call(
            domain_tool_name="build_scene_asset",
            operation="prepare_generation",
            arguments=arguments,
            outputs=outputs,
            ok=plan.ok,
            dry_run=bool(options and options.dry_run),
        )
        return self._result(
            "build_scene_asset",
            record,
            arguments,
            outputs=outputs,
            dry_run=bool(options and options.dry_run),
        )

    def _upload_inputs(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        dry_run = bool(options and options.dry_run)
        request = WorldMirrorGenerationRequest(
            input_files=[str(item) for item in arguments.get("input_files", [])],
            workspace_dir=arguments.get("workspace_dir"),
            time_interval=arguments.get("time_interval", 1.0),
            frame_selector=arguments.get("frame_selector", "All"),
            show_camera=arguments.get("show_camera", True),
            filter_sky_bg=arguments.get("filter_sky_bg", False),
            show_mesh=arguments.get("show_mesh", True),
            filter_ambiguous=arguments.get("filter_ambiguous", True),
        )
        plan = self.service_adapter.build_generation_call_plan(request)
        confirm_upload = bool(arguments.get("confirm_upload"))
        if dry_run:
            outputs = {
                "operation": "upload_inputs",
                "submitted": False,
                "submits_long_running_job": False,
                "requires_confirmation": True,
                "call_plan": _model_to_dict(plan),
            }
            ok = plan.ok and plan.upload_payload is not None
        elif not confirm_upload:
            outputs = {
                "operation": "upload_inputs",
                "submitted": False,
                "submits_long_running_job": False,
                "requires_confirmation": True,
                "issues": ["worldmirror_upload_requires_explicit_confirmation"],
                "call_plan": _model_to_dict(plan),
            }
            ok = False
        else:
            submission = self.service_adapter.submit_upload(request)
            outputs = {
                "operation": "upload_inputs",
                "submitted": submission.ok,
                "submits_long_running_job": False,
                "requires_confirmation": True,
                "submission": _model_to_dict(submission),
            }
            ok = submission.ok
        record = self._record_service_call(
            domain_tool_name="build_scene_asset",
            operation="upload_inputs",
            arguments=arguments,
            outputs=outputs,
            ok=ok,
            dry_run=dry_run,
        )
        return self._result("build_scene_asset", record, arguments, outputs=outputs, dry_run=dry_run)

    def _poll_upload(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        dry_run = bool(options and options.dry_run)
        event_id = arguments.get("event_id")
        api_prefix = arguments.get("api_prefix") or "/gradio_api"
        confirm_poll = bool(arguments.get("confirm_poll"))
        if dry_run:
            outputs = {
                "operation": "poll_upload",
                "polled": False,
                "submits_long_running_job": False,
                "requires_confirmation": True,
                "api_name": "_on_upload",
                "event_id": event_id,
            }
            ok = bool(event_id)
        elif not confirm_poll:
            outputs = {
                "operation": "poll_upload",
                "polled": False,
                "submits_long_running_job": False,
                "requires_confirmation": True,
                "api_name": "_on_upload",
                "event_id": event_id,
                "issues": ["worldmirror_upload_poll_requires_explicit_confirmation"],
            }
            ok = False
        elif not event_id:
            outputs = {
                "operation": "poll_upload",
                "polled": False,
                "submits_long_running_job": False,
                "api_name": "_on_upload",
                "issues": ["event_id_required"],
            }
            ok = False
        else:
            upload_result = self.service_adapter.poll_upload(event_id=str(event_id), api_prefix=api_prefix)
            outputs = {
                "operation": "poll_upload",
                "polled": True,
                "submits_long_running_job": False,
                "api_name": "_on_upload",
                "event_id": event_id,
                "target_dir": upload_result.target_dir,
                "upload_result": _model_to_dict(upload_result),
            }
            ok = upload_result.ok
        record = self._record_service_call(
            domain_tool_name="build_scene_asset",
            operation="poll_upload",
            arguments=arguments,
            outputs=outputs,
            ok=ok,
            dry_run=dry_run,
        )
        return self._result("build_scene_asset", record, arguments, outputs=outputs, dry_run=dry_run)

    def _submit_generation(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        dry_run = bool(options and options.dry_run)
        request = WorldMirrorGenerationRequest(
            input_files=[str(item) for item in arguments.get("input_files", [])],
            workspace_dir=arguments.get("workspace_dir"),
            time_interval=arguments.get("time_interval", 1.0),
            frame_selector=arguments.get("frame_selector", "All"),
            show_camera=arguments.get("show_camera", True),
            filter_sky_bg=arguments.get("filter_sky_bg", False),
            show_mesh=arguments.get("show_mesh", True),
            filter_ambiguous=arguments.get("filter_ambiguous", True),
        )
        plan = self.service_adapter.build_generation_call_plan(request)
        confirm_submit = bool(arguments.get("confirm_submit"))
        if dry_run:
            outputs = {
                "operation": "submit_generation",
                "submitted": False,
                "submits_long_running_job": False,
                "requires_confirmation": True,
                "call_plan": _model_to_dict(plan),
            }
            ok = plan.ok
        elif not confirm_submit:
            outputs = {
                "operation": "submit_generation",
                "submitted": False,
                "submits_long_running_job": False,
                "requires_confirmation": True,
                "issues": ["worldmirror_submit_requires_explicit_confirmation"],
                "call_plan": _model_to_dict(plan),
            }
            ok = False
        else:
            submission = self.service_adapter.submit_generation(request)
            outputs = {
                "operation": "submit_generation",
                "submitted": submission.ok,
                "submits_long_running_job": True,
                "requires_confirmation": True,
                "submission": _model_to_dict(submission),
            }
            ok = submission.ok
        record = self._record_service_call(
            domain_tool_name="build_scene_asset",
            operation="submit_generation",
            arguments=arguments,
            outputs=outputs,
            ok=ok,
            dry_run=dry_run,
        )
        return self._result("build_scene_asset", record, arguments, outputs=outputs, dry_run=dry_run)

    def _poll_generation(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        dry_run = bool(options and options.dry_run)
        event_id = arguments.get("event_id")
        api_name = arguments.get("api_name") or "gradio_demo"
        api_prefix = arguments.get("api_prefix") or "/gradio_api"
        confirm_poll = bool(arguments.get("confirm_poll"))
        if dry_run:
            outputs = {
                "operation": "poll_generation",
                "polled": False,
                "submits_long_running_job": False,
                "requires_confirmation": True,
                "api_name": api_name,
                "event_id": event_id,
            }
            ok = bool(event_id)
        elif not confirm_poll:
            outputs = {
                "operation": "poll_generation",
                "polled": False,
                "submits_long_running_job": False,
                "requires_confirmation": True,
                "api_name": api_name,
                "event_id": event_id,
                "issues": ["worldmirror_poll_requires_explicit_confirmation"],
            }
            ok = False
        elif not event_id:
            outputs = {
                "operation": "poll_generation",
                "polled": False,
                "submits_long_running_job": False,
                "api_name": api_name,
                "issues": ["event_id_required"],
            }
            ok = False
        else:
            poll_result = self.service_adapter.poll_queued_call(
                api_name=api_name,
                event_id=str(event_id),
                api_prefix=api_prefix,
            )
            outputs = {
                "operation": "poll_generation",
                "polled": True,
                "submits_long_running_job": True,
                "api_name": api_name,
                "event_id": event_id,
                "poll_result": _model_to_dict(poll_result),
            }
            ok = poll_result.ok
        record = self._record_service_call(
            domain_tool_name="build_scene_asset",
            operation="poll_generation",
            arguments=arguments,
            outputs=outputs,
            ok=ok,
            dry_run=dry_run,
        )
        return self._result("build_scene_asset", record, arguments, outputs=outputs, dry_run=dry_run)

    def _inspect_output(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        args = _require_args(arguments, ["output_dir"])
        summary = inspect_worldmirror_output(args["output_dir"])
        outputs = {
            "operation": "inspect_output",
            "registered": False,
            "summary": _model_to_dict(summary),
        }
        ok = summary.status != "failed"
        record = self._record_service_call(
            domain_tool_name="adapt_scene_asset",
            operation="inspect_output",
            arguments=arguments,
            outputs=outputs,
            ok=ok,
            dry_run=bool(options and options.dry_run),
        )
        return self._result(
            "adapt_scene_asset",
            record,
            arguments,
            outputs=outputs,
            dry_run=bool(options and options.dry_run),
        )

    def _register_existing_output(
        self,
        arguments: dict[str, Any],
        *,
        options: CommandExecutionOptions | None,
    ) -> DomainToolDispatchResult:
        args = _require_args(arguments, ["output_dir", "scene_asset_id"])
        dry_run = bool(options and options.dry_run)
        if dry_run:
            summary = inspect_worldmirror_output(args["output_dir"])
            outputs = {
                "operation": "register_existing_output",
                "registered": False,
                "summary": _model_to_dict(summary),
            }
            record = self._record_service_call(
                domain_tool_name="adapt_scene_asset",
                operation="register_existing_output",
                arguments=arguments,
                outputs=outputs,
                ok=summary.status != "failed",
                dry_run=True,
            )
            return self._result("adapt_scene_asset", record, arguments, outputs=outputs, dry_run=True)
        if self.artifact_store is None:
            raise ValueError("artifact_store is required for register_existing_output")

        summary, self.state = register_worldmirror_output(
            state=self.state,
            artifact_store=self.artifact_store,
            output_dir=args["output_dir"],
            scene_asset_id=args["scene_asset_id"],
            source_scene_concept_image_ids=arguments.get("source_scene_concept_image_ids"),
            source_prompt=arguments.get("source_prompt"),
        )
        outputs = {
            "operation": "register_existing_output",
            "registered": summary.status != "failed",
            "scene_asset_id": args["scene_asset_id"],
            "summary": _model_to_dict(summary),
            "artifact_ids": [artifact.artifact_id for artifact in self.state.artifacts],
        }
        record = self._record_service_call(
            domain_tool_name="adapt_scene_asset",
            operation="register_existing_output",
            arguments=arguments,
            outputs=outputs,
            ok=summary.status != "failed",
            dry_run=False,
        )
        return self._result("adapt_scene_asset", record, arguments, outputs=outputs, dry_run=False)

    def _record_service_call(
        self,
        *,
        domain_tool_name: str,
        operation: str,
        arguments: dict[str, Any],
        outputs: dict[str, Any],
        ok: bool,
        dry_run: bool,
    ) -> ToolCallRecord:
        ended_at = utc_now_iso()
        record = ToolCallRecord(
            tool_call_id=f"tool_call_{uuid4().hex[:12]}",
            project_id=self.state.project_id,
            phase=self.state.phase,
            domain_tool_name=domain_tool_name,
            tool_name=domain_tool_name,
            raw_tool_calls=[
                {
                    "kind": "service_adapter",
                    "service": "hy_world",
                    "operation": operation,
                    "base_url": self.service_adapter.base_url,
                }
            ],
            arguments=_redact_generation_payload(arguments),
            arguments_summary=_redact_generation_payload(arguments),
            result_summary={"dry_run": dry_run, **_redact_outputs(outputs)},
            status=ToolCallStatus.SUCCEEDED if ok else ToolCallStatus.FAILED,
            error=None if ok else {"code": "SERVICE_CALL_FAILED", "message": f"{operation} failed"},
            error_message=None if ok else f"{operation} failed",
            started_at=ended_at,
            ended_at=ended_at,
            finished_at=ended_at,
        )
        self.state.tool_call_log.append(record)
        return record

    @staticmethod
    def _result(
        domain_tool_name: str,
        record: ToolCallRecord,
        arguments: dict[str, Any],
        *,
        outputs: dict[str, Any],
        dry_run: bool,
    ) -> DomainToolDispatchResult:
        return DomainToolDispatchResult(
            domain_tool_name=domain_tool_name,
            ok=record.status == ToolCallStatus.SUCCEEDED,
            dry_run=dry_run,
            tool_call_id=record.tool_call_id,
            tool_call_status=record.status.value,
            arguments=_redact_generation_payload(arguments),
            outputs=_redact_outputs(outputs),
            tool_call_record=record,
        )


def _upsert_subject_asset(existing: list[Asset3DRecord], asset: Asset3DRecord) -> list[Asset3DRecord]:
    updated = []
    replaced = False
    for item in existing:
        if item.asset_id == asset.asset_id:
            updated.append(asset)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(asset)
    return updated


def _redact_generation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"image", "image_base64", "model_base64"} and isinstance(value, str):
            redacted[key] = f"<base64:{len(value)} chars>"
        elif key == "status_payload" and isinstance(value, dict):
            redacted[key] = _redact_status_payload(value)
        elif isinstance(value, Path):
            redacted[key] = str(value.expanduser().resolve())
        else:
            redacted[key] = value
    return redacted


def _redact_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    copied = dict(payload)
    raw = copied.get("raw")
    if isinstance(raw, dict):
        raw = dict(raw)
        data = raw.get("data")
        if isinstance(data, dict):
            data = dict(data)
            model_base64 = data.get("model_base64")
            if isinstance(model_base64, str):
                data["model_base64"] = f"<base64:{len(model_base64)} chars>"
            raw["data"] = data
        copied["raw"] = raw
    return copied


def _redact_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    redacted = _redact_generation_payload(outputs)
    status = redacted.get("status")
    if isinstance(status, dict):
        redacted["status"] = _redact_status_payload(status)
    return redacted


def _raw_mcp_result_ok(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("status") == "error":
        return False
    nested = result.get("result")
    if isinstance(nested, dict) and nested.get("status") == "error":
        return False
    if result.get("status") == "ok":
        return True
    if isinstance(nested, dict) and nested.get("ok") is False:
        return False
    return bool(result.get("ok", True))


def _raw_mcp_error_message(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return "Blender MCP raw tool returned a non-dict result"
    nested = result.get("result")
    if isinstance(nested, dict) and nested.get("message"):
        return str(nested["message"])
    if result.get("message"):
        return str(result["message"])
    return "Blender MCP raw tool failed"


def _summarize_raw_mcp_result(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"type": type(result).__name__}
    summary: dict[str, Any] = {"status": result.get("status")}
    nested = result.get("result")
    if isinstance(nested, dict):
        summary["result_status"] = nested.get("status")
        for key in ("ok", "scene_name", "object_mode", "active_object", "camera_object", "message"):
            if key in nested:
                summary[key] = nested[key]
        collections = nested.get("collections")
        if isinstance(collections, list):
            summary["collection_count"] = len(collections)
            summary["object_count"] = sum(len(collection.get("objects", []) or []) for collection in collections)
    else:
        for key in ("ok", "message"):
            if key in result:
                summary[key] = result[key]
    return {key: value for key, value in summary.items() if value is not None}


def _model_to_dict(model) -> dict:
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
