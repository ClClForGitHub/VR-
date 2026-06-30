"""Small workflow runners that compose existing V1 infrastructure.

The runner in this module intentionally reuses script adapters, ToolExecutor,
ArtifactStore, state views, and the existing GLB viewer checker. It is not a
second implementation of Blender composition, viewer export, or rendering.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_runtime.asset_quality import (
    apply_subject_asset_repair_decision,
    evaluate_subject_asset,
    plan_subject_asset_repair,
    quality_result_from_asset,
)
from agent_runtime.artifacts import FileArtifactStore, utc_now_iso
from agent_runtime.blender_assembly_planner import build_compose_scene_plan
from agent_runtime.blender_mcp import BlenderLabSocketRawToolCaller
from agent_runtime.codex_self_mcp import (
    ApprovalPolicy,
    CodexSelfMCPAdapter,
    CodexSelfMCPCallPlan,
    SandboxMode,
)
from agent_runtime.concept_regeneration import apply_review_patch_concept_regeneration
from agent_runtime.delivery_handoff import build_delivery_handoff
from agent_runtime.delivery_package import build_delivery_package
from agent_runtime.domain_dispatcher import (
    BlenderMCPDomainToolDispatcher,
    Hunyuan3DDomainToolDispatcher,
    RawBlenderMCPToolCaller,
    ScriptDomainToolDispatcher,
    WorldMirrorDomainToolDispatcher,
)
from agent_runtime.domain_tools import allowed_tool_names
from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.llm_providers import build_provider_configs, load_agent_llm_env
from agent_runtime.mcp_client_manager import build_default_mcp_client_manager
from agent_runtime.persistence import FileStateCheckpointStore
from agent_runtime.review_patches import create_review_patch_from_pending_action
from agent_runtime.runtime_profiles import resolve_hunyuan3d_generation_kwargs
from agent_runtime.service_adapters import Hunyuan3DServiceAdapter, WorldMirrorServiceAdapter
from agent_runtime.smoke import patch_scene_state_artifact_ids
from agent_runtime.state import (
    AgentProjectState,
    ArtifactType,
    Asset3DRecord,
    BlenderSceneState,
    ConceptBundle,
    ConceptPromptPack,
    PendingAction,
    Scene3DRecord,
    SceneSpec,
    ViewerSceneState,
    WorkflowPhase,
)
from agent_runtime.state_views import (
    MissingStateContextError,
    apply_state_updates,
    build_blender_assembly_planner_context,
)
from agent_runtime.tool_executor import CommandExecutionOptions
from agent_runtime.viewer_runtime import ViewerRuntimeAdapter, annotate_state_artifact_with_viewer
from agent_runtime.visual_qa import SubjectAssetVisualQARequest, run_subject_asset_visual_qa


WORKFLOW_STAGE_ORDER = ("compose", "export_viewer", "viewer_check")
SUBJECT_ASSET_STAGE_ORDER = (
    "submit",
    "check_status",
    "save_completed",
    "quality_check",
    "repair_decision",
    "repair_execute",
)
SCENE_ASSET_STAGE_ORDER = (
    "runtime_status",
    "prepare_generation",
    "upload_inputs",
    "poll_upload",
    "submit_generation",
    "poll_generation",
    "inspect_output",
    "save_generation",
    "register_existing_output",
)
CODEX_SELF_MCP_STAGE_ORDER = ("status", "plan_handoff", "execute_handoff")
REVIEW_PATCH_STAGE_ORDER = ("review_patch",)
CONCEPT_SEED_STAGE_ORDER = ("seed_concept",)
CONCEPT_REGENERATION_STAGE_ORDER = ("apply_review_patch",)


class _WorkflowCheckpointRecorder:
    def __init__(self, output_path: Path) -> None:
        self.store = FileStateCheckpointStore(output_path / "checkpoints")
        self.last_checkpoint_id: str | None = None
        self.stage_records: list[dict] = []

    def record_stage(
        self,
        state: AgentProjectState,
        *,
        workflow: str,
        stage: str,
        ok: bool,
        node_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        record = self.store.save_checkpoint(
            state,
            reason=_stage_checkpoint_reason(stage, ok=ok),
            node_name=node_name,
            parent_checkpoint_id=self.last_checkpoint_id,
            metadata={
                "checkpoint_kind": "stage",
                "workflow": workflow,
                "stage": stage,
                "ok": ok,
                **(metadata or {}),
            },
        )
        self.last_checkpoint_id = record.checkpoint_id
        payload = model_to_dict(record)
        self.stage_records.append(payload)
        return payload

    def record_final(self, state: AgentProjectState, *, output_path: Path) -> dict:
        record = self.store.save_checkpoint(
            state,
            reason="workflow_output",
            node_name="workflow_runner",
            parent_checkpoint_id=self.last_checkpoint_id,
            metadata={
                "checkpoint_kind": "final",
                "summary_json": str(output_path / "summary.json"),
                "state_json": str(output_path / "state.json"),
                "tool_call_log_json": str(output_path / "tool_call_log.json"),
            },
        )
        self.last_checkpoint_id = record.checkpoint_id
        return model_to_dict(record)


def model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _load_scene_spec_json(path: Path) -> SceneSpec:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("scene_spec"), dict):
        payload = payload["scene_spec"]
    return SceneSpec(**payload)


def _first_scene_subject_id(scene_spec: SceneSpec | None) -> str | None:
    if scene_spec is None or not scene_spec.subjects:
        return None
    return scene_spec.subjects[0].subject_id


def run_local_e2e_workflow(
    *,
    root: str | Path,
    scene_glb: str | Path,
    asset_glb: str | Path,
    output_dir: str | Path,
    blender_path: str | Path | None = None,
    viewer_base_url: str = "http://127.0.0.1:8092",
    compose_timeout_seconds: float = 300,
    export_timeout_seconds: float = 180,
    viewer_timeout_seconds: float = 10,
    dry_run: bool = False,
    reset_metadata: bool = True,
    stages: str | list[str] | tuple[str, ...] | None = None,
    scene_spec_json: str | Path | None = None,
) -> dict:
    """Run an existing scene GLB + subject GLB through one project state.

    Stages:
    1. register input artifacts;
    2. compose existing scene and subject GLBs through the existing Blender
       composition script;
    3. export `viewer_scene.glb` and `scene_state.json` through the existing
       viewer export script;
    4. optionally HEAD-check the existing GLB viewer runtime.
    """

    requested_stages = _normalize_stages(stages)
    root_path = Path(root).expanduser().resolve()
    scene_path = Path(scene_glb).expanduser().resolve()
    asset_path = Path(asset_glb).expanduser().resolve()
    scene_spec_path = Path(scene_spec_json).expanduser().resolve() if scene_spec_json else None
    scene_spec = _load_scene_spec_json(scene_spec_path) if scene_spec_path is not None else None
    output_path = Path(output_dir).expanduser().resolve()
    compose_dir = output_path / "compose"
    viewer_dir = output_path / "viewer_export"
    output_path.mkdir(parents=True, exist_ok=True)
    compose_dir.mkdir(parents=True, exist_ok=True)
    viewer_dir.mkdir(parents=True, exist_ok=True)

    if reset_metadata:
        _reset_known_outputs(output_path)

    checkpoint_recorder = _WorkflowCheckpointRecorder(output_path)
    artifact_store = FileArtifactStore(output_path / "artifacts")
    state = AgentProjectState(
        project_id="v1_local_e2e_workflow",
        thread_id="local_workflow",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=scene_spec,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    scene_artifact = artifact_store.register_file(
        scene_path,
        ArtifactType.SCENE_3D_ASSET,
        artifact_id="workflow_scene_glb",
        semantic_role="source_scene_glb",
        metadata={"stage": "input"},
    )
    subject_artifact = artifact_store.register_file(
        asset_path,
        ArtifactType.SUBJECT_3D_ASSET,
        artifact_id="workflow_subject_glb",
        semantic_role="source_subject_glb",
        metadata={"stage": "input"},
    )
    state.artifacts.extend([scene_artifact, subject_artifact])
    subject_id = _first_scene_subject_id(scene_spec) or "subject_001"
    state.subject_assets.append(
        Asset3DRecord(
            asset_id=subject_artifact.artifact_id,
            subject_id=subject_id,
            source_image_id="workflow_subject_source",
            service="existing_asset",
            glb_uri=subject_artifact.uri,
            status="succeeded",
            generation_params={"stage": "input", "source": "local_e2e_existing_glb"},
        )
    )
    state.scene_asset = Scene3DRecord(
        scene_asset_id=scene_artifact.artifact_id,
        service="proxy_blender_scene",
        raw_output_type="mesh",
        raw_artifact_ids=[scene_artifact.artifact_id],
        adapted_artifact_ids=[scene_artifact.artifact_id],
        blender_import_mode="mesh_import",
        status="adapted",
        adapter_notes="Registered from local-e2e existing scene GLB.",
        generation_params={"stage": "input", "source": "local_e2e_existing_glb"},
    )

    viewer_adapter = ViewerRuntimeAdapter(base_url=viewer_base_url, timeout=viewer_timeout_seconds)

    compose_summary, state = _run_compose_stage(
        state=state,
        artifact_store=artifact_store,
        root_path=root_path,
        scene_path=scene_path,
        asset_path=asset_path,
        compose_dir=compose_dir,
        blender_path=blender_path,
        timeout_seconds=compose_timeout_seconds,
        dry_run=dry_run,
    )
    state.updated_at = utc_now_iso()
    checkpoint_recorder.record_stage(
        state,
        workflow="local-e2e",
        stage="compose",
        ok=bool(compose_summary.get("ok")),
        node_name="workflow_runner.compose",
        metadata={
            "dry_run": dry_run,
            "requested_stages": list(requested_stages),
            "output_blend_exists": compose_summary.get("output_blend_exists"),
            "preview_png_exists": compose_summary.get("preview_png_exists"),
            "assembly_plan_id": compose_summary.get("assembly_plan", {}).get("plan_id"),
            "assembly_plan_json": compose_summary.get("assembly_plan_json"),
        },
    )

    export_summary = None
    viewer_check = None
    context_views: dict[str, dict | None] = {
        "compose": compose_summary.get("context_view_input"),
        "export_viewer": None,
        "viewer_check": None,
    }
    executed_stages = ["compose"]
    skipped_stages: dict[str, str] = {}

    if "export_viewer" in requested_stages and compose_summary["ok"] and not dry_run:
        export_summary, state = _run_export_viewer_stage(
            state=state,
            artifact_store=artifact_store,
            root_path=root_path,
            input_blend=compose_dir / "composed_scene.blend",
            viewer_dir=viewer_dir,
            blender_path=blender_path,
            timeout_seconds=export_timeout_seconds,
            viewer_adapter=viewer_adapter,
        )
        context_views["export_viewer"] = export_summary.get("context_view_input")
        executed_stages.append("export_viewer")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="local-e2e",
            stage="export_viewer",
            ok=bool(export_summary.get("ok")),
            node_name="workflow_runner.export_viewer",
            metadata={
                "viewer_glb_exists": export_summary.get("viewer_glb_exists"),
                "scene_state_json_exists": export_summary.get("scene_state_json_exists"),
                "viewer_scene_object_count": export_summary.get("viewer_scene_object_count"),
            },
        )
        if "viewer_check" in requested_stages and export_summary["ok"] and export_summary["viewer_glb_exists"]:
            viewer_context = _state_context_view_report(
                state=state,
                stage="viewer_check",
                view="ViewerRuntimeCheckStateInput",
                phase=state.phase,
                required_state_fields=("viewer_scene",),
                extra_summary={"viewer_glb": str(viewer_dir / "viewer_scene.glb")},
            )
            viewer_runtime = viewer_adapter.runtime_status()
            viewer_check = viewer_adapter.check_model(viewer_dir / "viewer_scene.glb")
            viewer_check["runtime"] = viewer_runtime
            viewer_check["ok"] = bool(viewer_check["ok"] and viewer_runtime["ok"])
            viewer_check["context_view_input"] = viewer_context
            context_views["viewer_check"] = viewer_context
            state.artifacts = annotate_state_artifact_with_viewer(
                state.artifacts,
                artifact_id="workflow_viewer_scene_glb",
                adapter=viewer_adapter,
                runtime_status=viewer_runtime,
                model_check=viewer_check,
            )
            executed_stages.append("viewer_check")
            state.updated_at = utc_now_iso()
            checkpoint_recorder.record_stage(
                state,
                workflow="local-e2e",
                stage="viewer_check",
                ok=bool(viewer_check.get("ok")),
                node_name="workflow_runner.viewer_check",
                metadata={
                    "viewer_glb": str(viewer_dir / "viewer_scene.glb"),
                    "runtime_ok": viewer_check.get("runtime", {}).get("ok")
                    if isinstance(viewer_check.get("runtime"), dict)
                    else None,
                },
            )
        elif "viewer_check" in requested_stages:
            skipped_stages["viewer_check"] = "export_viewer_failed_or_missing_viewer_glb"
    elif "export_viewer" in requested_stages:
        skipped_stages["export_viewer"] = "dry_run" if dry_run else "compose_failed"
        if "viewer_check" in requested_stages:
            skipped_stages["viewer_check"] = "export_viewer_skipped"

    for stage in WORKFLOW_STAGE_ORDER:
        if stage not in requested_stages and stage != "compose":
            skipped_stages[stage] = "not_requested"

    ok = compose_summary["ok"]
    if not dry_run and "export_viewer" in requested_stages:
        ok = ok and bool(export_summary and export_summary["ok"])
    if not dry_run and "viewer_check" in requested_stages:
        ok = ok and bool(viewer_check and viewer_check["ok"])

    state.updated_at = utc_now_iso()
    delivery_handoff = model_to_dict(build_delivery_handoff(state))
    summary = {
        "ok": ok,
        "dry_run": dry_run,
        "root": str(root_path),
        "scene_glb": str(scene_path),
        "asset_glb": str(asset_path),
        "scene_spec_json": str(scene_spec_path) if scene_spec_path is not None else None,
        "scene_spec_id": scene_spec.scene_id if scene_spec is not None else None,
        "output_dir": str(output_path),
        "compose_dir": str(compose_dir),
        "viewer_export_dir": str(viewer_dir),
        "requested_stages": list(requested_stages),
        "executed_stages": executed_stages,
        "skipped_stages": skipped_stages,
        "single_project_state": True,
        "phase": state.phase.value,
        "artifact_ids": sorted(state.artifact_ids()),
        "tool_call_count": len(state.tool_call_log),
        "context_views": context_views,
        "compose": compose_summary,
        "export_viewer": export_summary,
        "viewer_check": viewer_check,
        "delivery_handoff": delivery_handoff,
        "state_json": str(output_path / "state.json"),
        "tool_call_log_json": str(output_path / "tool_call_log.json"),
        "delivery_handoff_json": str(output_path / "delivery_handoff.json"),
    }
    _write_workflow_outputs(output_path, state, summary, checkpoint_recorder=checkpoint_recorder)
    return summary


def run_subject_asset_workflow(
    *,
    output_dir: str | Path,
    subject_id: str,
    source_image_id: str,
    image_path: str | Path | None = None,
    image_base64: str | None = None,
    asset_id: str | None = None,
    job_id: str | None = None,
    output_glb: str | Path | None = None,
    status_payload: dict | None = None,
    hunyuan_base_url: str = "http://127.0.0.1:8091",
    service_adapter: Hunyuan3DServiceAdapter | None = None,
    timeout_seconds: float = 10,
    dry_run: bool = False,
    reset_metadata: bool = True,
    stages: str | list[str] | tuple[str, ...] | None = None,
    hunyuan_profile_id: str | None = None,
    remove_background: bool | None = None,
    texture: bool | None = None,
    seed: int | None = None,
    randomize_seed: bool | None = None,
    octree_resolution: int | None = None,
    num_inference_steps: int | None = None,
    guidance_scale: float | None = None,
    num_chunks: int | None = None,
    face_count: int | None = None,
    qa_render_preview: bool = False,
    qa_root: str | Path | None = None,
    qa_blender_path: str | Path | None = None,
    qa_timeout_seconds: float = 180,
    qa_visual_dry_run: bool = False,
    qa_visual_live: bool = False,
    llm_env_file: str | Path | None = "/home/team/zouzhiyuan/image23D_Agent/.env.agent_llm.local",
    qa_retry_count: int = 0,
    qa_max_hunyuan_retries: int = 1,
    qa_concept_regen_count: int = 0,
    qa_max_concept_regens: int = 1,
    qa_user_requested_review: bool = False,
    confirm_repair_execute: bool = False,
) -> dict:
    """Run explicit Hunyuan3D subject-asset stages through one project state.

    The runner reuses Hunyuan3DDomainToolDispatcher and FileArtifactStore. It
    does not poll indefinitely or hide long-running generation behind the CLI:
    callers choose submit/status/save stages explicitly.
    """

    requested_stages = _normalize_subject_asset_stages(stages)
    generation_kwargs = resolve_hunyuan3d_generation_kwargs(
        hunyuan_profile_id,
        remove_background=remove_background,
        texture=texture,
        seed=seed,
        randomize_seed=randomize_seed,
        octree_resolution=octree_resolution,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        num_chunks=num_chunks,
        face_count=face_count,
    )
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    resolved_asset_id = asset_id or f"asset_{subject_id}"
    explicit_output_glb = output_glb is not None
    output_glb_path = (
        Path(output_glb).expanduser().resolve()
        if explicit_output_glb
        else output_path / "subject_assets" / f"{resolved_asset_id}.glb"
    )

    if reset_metadata:
        _reset_subject_asset_outputs(output_path, output_glb_path, reset_output_glb=not explicit_output_glb)

    checkpoint_recorder = _WorkflowCheckpointRecorder(output_path)
    artifact_store = FileArtifactStore(output_path / "artifacts")
    state = AgentProjectState(
        project_id="v1_subject_asset_workflow",
        thread_id="local_subject_asset_workflow",
        phase=WorkflowPhase.SUBJECT_ASSET_GENERATION,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    input_image_artifact_id = None
    image_path_value = Path(image_path).expanduser().resolve() if image_path is not None else None
    if image_path_value is not None:
        input_image_artifact_id = source_image_id
        state.artifacts.append(
            artifact_store.register_file(
                image_path_value,
                ArtifactType.SUBJECT_CONCEPT_IMAGE,
                artifact_id=source_image_id,
                semantic_role="subject_concept_image",
                metadata={
                    "stage": "input",
                    "subject_id": subject_id,
                    "source_image_id": source_image_id,
                },
            )
        )

    adapter = service_adapter or Hunyuan3DServiceAdapter(base_url=hunyuan_base_url, timeout=timeout_seconds)
    dispatcher = Hunyuan3DDomainToolDispatcher(
        state=state,
        service_adapter=adapter,
        artifact_store=artifact_store,
    )
    options = CommandExecutionOptions(timeout_seconds=timeout_seconds, dry_run=dry_run)
    stage_summaries: dict[str, dict | None] = {
        "submit": None,
        "check_status": None,
        "save_completed": None,
        "quality_check": None,
        "repair_decision": None,
        "repair_execute": None,
    }
    context_views: dict[str, dict | None] = {
        "submit": None,
        "check_status": None,
        "save_completed": None,
        "quality_check": None,
        "repair_decision": None,
        "repair_execute": None,
    }
    executed_stages: list[str] = []
    skipped_stages: dict[str, str] = {}
    resolved_job_id = job_id
    raw_status_payload = status_payload
    qa_result_for_repair = None

    if "submit" in requested_stages:
        context_views["submit"] = _state_context_view_report(
            state=state,
            stage="submit",
            view="SubjectAssetGenerationStateInput",
            phase=WorkflowPhase.SUBJECT_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "subject_id": subject_id,
                "asset_id": resolved_asset_id,
                "source_image_id": source_image_id,
                "source_image_artifact_id": input_image_artifact_id,
            },
        )
        if image_path_value is None and image_base64 is None:
            raise ValueError("image_path or image_base64 is required for submit stage")
        submit_args = _without_none(
            {
                "operation": "submit_async",
                "asset_id": resolved_asset_id,
                "subject_id": subject_id,
                "source_image_id": source_image_id,
                "image_path": str(image_path_value) if image_path_value is not None else None,
                "image_base64": image_base64,
                "remove_background": generation_kwargs["remove_background"],
                "texture": generation_kwargs["texture"],
                "seed": generation_kwargs["seed"],
                "randomize_seed": generation_kwargs["randomize_seed"],
                "octree_resolution": generation_kwargs["octree_resolution"],
                "num_inference_steps": generation_kwargs["num_inference_steps"],
                "guidance_scale": generation_kwargs["guidance_scale"],
                "num_chunks": generation_kwargs["num_chunks"],
                "face_count": generation_kwargs["face_count"],
                "hunyuan_profile_id": hunyuan_profile_id,
            }
        )
        submit_result = dispatcher.dispatch("build_subject_asset", submit_args, options=options)
        state = dispatcher.state
        stage_summaries["submit"] = _domain_result_summary(submit_result)
        executed_stages.append("submit")
        resolved_job_id = resolved_job_id or submit_result.outputs.get("uid")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="subject-asset",
            stage="submit",
            ok=bool(stage_summaries["submit"].get("ok")),
            node_name="workflow_runner.subject_asset.submit",
            metadata={
                "dry_run": dry_run,
                "asset_id": resolved_asset_id,
                "subject_id": subject_id,
                "source_image_id": source_image_id,
                "job_id": resolved_job_id,
            },
        )

    if "check_status" in requested_stages:
        context_views["check_status"] = _state_context_view_report(
            state=state,
            stage="check_status",
            view="SubjectAssetStatusStateInput",
            phase=WorkflowPhase.SUBJECT_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "job_id": resolved_job_id,
                "asset_id": resolved_asset_id,
            },
        )
        if not resolved_job_id:
            skipped_stages["check_status"] = "missing_job_id"
        else:
            check_result = dispatcher.dispatch(
                "build_subject_asset",
                {"operation": "check_status", "uid": resolved_job_id},
                options=options,
            )
            state = dispatcher.state
            stage_summaries["check_status"] = _domain_result_summary(check_result)
            executed_stages.append("check_status")
            state.updated_at = utc_now_iso()
            checkpoint_recorder.record_stage(
                state,
                workflow="subject-asset",
                stage="check_status",
                ok=bool(stage_summaries["check_status"].get("ok")),
                node_name="workflow_runner.subject_asset.check_status",
                metadata={
                    "asset_id": resolved_asset_id,
                    "subject_id": subject_id,
                    "job_id": resolved_job_id,
                },
            )

    if "save_completed" in requested_stages:
        context_views["save_completed"] = _state_context_view_report(
            state=state,
            stage="save_completed",
            view="SubjectAssetSaveCompletedStateInput",
            phase=WorkflowPhase.SUBJECT_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "job_id": resolved_job_id,
                "asset_id": resolved_asset_id,
                "output_glb": str(output_glb_path),
            },
        )
        if raw_status_payload is None and resolved_job_id and not dry_run:
            raw_status_payload = adapter.task_status(resolved_job_id)
        if raw_status_payload is None and dry_run:
            raw_status_payload = {"raw": {"data": {}}}
        if not resolved_job_id:
            skipped_stages["save_completed"] = "missing_job_id"
        elif raw_status_payload is None:
            skipped_stages["save_completed"] = "missing_status_payload"
        elif not dry_run and not _status_payload_has_model(raw_status_payload):
            skipped_stages["save_completed"] = "status_payload_missing_model_base64"
            stage_summaries["save_completed"] = {
                "ok": False,
                "dry_run": False,
                "uid": resolved_job_id,
                "status": _redact_large_payloads(raw_status_payload),
            }
        else:
            save_result = dispatcher.dispatch(
                "build_subject_asset",
                {
                    "operation": "save_completed",
                    "asset_id": resolved_asset_id,
                    "uid": resolved_job_id,
                    "subject_id": subject_id,
                    "source_image_id": source_image_id,
                    "status_payload": raw_status_payload,
                    "output_glb": str(output_glb_path),
                },
                options=options,
            )
            state = dispatcher.state
            stage_summaries["save_completed"] = _domain_result_summary(save_result)
            executed_stages.append("save_completed")
            state.updated_at = utc_now_iso()
            checkpoint_recorder.record_stage(
                state,
                workflow="subject-asset",
                stage="save_completed",
                ok=bool(stage_summaries["save_completed"].get("ok")),
                node_name="workflow_runner.subject_asset.save_completed",
                metadata={
                    "asset_id": resolved_asset_id,
                    "subject_id": subject_id,
                    "job_id": resolved_job_id,
                    "output_glb": str(output_glb_path),
                },
            )

    if "quality_check" in requested_stages:
        state.phase = WorkflowPhase.SUBJECT_ASSET_QA
        asset = _find_subject_asset(state, resolved_asset_id)
        if asset is None and output_glb_path.exists():
            state.artifacts.append(
                artifact_store.register_file(
                    output_glb_path,
                    ArtifactType.SUBJECT_3D_ASSET,
                    artifact_id=resolved_asset_id,
                    semantic_role="subject_asset_quality_input",
                    metadata={
                        "stage": "subject_asset_qa",
                        "subject_id": subject_id,
                        "source_image_id": source_image_id,
                    },
                )
            )
            asset = Asset3DRecord(
                asset_id=resolved_asset_id,
                subject_id=subject_id,
                source_image_id=source_image_id,
                service="existing_asset",
                glb_uri=str(output_glb_path),
                status="succeeded",
                generation_params={"quality_source": "existing_output_glb"},
            )
            state = apply_state_updates(
                state,
                node_name="SubjectAssetQualityEvaluator",
                updates={"subject_assets": [*state.subject_assets, asset]},
            )
        context_views["quality_check"] = _state_context_view_report(
            state=state,
            stage="quality_check",
            view="SubjectAssetQualityStateInput",
            phase=WorkflowPhase.SUBJECT_ASSET_QA,
            required_state_fields=("subject_assets",),
            extra_summary={
                "asset_id": resolved_asset_id,
                "output_glb": str(output_glb_path),
                "render_preview_requested": qa_render_preview,
                "visual_qa_requested": qa_visual_dry_run or qa_visual_live,
                "visual_qa_live": qa_visual_live,
            },
        )
        if asset is None:
            skipped_stages["quality_check"] = "missing_subject_asset"
        else:
            visual_qa_runner = None
            if qa_visual_dry_run or qa_visual_live:
                visual_qa_runner = _build_visual_qa_runner(
                    subject_id=subject_id,
                    asset_id=resolved_asset_id,
                    llm_env_file=llm_env_file,
                    dry_run=not qa_visual_live,
                    timeout=qa_timeout_seconds,
                )
            qa_result, state = evaluate_subject_asset(
                state=state,
                asset=asset,
                artifact_store=artifact_store,
                root=qa_root,
                output_dir=output_path / "subject_asset_qa",
                blender_path=qa_blender_path,
                render_preview=qa_render_preview,
                dry_run=dry_run,
                timeout_seconds=qa_timeout_seconds,
                source_image_path=image_path_value,
                visual_qa_runner=visual_qa_runner,
            )
            qa_result_for_repair = qa_result
            stage_summaries["quality_check"] = {
                "ok": qa_result.status == "pass",
                **model_to_dict(qa_result),
            }
            executed_stages.append("quality_check")
            state.updated_at = utc_now_iso()
            checkpoint_recorder.record_stage(
                state,
                workflow="subject-asset",
                stage="quality_check",
                ok=bool(stage_summaries["quality_check"].get("ok")),
                node_name="workflow_runner.subject_asset.quality_check",
                metadata={
                    "asset_id": resolved_asset_id,
                    "subject_id": subject_id,
                    "status": qa_result.status,
                    "suggested_action": qa_result.suggested_action,
                },
            )

    if "repair_decision" in requested_stages:
        state.phase = WorkflowPhase.SUBJECT_ASSET_QA
        asset = _find_subject_asset(state, resolved_asset_id)
        context_views["repair_decision"] = _state_context_view_report(
            state=state,
            stage="repair_decision",
            view="SubjectAssetRepairDecisionStateInput",
            phase=WorkflowPhase.SUBJECT_ASSET_QA,
            required_state_fields=("subject_assets",),
            extra_summary={
                "asset_id": resolved_asset_id,
                "retry_count": qa_retry_count,
                "max_hunyuan_retries": qa_max_hunyuan_retries,
                "concept_regen_count": qa_concept_regen_count,
                "max_concept_regens": qa_max_concept_regens,
                "user_requested_review": qa_user_requested_review,
            },
        )
        if asset is None:
            skipped_stages["repair_decision"] = "missing_subject_asset"
        else:
            quality_result = qa_result_for_repair or quality_result_from_asset(asset)
            if quality_result is None:
                skipped_stages["repair_decision"] = "missing_quality_result"
            else:
                decision = plan_subject_asset_repair(
                    quality_result,
                    retry_count=qa_retry_count,
                    max_hunyuan_retries=qa_max_hunyuan_retries,
                    concept_regen_count=qa_concept_regen_count,
                    max_concept_regens=qa_max_concept_regens,
                    user_requested_review=qa_user_requested_review,
                )
                state = apply_subject_asset_repair_decision(
                    state=state,
                    asset_id=resolved_asset_id,
                    decision=decision,
                )
                stage_summaries["repair_decision"] = {
                    "ok": True,
                    "dry_run": True,
                    **model_to_dict(decision),
                }
                executed_stages.append("repair_decision")
                state.updated_at = utc_now_iso()
                checkpoint_recorder.record_stage(
                    state,
                    workflow="subject-asset",
                    stage="repair_decision",
                    ok=True,
                    node_name="workflow_runner.subject_asset.repair_decision",
                    metadata={
                        "asset_id": resolved_asset_id,
                        "subject_id": subject_id,
                        "action": decision.action,
                        "user_visible": decision.user_visible,
                        "next_stage": decision.next_stage,
                    },
                )

    if "repair_execute" in requested_stages:
        asset = _find_subject_asset(state, resolved_asset_id)
        decision_payload = (asset.generation_params or {}).get("repair_decision") if asset is not None else None
        repair_execute_phase = _subject_asset_repair_execution_phase(decision_payload)
        context_views["repair_execute"] = _state_context_view_report(
            state=state,
            stage="repair_execute",
            view="SubjectAssetRepairExecutionStateInput",
            phase=repair_execute_phase,
            required_state_fields=("subject_assets",),
            extra_summary={
                "asset_id": resolved_asset_id,
                "has_repair_decision": isinstance(decision_payload, dict),
                "dry_run": dry_run,
                "confirm_repair_execute": confirm_repair_execute,
                "execution_phase": repair_execute_phase.value,
            },
        )
        if asset is None:
            skipped_stages["repair_execute"] = "missing_subject_asset"
        elif not isinstance(decision_payload, dict):
            skipped_stages["repair_execute"] = "missing_repair_decision"
        else:
            execution_summary, state = _execute_subject_asset_repair_action(
                state=state,
                dispatcher=dispatcher,
                asset=asset,
                decision_payload=decision_payload,
                image_path_value=image_path_value,
                image_base64=image_base64,
                options=options,
                confirm_repair_execute=confirm_repair_execute,
                remove_background=generation_kwargs["remove_background"],
                texture=generation_kwargs["texture"],
                seed=generation_kwargs["seed"],
                randomize_seed=generation_kwargs["randomize_seed"],
                octree_resolution=generation_kwargs["octree_resolution"],
                num_inference_steps=generation_kwargs["num_inference_steps"],
                guidance_scale=generation_kwargs["guidance_scale"],
                num_chunks=generation_kwargs["num_chunks"],
                face_count=generation_kwargs["face_count"],
            )
            stage_summaries["repair_execute"] = execution_summary
            executed_stages.append("repair_execute")
            state.updated_at = utc_now_iso()
            checkpoint_recorder.record_stage(
                state,
                workflow="subject-asset",
                stage="repair_execute",
                ok=bool(execution_summary.get("ok")),
                node_name="workflow_runner.subject_asset.repair_execute",
                metadata={
                    "asset_id": resolved_asset_id,
                    "subject_id": subject_id,
                    "action": execution_summary.get("action"),
                    "status": execution_summary.get("status"),
                    "requires_confirmation": execution_summary.get("requires_confirmation"),
                    "pending_action_id": execution_summary.get("pending_action_id"),
                },
            )

    for stage in SUBJECT_ASSET_STAGE_ORDER:
        if stage not in requested_stages:
            skipped_stages[stage] = "not_requested"

    ok = True
    for stage in requested_stages:
        if stage in skipped_stages:
            ok = False
        stage_summary = stage_summaries.get(stage)
        if stage_summary is not None:
            ok = ok and bool(stage_summary.get("ok"))

    state.updated_at = utc_now_iso()
    summary = {
        "ok": ok,
        "dry_run": dry_run,
        "output_dir": str(output_path),
        "subject_id": subject_id,
        "source_image_id": source_image_id,
        "input_image_artifact_id": input_image_artifact_id,
        "asset_id": resolved_asset_id,
        "job_id": resolved_job_id,
        "output_glb": str(output_glb_path),
        "requested_stages": list(requested_stages),
        "executed_stages": executed_stages,
        "skipped_stages": skipped_stages,
        "single_project_state": True,
        "phase": state.phase.value,
        "artifact_ids": sorted(state.artifact_ids()),
        "subject_asset_count": len(state.subject_assets),
        "tool_call_count": len(state.tool_call_log),
        "context_views": context_views,
        "submit": stage_summaries["submit"],
        "check_status": stage_summaries["check_status"],
        "save_completed": stage_summaries["save_completed"],
        "quality_check": stage_summaries["quality_check"],
        "repair_decision": stage_summaries["repair_decision"],
        "repair_execute": stage_summaries["repair_execute"],
        "state_json": str(output_path / "state.json"),
        "tool_call_log_json": str(output_path / "tool_call_log.json"),
    }
    _write_workflow_outputs(output_path, state, summary, checkpoint_recorder=checkpoint_recorder)
    return summary


def run_scene_asset_workflow(
    *,
    output_dir: str | Path,
    scene_asset_id: str,
    worldmirror_output_dir: str | Path | None = None,
    worldmirror_input_files: list[str | Path] | None = None,
    worldmirror_workspace_dir: str | Path | None = None,
    worldmirror_upload_event_id: str | None = None,
    worldmirror_event_id: str | None = None,
    worldmirror_event_api_name: str = "gradio_demo",
    worldmirror_api_prefix: str = "/gradio_api",
    source_scene_concept_image_ids: list[str] | None = None,
    source_prompt: str | None = None,
    time_interval: float = 1.0,
    frame_selector: str = "All",
    show_camera: bool = True,
    filter_sky_bg: bool = False,
    show_mesh: bool = True,
    filter_ambiguous: bool = True,
    worldmirror_base_url: str = "http://127.0.0.1:8081",
    confirm_worldmirror_upload: bool = False,
    confirm_worldmirror_upload_poll: bool = False,
    confirm_worldmirror_submit: bool = False,
    confirm_worldmirror_poll: bool = False,
    service_adapter: WorldMirrorServiceAdapter | None = None,
    timeout_seconds: float = 10,
    dry_run: bool = False,
    reset_metadata: bool = True,
    stages: str | list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Run explicit WorldMirror scene-asset status/generation/adaptation stages.

    Long-running WorldMirror submission and polling are available only through
    explicit stages and confirmation flags. Existing output registration remains
    the evidence-backed save path for the current `Scene3DRecord`.
    """

    requested_stages = _normalize_scene_asset_stages(stages)
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        _reset_scene_asset_outputs(output_path)

    checkpoint_recorder = _WorkflowCheckpointRecorder(output_path)
    artifact_store = FileArtifactStore(output_path / "artifacts")
    state = AgentProjectState(
        project_id="v1_scene_asset_workflow",
        thread_id="local_scene_asset_workflow",
        phase=WorkflowPhase.SCENE_ASSET_GENERATION,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    adapter = service_adapter or WorldMirrorServiceAdapter(base_url=worldmirror_base_url, timeout=timeout_seconds)
    dispatcher = WorldMirrorDomainToolDispatcher(
        state=state,
        service_adapter=adapter,
        artifact_store=artifact_store,
    )
    options = CommandExecutionOptions(timeout_seconds=timeout_seconds, dry_run=dry_run)
    stage_summaries: dict[str, dict | None] = {
        "runtime_status": None,
        "prepare_generation": None,
        "upload_inputs": None,
        "poll_upload": None,
        "submit_generation": None,
        "poll_generation": None,
        "inspect_output": None,
        "save_generation": None,
        "register_existing_output": None,
    }
    context_views: dict[str, dict | None] = {
        "runtime_status": None,
        "prepare_generation": None,
        "upload_inputs": None,
        "poll_upload": None,
        "submit_generation": None,
        "poll_generation": None,
        "inspect_output": None,
        "save_generation": None,
        "register_existing_output": None,
    }
    executed_stages: list[str] = []
    skipped_stages: dict[str, str] = {}
    worldmirror_output_path = (
        Path(worldmirror_output_dir).expanduser().resolve() if worldmirror_output_dir is not None else None
    )
    worldmirror_workspace_path = _worldmirror_workspace_arg(worldmirror_workspace_dir)
    input_file_paths = [str(Path(path).expanduser().resolve()) for path in (worldmirror_input_files or [])]
    effective_workspace_dir = str(worldmirror_workspace_path) if worldmirror_workspace_path else None

    if "runtime_status" in requested_stages:
        context_views["runtime_status"] = _state_context_view_report(
            state=state,
            stage="runtime_status",
            view="SceneAssetRuntimeStatusStateInput",
            phase=WorkflowPhase.SCENE_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={"scene_asset_id": scene_asset_id, "base_url": adapter.base_url},
        )
        result = dispatcher.dispatch(
            "build_scene_asset",
            {"operation": "runtime_status"},
            options=options,
        )
        state = dispatcher.state
        stage_summaries["runtime_status"] = _domain_result_summary(result)
        executed_stages.append("runtime_status")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="scene-asset",
            stage="runtime_status",
            ok=bool(stage_summaries["runtime_status"].get("ok")),
            node_name="workflow_runner.scene_asset.runtime_status",
            metadata={
                "dry_run": dry_run,
                "scene_asset_id": scene_asset_id,
                "base_url": adapter.base_url,
            },
        )

    if "prepare_generation" in requested_stages:
        context_views["prepare_generation"] = _state_context_view_report(
            state=state,
            stage="prepare_generation",
            view="SceneAssetGenerationCallPlanStateInput",
            phase=WorkflowPhase.SCENE_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "scene_asset_id": scene_asset_id,
                "input_file_count": len(input_file_paths),
                "workspace_dir": worldmirror_workspace_path,
                "base_url": adapter.base_url,
            },
        )
        result = dispatcher.dispatch(
            "build_scene_asset",
            {
                "operation": "prepare_generation",
                "input_files": input_file_paths,
                "workspace_dir": worldmirror_workspace_path,
                "time_interval": time_interval,
                "frame_selector": frame_selector,
                "show_camera": show_camera,
                "filter_sky_bg": filter_sky_bg,
                "show_mesh": show_mesh,
                "filter_ambiguous": filter_ambiguous,
            },
            options=options,
        )
        state = dispatcher.state
        stage_summaries["prepare_generation"] = _domain_result_summary(result)
        executed_stages.append("prepare_generation")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="scene-asset",
            stage="prepare_generation",
            ok=bool(stage_summaries["prepare_generation"].get("ok")),
            node_name="workflow_runner.scene_asset.prepare_generation",
            metadata={
                "dry_run": dry_run,
                "scene_asset_id": scene_asset_id,
                "input_file_count": len(input_file_paths),
                "workspace_dir": worldmirror_workspace_path,
                "base_url": adapter.base_url,
            },
        )

    if "upload_inputs" in requested_stages:
        context_views["upload_inputs"] = _state_context_view_report(
            state=state,
            stage="upload_inputs",
            view="SceneAssetUploadInputsStateInput",
            phase=WorkflowPhase.SCENE_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "scene_asset_id": scene_asset_id,
                "input_file_count": len(input_file_paths),
                "base_url": adapter.base_url,
                "confirm_upload": confirm_worldmirror_upload,
            },
        )
        result = dispatcher.dispatch(
            "build_scene_asset",
            {
                "operation": "upload_inputs",
                "input_files": input_file_paths,
                "time_interval": time_interval,
                "frame_selector": frame_selector,
                "show_camera": show_camera,
                "filter_sky_bg": filter_sky_bg,
                "show_mesh": show_mesh,
                "filter_ambiguous": filter_ambiguous,
                "confirm_upload": confirm_worldmirror_upload,
            },
            options=options,
        )
        state = dispatcher.state
        stage_summaries["upload_inputs"] = _domain_result_summary(result)
        executed_stages.append("upload_inputs")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="scene-asset",
            stage="upload_inputs",
            ok=bool(stage_summaries["upload_inputs"].get("ok")),
            node_name="workflow_runner.scene_asset.upload_inputs",
            metadata={
                "dry_run": dry_run,
                "scene_asset_id": scene_asset_id,
                "input_file_count": len(input_file_paths),
                "base_url": adapter.base_url,
                "confirm_upload": confirm_worldmirror_upload,
            },
        )

    if "poll_upload" in requested_stages:
        context_views["poll_upload"] = _state_context_view_report(
            state=state,
            stage="poll_upload",
            view="SceneAssetUploadPollStateInput",
            phase=WorkflowPhase.SCENE_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "scene_asset_id": scene_asset_id,
                "event_id": worldmirror_upload_event_id,
                "api_prefix": worldmirror_api_prefix,
                "base_url": adapter.base_url,
                "confirm_poll": confirm_worldmirror_upload_poll,
            },
        )
        result = dispatcher.dispatch(
            "build_scene_asset",
            {
                "operation": "poll_upload",
                "event_id": worldmirror_upload_event_id,
                "api_prefix": worldmirror_api_prefix,
                "confirm_poll": confirm_worldmirror_upload_poll,
            },
            options=options,
        )
        state = dispatcher.state
        stage_summaries["poll_upload"] = _domain_result_summary(result)
        outputs = stage_summaries["poll_upload"].get("outputs", {})
        target_dir = outputs.get("target_dir") if isinstance(outputs, dict) else None
        if isinstance(target_dir, str) and target_dir:
            effective_workspace_dir = target_dir
        executed_stages.append("poll_upload")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="scene-asset",
            stage="poll_upload",
            ok=bool(stage_summaries["poll_upload"].get("ok")),
            node_name="workflow_runner.scene_asset.poll_upload",
            metadata={
                "dry_run": dry_run,
                "scene_asset_id": scene_asset_id,
                "event_id": worldmirror_upload_event_id,
                "api_prefix": worldmirror_api_prefix,
                "target_dir": target_dir,
                "base_url": adapter.base_url,
                "confirm_poll": confirm_worldmirror_upload_poll,
            },
        )

    if "submit_generation" in requested_stages:
        context_views["submit_generation"] = _state_context_view_report(
            state=state,
            stage="submit_generation",
            view="SceneAssetGenerationSubmitStateInput",
            phase=WorkflowPhase.SCENE_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "scene_asset_id": scene_asset_id,
                "input_file_count": len(input_file_paths),
                "workspace_dir": effective_workspace_dir,
                "base_url": adapter.base_url,
                "confirm_submit": confirm_worldmirror_submit,
            },
        )
        result = dispatcher.dispatch(
            "build_scene_asset",
            {
                "operation": "submit_generation",
                "input_files": input_file_paths,
                "workspace_dir": effective_workspace_dir,
                "time_interval": time_interval,
                "frame_selector": frame_selector,
                "show_camera": show_camera,
                "filter_sky_bg": filter_sky_bg,
                "show_mesh": show_mesh,
                "filter_ambiguous": filter_ambiguous,
                "confirm_submit": confirm_worldmirror_submit,
            },
            options=options,
        )
        state = dispatcher.state
        stage_summaries["submit_generation"] = _domain_result_summary(result)
        executed_stages.append("submit_generation")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="scene-asset",
            stage="submit_generation",
            ok=bool(stage_summaries["submit_generation"].get("ok")),
            node_name="workflow_runner.scene_asset.submit_generation",
            metadata={
                "dry_run": dry_run,
                "scene_asset_id": scene_asset_id,
                "workspace_dir": effective_workspace_dir,
                "base_url": adapter.base_url,
                "confirm_submit": confirm_worldmirror_submit,
            },
        )

    if "poll_generation" in requested_stages:
        context_views["poll_generation"] = _state_context_view_report(
            state=state,
            stage="poll_generation",
            view="SceneAssetGenerationPollStateInput",
            phase=WorkflowPhase.SCENE_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "scene_asset_id": scene_asset_id,
                "event_id": worldmirror_event_id,
                "api_name": worldmirror_event_api_name,
                "api_prefix": worldmirror_api_prefix,
                "base_url": adapter.base_url,
                "confirm_poll": confirm_worldmirror_poll,
            },
        )
        result = dispatcher.dispatch(
            "build_scene_asset",
            {
                "operation": "poll_generation",
                "event_id": worldmirror_event_id,
                "api_name": worldmirror_event_api_name,
                "api_prefix": worldmirror_api_prefix,
                "confirm_poll": confirm_worldmirror_poll,
            },
            options=options,
        )
        state = dispatcher.state
        stage_summaries["poll_generation"] = _domain_result_summary(result)
        executed_stages.append("poll_generation")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="scene-asset",
            stage="poll_generation",
            ok=bool(stage_summaries["poll_generation"].get("ok")),
            node_name="workflow_runner.scene_asset.poll_generation",
            metadata={
                "dry_run": dry_run,
                "scene_asset_id": scene_asset_id,
                "event_id": worldmirror_event_id,
                "api_name": worldmirror_event_api_name,
                "api_prefix": worldmirror_api_prefix,
                "base_url": adapter.base_url,
                "confirm_poll": confirm_worldmirror_poll,
            },
        )

    if "inspect_output" in requested_stages:
        context_views["inspect_output"] = _state_context_view_report(
            state=state,
            stage="inspect_output",
            view="SceneAssetInspectOutputStateInput",
            phase=WorkflowPhase.SCENE_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "scene_asset_id": scene_asset_id,
                "worldmirror_output_dir": str(worldmirror_output_path) if worldmirror_output_path else None,
            },
        )
        if worldmirror_output_path is None:
            skipped_stages["inspect_output"] = "missing_worldmirror_output_dir"
        else:
            result = dispatcher.dispatch(
                "adapt_scene_asset",
                {"operation": "inspect_output", "output_dir": str(worldmirror_output_path)},
                options=options,
            )
            state = dispatcher.state
            stage_summaries["inspect_output"] = _domain_result_summary(result)
            executed_stages.append("inspect_output")
            state.updated_at = utc_now_iso()
            checkpoint_recorder.record_stage(
                state,
                workflow="scene-asset",
                stage="inspect_output",
                ok=bool(stage_summaries["inspect_output"].get("ok")),
                node_name="workflow_runner.scene_asset.inspect_output",
                metadata={
                    "scene_asset_id": scene_asset_id,
                    "worldmirror_output_dir": str(worldmirror_output_path),
                },
            )

    if "save_generation" in requested_stages:
        context_views["save_generation"] = _state_context_view_report(
            state=state,
            stage="save_generation",
            view="SceneAssetGenerationSaveStateInput",
            phase=WorkflowPhase.SCENE_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "scene_asset_id": scene_asset_id,
                "worldmirror_output_dir": str(worldmirror_output_path) if worldmirror_output_path else None,
                "source_scene_concept_image_ids": source_scene_concept_image_ids or [],
            },
        )
        if worldmirror_output_path is None:
            skipped_stages["save_generation"] = "missing_worldmirror_output_dir"
        else:
            result = dispatcher.dispatch(
                "adapt_scene_asset",
                {
                    "operation": "register_existing_output",
                    "scene_asset_id": scene_asset_id,
                    "output_dir": str(worldmirror_output_path),
                    "source_scene_concept_image_ids": source_scene_concept_image_ids or [],
                    "source_prompt": source_prompt,
                },
                options=options,
            )
            state = dispatcher.state
            stage_summaries["save_generation"] = _domain_result_summary(result)
            executed_stages.append("save_generation")
            state.updated_at = utc_now_iso()
            checkpoint_recorder.record_stage(
                state,
                workflow="scene-asset",
                stage="save_generation",
                ok=bool(stage_summaries["save_generation"].get("ok")),
                node_name="workflow_runner.scene_asset.save_generation",
                metadata={
                    "scene_asset_id": scene_asset_id,
                    "worldmirror_output_dir": str(worldmirror_output_path),
                    "has_scene_asset": state.scene_asset is not None,
                },
            )

    if "register_existing_output" in requested_stages:
        context_views["register_existing_output"] = _state_context_view_report(
            state=state,
            stage="register_existing_output",
            view="SceneAssetRegisterExistingOutputStateInput",
            phase=WorkflowPhase.SCENE_ASSET_GENERATION,
            required_state_fields=(),
            extra_summary={
                "scene_asset_id": scene_asset_id,
                "worldmirror_output_dir": str(worldmirror_output_path) if worldmirror_output_path else None,
                "source_scene_concept_image_ids": source_scene_concept_image_ids or [],
            },
        )
        if worldmirror_output_path is None:
            skipped_stages["register_existing_output"] = "missing_worldmirror_output_dir"
        else:
            result = dispatcher.dispatch(
                "adapt_scene_asset",
                {
                    "operation": "register_existing_output",
                    "scene_asset_id": scene_asset_id,
                    "output_dir": str(worldmirror_output_path),
                    "source_scene_concept_image_ids": source_scene_concept_image_ids or [],
                    "source_prompt": source_prompt,
                },
                options=options,
            )
            state = dispatcher.state
            stage_summaries["register_existing_output"] = _domain_result_summary(result)
            executed_stages.append("register_existing_output")
            state.updated_at = utc_now_iso()
            checkpoint_recorder.record_stage(
                state,
                workflow="scene-asset",
                stage="register_existing_output",
                ok=bool(stage_summaries["register_existing_output"].get("ok")),
                node_name="workflow_runner.scene_asset.register_existing_output",
                metadata={
                    "scene_asset_id": scene_asset_id,
                    "worldmirror_output_dir": str(worldmirror_output_path),
                    "has_scene_asset": state.scene_asset is not None,
                },
            )

    for stage in SCENE_ASSET_STAGE_ORDER:
        if stage not in requested_stages:
            skipped_stages[stage] = "not_requested"

    ok = True
    for stage in requested_stages:
        if stage in skipped_stages:
            ok = False
        stage_summary = stage_summaries.get(stage)
        if stage_summary is not None:
            ok = ok and bool(stage_summary.get("ok"))

    state.updated_at = utc_now_iso()
    summary = {
        "ok": ok,
        "dry_run": dry_run,
        "output_dir": str(output_path),
        "scene_asset_id": scene_asset_id,
        "worldmirror_output_dir": str(worldmirror_output_path) if worldmirror_output_path else None,
        "worldmirror_workspace_dir": worldmirror_workspace_path,
        "worldmirror_effective_workspace_dir": effective_workspace_dir,
        "worldmirror_upload_event_id": worldmirror_upload_event_id,
        "worldmirror_event_id": worldmirror_event_id,
        "worldmirror_event_api_name": worldmirror_event_api_name,
        "requested_stages": list(requested_stages),
        "executed_stages": executed_stages,
        "skipped_stages": skipped_stages,
        "single_project_state": True,
        "phase": state.phase.value,
        "artifact_ids": sorted(state.artifact_ids()),
        "has_scene_asset": state.scene_asset is not None,
        "scene_asset": model_to_dict(state.scene_asset) if state.scene_asset is not None else None,
        "tool_call_count": len(state.tool_call_log),
        "context_views": context_views,
        "runtime_status": stage_summaries["runtime_status"],
        "prepare_generation": stage_summaries["prepare_generation"],
        "upload_inputs": stage_summaries["upload_inputs"],
        "poll_upload": stage_summaries["poll_upload"],
        "submit_generation": stage_summaries["submit_generation"],
        "poll_generation": stage_summaries["poll_generation"],
        "inspect_output": stage_summaries["inspect_output"],
        "save_generation": stage_summaries["save_generation"],
        "register_existing_output": stage_summaries["register_existing_output"],
        "state_json": str(output_path / "state.json"),
        "tool_call_log_json": str(output_path / "tool_call_log.json"),
    }
    _write_workflow_outputs(output_path, state, summary, checkpoint_recorder=checkpoint_recorder)
    return summary


