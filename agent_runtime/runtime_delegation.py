"""Runtime delegated-job handoff planning.

This module turns a recorded ``delegated`` execution row into a run-local JSON
handoff package for a background worker or sub-agent. It does not execute the
job; the purpose is to keep long model work outside the HTTP loop while
preserving exact input/output expectations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_runtime.runtime_dispatch import read_runtime_dispatch_plan
from agent_runtime.artifacts import utc_now_iso
from agent_runtime.runtime_execution import RuntimeJobExecutionRecord, read_runtime_execution_records
from agent_runtime.state import AgentProjectState, ConceptPromptPack


RuntimeHandoffStatus = Literal["planned", "skipped", "failed"]


class RuntimeDelegatedHandoffRecord(BaseModel):
    handoff_id: str
    execution_id: str | None = None
    job_id: str | None = None
    domain_tool_name: str | None = None
    executor: str | None = None
    status: RuntimeHandoffStatus
    ok: bool
    created_at: str
    handoff_json: str | None = None
    command_hint: str | None = None
    input_files: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    error: str | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)


class RuntimeDelegatedHandoffSummary(BaseModel):
    run_dir: str
    generated_at: str
    handoff_log_jsonl: str
    total_records: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    latest_record: RuntimeDelegatedHandoffRecord | None = None
    handed_off_execution_ids: list[str] = Field(default_factory=list)


class RuntimeDelegatedHandoffResult(BaseModel):
    ok: bool
    run_dir: str
    handoff_log_jsonl: str
    handoff_summary_json: str
    selected_execution_id: str | None = None
    record: RuntimeDelegatedHandoffRecord | None = None
    summary: RuntimeDelegatedHandoffSummary
    message: str | None = None
    issues: list[str] = Field(default_factory=list)


HANDOFF_DONE_STATUSES = {"planned", "skipped"}


def plan_next_delegated_handoff(run_dir: str | Path) -> RuntimeDelegatedHandoffResult:
    """Create a handoff package for the next delegated runtime execution."""

    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"state.json not found for runtime handoff: {state_path}")
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    records = read_runtime_handoff_records(path)
    handed_off = _handed_off_execution_ids(records)
    selected = _select_delegated_execution(read_runtime_execution_records(path), handed_off)
    if selected is None:
        summary = _write_handoff_summary(path, records)
        return RuntimeDelegatedHandoffResult(
            ok=True,
            run_dir=str(path),
            handoff_log_jsonl=str(_handoff_log_path(path)),
            handoff_summary_json=str(_handoff_summary_path(path)),
            summary=summary,
            message="no_unplanned_delegated_execution",
        )

    record = _create_handoff_record(path, state=state, execution=selected)
    _append_jsonl(_handoff_log_path(path), _model_to_dict(record))
    records.append(record)
    summary = _write_handoff_summary(path, records)
    return RuntimeDelegatedHandoffResult(
        ok=record.ok,
        run_dir=str(path),
        handoff_log_jsonl=str(_handoff_log_path(path)),
        handoff_summary_json=str(_handoff_summary_path(path)),
        selected_execution_id=selected.execution_id,
        record=record,
        summary=summary,
        message=record.status,
        issues=list(record.issues),
    )


def read_runtime_handoff_records(run_dir: str | Path, *, limit: int | None = None) -> list[RuntimeDelegatedHandoffRecord]:
    path = _handoff_log_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return []
    records = [
        RuntimeDelegatedHandoffRecord(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return records[-limit:] if limit is not None else records


def read_runtime_handoff_summary(run_dir: str | Path) -> dict[str, Any] | None:
    path = _handoff_summary_path(Path(run_dir).expanduser().resolve())
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _create_handoff_record(
    run_dir: Path,
    *,
    state: AgentProjectState,
    execution: RuntimeJobExecutionRecord,
) -> RuntimeDelegatedHandoffRecord:
    handoff_id = f"handoff_{uuid4().hex[:12]}"
    input_files = _input_files(run_dir)
    expected_outputs = _expected_outputs(execution)
    runtime_job = _runtime_job_snapshot(run_dir, execution.job_id)
    concept_generation = _concept_generation_handoff_payload(state, execution)
    subject_asset_generation = _subject_asset_generation_handoff_payload(
        state,
        execution,
        runtime_job=runtime_job,
    )
    scene_asset_generation = _scene_asset_generation_handoff_payload(
        state,
        execution,
        runtime_job=runtime_job,
    )
    selected_subject_concepts = _selected_subject_concept_prompt_snapshot(state)
    payload = {
        "handoff_id": handoff_id,
        "created_at": utc_now_iso(),
        "run_dir": str(run_dir),
        "execution": _model_to_dict(execution),
        "runtime_job": runtime_job,
        "state_summary": _state_summary(state),
        "input_files": input_files,
        "expected_outputs": expected_outputs,
        "task_prompt": _task_prompt(state, execution, concept_generation=concept_generation),
        "operator_notes": [
            "Do not mutate state.json directly; register outputs through the existing workflow/runtime apply path.",
            "Keep generated binaries under this run directory or its artifact store.",
            "Return a JSON summary with output paths, artifact ids, and any user-visible issues.",
        ],
    }
    if concept_generation is not None:
        payload["concept_generation"] = concept_generation
    if subject_asset_generation is not None:
        payload["subject_asset_generation"] = subject_asset_generation
    if scene_asset_generation is not None:
        payload["scene_asset_generation"] = scene_asset_generation
    if selected_subject_concepts:
        payload["selected_subject_concepts"] = selected_subject_concepts
    handoff_path = run_dir / "runtime_handoff" / f"{handoff_id}.json"
    _write_json(handoff_path, payload)
    return RuntimeDelegatedHandoffRecord(
        handoff_id=handoff_id,
        execution_id=execution.execution_id,
        job_id=execution.job_id,
        domain_tool_name=execution.domain_tool_name,
        executor=execution.executor,
        status="planned",
        ok=True,
        created_at=payload["created_at"],
        handoff_json=str(handoff_path),
        command_hint=execution.result_summary.get("command_hint") or execution.result_summary.get("reason"),
        input_files=input_files,
        expected_outputs=expected_outputs,
        result_summary={
            "task_type": execution.domain_tool_name or execution.job_kind,
            "phase": execution.phase.value,
            "subject_count": len(state.scene_spec.subjects) if state.scene_spec is not None else 0,
            "has_prompt_pack": state.concept_bundle is not None and state.concept_bundle.prompt_pack is not None,
            "has_runtime_job_snapshot": payload["runtime_job"] is not None,
            "concept_requirement_count": len(concept_generation.get("requirements", [])) if concept_generation else 0,
            "selected_subject_concept_count": len(selected_subject_concepts),
            "subject_asset_source_count": (
                len(subject_asset_generation.get("source_subject_concepts", []))
                if subject_asset_generation
                else 0
            ),
            "scene_asset_source_count": (
                len(scene_asset_generation.get("source_scene_images", []))
                if scene_asset_generation
                else 0
            ),
        },
    )


def _runtime_job_snapshot(run_dir: Path, job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    payload = read_runtime_dispatch_plan(run_dir)
    jobs = payload.get("runtime_plan", {}).get("jobs", []) if isinstance(payload, dict) else []
    for job in jobs:
        if job.get("job_id") == job_id:
            return job
    return None


def _input_files(run_dir: Path) -> list[str]:
    candidates = [
        run_dir / "state.json",
        run_dir / "runtime_plan.json",
        run_dir / "runtime_execution.jsonl",
        run_dir / "runtime_apply.jsonl",
        run_dir / "runtime_asset_action.jsonl",
        run_dir / "runtime_asset_action_summary.json",
        run_dir / "frontend_status.json",
    ]
    return [str(path) for path in candidates if path.exists()]


def _expected_outputs(execution: RuntimeJobExecutionRecord) -> list[str]:
    if execution.domain_tool_name in {"generate_concept_images", "regenerate_concept_images"}:
        return [
            "one image result per ConceptImageRequirement, unless a requirement is explicitly blocked with an issue",
            "subject concept image(s) registered as SUBJECT_CONCEPT_IMAGE",
            "scene concept image(s) registered as SCENE_CONCEPT_IMAGE",
            "target render registered as FINAL_PREVIEW_IMAGE after source_requirement_ids resolve to real image files",
            "generation log showing each MCP/image call and the actual input image paths uploaded",
            "updated state/checkpoint/frontend_status through the existing handoff-apply workflow",
        ]
    if execution.domain_tool_name == "build_subject_asset":
        return [
            "subject GLB file(s) under subject_assets/",
            "updated Asset3DRecord entries",
            "subject asset QA or retry decision evidence",
        ]
    if execution.domain_tool_name == "build_scene_asset":
        return [
            "scene/world GLB or adapter output directory",
            "updated Scene3DRecord",
            "service event ids and polling evidence",
        ]
    return list(execution.required_outputs) or ["worker JSON summary"]


def _task_prompt(
    state: AgentProjectState,
    execution: RuntimeJobExecutionRecord,
    *,
    concept_generation: dict[str, Any] | None = None,
) -> str:
    if execution.domain_tool_name in {"generate_concept_images", "regenerate_concept_images"}:
        prompt_pack = state.concept_bundle.prompt_pack if state.concept_bundle is not None else None
        prompt = prompt_pack.final_preview_prompt if prompt_pack is not None else ""
        subject_prompts = prompt_pack.subject_prompts if prompt_pack is not None else {}
        prompt_inputs = {
            "scene_spec": _scene_spec_prompt_snapshot(state),
            "reference_images": _input_image_prompt_snapshot(state),
            "reference_bindings": _reference_binding_prompt_snapshot(state),
            "final_preview_prompt": prompt,
            "subject_prompts": subject_prompts,
            "scene_prompts": prompt_pack.scene_prompts if prompt_pack is not None else [],
            "image_requirements": (
                [requirement.model_dump(mode="json") for requirement in prompt_pack.image_requirements]
                if prompt_pack is not None
                else []
            ),
            "concept_generation": concept_generation,
            "expected_subject_ids": (
                [subject.subject_id for subject in state.scene_spec.subjects]
                if state.scene_spec is not None
                else []
            ),
            "runtime_job_id": execution.job_id,
        }
        return (
            "You are a bounded concept-image worker for the image23D Blender scene agent.\n"
            "\n"
            "Task:\n"
            "- Execute the ConceptImageRequirement list below, in execution_order.\n"
            "- For subject_concept requirements, generate subject-only source images with neutral or studio backgrounds.\n"
            "- For scene_concept requirements, generate scene-only environment/layout images with no hero subjects.\n"
            "- For target_render requirements, first resolve every source_requirement_id to the previously generated "
            "subject/scene concept image file, then attach those files as visual inputs for a high-artistry composite render.\n"
            "- Use every resolved input_reference_image_ids file as an actual uploaded/attached image input to the MCP/image tool; "
            "do not merely mention the reference in text.\n"
            "- Record each MCP/image call with requirement_id, prompt, input image paths, output path, and issues.\n"
            "\n"
            "Hard boundaries:\n"
            "- Do not edit state.json, summary.json, frontend_status.json, runtime_plan.json, or any runtime logs.\n"
            "- Do not run Blender, Hunyuan3D, HY-World, model conversion, package, or viewer-export commands.\n"
            "- Do not create a parallel artifact store, queue, schema, or state file.\n"
            "- If the MCP/image tool cannot attach the required image inputs for a requirement, mark that requirement blocked "
            "with a clear issue instead of inventing a fake file path or silently degrading to text-only generation.\n"
            "\n"
            "Final assistant response after the image call:\n"
            "Return only compact JSON with keys: ok, generated_image_count, blocked_requirement_ids, image_results, "
            "generation_calls_jsonl, notes, issues. Each image_results item must include image_path, output_type, "
            "requirement_id, target_id, subject_id when applicable, artifact_id suggestion, and metadata.input_image_paths.\n"
            "\n"
            "Inputs JSON:\n"
            f"{json.dumps(prompt_inputs, ensure_ascii=False, indent=2, sort_keys=True)}"
        )
    if execution.domain_tool_name == "build_subject_asset":
        subjects = []
        if state.scene_spec is not None:
            subjects = [subject.model_dump(mode="json") for subject in state.scene_spec.subjects]
        concept_bundle = state.concept_bundle
        prompt_inputs = {
            "scene_spec": _scene_spec_prompt_snapshot(state),
            "subjects": subjects,
            "concept_bundle": (
                {
                    "approved": concept_bundle.approved,
                    "final_preview_image_id": concept_bundle.final_preview_image_id,
                    "subject_concept_images": concept_bundle.subject_concept_images,
                    "scene_concept_image_ids": concept_bundle.scene_concept_image_ids,
                    "concept_version": concept_bundle.concept_version,
                }
                if concept_bundle is not None
                else None
            ),
            "concept_artifacts": _artifact_prompt_snapshot(state, semantic_role="subject_concept_image"),
            "selected_subject_concepts": _selected_subject_concept_prompt_snapshot(state),
            "runtime_execution": {
                "job_id": execution.job_id,
                "domain_tool_name": execution.domain_tool_name,
                "result_summary": execution.result_summary,
                "required_outputs": execution.required_outputs,
            },
        }
        return (
            "You are a bounded subject-asset worker for the image23D Blender scene agent.\n"
            "\n"
            "Task:\n"
            "- Generate or submit 3D subject GLB assets for the SceneSpec subjects below.\n"
            "- Use selected_subject_concepts as the source image input for Hunyuan3D when present; otherwise use the approved concept image artifact URI(s).\n"
            "- Prefer the runtime job's Hunyuan3D profile/command hint; keep profile overrides explicit in your result.\n"
            "- If live generation is submitted asynchronously, return the service job id and status evidence.\n"
            "- If a completed GLB is available, return the GLB path, asset id, subject id, and QA evidence for handoff-apply.\n"
            "\n"
            "Hard boundaries:\n"
            "- Do not edit state.json, summary.json, frontend_status.json, runtime_plan.json, or runtime logs directly.\n"
            "- Do not create a parallel artifact store, queue, schema, or state file.\n"
            "- Keep generated binaries under this run directory or its subject_assets/artifacts folders.\n"
            "- Use the existing workflow_runner/Hunyuan3D service path; do not invent another Hunyuan client.\n"
            "\n"
            "Final assistant response:\n"
            "Return compact JSON with keys: ok, submitted, job_id, asset_results, qa, notes, issues.\n"
            "\n"
            "Inputs JSON:\n"
            f"{json.dumps(prompt_inputs, ensure_ascii=False, indent=2, sort_keys=True)}"
        )
    if execution.domain_tool_name == "build_scene_asset":
        prompt_inputs = {
            "scene_spec": _scene_spec_prompt_snapshot(state),
            "concept_bundle": (
                {
                    "approved": state.concept_bundle.approved,
                    "final_preview_image_id": state.concept_bundle.final_preview_image_id,
                    "scene_concept_image_ids": state.concept_bundle.scene_concept_image_ids,
                    "concept_version": state.concept_bundle.concept_version,
                }
                if state.concept_bundle is not None
                else None
            ),
            "source_scene_images": _scene_asset_source_image_prompt_snapshot(state),
            "active_assembly_selection": _active_assembly_selection_prompt_snapshot(state),
            "runtime_execution": {
                "job_id": execution.job_id,
                "domain_tool_name": execution.domain_tool_name,
                "result_summary": execution.result_summary,
                "required_outputs": execution.required_outputs,
            },
        }
        return (
            "You are a bounded scene-asset worker for the image23D Blender scene agent.\n"
            "\n"
            "Task:\n"
            "- Generate, submit, or register a scene/world asset for the SceneSpec environment below.\n"
            "- Prefer source_scene_images in priority order; active assembly selections override older concept artifacts.\n"
            "- Use scene_concept images for environment/layout and target_render images only as composition guidance.\n"
            "- Do not use subject_concept images as scene-service inputs unless they are already part of an explicitly selected target_render.\n"
            "- If live generation is submitted asynchronously, return service job ids and polling/status evidence.\n"
            "\n"
            "Hard boundaries:\n"
            "- Do not edit state.json, summary.json, frontend_status.json, runtime_plan.json, or runtime logs directly.\n"
            "- Do not create a parallel artifact store, queue, schema, or state file.\n"
            "- Use the existing HY-World/WorldMirror or scene asset registration path; do not invent a second scene service client.\n"
            "\n"
            "Final assistant response:\n"
            "Return compact JSON with keys: ok, submitted, job_id, scene_asset_results, notes, issues.\n"
            "\n"
            "Inputs JSON:\n"
            f"{json.dumps(prompt_inputs, ensure_ascii=False, indent=2, sort_keys=True)}"
        )
    return f"Execute delegated runtime job {execution.job_id} for domain tool {execution.domain_tool_name}."


def _concept_generation_handoff_payload(
    state: AgentProjectState,
    execution: RuntimeJobExecutionRecord,
) -> dict[str, Any] | None:
    if execution.domain_tool_name not in {"generate_concept_images", "regenerate_concept_images"}:
        return None
    prompt_pack = state.concept_bundle.prompt_pack if state.concept_bundle is not None else None
    if prompt_pack is None:
        return {
            "ok": False,
            "issues": ["missing_concept_prompt_pack"],
            "requirements": [],
            "execution_order": [],
        }

    requirements = [
        _concept_requirement_handoff_item(state, prompt_pack, requirement)
        for requirement in prompt_pack.image_requirements
    ]
    return {
        "ok": True,
        "scene_spec": _scene_spec_prompt_snapshot(state),
        "reference_images": _input_image_prompt_snapshot(state),
        "reference_bindings": _reference_binding_prompt_snapshot(state),
        "requirements": requirements,
        "execution_order": [item["requirement_id"] for item in requirements],
        "mcp_upload_rules": [
            "Attach every resolved_input_images[].uri for image_guided requirements.",
            "For multi_image_composite requirements, resolve source_requirement_ids to generated output paths from earlier requirements and attach them.",
            "A requirement with must_use_image_inputs=true is blocked if its input images cannot be attached.",
        ],
        "apply_result_schema": {
            "image_results": [
                {
                    "image_path": "absolute path to generated image",
                    "output_type": "subject_concept | scene_concept | target_render",
                    "requirement_id": "ConceptImageRequirement.requirement_id",
                    "target_id": "ConceptImageRequirement.target_id",
                    "subject_id": "subject id for subject_concept only, otherwise null",
                    "artifact_id": "stable suggested artifact id",
                    "final_preview": "true only for target_render or intentionally selected preview",
                    "metadata": {
                        "input_reference_image_ids": [],
                        "input_image_paths": [],
                        "source_requirement_ids": [],
                        "prompt_key": "ConceptImageRequirement.prompt_key",
                    },
                }
            ]
        },
    }


def _concept_requirement_handoff_item(
    state: AgentProjectState,
    prompt_pack: ConceptPromptPack,
    requirement: Any,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement.requirement_id,
        "output_type": requirement.output_type,
        "target_id": requirement.target_id,
        "prompt_key": requirement.prompt_key,
        "prompt": _prompt_text_for_requirement(prompt_pack, requirement.prompt_key),
        "negative_prompt": prompt_pack.negative_prompt,
        "user_review_label": requirement.user_review_label,
        "purpose": requirement.purpose,
        "generation_mode": requirement.generation_mode,
        "input_reference_image_ids": list(requirement.input_reference_image_ids),
        "resolved_input_images": _resolved_input_images(state, requirement.input_reference_image_ids),
        "source_requirement_ids": list(requirement.source_requirement_ids),
        "source_requirements": [
            _source_requirement_summary(prompt_pack, source_id)
            for source_id in requirement.source_requirement_ids
        ],
        "must_use_image_inputs": requirement.must_use_image_inputs,
        "quality_bar": requirement.quality_bar,
        "blocked_if": _concept_requirement_blockers(state, prompt_pack, requirement),
    }


def _prompt_text_for_requirement(prompt_pack: ConceptPromptPack, prompt_key: str) -> str:
    if prompt_key == "final_preview_prompt":
        return prompt_pack.final_preview_prompt
    if prompt_key.startswith("subject_prompts."):
        subject_id = prompt_key.removeprefix("subject_prompts.")
        return prompt_pack.subject_prompts.get(subject_id, "")
    if prompt_key.startswith("scene_prompts."):
        index_text = prompt_key.removeprefix("scene_prompts.")
        try:
            index = int(index_text)
        except ValueError:
            return ""
        if 0 <= index < len(prompt_pack.scene_prompts):
            return prompt_pack.scene_prompts[index]
    return ""


def _resolved_input_images(state: AgentProjectState, image_ids: list[str]) -> list[dict[str, Any]]:
    inputs_by_id = {image.image_id: image for image in state.input_images}
    resolved = []
    for image_id in image_ids:
        image = inputs_by_id.get(image_id)
        if image is None:
            resolved.append({"image_id": image_id, "uri": None, "exists": False, "issue": "input_image_not_found"})
            continue
        path = Path(image.uri).expanduser()
        resolved.append(
            {
                "image_id": image.image_id,
                "artifact_id": image.artifact_id,
                "uri": image.uri,
                "mime_type": image.mime_type,
                "user_declared_label": image.user_declared_label,
                "notes": image.notes,
                "exists": path.exists(),
            }
        )
    return resolved


def _source_requirement_summary(prompt_pack: ConceptPromptPack, requirement_id: str) -> dict[str, Any]:
    for requirement in prompt_pack.image_requirements:
        if requirement.requirement_id == requirement_id:
            return {
                "requirement_id": requirement.requirement_id,
                "output_type": requirement.output_type,
                "target_id": requirement.target_id,
                "prompt_key": requirement.prompt_key,
                "must_be_generated_before_use": True,
            }
    return {
        "requirement_id": requirement_id,
        "issue": "source_requirement_not_found",
        "must_be_generated_before_use": True,
    }


def _concept_requirement_blockers(
    state: AgentProjectState,
    prompt_pack: ConceptPromptPack,
    requirement: Any,
) -> list[str]:
    blockers = []
    resolved_images = _resolved_input_images(state, requirement.input_reference_image_ids)
    for image in resolved_images:
        if not image.get("exists"):
            blockers.append(f"missing_input_reference_file:{image.get('image_id')}")
    requirement_ids = {item.requirement_id for item in prompt_pack.image_requirements}
    for source_id in requirement.source_requirement_ids:
        if source_id not in requirement_ids:
            blockers.append(f"missing_source_requirement:{source_id}")
    return blockers


def _subject_asset_generation_handoff_payload(
    state: AgentProjectState,
    execution: RuntimeJobExecutionRecord,
    *,
    runtime_job: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if execution.domain_tool_name != "build_subject_asset":
        return None
    tool_arguments = _runtime_job_tool_arguments(runtime_job)
    subject_ids = _subject_ids_for_subject_asset_generation(state, tool_arguments)
    selected = _selected_subject_concept_prompt_snapshot(state)
    return {
        "ok": True,
        "subject_ids": subject_ids,
        "selected_subject_concepts": selected,
        "source_subject_concepts": _subject_concept_inputs_prompt_snapshot(
            state,
            subject_ids=subject_ids,
            selected=selected,
        ),
        "hunyuan3d_profile": _runtime_job_metadata(runtime_job).get("hunyuan3d_profile"),
        "profile_id": (
            runtime_job.get("profile_id")
            if runtime_job is not None
            else execution.result_summary.get("profile_id")
        ),
        "tool_arguments": tool_arguments,
        "mcp_upload_rules": [
            "Use the selected_subject_concepts entry for each subject when present.",
            "Pass the selected concept artifact URI/path as the Hunyuan3D image input.",
            "If a selected concept URI is missing or the file cannot be uploaded, block the subject instead of falling back silently.",
        ],
        "apply_result_schema": {
            "asset_results": [
                {
                    "glb_path": "absolute path to generated GLB",
                    "subject_id": "SceneSpec subject_id",
                    "asset_id": "stable suggested subject asset id",
                    "source_image_id": "selected concept artifact id used for Hunyuan3D",
                    "service_job_id": "optional live service job id",
                    "metadata": {
                        "hunyuan3d_profile_id": "runtime profile id",
                        "selected_concept_artifact_id": "artifact id used as input",
                    },
                }
            ]
        },
    }


def _scene_asset_generation_handoff_payload(
    state: AgentProjectState,
    execution: RuntimeJobExecutionRecord,
    *,
    runtime_job: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if execution.domain_tool_name != "build_scene_asset":
        return None
    tool_arguments = _runtime_job_tool_arguments(runtime_job)
    return {
        "ok": True,
        "scene_id": state.scene_spec.scene_id if state.scene_spec is not None else None,
        "environment": (
            state.scene_spec.environment.model_dump(mode="json")
            if state.scene_spec is not None and state.scene_spec.environment is not None
            else None
        ),
        "source_scene_images": _scene_asset_source_image_prompt_snapshot(state),
        "active_assembly_selection": _active_assembly_selection_prompt_snapshot(state),
        "tool_arguments": tool_arguments,
        "mcp_upload_rules": [
            "Prefer active_assembly_selection.selected_scene_concept_image_id when present.",
            "Prefer active_assembly_selection.selected_target_render_image_id as composition guidance when present.",
            "Do not treat subject concept images as scene-generation inputs unless explicitly selected as target_render sources.",
        ],
        "apply_result_schema": {
            "scene_asset_results": [
                {
                    "output_dir": "absolute path to HY-World/WorldMirror output directory",
                    "scene_asset_id": "stable scene asset id",
                    "source_scene_concept_image_ids": [],
                    "source_prompt": "scene generation prompt or selected scene prompt",
                    "service_job_id": "optional live service job id",
                    "metadata": {
                        "selected_scene_concept_image_id": "optional artifact id",
                        "selected_target_render_image_id": "optional artifact id",
                    },
                }
            ]
        },
    }


def _state_summary(state: AgentProjectState) -> dict[str, Any]:
    return {
        "project_id": state.project_id,
        "thread_id": state.thread_id,
        "phase": state.phase.value,
        "scene_id": state.scene_spec.scene_id if state.scene_spec is not None else None,
        "subject_ids": [subject.subject_id for subject in state.scene_spec.subjects] if state.scene_spec is not None else [],
        "concept_version": state.concept_bundle.concept_version if state.concept_bundle is not None else None,
        "has_prompt_pack": state.concept_bundle is not None and state.concept_bundle.prompt_pack is not None,
    }


def _scene_spec_prompt_snapshot(state: AgentProjectState) -> dict[str, Any] | None:
    if state.scene_spec is None:
        return None
    scene = state.scene_spec
    return {
        "scene_id": scene.scene_id,
        "title": scene.title,
        "user_goal": scene.user_goal,
        "style": scene.style.model_dump(mode="json") if scene.style is not None else None,
        "environment": scene.environment.model_dump(mode="json") if scene.environment is not None else None,
        "lighting": scene.lighting.model_dump(mode="json") if scene.lighting is not None else None,
        "camera": scene.camera.model_dump(mode="json") if scene.camera is not None else None,
        "subjects": [subject.model_dump(mode="json") for subject in scene.subjects],
    }


def _input_image_prompt_snapshot(state: AgentProjectState) -> list[dict[str, Any]]:
    return [
        {
            "image_id": image.image_id,
            "uri": image.uri,
            "user_declared_label": image.user_declared_label,
            "notes": image.notes,
        }
        for image in state.input_images
    ]


def _reference_binding_prompt_snapshot(state: AgentProjectState) -> list[dict[str, Any]]:
    return [
        {
            "image_id": binding.image_id,
            "target_type": binding.target_type,
            "target_id": binding.target_id,
            "usage": binding.usage,
            "confidence": binding.confidence,
            "notes": binding.notes,
        }
        for binding in state.reference_bindings
    ]


def _artifact_prompt_snapshot(state: AgentProjectState, *, semantic_role: str | None = None) -> list[dict[str, Any]]:
    artifacts = state.artifacts
    if semantic_role is not None:
        artifacts = [artifact for artifact in artifacts if artifact.semantic_role == semantic_role]
    return [
        {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type.value,
            "uri": artifact.uri,
            "mime_type": artifact.mime_type,
            "semantic_role": artifact.semantic_role,
            "linked_subject_id": artifact.linked_subject_id,
            "size_bytes": artifact.size_bytes,
            "sha256": artifact.sha256,
            "metadata": artifact.metadata,
        }
        for artifact in artifacts
    ]


def _selected_subject_concept_prompt_snapshot(state: AgentProjectState) -> list[dict[str, Any]]:
    artifacts_by_id = {artifact.artifact_id: artifact for artifact in state.artifacts}
    output = []
    for item in state.asset_library:
        if item.asset_kind != "subject_concept":
            continue
        if item.selection_status != "selected_for_model_generation":
            continue
        artifact = artifacts_by_id.get(item.artifact_id)
        output.append(
            {
                "subject_id": item.subject_id,
                "artifact_id": item.artifact_id,
                "uri": artifact.uri if artifact is not None else None,
                "mime_type": artifact.mime_type if artifact is not None else None,
                "review_status": item.review_status,
                "selection_status": item.selection_status,
                "requirement_id": item.requirement_id,
                "source_artifact_ids": list(item.source_artifact_ids),
                "user_notes": item.user_notes,
                "metadata": dict(item.metadata),
            }
        )
    return output


def _subject_ids_for_subject_asset_generation(
    state: AgentProjectState,
    tool_arguments: dict[str, Any],
) -> list[str]:
    payload_ids = tool_arguments.get("subject_ids")
    if isinstance(payload_ids, list):
        return [str(item) for item in payload_ids if item]
    if state.scene_spec is None:
        return []
    return [
        subject.subject_id
        for subject in state.scene_spec.subjects
        if subject.needs_3d_asset and subject.asset_strategy in {"hunyuan3d_img2asset", "existing_asset"}
    ]


def _subject_concept_inputs_prompt_snapshot(
    state: AgentProjectState,
    *,
    subject_ids: list[str],
    selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    subject_id_set = set(subject_ids)
    selected_by_subject = {
        item.get("subject_id"): item
        for item in selected
        if item.get("subject_id")
    }
    output: list[dict[str, Any]] = []
    for subject_id in subject_ids:
        selected_item = selected_by_subject.get(subject_id)
        if selected_item is not None:
            output.append({**selected_item, "source_priority": "selected_for_model_generation"})
            continue
        for artifact in state.artifacts:
            if artifact.artifact_type.value != "SUBJECT_CONCEPT_IMAGE":
                continue
            if artifact.linked_subject_id != subject_id:
                continue
            output.append(
                {
                    "subject_id": subject_id,
                    "artifact_id": artifact.artifact_id,
                    "uri": artifact.uri,
                    "mime_type": artifact.mime_type,
                    "semantic_role": artifact.semantic_role,
                    "metadata": dict(artifact.metadata),
                    "source_priority": "approved_or_available_concept_artifact",
                }
            )
    if output or subject_id_set:
        return output
    return [
        {
            "subject_id": artifact.linked_subject_id,
            "artifact_id": artifact.artifact_id,
            "uri": artifact.uri,
            "mime_type": artifact.mime_type,
            "semantic_role": artifact.semantic_role,
            "metadata": dict(artifact.metadata),
            "source_priority": "available_concept_artifact",
        }
        for artifact in state.artifacts
        if artifact.artifact_type.value == "SUBJECT_CONCEPT_IMAGE"
    ]


def _scene_asset_source_image_prompt_snapshot(state: AgentProjectState) -> list[dict[str, Any]]:
    preferred_ids: list[tuple[str, str]] = []
    selection = state.active_assembly_selection
    if selection is not None:
        if selection.selected_scene_concept_image_id:
            preferred_ids.append((selection.selected_scene_concept_image_id, "active_assembly_selection.scene_concept"))
        if selection.selected_target_render_image_id:
            preferred_ids.append((selection.selected_target_render_image_id, "active_assembly_selection.target_render"))
    for item in state.asset_library:
        if item.asset_kind not in {"scene_concept", "target_render"}:
            continue
        if item.selection_status not in {"selected_for_scene_generation", "selected_for_assembly"}:
            continue
        preferred_ids.append((item.artifact_id, f"asset_library.{item.selection_status}"))

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact_id, source_priority in preferred_ids:
        if artifact_id in seen:
            continue
        seen.add(artifact_id)
        output.append(_artifact_source_image_item(state, artifact_id, source_priority=source_priority))

    if output:
        return output

    concept = state.concept_bundle
    fallback_ids: list[tuple[str, str]] = []
    if concept is not None:
        fallback_ids.extend((artifact_id, "concept_bundle.scene_concept") for artifact_id in concept.scene_concept_image_ids)
        if concept.final_preview_image_id:
            fallback_ids.append((concept.final_preview_image_id, "concept_bundle.target_render"))
    for artifact_id, source_priority in fallback_ids:
        if artifact_id in seen:
            continue
        seen.add(artifact_id)
        output.append(_artifact_source_image_item(state, artifact_id, source_priority=source_priority))
    return output


def _artifact_source_image_item(
    state: AgentProjectState,
    artifact_id: str,
    *,
    source_priority: str,
) -> dict[str, Any]:
    artifact = _artifact_by_id(state, artifact_id)
    item = _asset_library_item_by_artifact_id(state, artifact_id)
    return {
        "artifact_id": artifact_id,
        "uri": artifact.uri if artifact is not None else None,
        "mime_type": artifact.mime_type if artifact is not None else None,
        "artifact_type": artifact.artifact_type.value if artifact is not None else None,
        "semantic_role": artifact.semantic_role if artifact is not None else None,
        "asset_kind": item.asset_kind if item is not None else None,
        "review_status": item.review_status if item is not None else None,
        "selection_status": item.selection_status if item is not None else None,
        "requirement_id": item.requirement_id if item is not None else None,
        "source_priority": source_priority,
        "metadata": dict(artifact.metadata) if artifact is not None else {},
    }


def _active_assembly_selection_prompt_snapshot(state: AgentProjectState) -> dict[str, Any] | None:
    selection = state.active_assembly_selection
    if selection is None:
        return None
    return selection.model_dump(mode="json") if hasattr(selection, "model_dump") else selection.dict()


def _runtime_job_tool_arguments(runtime_job: dict[str, Any] | None) -> dict[str, Any]:
    if runtime_job is None:
        return {}
    arguments = runtime_job.get("tool_arguments")
    return dict(arguments) if isinstance(arguments, dict) else {}


def _runtime_job_metadata(runtime_job: dict[str, Any] | None) -> dict[str, Any]:
    if runtime_job is None:
        return {}
    metadata = runtime_job.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _artifact_by_id(state: AgentProjectState, artifact_id: str) -> Any | None:
    for artifact in state.artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    return None


def _asset_library_item_by_artifact_id(state: AgentProjectState, artifact_id: str) -> Any | None:
    for item in state.asset_library:
        if item.artifact_id == artifact_id:
            return item
    return None


def _select_delegated_execution(
    records: list[RuntimeJobExecutionRecord],
    handed_off_execution_ids: set[str],
) -> RuntimeJobExecutionRecord | None:
    for record in records:
        if record.execution_id in handed_off_execution_ids:
            continue
        if record.status == "delegated":
            return record
    return None


def _write_handoff_summary(run_dir: Path, records: list[RuntimeDelegatedHandoffRecord]) -> RuntimeDelegatedHandoffSummary:
    counts: dict[str, int] = {}
    handed_off_ids = []
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
        if record.status in HANDOFF_DONE_STATUSES and record.execution_id:
            handed_off_ids.append(record.execution_id)
    summary = RuntimeDelegatedHandoffSummary(
        run_dir=str(run_dir),
        generated_at=utc_now_iso(),
        handoff_log_jsonl=str(_handoff_log_path(run_dir)),
        total_records=len(records),
        status_counts=counts,
        latest_record=records[-1] if records else None,
        handed_off_execution_ids=handed_off_ids,
    )
    _write_json(_handoff_summary_path(run_dir), _model_to_dict(summary))
    return summary


def _handed_off_execution_ids(records: list[RuntimeDelegatedHandoffRecord]) -> set[str]:
    return {record.execution_id for record in records if record.execution_id and record.status in HANDOFF_DONE_STATUSES}


def _handoff_log_path(run_dir: Path) -> Path:
    return run_dir / "runtime_handoff.jsonl"


def _handoff_summary_path(run_dir: Path) -> Path:
    return run_dir / "runtime_handoff_summary.json"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
