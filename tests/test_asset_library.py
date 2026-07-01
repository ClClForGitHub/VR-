import json
from pathlib import Path

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.runtime_delegation import RuntimeDelegatedHandoffRecord
from agent_runtime.runtime_handoff_apply import apply_concept_handoff_result, apply_subject_asset_handoff_result
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    AssetLibraryItem,
    CameraSpec,
    ConceptBundle,
    ConceptImageRequirement,
    ConceptPromptPack,
    EnvironmentSpec,
    InputImage,
    LightingSpec,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_concept_handoff_apply_records_asset_library_lineage(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_asset_library_concepts"
    run_dir.mkdir(parents=True)
    subject_image = tmp_path / "subject_concept.png"
    target_image = tmp_path / "target_render.png"
    subject_image.write_bytes(b"subject concept")
    target_image.write_bytes(b"target render")
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.CONCEPT_GENERATION,
        scene_spec=_scene_spec(),
        input_images=[
            InputImage(
                image_id="image_ref_001",
                artifact_id="artifact_ref_001",
                uri=str(tmp_path / "reference.png"),
                mime_type="image/png",
            )
        ],
        concept_bundle=ConceptBundle(
            concept_version=2,
            prompt_pack=ConceptPromptPack(
                final_preview_prompt="Robot on a clean pedestal.",
                subject_prompts={"subject_robot": "Use the reference image for the robot."},
                image_requirements=[
                    ConceptImageRequirement(
                        requirement_id="subject_concept:subject_robot",
                        output_type="subject_concept",
                        target_id="subject_robot",
                        prompt_key="subject_prompts.subject_robot",
                        user_review_label="主体概念图",
                        purpose="subject source image",
                        generation_mode="image_guided",
                        input_reference_image_ids=["image_ref_001"],
                        must_use_image_inputs=True,
                    ),
                    ConceptImageRequirement(
                        requirement_id="target_render:final_preview",
                        output_type="target_render",
                        target_id="scene_001",
                        prompt_key="final_preview_prompt",
                        user_review_label="最终构图图",
                        purpose="composition preview",
                        generation_mode="multi_image_composite",
                        source_requirement_ids=["subject_concept:subject_robot"],
                        must_use_image_inputs=True,
                    ),
                ],
            ),
        ),
    )
    _write_state(run_dir, state)
    handoff_id = _write_handoff(run_dir, domain_tool_name="generate_concept_images")

    result = apply_concept_handoff_result(
        run_dir,
        handoff_id=handoff_id,
        image_results=[
            {
                "image_path": str(subject_image),
                "artifact_id": "concept_robot_selected",
                "output_type": "subject_concept",
                "subject_id": "subject_robot",
                "requirement_id": "subject_concept:subject_robot",
            },
            {
                "image_path": str(target_image),
                "artifact_id": "target_render_001",
                "output_type": "target_render",
                "target_id": "scene_001",
                "requirement_id": "target_render:final_preview",
            },
        ],
    )
    payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    items = {item["artifact_id"]: item for item in payload["asset_library"]}

    assert result.ok is True
    assert set(items) == {"concept_robot_selected", "target_render_001"}
    assert items["concept_robot_selected"]["asset_kind"] == "subject_concept"
    assert items["concept_robot_selected"]["subject_id"] == "subject_robot"
    assert items["concept_robot_selected"]["requirement_id"] == "subject_concept:subject_robot"
    assert items["concept_robot_selected"]["source_artifact_ids"] == ["artifact_ref_001"]
    assert items["concept_robot_selected"]["derived_artifact_ids"] == ["target_render_001"]
    assert items["target_render_001"]["asset_kind"] == "target_render"
    assert items["target_render_001"]["source_artifact_ids"] == ["concept_robot_selected"]
    assert payload["artifacts"][0]["linked_subject_id"] == "subject_robot"


def test_subject_asset_application_preserves_selected_concept_lineage(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_asset_library_subject_asset"
    run_dir.mkdir(parents=True)
    concept_path = tmp_path / "concept_rejected_but_selected.png"
    concept_path.write_bytes(b"concept")
    glb = tmp_path / "robot.glb"
    glb.write_bytes(b"glb")
    now = utc_now_iso()
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            subject_concept_images={"subject_robot": ["concept_rejected_but_selected"]},
            approved=True,
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="concept_rejected_but_selected",
                artifact_type=ArtifactType.SUBJECT_CONCEPT_IMAGE,
                uri=str(concept_path),
                mime_type="image/png",
                semantic_role="subject_concept_image",
                linked_subject_id="subject_robot",
            )
        ],
        asset_library=[
            AssetLibraryItem(
                library_item_id="library_concept_rejected_but_selected",
                artifact_id="concept_rejected_but_selected",
                asset_kind="subject_concept",
                subject_id="subject_robot",
                review_status="rejected",
                selection_status="selected_for_model_generation",
                created_at=now,
                updated_at=now,
            )
        ],
    )
    _write_state(run_dir, state)
    handoff_id = _write_handoff(run_dir, domain_tool_name="build_subject_asset")

    result = apply_subject_asset_handoff_result(
        run_dir,
        handoff_id=handoff_id,
        asset_results=[
            {
                "glb_path": str(glb),
                "subject_id": "subject_robot",
                "asset_id": "asset_robot_from_selected_concept",
            }
        ],
    )
    payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    items = {item["artifact_id"]: item for item in payload["asset_library"]}

    assert result.ok is True
    assert payload["subject_assets"][0]["source_image_id"] == "concept_rejected_but_selected"
    assert items["concept_rejected_but_selected"]["review_status"] == "rejected"
    assert items["concept_rejected_but_selected"]["derived_artifact_ids"] == ["asset_robot_from_selected_concept"]
    assert items["asset_robot_from_selected_concept"]["asset_kind"] == "subject_model"
    assert items["asset_robot_from_selected_concept"]["source_artifact_ids"] == ["concept_rejected_but_selected"]
    assert payload["artifacts"][-1]["linked_subject_id"] == "subject_robot"


def _write_state(run_dir: Path, state: AgentProjectState) -> None:
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")


def _write_handoff(run_dir: Path, *, domain_tool_name: str) -> str:
    handoff = RuntimeDelegatedHandoffRecord(
        handoff_id=f"handoff_{domain_tool_name}",
        execution_id=f"exec_{domain_tool_name}",
        job_id=f"job_{domain_tool_name}",
        domain_tool_name=domain_tool_name,
        executor="sub_agent",
        status="planned",
        ok=True,
        created_at=utc_now_iso(),
    )
    with (run_dir / "runtime_handoff.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(handoff.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n")
    return handoff.handoff_id


def _scene_spec() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_001",
        title="Robot Display",
        user_goal="Create a robot display.",
        style=StyleSpec(style_keywords=["clean"]),
        environment=EnvironmentSpec(environment_type="studio", description="Small studio."),
        lighting=LightingSpec(description="Soft light."),
        camera=CameraSpec(shot_type="three quarter"),
        subjects=[
            SubjectSpec(
                subject_id="subject_robot",
                display_name="Robot",
                category="character",
                description="A compact robot.",
            )
        ],
    )