def run_delivery_package_workflow(
    *,
    state_json: str | Path,
    output_dir: str | Path,
    package_id: str | None = None,
    reset_metadata: bool = True,
) -> dict:
    """Build a deterministic delivery package from a saved AgentProjectState."""

    state_path = Path(state_json).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        _reset_delivery_package_outputs(output_path, package_id=package_id)

    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    artifact_store = FileArtifactStore(output_path / "artifacts")
    result, state = build_delivery_package(
        state=state,
        output_dir=output_path / "package",
        artifact_store=artifact_store,
        package_id=package_id,
    )
    state.updated_at = utc_now_iso()
    checkpoint_recorder = _WorkflowCheckpointRecorder(output_path)
    checkpoint_recorder.record_stage(
        state,
        workflow="delivery-package",
        stage="delivery_package",
        ok=result.ok,
        node_name="workflow_runner.delivery_package",
        metadata={
            "package_id": result.package_artifact_id,
            "package_zip": result.package_zip,
            "metadata_json": result.metadata_json,
            "version_manifest_json": result.version_manifest_json,
        },
    )
    summary = {
        "ok": result.ok,
        "state_json_input": str(state_path),
        "output_dir": str(output_path),
        "package": model_to_dict(result),
        "artifact_ids": sorted(state.artifact_ids()),
        "phase": state.phase.value,
        "state_json": str(output_path / "state.json"),
        "tool_call_log_json": str(output_path / "tool_call_log.json"),
    }
    _write_workflow_outputs(output_path, state, summary, checkpoint_recorder=checkpoint_recorder)
    return summary


