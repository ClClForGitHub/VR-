import json
from pathlib import Path

from agent_runtime.agent_prompts import ConceptPromptPlannerOutput, concept_prompt_pack_from_planner_output
from agent_runtime.artifacts import utc_now_iso
from agent_runtime.runtime_delegation import plan_next_delegated_handoff
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.runtime_execution import execute_next_runtime_job
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    AssemblySelection,
    Asset3DRecord,
    AssetLibraryItem,
    ConceptBundle,
    EnvironmentSpec,
    InputImage,
    LightingSpec,
    ReferenceBinding,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_concept_generation_handoff_carries_scene_refs_requirements_and_apply_schema(tmp_path: Path) -> None:
    subject_ref = tmp_path / "subject_ref.png"
    scene_ref = tmp_path / "scene_ref.png"
    subject_ref.write_bytes(b"subject")
    scene_ref.write_bytes(b"scene")
    run_dir = _write_state_run(
        tmp_path,
        "concept_handoff",
        AgentProjectState(
            project_id="project_round03",
            thread_id="thread_round03",
            phase=WorkflowPhase.CONCEPT_GENERATION,
            scene_spec=_scene_spec(subject_ref=True, scene_ref=True),
            input_images=[
                InputImage(
                    image_id="image_subject_ref",
                    artifact_id="artifact_subject_ref",
                    uri=str(subject_ref),
                    mime_type="image/png",
                    user_declared_label="subject only",
                ),
                InputImage(
                    image_id="image_scene_ref",
                    artifact_id="artifact_scene_ref",
                    uri=str(scene_ref),
                    mime_type="image/png",
                    user_declared_label="scene only",
                ),
            ],
            reference_bindings=[
                ReferenceBinding(
                    binding_id="binding_subject",
                    image_id="image_subject_ref",
                    target_type="subject",
                    target_id="subject_robot",
                    usage="subject_reference",
                ),
                ReferenceBinding(
                    binding_id="binding_scene",
                    image_id="image_scene_ref",
                    target_type="scene",
                    target_id="scene_robot_display",
                    usage="scene_reference",
                ),
            ],
            concept_bundle=ConceptBundle(
                concept_version=1,
                prompt_pack=concept_prompt_pack_from_planner_output(
                    ConceptPromptPlannerOutput(
                        final_preview_prompt="Target render using subject and scene concepts.",
                        subject_prompts={"subject_robot": "Subject-only robot from image_subject_ref."},
                        scene_prompts=["Scene-only studio from image_scene_ref."],
                    ),
                    scene_spec=_scene_spec(subject_ref=True, scene_ref=True),
                ),
            ),
        ),
    )
    build_and_save_runtime_dispatch_plan(run_dir)
    step = execute_next_runtime_job(run_dir)
    result = plan_next_delegated_handoff(run_dir)
    payload = json.loads(Path(result.record.handoff_json).read_text(encoding="utf-8"))
    concept_generation = payload["concept_generation"]

    assert step.record.status == "delegated"
    assert result.record.domain_tool_name == "generate_concept_images"
    assert concept_generation["scene_spec"]["scene_id"] == "scene_robot_display"
    assert [image["image_id"] for image in concept_generation["reference_images"]] == [
        "image_subject_ref",
        "image_scene_ref",
    ]
    assert [binding["usage"] for binding in concept_generation["reference_bindings"]] == [
        "subject_reference",
        "scene_reference",
    ]
    assert concept_generation["execution_order"] == [
        "subject_concept:subject_robot",
        "scene_concept:1",
        "target_render:final_preview",
    ]
    subject_requirement = concept_generation["requirements"][0]
    scene_requirement = concept_generation["requirements"][1]
    assert subject_requirement["resolved_input_images"][0]["uri"] == str(subject_ref)
    assert subject_requirement["resolved_input_images"][0]["exists"] is True
    assert scene_requirement["resolved_input_images"][0]["uri"] == str(scene_ref)
    assert "image_results" in concept_generation["apply_result_schema"]


def test_subject_asset_handoff_carries_selected_concept_profile_and_output_schema(tmp_path: Path) -> None:
    concept_path = tmp_path / "concept_selected.png"
    concept_path.write_bytes(b"concept")
    now = utc_now_iso()
    run_dir = _write_state_run(
        tmp_path,
        "subject_handoff",
        AgentProjectState(
            project_id="project_round03",
            thread_id="thread_round03",
            phase=WorkflowPhase.CONCEPT_APPROVED,
            scene_spec=_scene_spec(),
            concept_bundle=ConceptBundle(
                concept_version=1,
                final_preview_image_id="concept_selected",
                subject_concept_images={"subject_robot": ["concept_selected"]},
                approved=True,
            ),
            artifacts=[
                ArtifactRecord(
                    artifact_id="concept_selected",
                    artifact_type=ArtifactType.SUBJECT_CONCEPT_IMAGE,
                    uri=str(concept_path),
                    mime_type="image/png",
                    semantic_role="subject_concept_image",
                    linked_subject_id="subject_robot",
                )
            ],
            asset_library=[
                AssetLibraryItem(
                    library_item_id="library_concept_selected",
                    artifact_id="concept_selected",
                    asset_kind="subject_concept",
                    subject_id="subject_robot",
                    selection_status="selected_for_model_generation",
                    created_at=now,
                    updated_at=now,
                )
            ],
        ),
    )
    build_and_save_runtime_dispatch_plan(run_dir, hunyuan3d_profile_id="fast_shape_50k_768")
    execute_next_runtime_job(run_dir)
    result = plan_next_delegated_handoff(run_dir)
    payload = json.loads(Path(result.record.handoff_json).read_text(encoding="utf-8"))
    subject_payload = payload["subject_asset_generation"]

    assert result.record.domain_tool_name == "build_subject_asset"
    assert subject_payload["subject_ids"] == ["subject_robot"]
    assert subject_payload["selected_subject_concepts"][0]["artifact_id"] == "concept_selected"
    assert subject_payload["source_subject_concepts"][0]["uri"] == str(concept_path)
    assert subject_payload["profile_id"] == "fast_shape_50k_768"
    assert subject_payload["hunyuan3d_profile_policy"] == "global"
    assert subject_payload["hunyuan3d_profiles_by_subject"] == {"subject_robot": "fast_shape_50k_768"}
    assert subject_payload["hunyuan3d_profile_kwargs_by_subject"]["subject_robot"]["face_count"] == 50000
    assert "asset_results" in subject_payload["apply_result_schema"]
    assert result.record.result_summary["subject_asset_source_count"] == 1


