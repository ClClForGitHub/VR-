#!/usr/bin/env python3
"""Run Round04 scripted user samples through the runtime boundary.

Default mode is contract-only and never counts as live acceptance. Use
``--live`` after service preflight to attempt real provider/service calls.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
from pathlib import Path
from typing import Any

from agent_runtime.agent_prompts import ConceptPromptPlannerOutput
from agent_runtime.artifacts import utc_now_iso
from agent_runtime.concept_image_execution import ConceptImageBackend
from agent_runtime.concept_planning import apply_concept_prompt_planner_output
from agent_runtime.frontend_status import build_frontend_status
from agent_runtime.persistence import FileStateCheckpointStore
from agent_runtime.reference_intake import ReferenceBindingPlan, build_reference_intake_result
from agent_runtime.round04_live_samples import (
    Round04CaseManifest,
    Round04ReferenceImage,
    Round04ScriptedUserAction,
    load_round04_case_manifests,
    round04_case_run_dir,
    validate_round04_case_manifests,
    write_round04_case_reports,
)
from agent_runtime.runtime_console import append_console_message, save_console_upload
from agent_runtime.runtime_delegation import plan_next_delegated_handoff
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.runtime_execution import execute_next_runtime_job
from agent_runtime.runtime_runs import build_runtime_run_bundle
from agent_runtime.runtime_worker import execute_next_runtime_worker
from agent_runtime.state import (
    AgentProjectState,
    CameraSpec,
    ConceptImageRequirement,
    EnvironmentSpec,
    LightingSpec,
    ReferenceBinding,
    ReviewPatch,
    SceneInterpreterContext,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    UserTurn,
    WorkflowPhase,
)
from agent_runtime.state_views import apply_state_updates


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES_ROOT = ROOT / "tests/fixtures/live_user_samples/round04"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs/runs/round04_live_user_samples"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-root", default=str(DEFAULT_FIXTURES_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--case", dest="case_id")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-concept-regens", type=int, default=2)
    parser.add_argument("--seeded-scene-spec", action="store_true")
    parser.add_argument("--live-llm-intake", action="store_true")
    args = parser.parse_args()

    fixtures_root = Path(args.fixtures_root).expanduser().resolve()
    validation = validate_round04_case_manifests(fixtures_root)
    if not validation.ok:
        print(json.dumps({"ok": False, "issues": validation.issues}, ensure_ascii=False, indent=2))
        return 2

    loaded = load_round04_case_manifests(fixtures_root)
    if args.all:
        selected = loaded
    elif args.case_id:
        selected = [(case_dir, manifest) for case_dir, manifest in loaded if manifest.case_id == args.case_id]
        if not selected:
            print(json.dumps({"ok": False, "issues": [f"unknown_case:{args.case_id}"]}, ensure_ascii=False))
            return 2
    else:
        print(json.dumps({"ok": False, "issues": ["pass --case or --all"]}, ensure_ascii=False))
        return 2

    results = []
    for case_dir, manifest in selected:
        result = run_case(
            case_dir=case_dir,
            manifest=manifest,
            output_root=Path(args.output_root).expanduser().resolve(),
            live=args.live,
            overwrite=args.overwrite,
            max_concept_regens=args.max_concept_regens,
            seeded_scene_spec=args.seeded_scene_spec or not args.live_llm_intake,
            live_llm_intake=args.live_llm_intake,
        )
        results.append(result)
    ok = all(item["status"] in {"completed", "partial"} for item in results) if args.live else all(item["status"] in {"blocked", "partial"} for item in results)
    print(json.dumps({"ok": ok, "live": args.live, "case_count": len(results), "results": results}, ensure_ascii=False, indent=2))
    return 0 if ok or not args.live else 1


def run_case(
    *,
    case_dir: Path,
    manifest: Round04CaseManifest,
    output_root: Path,
    live: bool,
    overwrite: bool,
    max_concept_regens: int,
    seeded_scene_spec: bool = True,
    live_llm_intake: bool = False,
    concept_image_backend: ConceptImageBackend | None = None,
) -> dict[str, Any]:
    run_dir = round04_case_run_dir(output_root=output_root, case_id=manifest.case_id)
    if run_dir.exists():
        if not overwrite:
            raise FileExistsError(f"run_dir already exists, pass --overwrite: {run_dir}")
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    shutil.copy2(case_dir / "user_script.md", run_dir / "user_script.md")
    shutil.copy2(case_dir / "case_manifest.json", run_dir / "case_manifest.json")
    (run_dir / "runtime_console").mkdir(exist_ok=True)

    issues: list[str] = []
    state = _initial_state(manifest)
    _write_json(run_dir / "state.json", _model_to_dict(state))
    summary = {
        "ok": True,
        "workflow": "round04-live-user-samples",
        "dry_run": not live,
        "requested_stages": [
            "sample_ingestion",
            "reference_upload_binding",
            "scene_spec",
            "concept_prompt_pack",
            "live_generation",
            "subject_asset_generation",
            "scene_asset_generation",
            "blender_assembly",
        ],
        "executed_stages": ["sample_ingestion"],
        "skipped_stages": {},
        "max_concept_regens": max_concept_regens,
        "intake_mode": "live_llm_intake" if live_llm_intake else "seeded_scene_spec",
        "seeded_scene_spec": seeded_scene_spec,
    }
    _write_json(run_dir / "summary.json", summary)
    _write_frontend_status(run_dir)

    runtime_image_ids: dict[str, str] = {}
    _simulate_initial_request(run_dir, case_dir=case_dir, manifest=manifest, runtime_image_ids=runtime_image_ids)
    _prepare_concept_round(
        run_dir,
        manifest=manifest,
        runtime_image_ids=runtime_image_ids,
        visible_subject_ids=_visible_subject_ids_through_action(manifest, action_index=-1),
    )

    if live:
        if live_llm_intake:
            issues.append("live_llm_intake_not_executed_provider_unavailable_or_not_wired")
        applied_rounds = 0
        concept_regens = 0
        initial_result = _run_live_concept_worker(
            run_dir,
            concept_image_backend=concept_image_backend,
        )
        _record_live_concept_worker(run_dir, initial_result, trigger="initial_request", action_index=None)
        issues.extend(initial_result["issues"])
        if initial_result["concept_generation_applied"]:
            applied_rounds += 1
            _append_stage(run_dir, "live_generation")
        else:
            status = "blocked"

        if initial_result["concept_generation_applied"]:
            for action_index, action in enumerate(manifest.scripted_user_actions):
                message_id = _simulate_scripted_user_action(
                    run_dir,
                    case_dir=case_dir,
                    manifest=manifest,
                    action=action,
                    action_index=action_index,
                    runtime_image_ids=runtime_image_ids,
                )
                if _action_approves_concept(action):
                    _apply_concept_approval(run_dir, action=action)
                    continue
                if not _action_requests_concept_regeneration(action):
                    continue
                if concept_regens >= max_concept_regens:
                    issues.append(f"max_concept_regens_reached:{manifest.case_id}:{action_index + 1}")
                    continue
                concept_regens += 1
                _append_review_patch(run_dir, action=action, action_index=action_index, source_turn_id=message_id)
                _prepare_concept_round(
                    run_dir,
                    manifest=manifest,
                    runtime_image_ids=runtime_image_ids,
                    visible_subject_ids=_visible_subject_ids_through_action(manifest, action_index=action_index),
                )
                live_result = _run_live_concept_worker(
                    run_dir,
                    concept_image_backend=concept_image_backend,
                )
                _record_live_concept_worker(run_dir, live_result, trigger=action.action, action_index=action_index)
                issues.extend(live_result["issues"])
                if live_result["concept_generation_applied"]:
                    applied_rounds += 1
                    _mark_pending_review_patches_applied(run_dir)
                    _append_stage(run_dir, "live_generation")
                else:
                    break

        if applied_rounds:
            issues.append("live_execution_blocked: downstream Hunyuan3D/HY-World/Blender stages are not started by the Round04 concept-only runner")
            status = "partial"
        else:
            status = "blocked"
    else:
        issues.append("contract_only_run_live_services_not_requested")
        _write_contract_generation_records(run_dir, manifest=manifest)
        status = "blocked"

    _write_json(run_dir / "runtime_api_bundle_snapshot.json", _model_to_dict(build_runtime_run_bundle(run_dir)))
    report = write_round04_case_reports(
        case_dir=case_dir,
        manifest=manifest,
        run_dir=run_dir,
        status=status,
        issues=issues,
    )
    return {
        "case_id": manifest.case_id,
        "status": report.status,
        "run_dir": str(run_dir),
        "issues": report.issues,
    }


def _run_live_concept_worker(
    run_dir: Path,
    *,
    concept_image_backend: ConceptImageBackend | None,
) -> dict[str, Any]:
    issues = []
    execution = execute_next_runtime_job(run_dir, dry_run=False)
    if not execution.ok or execution.record is None:
        issues.extend(execution.issues or ["runtime_execution_did_not_select_concept_job"])
    elif execution.record.status != "delegated":
        issues.append(f"runtime_execution_not_delegated:{execution.record.status}")

    handoff = plan_next_delegated_handoff(run_dir)
    if not handoff.ok or handoff.record is None:
        issues.extend(handoff.issues or ["runtime_handoff_not_created"])
        return {
            "ok": False,
            "concept_generation_applied": False,
            "execution": _model_to_dict(execution),
            "handoff": _model_to_dict(handoff),
            "worker": None,
            "live_generation_calls_jsonl": str(run_dir / "live_generation_calls.jsonl"),
            "issues": issues,
        }

    worker = execute_next_runtime_worker(
        run_dir,
        backend="live_image",
        dry_run=False,
        confirm_execute=True,
        concept_image_backend=concept_image_backend,
        timeout_seconds=900,
    )
    applied = bool(worker.record is not None and worker.record.status == "applied" and worker.ok)
    if not applied:
        issues.extend(worker.issues or ["live_image_worker_did_not_apply_concept_results"])
    return {
        "ok": applied,
        "concept_generation_applied": applied,
        "execution": _model_to_dict(execution),
        "handoff": _model_to_dict(handoff),
        "worker": _model_to_dict(worker),
        "live_generation_calls_jsonl": str(run_dir / "live_generation_calls.jsonl"),
        "issues": issues,
    }


def _initial_state(manifest: Round04CaseManifest) -> AgentProjectState:
    now = utc_now_iso()
    return AgentProjectState(
        project_id=manifest.case_id,
        thread_id="round04_live_user_samples",
        phase=WorkflowPhase.INTAKE,
        created_at=now,
        updated_at=now,
    )


def _simulate_initial_request(
    run_dir: Path,
    *,
    case_dir: Path,
    manifest: Round04CaseManifest,
    runtime_image_ids: dict[str, str],
) -> None:
    initial_images = [image for image in manifest.reference_images if image.upload_stage == "initial_request"]
    initial_attachments = _upload_stage_images(run_dir, case_dir, manifest, initial_images, runtime_image_ids)
    append_console_message(
        run_dir,
        role="user",
        text=manifest.initial_user_request,
        attachment_ids=initial_attachments,
        metadata={"round04_case_id": manifest.case_id, "stage": "initial_request", "chronological_turn": 1},
    )
    _write_frontend_status(run_dir)


def _simulate_scripted_user_action(
    run_dir: Path,
    *,
    case_dir: Path,
    manifest: Round04CaseManifest,
    action: Round04ScriptedUserAction,
    action_index: int,
    runtime_image_ids: dict[str, str],
) -> str:
    attachments = _upload_stage_images(
        run_dir,
        case_dir,
        manifest,
        [image for image in manifest.reference_images if image.image_id in action.reference_image_ids],
        runtime_image_ids,
    )
    message = append_console_message(
        run_dir,
        role="user",
        text=action.text,
        attachment_ids=attachments,
        metadata={
            "round04_case_id": manifest.case_id,
            "gate": action.gate,
            "action": action.action,
            "expected_next_phase": action.expected_next_phase,
            "chronological_turn": action_index + 2,
        },
    )
    _write_frontend_status(run_dir)
    return message.message_id


def _prepare_concept_round(
    run_dir: Path,
    *,
    manifest: Round04CaseManifest,
    runtime_image_ids: dict[str, str],
    visible_subject_ids: set[str],
) -> None:
    _apply_reference_bindings(run_dir, manifest=manifest, runtime_image_ids=runtime_image_ids)
    _apply_scene_spec(
        run_dir,
        manifest=manifest,
        runtime_image_ids=runtime_image_ids,
        visible_subject_ids=visible_subject_ids,
    )
    _apply_prompt_pack(run_dir, manifest=manifest)
    build_and_save_runtime_dispatch_plan(run_dir)
    _append_stage(run_dir, "reference_upload_binding")
    _append_stage(run_dir, "scene_spec")
    _append_stage(run_dir, "concept_prompt_pack")


def _record_live_concept_worker(
    run_dir: Path,
    live_result: dict[str, Any],
    *,
    trigger: str,
    action_index: int | None,
) -> None:
    state = _read_state(run_dir)
    summary = _read_json(run_dir / "summary.json") or {}
    round_record = {
        "trigger": trigger,
        "action_index": action_index,
        "concept_version": state.concept_bundle.concept_version if state.concept_bundle is not None else None,
        "concept_generation_applied": live_result["concept_generation_applied"],
        "worker_status": (live_result.get("worker") or {}).get("record", {}).get("status"),
        "artifact_ids": (live_result.get("worker") or {}).get("record", {}).get("applied_artifact_ids", []),
        "issues": list(live_result.get("issues") or []),
    }
    summary.setdefault("live_concept_workers", []).append(live_result)
    summary.setdefault("concept_rounds", []).append(round_record)
    summary["live_concept_worker"] = live_result
    _write_json(run_dir / "summary.json", summary)
    _write_frontend_status(run_dir)


def _simulate_user_turns_and_uploads(
    run_dir: Path,
    *,
    case_dir: Path,
    manifest: Round04CaseManifest,
) -> dict[str, str]:
    runtime_image_ids: dict[str, str] = {}
    images_by_stage: dict[str, list[Round04ReferenceImage]] = {}
    for image in manifest.reference_images:
        images_by_stage.setdefault(image.upload_stage, []).append(image)

    initial_attachments = _upload_stage_images(run_dir, case_dir, manifest, images_by_stage.get("initial_request", []), runtime_image_ids)
    append_console_message(
        run_dir,
        role="user",
        text=manifest.initial_user_request,
        attachment_ids=initial_attachments,
        metadata={"round04_case_id": manifest.case_id, "stage": "initial_request"},
    )
    for action in manifest.scripted_user_actions:
        attachments = _upload_stage_images(
            run_dir,
            case_dir,
            manifest,
            [image for image in manifest.reference_images if image.image_id in action.reference_image_ids],
            runtime_image_ids,
        )
        append_console_message(
            run_dir,
            role="user",
            text=action.text,
            attachment_ids=attachments,
            metadata={
                "round04_case_id": manifest.case_id,
                "gate": action.gate,
                "action": action.action,
                "expected_next_phase": action.expected_next_phase,
            },
        )
    _write_frontend_status(run_dir)
    return runtime_image_ids


def _upload_stage_images(
    run_dir: Path,
    case_dir: Path,
    manifest: Round04CaseManifest,
    images: list[Round04ReferenceImage],
    runtime_image_ids: dict[str, str],
) -> list[str]:
    attachment_ids = []
    for image in images:
        if image.image_id in runtime_image_ids:
            attachment_ids.append(runtime_image_ids[image.image_id])
            continue
        path = manifest.reference_path(case_dir, image)
        result = save_console_upload(
            run_dir,
            filename=path.name,
            content=path.read_bytes(),
            mime_type=_guess_image_mime(path),
        )
        if result.image_id is None:
            raise ValueError(f"upload did not create image_id: {path}")
        runtime_image_ids[image.image_id] = result.image_id
        attachment_ids.append(result.image_id)
    return attachment_ids


def _guess_image_mime(path: Path) -> str | None:
    suffix = path.suffix.lower()
    explicit = {
        ".avif": "image/avif",
        ".bmp": "image/bmp",
        ".gif": "image/gif",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    if suffix in explicit:
        return explicit[suffix]
    guessed = mimetypes.guess_type(path.name)[0]
    return guessed if guessed and guessed.startswith("image/") else guessed


def _apply_reference_bindings(
    run_dir: Path,
    *,
    manifest: Round04CaseManifest,
    runtime_image_ids: dict[str, str],
) -> None:
    state = _read_state(run_dir)
    plans = []
    for image in manifest.reference_images:
        runtime_image_id = runtime_image_ids.get(image.image_id)
        if runtime_image_id is None:
            continue
        plans.append(
            ReferenceBindingPlan(
                image_id=runtime_image_id,
                target_type=image.declared_target_type,
                target_id=image.declared_target_id,
                usage=image.usage,
                explicit_in_user_text=True,
                confidence=1.0,
                source_text_span=image.source_text_span,
                notes=image.notes or f"Round04 manifest {image.slot} -> {image.declared_target_id}",
            )
        )
    result = build_reference_intake_result(
        user_text=manifest.initial_user_request,
        input_images=state.input_images,
        declared_bindings=plans,
        require_all_images_bound=True,
    )
    if not result.ok:
        raise ValueError(";".join(result.issues))
    updated = apply_state_updates(
        state,
        node_name="Round04ReferenceBindingIngestor",
        updates={"reference_bindings": _merge_reference_bindings(state.reference_bindings, result.reference_bindings)},
    )
    _persist_control_update(run_dir, updated, stage="reference_upload_binding", node_name="Round04ReferenceBindingIngestor")


def _apply_scene_spec(
    run_dir: Path,
    *,
    manifest: Round04CaseManifest,
    runtime_image_ids: dict[str, str],
    visible_subject_ids: set[str] | None = None,
) -> None:
    state = _read_state(run_dir)
    scene_reference_ids = [
        runtime_image_ids[image.image_id]
        for image in manifest.reference_images
        if image.image_id in runtime_image_ids and image.declared_target_type in {"scene", "layout"}
    ]
    subject_specs = []
    for subject in manifest.expected_subjects:
        if visible_subject_ids is not None and subject.subject_id not in visible_subject_ids:
            continue
        reference_ids = [runtime_image_ids[image_id] for image_id in subject.reference_image_ids if image_id in runtime_image_ids]
        subject_specs.append(
            SubjectSpec(
                subject_id=subject.subject_id,
                display_name=subject.display_name,
                source_text_span=subject.display_name,
                category=subject.category,  # type: ignore[arg-type]
                description=f"Round04 expected subject: {subject.display_name}",
                reference_image_ids=reference_ids,
                needs_2d_concept=True,
                needs_3d_asset=subject.needs_3d_asset,
                asset_strategy="hunyuan3d_img2asset" if subject.needs_3d_asset else "scene_service_component",
            )
        )
    scene_spec = SceneSpec(
        scene_id=f"scene_{manifest.case_id}",
        title=manifest.title,
        user_goal=manifest.initial_user_request,
        style=StyleSpec(style_keywords=[manifest.category], rendering_style=manifest.category),
        environment=EnvironmentSpec(
            environment_type=manifest.category,
            description=manifest.expected_scene,
            scene_reference_image_ids=scene_reference_ids,
        ),
        lighting=LightingSpec(description="Follow user sample lighting and scene mood."),
        camera=CameraSpec(shot_type="full_scene", framing="show all requested subjects and environment"),
        subjects=subject_specs,
        constraints=["Round04 scripted live user sample; preserve explicit reference bindings."],
    )
    context = SceneInterpreterContext(
        user_text=manifest.initial_user_request,
        input_images=state.input_images,
        declared_bindings=state.reference_bindings,
    )
    updated = apply_state_updates(
        state,
        node_name="Round04SceneSpecCompiler",
        updates={
            "scene_spec": scene_spec,
            "conversation_summary": f"Round04 SceneInterpreterContext: {context.user_text[:240]}",
            "phase": WorkflowPhase.SCENE_SPEC_READY,
        },
    )
    _persist_control_update(run_dir, updated, stage="scene_spec", node_name="Round04SceneSpecCompiler")


def _apply_prompt_pack(run_dir: Path, *, manifest: Round04CaseManifest) -> None:
    state = _read_state(run_dir)
    if state.scene_spec is None:
        raise ValueError("scene_spec required before prompt pack")
    scene_requirement_id = "scene_concept:1"
    subject_prompts = {
        subject.subject_id: (
            f"Clean subject-only concept image for {subject.display_name}. "
            "Use a neutral background, readable full-body silhouette, and preserve any bound reference images."
        )
        for subject in state.scene_spec.subjects
        if subject.needs_2d_concept
    }
    requirements: list[ConceptImageRequirement] = []
    for subject in state.scene_spec.subjects:
        if not subject.needs_2d_concept:
            continue
        refs = list(subject.reference_image_ids)
        requirements.append(
            ConceptImageRequirement(
                requirement_id=f"subject_concept:{subject.subject_id}",
                output_type="subject_concept",
                target_id=subject.subject_id,
                prompt_key=f"subject_prompts.{subject.subject_id}",
                user_review_label=f"{subject.display_name} subject concept",
                purpose="subject concept for Hunyuan3D source image",
                generation_mode="image_guided" if refs else "text_to_image",
                input_reference_image_ids=refs,
                must_use_image_inputs=bool(refs),
                quality_bar="clean subject-only image suitable for image-to-3D",
            )
        )
    scene_refs = list(state.scene_spec.environment.scene_reference_image_ids)
    requirements.append(
        ConceptImageRequirement(
            requirement_id=scene_requirement_id,
            output_type="scene_concept",
            target_id=state.scene_spec.scene_id,
            prompt_key="scene_prompts.0",
            user_review_label=f"{manifest.title} scene concept",
            purpose="scene-only concept for world/scene generation",
            generation_mode="image_guided" if scene_refs else "text_to_image",
            input_reference_image_ids=scene_refs,
            must_use_image_inputs=bool(scene_refs),
            quality_bar="scene-only environment image with clear layout",
        )
    )
    source_ids = [requirement.requirement_id for requirement in requirements]
    requirements.append(
        ConceptImageRequirement(
            requirement_id="target_render:final_preview",
            output_type="target_render",
            target_id=state.scene_spec.scene_id,
            prompt_key="final_preview_prompt",
            user_review_label=f"{manifest.title} target render",
            purpose="final composition concept using generated subject and scene concepts",
            generation_mode="multi_image_composite",
            source_requirement_ids=source_ids,
            must_use_image_inputs=True,
            quality_bar="polished target render with all selected subjects and environment",
        )
    )
    output = ConceptPromptPlannerOutput(
        final_preview_prompt=(
            f"Create the final target render for {manifest.title}. "
            f"Combine all subject concept images with the scene concept for: {manifest.expected_scene}."
        ),
        subject_prompts=subject_prompts,
        scene_prompts=[f"Scene-only concept for {manifest.expected_scene}. Exclude hero subjects."],
        image_requirements=requirements,
        negative_prompt="messy composition, distorted anatomy, unreadable subject, missing requested asset",
        identity_notes=[
            "Round04 runner requires live identity_research.jsonl before live acceptance for named IP cases."
        ],
    )
    result, updated = apply_concept_prompt_planner_output(state=state, planner_output=output)
    if not result.ok:
        raise ValueError(";".join(result.issues))
    _persist_control_update(run_dir, updated, stage="concept_prompt_pack", node_name="Round04ConceptPromptPlanner")


def _write_contract_generation_records(run_dir: Path, *, manifest: Round04CaseManifest) -> None:
    state = _read_state(run_dir)
    requirements = state.concept_bundle.prompt_pack.image_requirements if state.concept_bundle and state.concept_bundle.prompt_pack else []
    for requirement in requirements:
        _append_jsonl(
            run_dir / "live_generation_calls.jsonl",
            {
                "case_id": manifest.case_id,
                "requirement_id": requirement.requirement_id,
                "generation_mode": requirement.generation_mode,
                "prompt": _prompt_for_requirement(state, requirement),
                "input_reference_image_ids": list(requirement.input_reference_image_ids),
                "input_image_paths": _input_paths_for_ids(state, requirement.input_reference_image_ids),
                "source_requirement_ids": list(requirement.source_requirement_ids),
                "source_image_paths": [],
                "output_image_path": None,
                "backend": "not_run_contract_only",
                "ok": False,
                "issues": ["contract_only_run_not_live_acceptance"],
            },
        )
    if _identity_required(manifest):
        _append_jsonl(
            run_dir / "identity_research.jsonl",
            {
                "case_id": manifest.case_id,
                "query": manifest.title,
                "resolved_identity": None,
                "aliases": [],
                "source_urls": [],
                "source_quality": "unknown",
                "confidence": 0.0,
                "notes": "contract-only run; live identity research not executed",
                "issues": ["identity_research_not_run_contract_only"],
            },
        )


def _write_live_blockers(run_dir: Path, *, manifest: Round04CaseManifest) -> list[str]:
    issues = [
        "live_execution_blocked: no project-integrated image generation backend can execute multi-requirement image-guided concept and target-render calls",
        "live_execution_blocked: downstream Hunyuan3D/HY-World/Blender stages are not started without live concept artifacts",
    ]
    _write_contract_generation_records(run_dir, manifest=manifest)
    rows = _read_jsonl(run_dir / "live_generation_calls.jsonl")
    for row in rows:
        row["backend"] = "blocked_live_backend_not_selected"
        row["issues"] = issues
    _write_jsonl(run_dir / "live_generation_calls.jsonl", rows)
    return issues


def _visible_subject_ids_through_action(manifest: Round04CaseManifest, *, action_index: int) -> set[str]:
    texts = [manifest.initial_user_request]
    if action_index >= 0:
        texts.extend(action.text for action in manifest.scripted_user_actions[: action_index + 1])
    visible_text = _normalize_visible_text("\n".join(texts))
    uploaded_manifest_image_ids = _manifest_image_ids_through_action(manifest, action_index=action_index)
    visible = set()
    for subject in manifest.expected_subjects:
        if any(image_id in uploaded_manifest_image_ids for image_id in subject.reference_image_ids):
            visible.add(subject.subject_id)
            continue
        if _subject_mentioned(subject.display_name, visible_text):
            visible.add(subject.subject_id)
    if visible:
        return visible
    return {subject.subject_id for subject in manifest.expected_subjects}


def _manifest_image_ids_through_action(manifest: Round04CaseManifest, *, action_index: int) -> set[str]:
    image_ids = {image.image_id for image in manifest.reference_images if image.upload_stage == "initial_request"}
    if action_index >= 0:
        for action in manifest.scripted_user_actions[: action_index + 1]:
            image_ids.update(action.reference_image_ids)
    return image_ids


def _subject_mentioned(display_name: str, visible_text: str) -> bool:
    normalized_name = _normalize_visible_text(display_name)
    if not normalized_name:
        return False
    if normalized_name in visible_text:
        return True
    compact_name = normalized_name.replace("皮肤", "")
    return bool(compact_name and compact_name in visible_text)


def _normalize_visible_text(value: str) -> str:
    return "".join(str(value).casefold().split())


def _action_requests_concept_regeneration(action: Round04ScriptedUserAction) -> bool:
    return action.action in {"request_concept_changes", "request_model_changes"} or action.expected_next_phase == "CONCEPT_GENERATION"


def _action_approves_concept(action: Round04ScriptedUserAction) -> bool:
    return action.gate == "concept_review" and action.action == "approve_concept"


def _append_review_patch(
    run_dir: Path,
    *,
    action: Round04ScriptedUserAction,
    action_index: int,
    source_turn_id: str,
) -> None:
    state = _read_state(run_dir)
    patch = ReviewPatch(
        patch_id=f"round04_review_patch_{action_index + 1:02d}",
        source_turn_id=source_turn_id,
        phase_created=state.phase,
        target_type="global",
        patch_type="add_subject" if "新增" in action.text else "appearance_change",
        instruction=action.text,
        structured_delta={
            "round04_action": action.action,
            "gate": action.gate,
            "reference_image_ids": list(action.reference_image_ids),
            "expected_next_phase": action.expected_next_phase,
        },
        affected_artifact_ids=_current_concept_artifact_ids(state),
        status="pending",
    )
    updated = apply_state_updates(
        state,
        node_name="Round04ReviewPatchNormalizer",
        updates={"review_patches": [*state.review_patches, patch]},
    )
    _persist_control_update(run_dir, updated, stage="review_patch", node_name="Round04ReviewPatchNormalizer")


def _mark_pending_review_patches_applied(run_dir: Path) -> None:
    state = _read_state(run_dir)
    changed = False
    for patch in state.review_patches:
        if patch.status == "pending":
            patch.status = "applied"
            changed = True
    if changed:
        _persist_control_update(run_dir, state, stage="review_patch_applied", node_name="Round04RegenerationRouter")


def _apply_concept_approval(run_dir: Path, *, action: Round04ScriptedUserAction) -> None:
    state = _read_state(run_dir)
    if state.concept_bundle is None:
        return
    state.concept_bundle.approved = True
    state.concept_bundle.approved_at = utc_now_iso()
    state.phase = _workflow_phase_from_action(action, fallback=WorkflowPhase.CONCEPT_APPROVED)
    _persist_control_update(run_dir, state, stage="concept_approval", node_name="Round04ConceptApprovalGate")


def _workflow_phase_from_action(
    action: Round04ScriptedUserAction,
    *,
    fallback: WorkflowPhase,
) -> WorkflowPhase:
    if not action.expected_next_phase:
        return fallback
    try:
        return WorkflowPhase(action.expected_next_phase)
    except ValueError:
        return fallback


def _current_concept_artifact_ids(state: AgentProjectState) -> list[str]:
    if state.concept_bundle is None:
        return []
    artifact_ids: list[str] = []
    for ids in state.concept_bundle.subject_concept_images.values():
        artifact_ids.extend(ids)
    artifact_ids.extend(state.concept_bundle.scene_concept_image_ids)
    if state.concept_bundle.final_preview_image_id:
        artifact_ids.append(state.concept_bundle.final_preview_image_id)
    return list(dict.fromkeys(artifact_ids))


def _persist_control_update(run_dir: Path, state: AgentProjectState, *, stage: str, node_name: str) -> None:
    state.updated_at = utc_now_iso()
    _write_json(run_dir / "state.json", _model_to_dict(state))
    store = FileStateCheckpointStore(run_dir / "checkpoints")
    latest = store.latest_checkpoint(project_id=state.project_id, thread_id=state.thread_id)
    checkpoint = store.save_checkpoint(
        state,
        reason=stage,
        node_name=node_name,
        parent_checkpoint_id=latest.checkpoint_id if latest is not None else None,
        metadata={"stage": stage, "ok": True, "workflow": "round04-live-user-samples"},
    )
    summary = _read_json(run_dir / "summary.json") or {}
    summary.setdefault("stage_checkpoints", []).append(_model_to_dict(checkpoint))
    _write_json(run_dir / "summary.json", summary)
    _write_frontend_status(run_dir)


def _append_stage(run_dir: Path, stage: str) -> None:
    summary = _read_json(run_dir / "summary.json") or {}
    executed = summary.setdefault("executed_stages", [])
    if stage not in executed:
        executed.append(stage)
    _write_json(run_dir / "summary.json", summary)
    _write_frontend_status(run_dir)


def _write_frontend_status(run_dir: Path) -> None:
    state = _read_state(run_dir)
    summary = _read_json(run_dir / "summary.json") or {}
    _write_json(run_dir / "frontend_status.json", _model_to_dict(build_frontend_status(state=state, summary=summary)))


def _merge_reference_bindings(existing: list[ReferenceBinding], incoming: list[ReferenceBinding]) -> list[ReferenceBinding]:
    by_id = {binding.binding_id: binding for binding in existing}
    for binding in incoming:
        by_id[binding.binding_id] = binding
    return list(by_id.values())


def _input_paths_for_ids(state: AgentProjectState, image_ids: list[str]) -> list[str]:
    by_id = {image.image_id: image.uri for image in state.input_images}
    return [by_id[image_id] for image_id in image_ids if image_id in by_id]


def _prompt_for_requirement(state: AgentProjectState, requirement: ConceptImageRequirement) -> str:
    pack = state.concept_bundle.prompt_pack if state.concept_bundle else None
    if pack is None:
        return ""
    if requirement.prompt_key.startswith("subject_prompts."):
        return pack.subject_prompts.get(requirement.prompt_key.split(".", 1)[1], "")
    if requirement.prompt_key.startswith("scene_prompts."):
        try:
            return pack.scene_prompts[int(requirement.prompt_key.rsplit(".", 1)[1])]
        except Exception:
            return ""
    return pack.final_preview_prompt


def _identity_required(manifest: Round04CaseManifest) -> bool:
    markers = ["IP", "英雄联盟", "云顶", "TFT", "鸣潮", "崩坏", "星穹", "Helltaker", "剑星", "葬送"]
    text = f"{manifest.title}\n{manifest.initial_user_request}\n{manifest.category}"
    return any(marker in text for marker in markers)


def _read_state(run_dir: Path) -> AgentProjectState:
    return AgentProjectState(**json.loads((run_dir / "state.json").read_text(encoding="utf-8")))


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


if __name__ == "__main__":
    raise SystemExit(main())