def run_review_patch_workflow(
    *,
    state_json: str | Path,
    output_dir: str | Path,
    user_feedback: str,
    source_turn_id: str | None = None,
    patch_id: str | None = None,
    patch_type: str | None = None,
    clear_pending_action: bool = True,
    next_phase: WorkflowPhase | str = WorkflowPhase.CONCEPT_REVIEW,
    reset_metadata: bool = True,
) -> dict:
    """Create a structured ReviewPatch from a saved pending-action state."""

    state_path = Path(state_json).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        _reset_review_patch_outputs(output_path)

    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    resolved_next_phase = next_phase if isinstance(next_phase, WorkflowPhase) else WorkflowPhase(next_phase)
    checkpoint_recorder = _WorkflowCheckpointRecorder(output_path)
    pending_action_id = state.pending_action.action_id if state.pending_action is not None else None
    result, state = create_review_patch_from_pending_action(
        state=state,
        user_feedback=user_feedback,
        source_turn_id=source_turn_id,
        patch_id=patch_id,
        patch_type=patch_type,
        clear_pending_action=clear_pending_action,
        next_phase=resolved_next_phase,
    )
    state.updated_at = utc_now_iso()
    checkpoint_recorder.record_stage(
        state,
        workflow="review-patch",
        stage="review_patch",
        ok=result.ok,
        node_name="workflow_runner.review_patch",
        metadata={
            "pending_action_id": pending_action_id,
            "patch_id": result.patch.patch_id if result.patch is not None else None,
            "patch_type": result.patch.patch_type if result.patch is not None else None,
            "target_type": result.patch.target_type if result.patch is not None else None,
            "target_id": result.patch.target_id if result.patch is not None else None,
            "issues": result.issues,
            "cleared_pending_action": result.cleared_pending_action,
            "next_phase": result.next_phase.value if result.next_phase is not None else None,
        },
    )
    summary = {
        "ok": result.ok,
        "state_json_input": str(state_path),
        "output_dir": str(output_path),
        "requested_stages": ["review_patch"],
        "executed_stages": ["review_patch"],
        "skipped_stages": {},
        "review_patch": model_to_dict(result),
        "review_patch_count": len(state.review_patches),
        "pending_action_id": pending_action_id,
        "pending_action_cleared": state.pending_action is None,
        "phase": state.phase.value,
        "state_json": str(output_path / "state.json"),
        "tool_call_log_json": str(output_path / "tool_call_log.json"),
    }
    _write_workflow_outputs(output_path, state, summary, checkpoint_recorder=checkpoint_recorder)
    return summary