def test_scene_asset_handoff_carries_active_scene_selection_and_output_schema(tmp_path: Path) -> None:
    scene_concept_path = tmp_path / "scene_concept.png"
    target_render_path = tmp_path / "target_render.png"
    scene_concept_path.write_bytes(b"scene")
    target_render_path.write_bytes(b"target")
    now = utc_now_iso()
    run_dir = _write_state_run(
        tmp_path,
        "scene_handoff",
        AgentProjectState(
            project_id="project_round03",
            thread_id="thread_round03",
            phase=WorkflowPhase.SUBJECT_ASSET_QA,
            scene_spec=_scene_spec(),
            concept_bundle=ConceptBundle(
                concept_version=1,
                final_preview_image_id="target_render_selected",
                scene_concept_image_ids=["scene_concept_selected"],
                approved=True,
            ),
            subject_assets=[
                Asset3DRecord(
                    asset_id="asset_robot",
                    subject_id="subject_robot",
                    source_image_id="concept_selected",
                    glb_uri="/tmp/robot.glb",
                    status="succeeded",
                )
            ],
            artifacts=[
                ArtifactRecord(
                    artifact_id="scene_concept_selected",
                    artifact_type=ArtifactType.SCENE_CONCEPT_IMAGE,
                    uri=str(scene_concept_path),
                    mime_type="image/png",
                    semantic_role="scene_concept_image",
                    linked_scene_id="scene_robot_display",
                ),
                ArtifactRecord(
                    artifact_id="target_render_selected",
                    artifact_type=ArtifactType.FINAL_PREVIEW_IMAGE,
                    uri=str(target_render_path),
                    mime_type="image/png",
                    semantic_role="final_preview_image",
                    linked_scene_id="scene_robot_display",
                ),
            ],
            asset_library=[
                AssetLibraryItem(
                    library_item_id="library_scene_concept_selected",
                    artifact_id="scene_concept_selected",
                    asset_kind="scene_concept",
                    scene_id="scene_robot_display",
                    selection_status="selected_for_scene_generation",
                    created_at=now,
                    updated_at=now,
                ),
                AssetLibraryItem(
                    library_item_id="library_target_render_selected",
                    artifact_id="target_render_selected",
                    asset_kind="target_render",
                    scene_id="scene_robot_display",
                    selection_status="selected_for_assembly",
                    created_at=now,
                    updated_at=now,
                ),
            ],
            active_assembly_selection=AssemblySelection(
                selection_id="assembly_selection_round03",
                selected_subject_assets={"subject_robot": "asset_robot"},
                selected_scene_concept_image_id="scene_concept_selected",
                selected_target_render_image_id="target_render_selected",
                updated_at=now,
            ),
        ),
    )
    build_and_save_runtime_dispatch_plan(run_dir)
    execute_next_runtime_job(run_dir)
    result = plan_next_delegated_handoff(run_dir)
    payload = json.loads(Path(result.record.handoff_json).read_text(encoding="utf-8"))
    scene_payload = payload["scene_asset_generation"]

    assert result.record.domain_tool_name == "build_scene_asset"
    assert scene_payload["scene_id"] == "scene_robot_display"
    assert scene_payload["active_assembly_selection"]["selected_scene_concept_image_id"] == "scene_concept_selected"
    assert [item["artifact_id"] for item in scene_payload["source_scene_images"]] == [
        "scene_concept_selected",
        "target_render_selected",
    ]
    assert scene_payload["source_scene_images"][0]["source_priority"] == "active_assembly_selection.scene_concept"
    assert "scene_asset_results" in scene_payload["apply_result_schema"]
    assert result.record.result_summary["scene_asset_source_count"] == 2


def _write_state_run(tmp_path: Path, run_id: str, state: AgentProjectState) -> Path:
    run_dir = tmp_path / "outputs/runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    return run_dir


def _scene_spec(*, subject_ref: bool = False, scene_ref: bool = False) -> SceneSpec:
    return SceneSpec(
        scene_id="scene_robot_display",
        title="Robot Display",
        user_goal="Create a robot display.",
        style=StyleSpec(style_keywords=["clean"]),
        environment=EnvironmentSpec(
            environment_type="studio",
            description="Clean display.",
            scene_reference_image_ids=["image_scene_ref"] if scene_ref else [],
        ),
        lighting=LightingSpec(description="Soft light."),
        camera={},
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Hero Robot",
                category="character",
                description="A compact robot.",
                reference_image_ids=["image_subject_ref"] if subject_ref else [],
            )
        ],
    )
