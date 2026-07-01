import json
from pathlib import Path

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.runtime_asset_actions import (
    read_runtime_asset_action_records,
    select_asset_for_assembly,
    select_concept_for_subject_generation,
)
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    Asset3DRecord,
    AssetLibraryItem,
    BlenderAssemblyPlan,
    CameraSpec,
    ConceptBundle,
    EnvironmentSpec,
    LightingSpec,
    Scene3DRecord,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_asset_library_selection_fixture_contains_user_cases() -> None:
    path = Path(__file__).resolve().parent / "fixtures" / "user_journeys" / "asset_library_selection_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))

    assert {case["case_id"] for case in cases} == {
        "user_reselects_rejected_subject_concept",
        "user_selects_model_scene_for_assembly",
        "frontend_status_contains_asset_library",
    }


def test_rejected_concept_can_be_selected_without_deleting_history(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_select_rejected_concept"
    run_dir.mkdir(parents=True)
    state = _concept_selection_state(tmp_path)
    _write_state(run_dir, state)

    result = select_concept_for_subject_generation(
        run_dir,
        subject_id="subject_robot",
        concept_artifact_id="concept_a",
        note="用户决定还是用最早那张生成模型",
    )
    payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    items = {item["artifact_id"]: item for item in payload["asset_library"]}
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    records = read_runtime_asset_action_records(run_dir)

    assert result.ok is True
    assert result.record.checkpoint_id is not None
    assert result.record.runtime_plan_json == str(run_dir / "runtime_plan.json")
    assert records[-1].action_type == "select_concept_for_subject_generation"
    assert items["concept_a"]["selection_status"] == "selected_for_model_generation"
    assert items["concept_a"]["review_status"] == "rejected"
    assert items["concept_a"]["user_notes"] == "用户决定还是用最早那张生成模型"
    assert items["concept_b"]["selection_status"] == "available"
    assert {item["artifact_id"] for item in frontend_status["asset_library"]} == {"concept_a", "concept_b"}
    assert "select_concept_for_subject_generation" in frontend_status["available_asset_actions"]
    assert plan["runtime_plan"]["jobs"][0]["tool_arguments"]["selected_concept_artifact_ids_by_subject"] == {
        "subject_robot": "concept_a"
    }


def test_select_asset_for_assembly_updates_state_frontend_and_controller_payload(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_select_assembly_assets"
    run_dir.mkdir(parents=True)
    state = _assembly_selection_state(tmp_path)
    _write_state(run_dir, state)

    result = select_asset_for_assembly(
        run_dir,
        subject_asset_ids_by_subject={"subject_robot": "subject_model_v2"},
        scene_asset_id="scene_asset_v1",
        target_render_image_id="target_render_001",
        placement_hints=[
            {"subject_id": "subject_robot", "target_region": "front_right", "note": "站在右前方"}
        ],
    )
    payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    frontend_status = json.loads((run_dir / "frontend_status.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    items = {item["artifact_id"]: item for item in payload["asset_library"]}

    assert result.ok is True
    assert payload["active_assembly_selection"]["selected_subject_assets"] == {
        "subject_robot": "subject_model_v2"
    }
    assert payload["active_assembly_selection"]["selected_scene_asset_id"] == "scene_asset_v1"
    assert payload["active_assembly_selection"]["object_placements"][0]["placement_hint"]["target_region"] == "front_right"
    assert items["subject_model_v2"]["selection_status"] == "selected_for_assembly"
    assert items["scene_asset_v1"]["selection_status"] == "selected_for_assembly"
    assert frontend_status["active_assembly_selection"]["selected_subject_assets"] == {
        "subject_robot": "subject_model_v2"
    }
    assert "select_asset_for_assembly" in frontend_status["available_asset_actions"]
    assert plan["runtime_plan"]["jobs"][0]["domain_tool_name"] == "import_scene_asset"
    assert plan["runtime_plan"]["jobs"][0]["tool_arguments"]["subject_asset_id"] == "subject_model_v2"
    assert plan["runtime_plan"]["jobs"][0]["tool_arguments"]["scene_asset_id"] == "scene_asset_v1"
    assert plan["runtime_plan"]["jobs"][0]["tool_arguments"]["active_assembly_selection_id"].startswith(
        "assembly_selection_"
    )


def test_invalid_assembly_selection_records_failure_without_state_mutation(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_invalid_assembly_selection"
    run_dir.mkdir(parents=True)
    state = _assembly_selection_state(tmp_path)
    _write_state(run_dir, state)

    result = select_asset_for_assembly(
        run_dir,
        subject_asset_ids_by_subject={"subject_robot": "missing_subject_model"},
        scene_asset_id="scene_asset_v1",
    )
    payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    records = read_runtime_asset_action_records(run_dir)

    assert result.ok is False
    assert records[-1].status == "failed"
    assert "subject asset not found" in records[-1].error
    assert payload.get("active_assembly_selection") is None


def _write_state(run_dir: Path, state: AgentProjectState) -> None:
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")


def _concept_selection_state(tmp_path: Path) -> AgentProjectState:
    now = utc_now_iso()
    concept_a = tmp_path / "concept_a.png"
    concept_b = tmp_path / "concept_b.png"
    concept_a.write_bytes(b"a")
    concept_b.write_bytes(b"b")
    return AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            subject_concept_images={"subject_robot": ["concept_a", "concept_b"]},
            approved=True,
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="concept_a",
                artifact_type=ArtifactType.SUBJECT_CONCEPT_IMAGE,
                uri=str(concept_a),
                mime_type="image/png",
                semantic_role="subject_concept_image",
                linked_subject_id="subject_robot",
            ),
            ArtifactRecord(
                artifact_id="concept_b",
                artifact_type=ArtifactType.SUBJECT_CONCEPT_IMAGE,
                uri=str(concept_b),
                mime_type="image/png",
                semantic_role="subject_concept_image",
                linked_subject_id="subject_robot",
            ),
        ],
        asset_library=[
            _library_item("concept_a", "subject_concept", now, subject_id="subject_robot", review_status="rejected"),
            _library_item("concept_b", "subject_concept", now, subject_id="subject_robot", review_status="liked"),
        ],
    )


def _assembly_selection_state(tmp_path: Path) -> AgentProjectState:
    now = utc_now_iso()
    subject_v1 = tmp_path / "subject_v1.glb"
    subject_v2 = tmp_path / "subject_v2.glb"
    scene_glb = tmp_path / "scene.glb"
    target_render = tmp_path / "target_render.png"
    for path in [subject_v1, subject_v2, scene_glb, target_render]:
        path.write_bytes(b"asset")
    return AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(concept_version=1, approved=True),
        blender_assembly_plan=BlenderAssemblyPlan(
            plan_id="assembly_plan_001",
            placement_plans=[{"subject_id": "subject_robot", "target_region": "center"}],
        ),
        subject_assets=[
            Asset3DRecord(
                asset_id="subject_model_v1",
                subject_id="subject_robot",
                source_image_id="concept_a",
                glb_uri=str(subject_v1),
                status="succeeded",
            ),
            Asset3DRecord(
                asset_id="subject_model_v2",
                subject_id="subject_robot",
                source_image_id="concept_b",
                glb_uri=str(subject_v2),
                status="succeeded",
            ),
        ],
        scene_asset=Scene3DRecord(
            scene_asset_id="scene_record_001",
            source_scene_concept_image_ids=["scene_concept_001"],
            service="hy_world",
            raw_output_type="mesh",
            adapted_artifact_ids=["scene_asset_v1"],
            blender_import_mode="mesh_import",
            status="adapted",
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="subject_model_v1",
                artifact_type=ArtifactType.SUBJECT_3D_ASSET,
                uri=str(subject_v1),
                mime_type="model/gltf-binary",
                linked_subject_id="subject_robot",
            ),
            ArtifactRecord(
                artifact_id="subject_model_v2",
                artifact_type=ArtifactType.SUBJECT_3D_ASSET,
                uri=str(subject_v2),
                mime_type="model/gltf-binary",
                linked_subject_id="subject_robot",
            ),
            ArtifactRecord(
                artifact_id="scene_asset_v1",
                artifact_type=ArtifactType.SCENE_3D_ASSET,
                uri=str(scene_glb),
                mime_type="model/gltf-binary",
                linked_scene_id="scene_001",
            ),
            ArtifactRecord(
                artifact_id="target_render_001",
                artifact_type=ArtifactType.FINAL_PREVIEW_IMAGE,
                uri=str(target_render),
                mime_type="image/png",
                linked_scene_id="scene_001",
            ),
        ],
        asset_library=[
            _library_item("subject_model_v1", "subject_model", now, subject_id="subject_robot"),
            _library_item("subject_model_v2", "subject_model", now, subject_id="subject_robot"),
            _library_item("scene_asset_v1", "scene_asset", now, scene_id="scene_001"),
            _library_item("target_render_001", "target_render", now, scene_id="scene_001"),
        ],
    )


def _library_item(
    artifact_id: str,
    asset_kind: str,
    now: str,
    *,
    subject_id: str | None = None,
    scene_id: str | None = None,
    review_status: str = "new",
) -> AssetLibraryItem:
    return AssetLibraryItem(
        library_item_id=f"library_{artifact_id}",
        artifact_id=artifact_id,
        asset_kind=asset_kind,
        subject_id=subject_id,
        scene_id=scene_id,
        review_status=review_status,
        created_at=now,
        updated_at=now,
    )


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