def run_concept_seed_workflow(
    *,
    image_path: str | Path,
    output_dir: str | Path,
    subject_id: str,
    source_image_id: str,
    project_id: str = "v1_real_demo",
    thread_id: str = "local_real_demo",
    prompt: str | None = None,
    negative_prompt: str | None = None,
    approve: bool = True,
    copy_into_store: bool = True,
    reset_metadata: bool = True,
) -> dict:
    """Register an existing/generated subject concept image into V1 state."""

    source_path = Path(image_path).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        _reset_concept_seed_outputs(output_path)

    artifact_store = FileArtifactStore(output_path / "artifacts")
    artifact = artifact_store.register_file(
        source_path,
        ArtifactType.SUBJECT_CONCEPT_IMAGE,
        artifact_id=source_image_id,
        semantic_role="subject_concept_image",
        copy_into_store=copy_into_store,
        metadata={
            "stage": "concept_seed",
            "subject_id": subject_id,
            "prompt": prompt,
            "source_path": str(source_path),
            "copy_into_store": copy_into_store,
        },
    )
    concept_bundle = ConceptBundle(
        concept_version=1,
        subject_concept_images={subject_id: [artifact.artifact_id]},
        prompt_pack=ConceptPromptPack(
            final_preview_prompt=prompt or "",
            subject_prompts={subject_id: prompt or ""},
            negative_prompt=negative_prompt,
        )
        if prompt or negative_prompt
        else None,
        approved=approve,
        approved_at=utc_now_iso() if approve else None,
    )
    state = AgentProjectState(
        project_id=project_id,
        thread_id=thread_id,
        phase=WorkflowPhase.SUBJECT_ASSET_GENERATION if approve else WorkflowPhase.CONCEPT_REVIEW,
        concept_bundle=concept_bundle,
        artifacts=[artifact],
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    checkpoint_recorder = _WorkflowCheckpointRecorder(output_path)
    checkpoint_recorder.record_stage(
        state,
        workflow="concept-seed",
        stage="seed_concept",
        ok=True,
        node_name="workflow_runner.concept_seed",
        metadata={
            "subject_id": subject_id,
            "source_image_id": source_image_id,
            "image_path": str(source_path),
            "artifact_id": artifact.artifact_id,
            "approved": approve,
        },
    )
    summary = {
        "ok": True,
        "output_dir": str(output_path),
        "requested_stages": list(CONCEPT_SEED_STAGE_ORDER),
        "executed_stages": list(CONCEPT_SEED_STAGE_ORDER),
        "skipped_stages": {},
        "concept_seed": {
            "subject_id": subject_id,
            "source_image_id": source_image_id,
            "artifact_id": artifact.artifact_id,
            "artifact_uri": artifact.uri,
            "source_path": str(source_path),
            "approved": approve,
            "copy_into_store": copy_into_store,
            "prompt": prompt,
        },
        "artifact_ids": sorted(state.artifact_ids()),
        "phase": state.phase.value,
        "state_json": str(output_path / "state.json"),
        "tool_call_log_json": str(output_path / "tool_call_log.json"),
    }
    _write_workflow_outputs(output_path, state, summary, checkpoint_recorder=checkpoint_recorder)
    return summary


def run_concept_regeneration_workflow(
    *,
    state_json: str | Path,
    output_dir: str | Path,
    patch_id: str | None = None,
    generated_image_path: str | Path | None = None,
    generated_image_artifact_id: str | None = None,
    dry_run: bool = True,
    copy_into_store: bool = True,
    reset_metadata: bool = True,
) -> dict:
    """Consume a pending ReviewPatch into the existing concept image path."""

    state_path = Path(state_json).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        _reset_concept_regeneration_outputs(output_path)

    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    artifact_store = FileArtifactStore(output_path / "artifacts")
    checkpoint_recorder = _WorkflowCheckpointRecorder(output_path)
    result, state = apply_review_patch_concept_regeneration(
        state=state,
        artifact_store=artifact_store,
        patch_id=patch_id,
        generated_image_path=generated_image_path,
        generated_image_artifact_id=generated_image_artifact_id,
        dry_run=dry_run,
        copy_into_store=copy_into_store,
    )
    state.updated_at = utc_now_iso()
    checkpoint_recorder.record_stage(
        state,
        workflow="concept-regeneration",
        stage="apply_review_patch",
        ok=result.ok,
        node_name="workflow_runner.concept_regeneration.apply_review_patch",
        metadata={
            "dry_run": dry_run,
            "patch_id": result.patch_id,
            "patch_type": result.patch_type,
            "target_subject_id": result.target_subject_id,
            "status": result.status,
            "generated_image_artifact_id": result.generated_image_artifact_id,
            "issues": result.issues,
            "next_phase": result.next_phase.value if result.next_phase is not None else None,
        },
    )
    summary = {
        "ok": result.ok,
        "dry_run": dry_run,
        "state_json_input": str(state_path),
        "output_dir": str(output_path),
        "requested_stages": list(CONCEPT_REGENERATION_STAGE_ORDER),
        "executed_stages": list(CONCEPT_REGENERATION_STAGE_ORDER),
        "skipped_stages": {},
        "concept_regeneration": model_to_dict(result),
        "review_patch_count": len(state.review_patches),
        "artifact_ids": sorted(state.artifact_ids()),
        "phase": state.phase.value,
        "state_json": str(output_path / "state.json"),
        "tool_call_log_json": str(output_path / "tool_call_log.json"),
    }
    _write_workflow_outputs(output_path, state, summary, checkpoint_recorder=checkpoint_recorder)
    return summary


def run_codex_self_mcp_workflow(
    *,
    output_dir: str | Path,
    cwd: str | Path,
    prompt: str | None = None,
    prompt_file: str | Path | None = None,
    sandbox: SandboxMode = "workspace-write",
    approval_policy: ApprovalPolicy = "never",
    timeout_seconds: float = 300,
    log_path: str | Path | None = None,
    extract_last_image_to: str | Path | None = None,
    repo_path: str | Path = "/home/team/zouzhiyuan/codex-self-mcp",
    codex_command: str = "codex",
    service_adapter: CodexSelfMCPAdapter | None = None,
    dry_run: bool = True,
    confirm_execute: bool = False,
    reset_metadata: bool = True,
    stages: str | list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Plan or explicitly execute a codex-self-mcp sub-agent handoff."""

    requested_stages = _normalize_codex_self_mcp_stages(stages)
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        _reset_codex_self_mcp_outputs(output_path)

    adapter = service_adapter or CodexSelfMCPAdapter(repo_path=repo_path, codex_command=codex_command)
    checkpoint_recorder = _WorkflowCheckpointRecorder(output_path)
    state = AgentProjectState(
        project_id="v1_codex_self_mcp_workflow",
        thread_id="local_codex_self_mcp_workflow",
        phase=WorkflowPhase.INTAKE,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    stage_summaries: dict[str, dict | None] = {
        "status": None,
        "plan_handoff": None,
        "execute_handoff": None,
    }
    context_views: dict[str, dict | None] = {
        "status": None,
        "plan_handoff": None,
        "execute_handoff": None,
    }
    executed_stages: list[str] = []
    skipped_stages: dict[str, str] = {}
    plan: CodexSelfMCPCallPlan | None = None
    resolved_log_path = Path(log_path).expanduser() if log_path is not None else output_path / "codex_self_mcp_call.jsonl"

    if "status" in requested_stages:
        context_views["status"] = _state_context_view_report(
            state=state,
            stage="status",
            view="CodexSelfMCPStatusStateInput",
            phase=WorkflowPhase.INTAKE,
            required_state_fields=(),
            extra_summary={"repo_path": str(adapter.repo_path), "codex_command": adapter.codex_command},
        )
        status = adapter.status(run_smoke=False, timeout_seconds=min(timeout_seconds, 60))
        stage_summaries["status"] = {
            "ok": status.ok,
            "dry_run": False,
            "outputs": model_to_dict(status),
        }
        executed_stages.append("status")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="codex-self-mcp",
            stage="status",
            ok=status.ok,
            node_name="workflow_runner.codex_self_mcp.status",
            metadata={
                "repo_path": str(adapter.repo_path),
                "codex_command": adapter.codex_command,
                "issues": status.issues,
            },
        )

    def ensure_plan() -> CodexSelfMCPCallPlan:
        nonlocal plan
        if plan is None:
            plan = adapter.build_call_plan(
                prompt=prompt,
                prompt_file=prompt_file,
                cwd=cwd,
                sandbox=sandbox,
                approval_policy=approval_policy,
                timeout_seconds=timeout_seconds,
                log_path=resolved_log_path,
                extract_last_image_to=extract_last_image_to,
            )
        return plan

    if "plan_handoff" in requested_stages:
        context_views["plan_handoff"] = _state_context_view_report(
            state=state,
            stage="plan_handoff",
            view="CodexSelfMCPHandoffPlanStateInput",
            phase=WorkflowPhase.INTAKE,
            required_state_fields=(),
            extra_summary={
                "repo_path": str(adapter.repo_path),
                "cwd": str(Path(cwd).expanduser().resolve()),
                "sandbox": sandbox,
                "approval_policy": approval_policy,
                "dry_run": dry_run,
            },
        )
        handoff_plan = ensure_plan()
        outputs = {
            "operation": "plan_handoff",
            "planned": True,
            "execute_requested": False,
            "call_plan": model_to_dict(handoff_plan),
        }
        stage_summaries["plan_handoff"] = {"ok": True, "dry_run": True, "outputs": outputs}
        executed_stages.append("plan_handoff")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="codex-self-mcp",
            stage="plan_handoff",
            ok=True,
            node_name="workflow_runner.codex_self_mcp.plan_handoff",
            metadata={
                "cwd": handoff_plan.cwd,
                "sandbox": handoff_plan.sandbox,
                "approval_policy": handoff_plan.approval_policy,
                "prompt_source": handoff_plan.prompt_source,
            },
        )

    if "execute_handoff" in requested_stages:
        context_views["execute_handoff"] = _state_context_view_report(
            state=state,
            stage="execute_handoff",
            view="CodexSelfMCPExecuteHandoffStateInput",
            phase=WorkflowPhase.INTAKE,
            required_state_fields=(),
            extra_summary={
                "repo_path": str(adapter.repo_path),
                "cwd": str(Path(cwd).expanduser().resolve()),
                "sandbox": sandbox,
                "approval_policy": approval_policy,
                "dry_run": dry_run,
                "confirm_execute": confirm_execute,
            },
        )
        handoff_plan = ensure_plan()
        if dry_run:
            outputs = {
                "operation": "execute_handoff",
                "executed": False,
                "requires_confirmation": True,
                "call_plan": model_to_dict(handoff_plan),
            }
            ok = True
        elif not confirm_execute:
            outputs = {
                "operation": "execute_handoff",
                "executed": False,
                "requires_confirmation": True,
                "issues": ["codex_self_mcp_execute_requires_explicit_confirmation"],
                "call_plan": model_to_dict(handoff_plan),
            }
            ok = False
        else:
            result = adapter.run_call_plan(handoff_plan)
            outputs = {
                "operation": "execute_handoff",
                "executed": True,
                "requires_confirmation": True,
                "result": model_to_dict(result),
            }
            ok = result.ok
        stage_summaries["execute_handoff"] = {"ok": ok, "dry_run": dry_run, "outputs": outputs}
        executed_stages.append("execute_handoff")
        state.updated_at = utc_now_iso()
        checkpoint_recorder.record_stage(
            state,
            workflow="codex-self-mcp",
            stage="execute_handoff",
            ok=ok,
            node_name="workflow_runner.codex_self_mcp.execute_handoff",
            metadata={
                "dry_run": dry_run,
                "confirm_execute": confirm_execute,
                "cwd": handoff_plan.cwd,
                "sandbox": handoff_plan.sandbox,
                "approval_policy": handoff_plan.approval_policy,
            },
        )

    for stage in CODEX_SELF_MCP_STAGE_ORDER:
        if stage not in requested_stages:
            skipped_stages[stage] = "not_requested"

    ok = True
    for stage in requested_stages:
        stage_summary = stage_summaries.get(stage)
        if stage_summary is not None:
            ok = ok and bool(stage_summary.get("ok"))

    summary = {
        "ok": ok,
        "dry_run": dry_run,
        "output_dir": str(output_path),
        "requested_stages": list(requested_stages),
        "executed_stages": executed_stages,
        "skipped_stages": skipped_stages,
        "single_project_state": True,
        "phase": state.phase.value,
        "tool_call_count": len(state.tool_call_log),
        "context_views": context_views,
        "status": stage_summaries["status"],
        "plan_handoff": stage_summaries["plan_handoff"],
        "execute_handoff": stage_summaries["execute_handoff"],
        "state_json": str(output_path / "state.json"),
        "tool_call_log_json": str(output_path / "tool_call_log.json"),
    }
    _write_workflow_outputs(output_path, state, summary, checkpoint_recorder=checkpoint_recorder)
    return summary


def run_blender_edit_workflow(
    *,
    state_json: str | Path,
    output_dir: str | Path,
    domain_tool_name: str,
    arguments: dict[str, Any] | None = None,
    raw_tool_caller: RawBlenderMCPToolCaller | None = None,
    raw_caller_source: str | None = None,
    dry_run: bool = False,
    reset_metadata: bool = True,
    root: str | Path = "/home/team/zouzhiyuan/image23D_Agent",
    blender_path: str | Path | None = None,
    export_viewer: bool = False,
    input_blend: str | Path | None = None,
    viewer_base_url: str = "http://127.0.0.1:8092",
    export_timeout_seconds: float = 180,
    viewer_timeout_seconds: float = 10,
) -> dict:
    """Apply one safe Blender MCP-backed edit/read operation to a saved state.

    Non-dry-run execution requires either an injected raw MCP caller or an
    explicit local raw-caller source such as the existing Blender Lab socket
    bridge.
    """

    if raw_tool_caller is not None and raw_caller_source is not None:
        raise ValueError("use either raw_tool_caller or raw_caller_source, not both")
    if raw_tool_caller is None and raw_caller_source is None and not dry_run:
        raise ValueError("raw_tool_caller or raw_caller_source is required for non-dry-run blender-edit workflow")

    state_path = Path(state_json).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if reset_metadata:
        _reset_blender_edit_outputs(output_path)

    checkpoint_recorder = _WorkflowCheckpointRecorder(output_path)
    root_path = Path(root).expanduser().resolve()
    viewer_dir = output_path / "viewer_export"
    viewer_dir.mkdir(parents=True, exist_ok=True)
    artifact_store = FileArtifactStore(output_path / "artifacts")

    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    state.phase = WorkflowPhase.BLENDER_EDIT
    state.updated_at = utc_now_iso()
    manager = None
    if raw_caller_source == "blender-lab-socket":
        raw_tool_caller = BlenderLabSocketRawToolCaller(root=root_path)
        manager = build_default_mcp_client_manager(blender_raw_tool_caller=raw_tool_caller)
    elif raw_caller_source is not None:
        raise ValueError(f"unsupported raw_caller_source: {raw_caller_source}")
    raw_caller_label = raw_caller_source or ("injected" if raw_tool_caller is not None else None)
    raw_tool_caller = raw_tool_caller or _unavailable_blender_mcp_raw_tool_caller
    edit_context = _state_context_view_report(
        state=state,
        stage="blender_edit",
        view="BlenderMCPDomainToolStateInput",
        phase=WorkflowPhase.BLENDER_EDIT,
        required_state_fields=() if domain_tool_name == "get_blender_scene_summary" else ("blender_scene",),
        extra_summary={
            "domain_tool_name": domain_tool_name,
            "dry_run": dry_run,
            "raw_caller_source": raw_caller_label,
            "arguments_keys": sorted((arguments or {}).keys()),
        },
    )
    if manager is not None:
        dispatcher = BlenderMCPDomainToolDispatcher.from_mcp_client_manager(
            state=state,
            manager=manager,
            ensure_blend_loaded=raw_caller_source == "blender-lab-socket",
        )
    else:
        dispatcher = BlenderMCPDomainToolDispatcher(state=state, raw_tool_caller=raw_tool_caller)
    edit_result = dispatcher.dispatch(
        domain_tool_name,
        arguments or {},
        options=CommandExecutionOptions(dry_run=dry_run),
    )
    state = dispatcher.state
    state.updated_at = utc_now_iso()
    edit_summary = _domain_result_summary(edit_result)
    edit_summary["context_view_input"] = edit_context
    checkpoint_recorder.record_stage(
        state,
        workflow="blender-edit",
        stage="blender_edit",
        ok=edit_result.ok,
        node_name="workflow_runner.blender_edit",
        metadata={
            "domain_tool_name": domain_tool_name,
            "dry_run": dry_run,
            "raw_caller_source": raw_caller_label,
            "raw_tool_name": edit_result.outputs.get("raw_tool_name"),
        },
    )

    export_summary = None
    viewer_check = None
    skipped_stages: dict[str, str] = {}
    executed_stages = ["blender_edit"]
    context_views = {"blender_edit": edit_context, "export_viewer": None, "viewer_check": None}

    if export_viewer:
        resolved_input_blend = _resolve_input_blend(input_blend=input_blend, state=state)
        if dry_run:
            skipped_stages["export_viewer"] = "dry_run"
            skipped_stages["viewer_check"] = "export_viewer_skipped"
        elif not edit_result.ok:
            skipped_stages["export_viewer"] = "blender_edit_failed"
            skipped_stages["viewer_check"] = "export_viewer_skipped"
        elif resolved_input_blend is None:
            skipped_stages["export_viewer"] = "missing_input_blend"
            skipped_stages["viewer_check"] = "export_viewer_skipped"
        else:
            viewer_adapter = ViewerRuntimeAdapter(base_url=viewer_base_url, timeout=viewer_timeout_seconds)
            export_summary, state = _run_export_viewer_stage(
                state=state,
                artifact_store=artifact_store,
                root_path=root_path,
                input_blend=resolved_input_blend,
                viewer_dir=viewer_dir,
                blender_path=blender_path,
                timeout_seconds=export_timeout_seconds,
                viewer_adapter=viewer_adapter,
                artifact_prefix="edit",
            )
            context_views["export_viewer"] = export_summary.get("context_view_input")
            executed_stages.append("export_viewer")
            state.updated_at = utc_now_iso()
            checkpoint_recorder.record_stage(
                state,
                workflow="blender-edit",
                stage="export_viewer",
                ok=bool(export_summary.get("ok")),
                node_name="workflow_runner.blender_edit.export_viewer",
                metadata={
                    "viewer_glb_exists": export_summary.get("viewer_glb_exists"),
                    "scene_state_json_exists": export_summary.get("scene_state_json_exists"),
                    "viewer_scene_object_count": export_summary.get("viewer_scene_object_count"),
                },
            )
            if export_summary["ok"] and export_summary["viewer_glb_exists"]:
                viewer_context = _state_context_view_report(
                    state=state,
                    stage="viewer_check",
                    view="ViewerRuntimeCheckStateInput",
                    phase=state.phase,
                    required_state_fields=("viewer_scene",),
                    extra_summary={"viewer_glb": str(viewer_dir / "viewer_scene.glb")},
                )
                viewer_runtime = viewer_adapter.runtime_status()
                viewer_check = viewer_adapter.check_model(viewer_dir / "viewer_scene.glb")
                viewer_check["runtime"] = viewer_runtime
                viewer_check["ok"] = bool(viewer_check["ok"] and viewer_runtime["ok"])
                viewer_check["context_view_input"] = viewer_context
                context_views["viewer_check"] = viewer_context
                state.artifacts = annotate_state_artifact_with_viewer(
                    state.artifacts,
                    artifact_id="edit_viewer_scene_glb",
                    adapter=viewer_adapter,
                    runtime_status=viewer_runtime,
                    model_check=viewer_check,
                )
                executed_stages.append("viewer_check")
                state.updated_at = utc_now_iso()
                checkpoint_recorder.record_stage(
                    state,
                    workflow="blender-edit",
                    stage="viewer_check",
                    ok=bool(viewer_check.get("ok")),
                    node_name="workflow_runner.blender_edit.viewer_check",
                    metadata={
                        "viewer_glb": str(viewer_dir / "viewer_scene.glb"),
                        "runtime_ok": viewer_check.get("runtime", {}).get("ok")
                        if isinstance(viewer_check.get("runtime"), dict)
                        else None,
                    },
                )
            else:
                skipped_stages["viewer_check"] = "export_viewer_failed_or_missing_viewer_glb"
    else:
        skipped_stages["export_viewer"] = "not_requested"
        skipped_stages["viewer_check"] = "not_requested"

    ok = bool(edit_result.ok)
    if export_viewer and "export_viewer" not in skipped_stages:
        ok = ok and bool(export_summary and export_summary.get("ok"))
    if export_viewer and "viewer_check" not in skipped_stages:
        ok = ok and bool(viewer_check and viewer_check.get("ok"))

    summary = {
        "ok": ok,
        "dry_run": dry_run,
        "state_json_input": str(state_path),
        "output_dir": str(output_path),
        "domain_tool_name": domain_tool_name,
        "raw_caller_source": raw_caller_label,
        "requested_stages": ["blender_edit", "export_viewer", "viewer_check"] if export_viewer else ["blender_edit"],
        "executed_stages": executed_stages,
        "skipped_stages": skipped_stages,
        "single_project_state": True,
        "phase": state.phase.value,
        "artifact_ids": sorted(state.artifact_ids()),
        "tool_call_count": len(state.tool_call_log),
        "context_views": context_views,
        "blender_edit": edit_summary,
        "export_viewer": export_summary,
        "viewer_check": viewer_check,
        "state_json": str(output_path / "state.json"),
        "tool_call_log_json": str(output_path / "tool_call_log.json"),
    }
    _write_workflow_outputs(output_path, state, summary, checkpoint_recorder=checkpoint_recorder)
    return summary


def _run_compose_stage(
    *,
    state: AgentProjectState,
    artifact_store: FileArtifactStore,
    root_path: Path,
    scene_path: Path,
    asset_path: Path,
    compose_dir: Path,
    blender_path: str | Path | None,
    timeout_seconds: float,
    dry_run: bool,
) -> tuple[dict, AgentProjectState]:
    context_view_input = _typed_context_view_report(
        state=state,
        stage="compose",
        view="BlenderAssemblyPlannerContext",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        builder=lambda: build_blender_assembly_planner_context(
            state,
            tool_phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        ),
        extra_summary={
            "scene_artifact_id": "workflow_scene_glb",
            "subject_asset_artifact_id": "workflow_subject_glb",
        },
    )
    preview_png = compose_dir / "composed_preview.png"
    output_blend = compose_dir / "composed_scene.blend"
    assembly_plan = build_compose_scene_plan(state)
    assembly_plan_json = compose_dir / "assembly_plan.json"
    write_json(assembly_plan_json, model_to_dict(assembly_plan))
    result = ScriptDomainToolDispatcher(
        state=state,
        root=root_path,
        blender_path=blender_path,
    ).dispatch(
        "import_scene_asset",
        {
            "scene_glb": str(scene_path),
            "asset_glb": str(asset_path),
            "preview_png": str(preview_png),
            "output_blend": str(output_blend),
            "assembly_plan_json": str(assembly_plan_json),
        },
        options=CommandExecutionOptions(timeout_seconds=timeout_seconds, dry_run=dry_run),
    )

    if result.ok and not dry_run:
        preview_artifact_id = None
        blend_artifact_id = None
        if preview_png.exists():
            preview_artifact_id = "workflow_composed_preview_png"
            state.artifacts.append(
                artifact_store.register_file(
                    preview_png,
                    ArtifactType.BLENDER_PREVIEW_RENDER,
                    artifact_id=preview_artifact_id,
                    semantic_role="blender_preview_render",
                    metadata={"stage": "compose"},
                )
            )
        if output_blend.exists():
            blend_artifact_id = "workflow_composed_blend"
            state.artifacts.append(
                artifact_store.register_file(
                    output_blend,
                    ArtifactType.BLENDER_FILE,
                    artifact_id=blend_artifact_id,
                    semantic_role="authoritative_blend_file",
                    metadata={"stage": "compose"},
                )
            )
        if blend_artifact_id is not None:
            blender_scene = BlenderSceneState(
                blender_scene_id=output_blend.stem,
                blend_file_artifact_id=blend_artifact_id,
                preview_image_id=preview_artifact_id,
                scene_asset_id="workflow_scene_glb",
                version=1,
                last_synced_at=utc_now_iso(),
            )
            state = apply_state_updates(
                state,
                node_name="BlenderCommandExecutor",
                updates={"blender_scene": blender_scene},
            )

    summary = {
        "ok": result.ok,
        "dry_run": dry_run,
        "tool_call_status": result.tool_call_status,
        "tool_call_id": result.tool_call_id,
        "preview_png_exists": preview_png.exists(),
        "output_blend_exists": output_blend.exists(),
        "preview_png": str(preview_png),
        "output_blend": str(output_blend),
        "assembly_plan_json": str(assembly_plan_json),
        "assembly_plan": model_to_dict(assembly_plan),
        "context_view_input": context_view_input,
    }
    return summary, state


def _run_export_viewer_stage(
    *,
    state: AgentProjectState,
    artifact_store: FileArtifactStore,
    root_path: Path,
    input_blend: Path,
    viewer_dir: Path,
    blender_path: str | Path | None,
    timeout_seconds: float,
    viewer_adapter: ViewerRuntimeAdapter,
    artifact_prefix: str = "workflow",
) -> tuple[dict, AgentProjectState]:
    context_view_input = _state_context_view_report(
        state=state,
        stage="export_viewer",
        view="ScenePreviewExporterStateInput",
        phase=state.phase,
        required_state_fields=("blender_scene",),
        extra_summary={"input_blend": str(input_blend)},
    )
    viewer_glb = viewer_dir / "viewer_scene.glb"
    scene_state_json = viewer_dir / "scene_state.json"
    result = ScriptDomainToolDispatcher(
        state=state,
        root=root_path,
        blender_path=blender_path,
    ).dispatch(
        "export_viewer_scene",
        {
            "input_blend": str(input_blend),
            "viewer_glb": str(viewer_glb),
            "scene_state_json": str(scene_state_json),
        },
        options=CommandExecutionOptions(timeout_seconds=timeout_seconds, dry_run=False),
    )

    if result.ok:
        viewer_scene_artifact_id = f"{artifact_prefix}_viewer_scene_glb"
        viewer_state_artifact_id = f"{artifact_prefix}_scene_state_json"
        if scene_state_json.exists():
            patch_scene_state_artifact_ids(
                scene_state_json,
                viewer_scene_artifact_id=viewer_scene_artifact_id,
                viewer_state_artifact_id=viewer_state_artifact_id,
            )
        if viewer_glb.exists():
            state.artifacts.append(
                artifact_store.register_file(
                    viewer_glb,
                    ArtifactType.VIEWER_SCENE_GLB,
                    artifact_id=viewer_scene_artifact_id,
                    semantic_role="viewer_scene",
                    metadata={
                        "stage": "viewer_export",
                        "viewer": viewer_adapter.artifact_metadata(viewer_glb),
                    },
                )
            )
        if scene_state_json.exists():
            state.artifacts.append(
                artifact_store.register_file(
                    scene_state_json,
                    ArtifactType.VIEWER_SCENE_STATE_JSON,
                    artifact_id=viewer_state_artifact_id,
                    semantic_role="viewer_scene_state",
                    metadata={"stage": "viewer_export"},
                )
            )
            viewer_scene = ViewerSceneState(**json.loads(scene_state_json.read_text(encoding="utf-8")))
            state = apply_state_updates(
                state,
                node_name="ScenePreviewExporter",
                updates={
                    "viewer_scene": viewer_scene,
                    "phase": WorkflowPhase.BLENDER_PREVIEW,
                },
            )

    summary = {
        "ok": result.ok,
        "dry_run": False,
        "tool_call_status": result.tool_call_status,
        "tool_call_id": result.tool_call_id,
        "viewer_glb_exists": viewer_glb.exists(),
        "scene_state_json_exists": scene_state_json.exists(),
        "viewer_scene_object_count": len(state.viewer_scene.objects) if state.viewer_scene is not None else None,
        "viewer_glb": str(viewer_glb),
        "scene_state_json": str(scene_state_json),
        "context_view_input": context_view_input,
    }
    return summary, state


def _typed_context_view_report(
    *,
    state: AgentProjectState,
    stage: str,
    view: str,
    phase: WorkflowPhase,
    builder: Callable[[], Any],
    extra_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = _base_context_view_report(
        state=state,
        stage=stage,
        view=view,
        phase=phase,
        extra_summary=extra_summary,
    )
    try:
        context = builder()
    except MissingStateContextError as exc:
        report.update(
            {
                "available": False,
                "missing": str(exc),
                "summary": _state_context_summary(state, extra_summary=extra_summary),
            }
        )
        return report
    report.update(
        {
            "available": True,
            "missing": None,
            "summary": _context_model_summary(context, extra_summary=extra_summary),
        }
    )
    return report


def _state_context_view_report(
    *,
    state: AgentProjectState,
    stage: str,
    view: str,
    phase: WorkflowPhase,
    required_state_fields: tuple[str, ...],
    extra_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing_fields = [
        field_name
        for field_name in required_state_fields
        if not _state_field_present(getattr(state, field_name))
    ]
    report = _base_context_view_report(
        state=state,
        stage=stage,
        view=view,
        phase=phase,
        extra_summary=extra_summary,
    )
    report.update(
        {
            "available": not missing_fields,
            "missing": ", ".join(f"state.{field_name}" for field_name in missing_fields) or None,
            "required_state_fields": list(required_state_fields),
            "missing_state_fields": missing_fields,
            "summary": _state_context_summary(state, extra_summary=extra_summary),
        }
    )
    return report


def _base_context_view_report(
    *,
    state: AgentProjectState,
    stage: str,
    view: str,
    phase: WorkflowPhase,
    extra_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "view": view,
        "phase": phase.value,
        "allowed_domain_tools": allowed_tool_names(phase),
        "state_artifact_ids": sorted(state.artifact_ids()),
        "extra_summary_keys": sorted((extra_summary or {}).keys()),
    }


def _context_model_summary(context: Any, *, extra_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    data = model_to_dict(context)
    summary: dict[str, Any] = {}
    scene_spec = data.get("scene_spec")
    if isinstance(scene_spec, dict):
        summary["scene_id"] = scene_spec.get("scene_id")
        summary["scene_title"] = scene_spec.get("title")
        summary["scene_subject_count"] = len(scene_spec.get("subjects") or [])
    if "subject_assets" in data:
        summary["subject_asset_ids"] = [
            asset.get("asset_id")
            for asset in data.get("subject_assets") or []
            if isinstance(asset, dict) and asset.get("asset_id")
        ]
    scene_asset = data.get("scene_asset")
    if isinstance(scene_asset, dict):
        summary["scene_asset_id"] = scene_asset.get("scene_asset_id")
    if "latest_preview_image_id" in data:
        summary["latest_preview_image_id"] = data.get("latest_preview_image_id")
    if "latest_viewer_scene_id" in data:
        summary["latest_viewer_scene_id"] = data.get("latest_viewer_scene_id")
    if "allowed_domain_tools" in data:
        summary["context_allowed_domain_tools"] = data.get("allowed_domain_tools")
    if extra_summary:
        summary.update(extra_summary)
    return summary


def _state_context_summary(
    state: AgentProjectState,
    *,
    extra_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "project_id": state.project_id,
        "phase": state.phase.value,
        "artifact_ids": sorted(state.artifact_ids()),
        "subject_asset_ids": [asset.asset_id for asset in state.subject_assets],
        "has_scene_spec": state.scene_spec is not None,
        "has_scene_asset": state.scene_asset is not None,
        "has_blender_scene": state.blender_scene is not None,
        "has_viewer_scene": state.viewer_scene is not None,
        "tool_call_count": len(state.tool_call_log),
    }
    if state.blender_scene is not None:
        summary["blender_scene_id"] = state.blender_scene.blender_scene_id
        summary["blender_preview_image_id"] = state.blender_scene.preview_image_id
    if state.viewer_scene is not None:
        summary["viewer_scene_id"] = state.viewer_scene.viewer_scene_id
        summary["viewer_scene_artifact_id"] = state.viewer_scene.viewer_scene_artifact_id
    if extra_summary:
        summary.update(extra_summary)
    return summary


def _state_field_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (dict, list, set, tuple)):
        return bool(value)
    return True


def _normalize_stages(stages: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if stages is None:
        return WORKFLOW_STAGE_ORDER
    if isinstance(stages, str):
        values = tuple(part.strip() for part in stages.split(",") if part.strip())
    else:
        values = tuple(stages)
    if not values:
        raise ValueError("at least one workflow stage is required")
    unknown = [stage for stage in values if stage not in WORKFLOW_STAGE_ORDER]
    if unknown:
        raise ValueError(f"unknown workflow stages: {unknown}; allowed: {list(WORKFLOW_STAGE_ORDER)}")
    expected_prefix = WORKFLOW_STAGE_ORDER[: len(values)]
    if values != expected_prefix:
        raise ValueError(
            "workflow stages must be an ordered prefix of "
            f"{list(WORKFLOW_STAGE_ORDER)}; got {list(values)}"
        )
    return values


def _normalize_subject_asset_stages(stages: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if stages is None:
        return ("submit",)
    if isinstance(stages, str):
        values = tuple(part.strip() for part in stages.split(",") if part.strip())
    else:
        values = tuple(stages)
    if not values:
        raise ValueError("at least one subject asset workflow stage is required")
    unknown = [stage for stage in values if stage not in SUBJECT_ASSET_STAGE_ORDER]
    if unknown:
        raise ValueError(
            f"unknown subject asset workflow stages: {unknown}; allowed: {list(SUBJECT_ASSET_STAGE_ORDER)}"
        )
    positions = [SUBJECT_ASSET_STAGE_ORDER.index(stage) for stage in values]
    if positions != sorted(positions):
        raise ValueError(
            "subject asset workflow stages must follow "
            f"{list(SUBJECT_ASSET_STAGE_ORDER)} order; got {list(values)}"
        )
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate subject asset workflow stages: {list(values)}")
    return values


def _normalize_scene_asset_stages(stages: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if stages is None:
        return ("runtime_status",)
    if isinstance(stages, str):
        values = tuple(part.strip() for part in stages.split(",") if part.strip())
    else:
        values = tuple(stages)
    if not values:
        raise ValueError("at least one scene asset workflow stage is required")
    unknown = [stage for stage in values if stage not in SCENE_ASSET_STAGE_ORDER]
    if unknown:
        raise ValueError(f"unknown scene asset workflow stages: {unknown}; allowed: {list(SCENE_ASSET_STAGE_ORDER)}")
    positions = [SCENE_ASSET_STAGE_ORDER.index(stage) for stage in values]
    if positions != sorted(positions):
        raise ValueError(
            "scene asset workflow stages must follow "
            f"{list(SCENE_ASSET_STAGE_ORDER)} order; got {list(values)}"
        )
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate scene asset workflow stages: {list(values)}")
    return values


def _worldmirror_workspace_arg(value: str | Path | None) -> str | None:
    """Preserve service-relative WorldMirror workspaces while normalizing local absolute paths."""

    if value is None:
        return None
    text = str(value)
    path = Path(text).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    return text


def _normalize_codex_self_mcp_stages(stages: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if stages is None:
        return ("status", "plan_handoff")
    if isinstance(stages, str):
        values = tuple(part.strip() for part in stages.split(",") if part.strip())
    else:
        values = tuple(stages)
    if not values:
        raise ValueError("at least one codex-self-mcp workflow stage is required")
    unknown = [stage for stage in values if stage not in CODEX_SELF_MCP_STAGE_ORDER]
    if unknown:
        raise ValueError(
            f"unknown codex-self-mcp workflow stages: {unknown}; allowed: {list(CODEX_SELF_MCP_STAGE_ORDER)}"
        )
    positions = [CODEX_SELF_MCP_STAGE_ORDER.index(stage) for stage in values]
    if positions != sorted(positions):
        raise ValueError(
            "codex-self-mcp workflow stages must follow "
            f"{list(CODEX_SELF_MCP_STAGE_ORDER)} order; got {list(values)}"
        )
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate codex-self-mcp workflow stages: {list(values)}")
    return values


def _write_workflow_outputs(
    output_path: Path,
    state: AgentProjectState,
    summary: dict,
    *,
    checkpoint_recorder: _WorkflowCheckpointRecorder | None = None,
) -> None:
    recorder = checkpoint_recorder or _WorkflowCheckpointRecorder(output_path)
    checkpoint = recorder.record_final(state, output_path=output_path)
    summary["stage_checkpoints"] = recorder.stage_records
    summary["checkpoint"] = checkpoint
    summary["checkpoint_index_jsonl"] = str(recorder.store.index_path)
    summary["checkpoint_events_jsonl"] = str(recorder.store.events_path)
    frontend_status = build_frontend_status(state=state, summary=summary)
    summary["frontend_status_json"] = str(output_path / "frontend_status.json")
    write_json(output_path / "state.json", model_to_dict(state))
    write_json(
        output_path / "tool_call_log.json",
        {"tool_call_log": [model_to_dict(item) for item in state.tool_call_log]},
    )
    write_json(output_path / "frontend_status.json", model_to_dict(frontend_status))
    write_json(output_path / "summary.json", summary)
    if isinstance(summary.get("delivery_handoff"), dict):
        write_json(output_path / "delivery_handoff.json", summary["delivery_handoff"])


def _reset_known_outputs(output_path: Path) -> None:
    _reset_checkpoint_outputs(output_path)
    for relative in [
        "artifacts/artifacts.jsonl",
        "state.json",
        "tool_call_log.json",
        "summary.json",
        "frontend_status.json",
        "compose/composed_preview.png",
        "compose/composed_scene.blend",
        "compose/composed_scene.blend1",
        "viewer_export/viewer_scene.glb",
        "viewer_export/scene_state.json",
    ]:
        target = output_path / relative
        if target.exists():
            target.unlink()


def _reset_subject_asset_outputs(output_path: Path, output_glb_path: Path, *, reset_output_glb: bool) -> None:
    _reset_checkpoint_outputs(output_path)
    for relative in [
        "artifacts/artifacts.jsonl",
        "state.json",
        "tool_call_log.json",
        "summary.json",
        "frontend_status.json",
    ]:
        target = output_path / relative
        if target.exists():
            target.unlink()
    if reset_output_glb and output_glb_path.exists():
        output_glb_path.unlink()


def _reset_scene_asset_outputs(output_path: Path) -> None:
    _reset_checkpoint_outputs(output_path)
    for relative in [
        "artifacts/artifacts.jsonl",
        "state.json",
        "tool_call_log.json",
        "summary.json",
        "frontend_status.json",
    ]:
        target = output_path / relative
        if target.exists():
            target.unlink()


def _reset_delivery_package_outputs(output_path: Path, *, package_id: str | None) -> None:
    _reset_checkpoint_outputs(output_path)
    for relative in [
        "artifacts/artifacts.jsonl",
        "state.json",
        "tool_call_log.json",
        "summary.json",
        "frontend_status.json",
    ]:
        target = output_path / relative
        if target.exists():
            target.unlink()
    package_root = output_path / "package"
    if package_id is not None:
        targets = [package_root / package_id, package_root / f"{package_id}.zip"]
    else:
        targets = []
    for target in targets:
        if target.is_dir():
            import shutil

            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def _reset_review_patch_outputs(output_path: Path) -> None:
    _reset_checkpoint_outputs(output_path)
    for relative in [
        "state.json",
        "tool_call_log.json",
        "summary.json",
        "frontend_status.json",
    ]:
        target = output_path / relative
        if target.exists():
            target.unlink()


def _reset_concept_seed_outputs(output_path: Path) -> None:
    _reset_checkpoint_outputs(output_path)
    for relative in [
        "artifacts/artifacts.jsonl",
        "state.json",
        "tool_call_log.json",
        "summary.json",
        "frontend_status.json",
    ]:
        target = output_path / relative
        if target.exists():
            target.unlink()


def _reset_concept_regeneration_outputs(output_path: Path) -> None:
    _reset_checkpoint_outputs(output_path)
    for relative in [
        "artifacts/artifacts.jsonl",
        "state.json",
        "tool_call_log.json",
        "summary.json",
        "frontend_status.json",
    ]:
        target = output_path / relative
        if target.exists():
            target.unlink()


def _reset_codex_self_mcp_outputs(output_path: Path) -> None:
    _reset_checkpoint_outputs(output_path)
    for relative in [
        "state.json",
        "tool_call_log.json",
        "summary.json",
        "frontend_status.json",
        "codex_self_mcp_call.jsonl",
    ]:
        target = output_path / relative
        if target.exists():
            target.unlink()


def _reset_blender_edit_outputs(output_path: Path) -> None:
    _reset_checkpoint_outputs(output_path)
    for relative in [
        "artifacts/artifacts.jsonl",
        "state.json",
        "tool_call_log.json",
        "summary.json",
        "frontend_status.json",
        "viewer_export/viewer_scene.glb",
        "viewer_export/scene_state.json",
    ]:
        target = output_path / relative
        if target.exists():
            target.unlink()


def _reset_checkpoint_outputs(output_path: Path) -> None:
    checkpoint_root = output_path / "checkpoints"
    if checkpoint_root.exists():
        import shutil

        shutil.rmtree(checkpoint_root)


def _stage_checkpoint_reason(stage: str, *, ok: bool) -> str:
    if not ok:
        return f"{stage}_failed"
    return {
        "compose": "blender_assembly_execution_completed",
        "export_viewer": "viewer_scene_exported",
        "viewer_check": "viewer_scene_state_updated",
        "submit": "subject_asset_generation_submitted",
        "check_status": "subject_asset_status_checked",
        "save_completed": "subject_asset_generation_completed",
        "quality_check": "subject_asset_quality_checked",
        "repair_decision": "subject_asset_repair_decision_planned",
        "repair_execute": "subject_asset_repair_execution_handled",
        "runtime_status": "scene_generation_runtime_checked",
        "prepare_generation": "scene_generation_call_prepared",
        "upload_inputs": "scene_generation_inputs_upload_stage_completed",
        "poll_upload": "scene_generation_upload_poll_stage_completed",
        "submit_generation": "scene_generation_submit_stage_completed",
        "poll_generation": "scene_generation_poll_stage_completed",
        "inspect_output": "scene_asset_output_inspected",
        "save_generation": "scene_generation_saved",
        "register_existing_output": "scene_asset_adapted",
        "status": "codex_self_mcp_status_checked",
        "plan_handoff": "codex_self_mcp_handoff_planned",
        "execute_handoff": "codex_self_mcp_execute_stage_completed",
        "blender_edit": "blender_edit_applied",
        "delivery_package": "delivery_package_created",
        "review_patch": "review_patch_created",
        "seed_concept": "concept_seed_registered",
        "apply_review_patch": "review_patch_concept_regeneration_handled",
    }.get(stage, f"{stage}_completed")


def _resolve_input_blend(*, input_blend: str | Path | None, state: AgentProjectState) -> Path | None:
    if input_blend is not None:
        return Path(input_blend).expanduser().resolve()
    if state.blender_scene is None or not state.blender_scene.blend_file_artifact_id:
        return None
    blend_artifact_id = state.blender_scene.blend_file_artifact_id
    for artifact in state.artifacts:
        if artifact.artifact_id == blend_artifact_id:
            return Path(artifact.uri).expanduser().resolve()
    return None


def _unavailable_blender_mcp_raw_tool_caller(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError(
        "raw Blender MCP caller is not available in this Python process; "
        "run with dry_run=True or inject raw_tool_caller"
    )


def _without_none(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value is not None}


def _find_subject_asset(state: AgentProjectState, asset_id: str) -> Any:
    for asset in state.subject_assets:
        if asset.asset_id == asset_id:
            return asset
    return None


def _subject_asset_repair_execution_phase(decision_payload: Any) -> WorkflowPhase:
    if not isinstance(decision_payload, dict):
        return WorkflowPhase.SUBJECT_ASSET_QA
    action = decision_payload.get("action")
    if action == "retry_hunyuan3d":
        return WorkflowPhase.SUBJECT_ASSET_GENERATION
    if action == "regenerate_subject_image":
        return WorkflowPhase.CONCEPT_GENERATION
    return WorkflowPhase.SUBJECT_ASSET_QA


def _execute_subject_asset_repair_action(
    *,
    state: AgentProjectState,
    dispatcher: Hunyuan3DDomainToolDispatcher,
    asset: Asset3DRecord,
    decision_payload: dict[str, Any],
    image_path_value: Path | None,
    image_base64: str | None,
    options: CommandExecutionOptions,
    confirm_repair_execute: bool,
    remove_background: bool,
    texture: bool,
    seed: int,
    randomize_seed: bool,
    octree_resolution: int,
    num_inference_steps: int,
    guidance_scale: float,
    num_chunks: int,
    face_count: int,
) -> tuple[dict[str, Any], AgentProjectState]:
    """Handle a planned repair action without hiding live generation calls."""

    action = str(decision_payload.get("action") or "")
    base_summary: dict[str, Any] = {
        "ok": True,
        "dry_run": bool(options.dry_run),
        "confirmed": confirm_repair_execute,
        "asset_id": asset.asset_id,
        "subject_id": asset.subject_id,
        "source_image_id": asset.source_image_id,
        "action": action,
        "decision_reason": decision_payload.get("reason"),
        "decision_next_stage": decision_payload.get("next_stage"),
        "user_visible": bool(decision_payload.get("user_visible")),
        "requires_confirmation": False,
        "executed": False,
        "tool_call_id": None,
        "pending_action_id": None,
        "outputs": {},
    }

    if action == "accept":
        summary = {
            **base_summary,
            "status": "accepted",
            "reason": "repair_decision_accepted_asset",
            "next_stage": "BLENDER_ASSEMBLY_PLANNING",
        }
        state = _record_subject_asset_repair_execution(
            state=state,
            asset_id=asset.asset_id,
            execution_summary=summary,
            asset_status="succeeded",
        )
        return summary, state

    if action == "retry_hunyuan3d":
        source_image_path = _resolve_subject_source_image_path(
            state=state,
            asset=asset,
            image_path_value=image_path_value,
        )
        if source_image_path is None and image_base64 is None:
            summary = {
                **base_summary,
                "ok": False,
                "status": "blocked",
                "reason": "missing_subject_source_image",
                "next_stage": "SUBJECT_ASSET_GENERATION",
                "requires_confirmation": not bool(options.dry_run),
            }
            state = _record_subject_asset_repair_execution(
                state=state,
                asset_id=asset.asset_id,
                execution_summary=summary,
                asset_status="needs_regen",
            )
            return summary, state
        if not options.dry_run and not confirm_repair_execute:
            summary = {
                **base_summary,
                "ok": False,
                "status": "blocked",
                "reason": "repair_execution_requires_explicit_confirmation",
                "next_stage": "SUBJECT_ASSET_GENERATION",
                "requires_confirmation": True,
                "outputs": {
                    "source_image_path": str(source_image_path) if source_image_path is not None else None,
                    "has_image_base64": image_base64 is not None,
                },
            }
            state = _record_subject_asset_repair_execution(
                state=state,
                asset_id=asset.asset_id,
                execution_summary=summary,
                asset_status="needs_regen",
            )
            return summary, state

        state.phase = WorkflowPhase.SUBJECT_ASSET_GENERATION
        dispatcher.state = state
        retry_args = _without_none(
            {
                "operation": "submit_async",
                "asset_id": asset.asset_id,
                "subject_id": asset.subject_id,
                "source_image_id": asset.source_image_id,
                "image_path": str(source_image_path) if source_image_path is not None else None,
                "image_base64": image_base64,
                "remove_background": remove_background,
                "texture": texture,
                "seed": seed,
                "randomize_seed": randomize_seed,
                "octree_resolution": octree_resolution,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "num_chunks": num_chunks,
                "face_count": face_count,
                "repair_action": action,
                "repair_decision_created_at": decision_payload.get("created_at"),
            }
        )
        retry_result = dispatcher.dispatch("build_subject_asset", retry_args, options=options)
        state = dispatcher.state
        result_summary = _domain_result_summary(retry_result)
        summary = {
            **base_summary,
            "ok": bool(retry_result.ok),
            "status": "planned" if options.dry_run else "submitted",
            "reason": "hunyuan3d_retry_planned" if options.dry_run else "hunyuan3d_retry_submitted",
            "next_stage": "SUBJECT_ASSET_GENERATION",
            "requires_confirmation": not bool(options.dry_run),
            "executed": bool(retry_result.ok and not options.dry_run),
            "tool_call_id": retry_result.tool_call_id,
            "outputs": result_summary,
        }
        state = _record_subject_asset_repair_execution(
            state=state,
            asset_id=asset.asset_id,
            execution_summary=summary,
            asset_status="needs_regen" if options.dry_run else None,
        )
        return summary, state

    if action == "regenerate_subject_image":
        state.phase = WorkflowPhase.CONCEPT_GENERATION
        summary = {
            **base_summary,
            "status": "planned",
            "reason": "subject_concept_regeneration_required",
            "next_stage": "CONCEPT_GENERATION",
            "outputs": {
                "regenerates_source_image_id": asset.source_image_id,
                "executor": "future_concept_generation_stage",
            },
        }
        state = _record_subject_asset_repair_execution(
            state=state,
            asset_id=asset.asset_id,
            execution_summary=summary,
            asset_status="needs_regen",
        )
        return summary, state

    if action in {"ask_user", "manual_review"}:
        pending_action = PendingAction(
            action_id=f"pending_{uuid4().hex[:12]}",
            phase=WorkflowPhase.SUBJECT_ASSET_QA,
            action_type="ask_user_clarification" if action == "ask_user" else "surface_failed_asset",
            payload={
                "kind": "subject_asset_repair",
                "asset_id": asset.asset_id,
                "subject_id": asset.subject_id,
                "source_image_id": asset.source_image_id,
                "repair_decision": decision_payload,
            },
        )
        summary = {
            **base_summary,
            "status": "pending_action",
            "reason": "user_or_manual_review_required",
            "next_stage": "USER_REVIEW" if action == "ask_user" else "MANUAL_REVIEW",
            "pending_action_id": pending_action.action_id,
            "outputs": {"pending_action_type": pending_action.action_type},
        }
        state = _record_subject_asset_repair_execution(
            state=state,
            asset_id=asset.asset_id,
            execution_summary=summary,
            asset_status="uncertain",
            pending_action=pending_action,
        )
        return summary, state

    summary = {
        **base_summary,
        "ok": False,
        "status": "blocked",
        "reason": f"unsupported_repair_action:{action}",
        "next_stage": None,
    }
    state = _record_subject_asset_repair_execution(
        state=state,
        asset_id=asset.asset_id,
        execution_summary=summary,
    )
    return summary, state


def _resolve_subject_source_image_path(
    *,
    state: AgentProjectState,
    asset: Asset3DRecord,
    image_path_value: Path | None,
) -> Path | None:
    if image_path_value is not None and image_path_value.exists():
        return image_path_value
    candidate_ids = {asset.source_image_id}
    for artifact in state.artifacts:
        if artifact.artifact_id not in candidate_ids:
            continue
        path = Path(artifact.uri).expanduser().resolve()
        if path.exists() and path.is_file():
            return path
    return None


def _record_subject_asset_repair_execution(
    *,
    state: AgentProjectState,
    asset_id: str,
    execution_summary: dict[str, Any],
    asset_status: str | None = None,
    pending_action: PendingAction | None = None,
) -> AgentProjectState:
    updated_assets: list[Asset3DRecord] = []
    for asset in state.subject_assets:
        if asset.asset_id != asset_id:
            updated_assets.append(asset)
            continue
        payload = model_to_dict(asset)
        generation_params = dict(payload.get("generation_params") or {})
        generation_params["repair_execution"] = _redact_large_payloads(execution_summary)
        payload["generation_params"] = generation_params
        if asset_status is not None:
            payload["status"] = asset_status
        updated_assets.append(Asset3DRecord(**payload))

    updates: dict[str, Any] = {"subject_assets": updated_assets}
    if pending_action is not None:
        updates["pending_action"] = pending_action
    return apply_state_updates(
        state,
        node_name="SubjectAssetRepairRouter",
        updates=updates,
    )


def _domain_result_summary(result) -> dict:
    return {
        "ok": result.ok,
        "dry_run": result.dry_run,
        "tool_call_status": result.tool_call_status,
        "tool_call_id": result.tool_call_id,
        "arguments": _redact_large_payloads(result.arguments),
        "outputs": _redact_large_payloads(result.outputs),
    }


def _build_visual_qa_runner(
    *,
    subject_id: str,
    asset_id: str,
    llm_env_file: str | Path | None,
    dry_run: bool,
    timeout: float,
):
    env = load_agent_llm_env(llm_env_file)
    provider_configs = build_provider_configs(env=env)

    def run(source_image_path: Path, preview_image_path: Path):
        return run_subject_asset_visual_qa(
            request=SubjectAssetVisualQARequest(
                subject_id=subject_id,
                asset_id=asset_id,
                source_image_path=str(source_image_path),
                preview_image_path=str(preview_image_path),
            ),
            provider_configs=provider_configs,
            env=env,
            dry_run=dry_run,
            timeout=timeout,
        )

    return run


def _status_payload_has_model(status_payload: dict) -> bool:
    raw = status_payload.get("raw", {})
    data = raw.get("data") if isinstance(raw, dict) else None
    return isinstance(data, dict) and bool(data.get("model_base64"))


def _redact_large_payloads(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key in {"image", "image_base64", "model_base64"} and isinstance(item, str):
                redacted[key] = item if item.startswith("<base64:") else f"<base64:{len(item)} chars>"
            else:
                redacted[key] = _redact_large_payloads(item)
        return redacted
    if isinstance(value, list):
        return [_redact_large_payloads(item) for item in value]
    if isinstance(value, Path):
        return str(value.expanduser().resolve())
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    local_e2e = subparsers.add_parser("local-e2e")
    local_e2e.add_argument("--root", default="/home/team/zouzhiyuan/image23D_Agent")
    local_e2e.add_argument("--scene-glb", required=True)
    local_e2e.add_argument("--asset-glb", required=True)
    local_e2e.add_argument("--output-dir", required=True)
    local_e2e.add_argument("--scene-spec-json")
    local_e2e.add_argument("--blender-path")
    local_e2e.add_argument("--viewer-base-url", default="http://127.0.0.1:8092")
    local_e2e.add_argument("--compose-timeout", type=float, default=300)
    local_e2e.add_argument("--export-timeout", type=float, default=180)
    local_e2e.add_argument("--viewer-timeout", type=float, default=10)
    local_e2e.add_argument("--dry-run", action="store_true")
    local_e2e.add_argument("--no-reset-metadata", action="store_true")
    local_e2e.add_argument(
        "--stages",
        default=None,
        help="Comma-separated ordered prefix: compose, compose,export_viewer, or compose,export_viewer,viewer_check",
    )
    subject_asset = subparsers.add_parser("subject-asset")
    subject_asset.add_argument("--output-dir", required=True)
    subject_asset.add_argument("--subject-id", required=True)
    subject_asset.add_argument("--source-image-id", required=True)
    subject_asset.add_argument("--image-path")
    subject_asset.add_argument("--asset-id")
    subject_asset.add_argument("--job-id")
    subject_asset.add_argument("--output-glb")
    subject_asset.add_argument("--status-payload-json")
    subject_asset.add_argument("--hunyuan-base-url", default="http://127.0.0.1:8091")
    subject_asset.add_argument("--timeout", type=float, default=10)
    subject_asset.add_argument("--dry-run", action="store_true")
    subject_asset.add_argument("--no-reset-metadata", action="store_true")
    subject_asset.add_argument(
        "--stages",
        default=None,
        help=(
            "Comma-separated ordered subset: submit, check_status, save_completed, "
            "quality_check, repair_decision, repair_execute"
        ),
    )
    subject_asset.add_argument("--hunyuan-profile", dest="hunyuan_profile_id")
    subject_asset.add_argument("--seed", type=int, default=None)
    subject_asset.add_argument("--face-count", type=int, default=None)
    subject_asset.add_argument("--octree-resolution", type=int, default=None)
    subject_asset.add_argument("--num-inference-steps", type=int, default=None)
    subject_asset.add_argument("--guidance-scale", type=float, default=None)
    subject_asset.add_argument("--num-chunks", type=int, default=None)
    subject_asset.add_argument("--remove-background", action=argparse.BooleanOptionalAction, default=None)
    subject_asset.add_argument("--texture", action=argparse.BooleanOptionalAction, default=None)
    subject_asset.add_argument("--randomize-seed", action=argparse.BooleanOptionalAction, default=None)
    subject_asset.add_argument("--qa-render-preview", action="store_true")
    subject_asset.add_argument("--qa-root", default="/home/team/zouzhiyuan/image23D_Agent")
    subject_asset.add_argument("--qa-blender-path")
    subject_asset.add_argument("--qa-timeout", type=float, default=180)
    subject_asset.add_argument("--qa-visual-dry-run", action="store_true")
    subject_asset.add_argument("--qa-visual-live", action="store_true")
    subject_asset.add_argument("--llm-env-file", default="/home/team/zouzhiyuan/image23D_Agent/.env.agent_llm.local")
    subject_asset.add_argument("--qa-retry-count", type=int, default=0)
    subject_asset.add_argument("--qa-max-hunyuan-retries", type=int, default=1)
    subject_asset.add_argument("--qa-concept-regen-count", type=int, default=0)
    subject_asset.add_argument("--qa-max-concept-regens", type=int, default=1)
    subject_asset.add_argument("--qa-user-requested-review", action="store_true")
    subject_asset.add_argument(
        "--confirm-repair-execute",
        action="store_true",
        help="Allow non-dry-run repair_execute to submit an explicit Hunyuan3D retry when the decision requires it.",
    )
    scene_asset = subparsers.add_parser("scene-asset")
    scene_asset.add_argument("--output-dir", required=True)
    scene_asset.add_argument("--scene-asset-id", required=True)
    scene_asset.add_argument("--worldmirror-output-dir")
    scene_asset.add_argument("--worldmirror-input-files", default="", help="Comma-separated image/video files for generation preparation.")
    scene_asset.add_argument("--worldmirror-workspace-dir", help="Existing WorldMirror workspace directory for reconstruction preparation.")
    scene_asset.add_argument("--worldmirror-upload-event-id", help="Queued Gradio event id for poll_upload.")
    scene_asset.add_argument("--worldmirror-event-id", help="Queued Gradio event id for poll_generation.")
    scene_asset.add_argument("--worldmirror-event-api-name", default="gradio_demo")
    scene_asset.add_argument("--worldmirror-api-prefix", default="/gradio_api")
    scene_asset.add_argument("--source-scene-concept-image-ids", default="")
    scene_asset.add_argument("--source-prompt")
    scene_asset.add_argument("--time-interval", type=float, default=1.0)
    scene_asset.add_argument("--frame-selector", default="All")
    scene_asset.add_argument("--show-camera", action=argparse.BooleanOptionalAction, default=True)
    scene_asset.add_argument("--filter-sky-bg", action=argparse.BooleanOptionalAction, default=False)
    scene_asset.add_argument("--show-mesh", action=argparse.BooleanOptionalAction, default=True)
    scene_asset.add_argument("--filter-ambiguous", action=argparse.BooleanOptionalAction, default=True)
    scene_asset.add_argument("--worldmirror-base-url", default="http://127.0.0.1:8081")
    scene_asset.add_argument("--confirm-worldmirror-upload", action="store_true")
    scene_asset.add_argument("--confirm-worldmirror-upload-poll", action="store_true")
    scene_asset.add_argument("--confirm-worldmirror-submit", action="store_true")
    scene_asset.add_argument("--confirm-worldmirror-poll", action="store_true")
    scene_asset.add_argument("--timeout", type=float, default=10)
    scene_asset.add_argument("--dry-run", action="store_true")
    scene_asset.add_argument("--no-reset-metadata", action="store_true")
    scene_asset.add_argument(
        "--stages",
        default=None,
        help=(
            "Comma-separated ordered subset: runtime_status, prepare_generation, upload_inputs, poll_upload, "
            "submit_generation, poll_generation, inspect_output, save_generation, register_existing_output"
        ),
    )
    delivery_package = subparsers.add_parser("delivery-package")
    delivery_package.add_argument("--state-json", required=True)
    delivery_package.add_argument("--output-dir", required=True)
    delivery_package.add_argument("--package-id")
    delivery_package.add_argument("--no-reset-metadata", action="store_true")
    review_patch = subparsers.add_parser("review-patch")
    review_patch.add_argument("--state-json", required=True)
    review_patch.add_argument("--output-dir", required=True)
    review_patch.add_argument("--user-feedback")
    review_patch.add_argument("--user-feedback-file")
    review_patch.add_argument("--source-turn-id")
    review_patch.add_argument("--patch-id")
    review_patch.add_argument("--patch-type", default="redo_subject")
    review_patch.add_argument("--next-phase", default=WorkflowPhase.CONCEPT_REVIEW.value)
    review_patch.add_argument("--keep-pending-action", action="store_true")
    review_patch.add_argument("--no-reset-metadata", action="store_true")
    concept_seed = subparsers.add_parser("concept-seed")
    concept_seed.add_argument("--image-path", required=True)
    concept_seed.add_argument("--output-dir", required=True)
    concept_seed.add_argument("--subject-id", required=True)
    concept_seed.add_argument("--source-image-id", required=True)
    concept_seed.add_argument("--project-id", default="v1_real_demo")
    concept_seed.add_argument("--thread-id", default="local_real_demo")
    concept_seed.add_argument("--prompt")
    concept_seed.add_argument("--negative-prompt")
    concept_seed.add_argument("--approve", action=argparse.BooleanOptionalAction, default=True)
    concept_seed.add_argument("--copy-into-store", action=argparse.BooleanOptionalAction, default=True)
    concept_seed.add_argument("--no-reset-metadata", action="store_true")
    concept_regeneration = subparsers.add_parser("concept-regeneration")
    concept_regeneration.add_argument("--state-json", required=True)
    concept_regeneration.add_argument("--output-dir", required=True)
    concept_regeneration.add_argument("--patch-id")
    concept_regeneration.add_argument("--generated-image-path")
    concept_regeneration.add_argument("--generated-image-artifact-id")
    concept_regeneration.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    concept_regeneration.add_argument("--copy-into-store", action=argparse.BooleanOptionalAction, default=True)
    concept_regeneration.add_argument("--no-reset-metadata", action="store_true")
    codex_self = subparsers.add_parser("codex-self")
    codex_self.add_argument("--output-dir", required=True)
    codex_self.add_argument("--cwd", default="/home/team/zouzhiyuan/image23D_Agent")
    codex_self.add_argument("--prompt")
    codex_self.add_argument("--prompt-file")
    codex_self.add_argument("--sandbox", choices=["read-only", "workspace-write", "danger-full-access"], default="workspace-write")
    codex_self.add_argument("--approval-policy", choices=["untrusted", "on-failure", "on-request", "never"], default="never")
    codex_self.add_argument("--timeout", type=float, default=300)
    codex_self.add_argument("--log-path")
    codex_self.add_argument("--extract-last-image-to")
    codex_self.add_argument("--repo-path", default="/home/team/zouzhiyuan/codex-self-mcp")
    codex_self.add_argument("--codex-command", default="codex")
    codex_self.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    codex_self.add_argument("--confirm-execute", action="store_true")
    codex_self.add_argument("--no-reset-metadata", action="store_true")
    codex_self.add_argument(
        "--stages",
        default=None,
        help="Comma-separated ordered subset: status, plan_handoff, execute_handoff",
    )
    blender_edit = subparsers.add_parser("blender-edit")
    blender_edit.add_argument("--state-json", required=True)
    blender_edit.add_argument("--output-dir", required=True)
    blender_edit.add_argument("--tool", required=True, dest="domain_tool_name")
    blender_edit.add_argument("--arguments-json")
    blender_edit.add_argument("--arguments", default=None, help="Inline JSON object for domain tool arguments")
    blender_edit.add_argument(
        "--raw-caller",
        choices=["blender-lab-socket"],
        default=None,
        help="Explicit local raw MCP caller source for non-dry-run execution.",
    )
    blender_edit.add_argument("--dry-run", action="store_true")
    blender_edit.add_argument("--no-reset-metadata", action="store_true")
    blender_edit.add_argument("--root", default="/home/team/zouzhiyuan/image23D_Agent")
    blender_edit.add_argument("--blender-path")
    blender_edit.add_argument("--export-viewer", action="store_true")
    blender_edit.add_argument("--input-blend")
    blender_edit.add_argument("--viewer-base-url", default="http://127.0.0.1:8092")
    blender_edit.add_argument("--export-timeout", type=float, default=180)
    blender_edit.add_argument("--viewer-timeout", type=float, default=10)
    args = parser.parse_args()

    if args.command == "local-e2e":
        summary = run_local_e2e_workflow(
            root=args.root,
            scene_glb=args.scene_glb,
            asset_glb=args.asset_glb,
            output_dir=args.output_dir,
            blender_path=args.blender_path,
            viewer_base_url=args.viewer_base_url,
            compose_timeout_seconds=args.compose_timeout,
            export_timeout_seconds=args.export_timeout,
            viewer_timeout_seconds=args.viewer_timeout,
            dry_run=args.dry_run,
            reset_metadata=not args.no_reset_metadata,
            stages=args.stages,
            scene_spec_json=args.scene_spec_json,
        )
    elif args.command == "subject-asset":
        status_payload = None
        if args.status_payload_json:
            status_payload = json.loads(Path(args.status_payload_json).read_text(encoding="utf-8"))
        summary = run_subject_asset_workflow(
            output_dir=args.output_dir,
            subject_id=args.subject_id,
            source_image_id=args.source_image_id,
            image_path=args.image_path,
            asset_id=args.asset_id,
            job_id=args.job_id,
            output_glb=args.output_glb,
            status_payload=status_payload,
            hunyuan_base_url=args.hunyuan_base_url,
            timeout_seconds=args.timeout,
            dry_run=args.dry_run,
            reset_metadata=not args.no_reset_metadata,
            stages=args.stages,
            hunyuan_profile_id=args.hunyuan_profile_id,
            remove_background=args.remove_background,
            seed=args.seed,
            face_count=args.face_count,
            octree_resolution=args.octree_resolution,
            num_inference_steps=args.num_inference_steps,
            guidance_scale=args.guidance_scale,
            num_chunks=args.num_chunks,
            texture=args.texture,
            randomize_seed=args.randomize_seed,
            qa_render_preview=args.qa_render_preview,
            qa_root=args.qa_root,
            qa_blender_path=args.qa_blender_path,
            qa_timeout_seconds=args.qa_timeout,
            qa_visual_dry_run=args.qa_visual_dry_run,
            qa_visual_live=args.qa_visual_live,
            llm_env_file=args.llm_env_file,
            qa_retry_count=args.qa_retry_count,
            qa_max_hunyuan_retries=args.qa_max_hunyuan_retries,
            qa_concept_regen_count=args.qa_concept_regen_count,
            qa_max_concept_regens=args.qa_max_concept_regens,
            qa_user_requested_review=args.qa_user_requested_review,
            confirm_repair_execute=args.confirm_repair_execute,
        )
    elif args.command == "scene-asset":
        source_scene_concept_image_ids = [
            item.strip()
            for item in args.source_scene_concept_image_ids.split(",")
            if item.strip()
        ]
        worldmirror_input_files = [
            item.strip()
            for item in args.worldmirror_input_files.split(",")
            if item.strip()
        ]
        summary = run_scene_asset_workflow(
            output_dir=args.output_dir,
            scene_asset_id=args.scene_asset_id,
            worldmirror_output_dir=args.worldmirror_output_dir,
            worldmirror_input_files=worldmirror_input_files,
            worldmirror_workspace_dir=args.worldmirror_workspace_dir,
            worldmirror_upload_event_id=args.worldmirror_upload_event_id,
            worldmirror_event_id=args.worldmirror_event_id,
            worldmirror_event_api_name=args.worldmirror_event_api_name,
            worldmirror_api_prefix=args.worldmirror_api_prefix,
            source_scene_concept_image_ids=source_scene_concept_image_ids,
            source_prompt=args.source_prompt,
            time_interval=args.time_interval,
            frame_selector=args.frame_selector,
            show_camera=args.show_camera,
            filter_sky_bg=args.filter_sky_bg,
            show_mesh=args.show_mesh,
            filter_ambiguous=args.filter_ambiguous,
            worldmirror_base_url=args.worldmirror_base_url,
            confirm_worldmirror_upload=args.confirm_worldmirror_upload,
            confirm_worldmirror_upload_poll=args.confirm_worldmirror_upload_poll,
            confirm_worldmirror_submit=args.confirm_worldmirror_submit,
            confirm_worldmirror_poll=args.confirm_worldmirror_poll,
            timeout_seconds=args.timeout,
            dry_run=args.dry_run,
            reset_metadata=not args.no_reset_metadata,
            stages=args.stages,
        )
    elif args.command == "delivery-package":
        summary = run_delivery_package_workflow(
            state_json=args.state_json,
            output_dir=args.output_dir,
            package_id=args.package_id,
            reset_metadata=not args.no_reset_metadata,
        )
    elif args.command == "review-patch":
        if args.user_feedback_file:
            user_feedback = Path(args.user_feedback_file).read_text(encoding="utf-8")
        else:
            user_feedback = args.user_feedback
        if not user_feedback:
            parser.error("review-patch requires --user-feedback or --user-feedback-file")
        summary = run_review_patch_workflow(
            state_json=args.state_json,
            output_dir=args.output_dir,
            user_feedback=user_feedback,
            source_turn_id=args.source_turn_id,
            patch_id=args.patch_id,
            patch_type=args.patch_type,
            clear_pending_action=not args.keep_pending_action,
            next_phase=args.next_phase,
            reset_metadata=not args.no_reset_metadata,
        )
    elif args.command == "concept-seed":
        summary = run_concept_seed_workflow(
            image_path=args.image_path,
            output_dir=args.output_dir,
            subject_id=args.subject_id,
            source_image_id=args.source_image_id,
            project_id=args.project_id,
            thread_id=args.thread_id,
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            approve=args.approve,
            copy_into_store=args.copy_into_store,
            reset_metadata=not args.no_reset_metadata,
        )
    elif args.command == "concept-regeneration":
        if not args.dry_run and not args.generated_image_path:
            parser.error("concept-regeneration non-dry-run requires --generated-image-path")
        summary = run_concept_regeneration_workflow(
            state_json=args.state_json,
            output_dir=args.output_dir,
            patch_id=args.patch_id,
            generated_image_path=args.generated_image_path,
            generated_image_artifact_id=args.generated_image_artifact_id,
            dry_run=args.dry_run,
            copy_into_store=args.copy_into_store,
            reset_metadata=not args.no_reset_metadata,
        )
    elif args.command == "codex-self":
        if (args.prompt is None) == (args.prompt_file is None):
            requested_codex_stages = _normalize_codex_self_mcp_stages(args.stages)
            if "plan_handoff" in requested_codex_stages or "execute_handoff" in requested_codex_stages:
                parser.error("codex-self plan_handoff/execute_handoff requires exactly one of --prompt or --prompt-file")
        if not args.dry_run and "execute_handoff" in _normalize_codex_self_mcp_stages(args.stages) and not args.confirm_execute:
            parser.error("codex-self non-dry-run execute_handoff requires --confirm-execute")
        summary = run_codex_self_mcp_workflow(
            output_dir=args.output_dir,
            cwd=args.cwd,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
            sandbox=args.sandbox,
            approval_policy=args.approval_policy,
            timeout_seconds=args.timeout,
            log_path=args.log_path,
            extract_last_image_to=args.extract_last_image_to,
            repo_path=args.repo_path,
            codex_command=args.codex_command,
            dry_run=args.dry_run,
            confirm_execute=args.confirm_execute,
            reset_metadata=not args.no_reset_metadata,
            stages=args.stages,
        )
    elif args.command == "blender-edit":
        if not args.dry_run and args.raw_caller is None:
            parser.error("blender-edit CLI non-dry-run requires --raw-caller blender-lab-socket")
        if args.arguments_json and args.arguments:
            parser.error("use only one of --arguments-json or --arguments")
        edit_arguments = {}
        if args.arguments_json:
            edit_arguments = json.loads(Path(args.arguments_json).read_text(encoding="utf-8"))
        elif args.arguments:
            edit_arguments = json.loads(args.arguments)
        if not isinstance(edit_arguments, dict):
            parser.error("blender-edit arguments must be a JSON object")
        summary = run_blender_edit_workflow(
            state_json=args.state_json,
            output_dir=args.output_dir,
            domain_tool_name=args.domain_tool_name,
            arguments=edit_arguments,
            raw_caller_source=args.raw_caller,
            dry_run=args.dry_run,
            reset_metadata=not args.no_reset_metadata,
            root=args.root,
            blender_path=args.blender_path,
            export_viewer=args.export_viewer,
            input_blend=args.input_blend,
            viewer_base_url=args.viewer_base_url,
            export_timeout_seconds=args.export_timeout,
            viewer_timeout_seconds=args.viewer_timeout,
        )
    else:
        parser.error(
            "expected subcommand: local-e2e, subject-asset, scene-asset, delivery-package, "
            "review-patch, codex-self, or blender-edit"
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
