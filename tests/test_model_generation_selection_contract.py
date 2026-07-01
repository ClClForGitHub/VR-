import json
from pathlib import Path

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.controller import build_controller_plan
from agent_runtime.runtime_asset_actions import select_concept_for_subject_generation
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    AssemblySelection,
    Asset3DRecord,
    AssetLibraryItem,
    BlenderAssemblyPlan,
    ConceptBundle,
    EnvironmentSpec,
    LightingSpec,
    Scene3DRecord,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_rejected_old_concept_can_be_reselected_for_model_generation(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs/runs/select_concept"
    run_dir.mkdir(parents=True)
    now = utc_now_iso()
    state = AgentProjectState(
        project_id="project_round03",
        thread_id="thread_round03",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(["subject_robot"]),
        concept_bundle=ConceptBundle(
            concept_version=2,
            final_preview_image_id="target_new",
            subject_concept_images={"subject_robot": ["concept_old", "concept_new"]},
            approved=True,
        ),
        artifacts=[
            _artifact("concept_old", ArtifactType.SUBJECT_CONCEPT_IMAGE, tmp_path / "concept_old.png", subject_id="subject_robot"),
            _artifact("concept_new", ArtifactType.SUBJECT_CONCEPT_IMAGE, tmp_path / "concept_new.png", subject_id="subject_robot"),
        ],
        asset_library=[
            AssetLibraryItem(
                library_item_id="library_concept_old",
                artifact_id="concept_old",
                asset_kind="subject_concept",
                subject_id="subject_robot",
                review_status="rejected",
                selection_status="available",
                created_at=now,
                updated_at=now,
            ),
            AssetLibraryItem(
                library_item_id="library_concept_new",
                artifact_id="concept_new",
                asset_kind="subject_concept",
                subject_id="subject_robot",
                review_status="liked",
                selection_status="selected_for_model_generation",
                created_at=now,
                updated_at=now,
            ),
        ],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")

    result = select_concept_for_subject_generation(
        run_dir,
        subject_id="subject_robot",
        concept_artifact_id="concept_old",
    )
    updated = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    runtime_plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    old_item = next(item for item in updated["asset_library"] if item["artifact_id"] == "concept_old")
    new_item = next(item for item in updated["asset_library"] if item["artifact_id"] == "concept_new")

    assert result.ok is True
    assert old_item["review_status"] == "rejected"
    assert old_item["selection_status"] == "selected_for_model_generation"
    assert new_item["selection_status"] == "available"
    subject_payload = runtime_plan["controller"]["actions"][0]["payload"]
    assert subject_payload["selected_concept_artifact_ids_by_subject"] == {"subject_robot": "concept_old"}
    assert subject_payload["selected_source_image_ids"] == ["concept_old"]


def test_multi_subject_active_selection_reaches_blender_assembly_payload() -> None:
    state = AgentProjectState(
        project_id="project_round03",
        thread_id="thread_round03",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=_scene_spec(["subject_robot_a", "subject_robot_b"]),
        blender_assembly_plan=BlenderAssemblyPlan(plan_id="assembly_plan_round03"),
        subject_assets=[
            Asset3DRecord(
                asset_id="asset_robot_a_v1",
                subject_id="subject_robot_a",
                source_image_id="concept_a_old",
                glb_uri="/tmp/a_v1.glb",
                status="succeeded",
            ),
            Asset3DRecord(
                asset_id="asset_robot_a_v2",
                subject_id="subject_robot_a",
                source_image_id="concept_a_selected",
                glb_uri="/tmp/a_v2.glb",
                status="succeeded",
            ),
            Asset3DRecord(
                asset_id="asset_robot_b_v2",
                subject_id="subject_robot_b",
                source_image_id="concept_b_selected",
                glb_uri="/tmp/b_v2.glb",
                status="succeeded",
            ),
        ],
        scene_asset=Scene3DRecord(
            scene_asset_id="scene_asset_record",
            service="hy_world",
            raw_output_type="mesh",
            adapted_artifact_ids=["scene_asset_selected"],
            blender_import_mode="mesh_import",
            status="adapted",
        ),
        active_assembly_selection=AssemblySelection(
            selection_id="assembly_selection_round03",
            selected_subject_assets={
                "subject_robot_a": "asset_robot_a_v2",
                "subject_robot_b": "asset_robot_b_v2",
            },
            selected_scene_asset_id="scene_asset_selected",
            selected_scene_concept_image_id="scene_concept_selected",
            selected_target_render_image_id="target_render_selected",
            object_placements=[
                {
                    "subject_id": "subject_robot_a",
                    "selected_subject_asset_id": "asset_robot_a_v2",
                    "source_concept_image_id": "concept_a_selected",
                    "placement_hint": {"target_region": "front_left"},
                },
                {
                    "subject_id": "subject_robot_b",
                    "selected_subject_asset_id": "asset_robot_b_v2",
                    "source_concept_image_id": "concept_b_selected",
                    "placement_hint": {"target_region": "front_right"},
                },
            ],
            updated_at="2026-07-01T00:00:00+00:00",
        ),
    )

    plan = build_controller_plan(state)
    payload = plan.actions[0].payload

    assert plan.actions[0].domain_tool_name == "import_scene_asset"
    assert payload["active_assembly_selection_id"] == "assembly_selection_round03"
    assert payload["selected_subject_assets"] == {
        "subject_robot_a": "asset_robot_a_v2",
        "subject_robot_b": "asset_robot_b_v2",
    }
    assert payload["scene_asset_id"] == "scene_asset_selected"
    assert payload["subject_asset_id"] == "asset_robot_a_v2"
    assert payload["selected_scene_concept_image_id"] == "scene_concept_selected"
    assert payload["selected_target_render_image_id"] == "target_render_selected"
    assert [item["placement_hint"]["target_region"] for item in payload["object_placements"]] == [
        "front_left",
        "front_right",
    ]


def _scene_spec(subject_ids: list[str]) -> SceneSpec:
    return SceneSpec(
        scene_id="scene_robot_display",
        title="Robot Display",
        user_goal="Create a robot display.",
        style=StyleSpec(style_keywords=["clean"]),
        environment=EnvironmentSpec(environment_type="studio", description="Clean display."),
        lighting=LightingSpec(description="Soft light."),
        camera={},
        subjects=[
            SubjectSpec(
                subject_id=subject_id,
                display_name=subject_id.replace("_", " ").title(),
                category="character",
                description="A compact robot.",
            )
            for subject_id in subject_ids
        ],
    )


def _artifact(artifact_id: str, artifact_type: ArtifactType, path: Path, *, subject_id: str | None = None) -> ArtifactRecord:
    path.write_bytes(b"artifact")
    return ArtifactRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        uri=str(path),
        mime_type="image/png",
        semantic_role="subject_concept_image",
        linked_subject_id=subject_id,
    )
