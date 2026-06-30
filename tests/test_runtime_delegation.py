import json
from pathlib import Path

from agent_runtime.runtime_console import append_console_message, create_runtime_console_run
from agent_runtime.runtime_audit import audit_runtime_run
from agent_runtime.runtime_delegation import plan_next_delegated_handoff, read_runtime_handoff_summary
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan
from agent_runtime.runtime_execution import execute_next_runtime_job
from agent_runtime.runtime_handoff_apply import (
    apply_blender_assembly_result,
    apply_concept_handoff_result,
    apply_scene_asset_handoff_result,
    apply_subject_asset_handoff_result,
)
from agent_runtime.runtime_loop import run_bounded_runtime_loop
from agent_runtime.runtime_runs import build_runtime_run_bundle
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    Asset3DRecord,
    CameraSpec,
    ConceptBundle,
    EnvironmentSpec,
    InputImage,
    LightingSpec,
    ReferenceBinding,
    Scene3DRecord,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


def test_runtime_delegation_plans_handoff_for_loop_delegated_job(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(created.run_dir, role="user", text="Create a compact robot display scene.")
    run_bounded_runtime_loop(
        created.run_dir,
        max_steps=8,
        dry_run=True,
        response_text_by_node=_fixture_responses(),
    )

    result = plan_next_delegated_handoff(created.run_dir)
    handoff = json.loads(Path(result.record.handoff_json).read_text(encoding="utf-8")) if result.record else {}
    bundle = build_runtime_run_bundle(created.run_dir)
    summary = read_runtime_handoff_summary(created.run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "planned"
    assert result.record.domain_tool_name == "generate_concept_images"
    assert "state.json" in " ".join(result.record.input_files)
    assert "concept image" in " ".join(result.record.expected_outputs)
    assert "A compact robot on a clean pedestal." in handoff["task_prompt"]
    assert "Generate exactly one new concept image" in handoff["task_prompt"]
    assert "Do not edit state.json" in handoff["task_prompt"]
    assert "Do not run Blender, Hunyuan3D, HY-World" in handoff["task_prompt"]
    assert "extract the last image_generation result" in handoff["task_prompt"]
    assert handoff["state_summary"]["has_prompt_pack"] is True
    assert summary is not None
    assert summary["handed_off_execution_ids"] == [result.record.execution_id]
    assert bundle.runtime_handoff_summary is not None
    assert {"runtime_handoff", "runtime_handoff_summary"} <= {item.label for item in bundle.file_manifest.files if item.exists}


def test_runtime_delegation_concept_handoff_prompt_includes_reference_image_context(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(created.run_dir, role="user", text="Create a compact robot display scene.")
    run_bounded_runtime_loop(
        created.run_dir,
        max_steps=8,
        dry_run=True,
        response_text_by_node=_fixture_responses(),
    )
    state_path = Path(created.run_dir) / "state.json"
    state = AgentProjectState(**json.loads(state_path.read_text(encoding="utf-8")))
    state.input_images.append(
        InputImage(
            image_id="image_ref_001",
            artifact_id="artifact_ref_001",
            uri="/tmp/reference.png",
            mime_type="image/png",
            user_declared_label="正面参考图",
            notes="黄色玩偶主体",
        )
    )
    state.reference_bindings.append(
        ReferenceBinding(
            binding_id="binding_ref_001",
            image_id="image_ref_001",
            target_type="subject",
            target_id="subject_robot",
            usage="subject_reference",
            confidence=0.92,
            notes="Use for character appearance only.",
        )
    )
    state_path.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")

    result = plan_next_delegated_handoff(created.run_dir)
    handoff = json.loads(Path(result.record.handoff_json).read_text(encoding="utf-8")) if result.record else {}
    prompt = handoff["task_prompt"]

    assert result.ok is True
    assert "image_ref_001" in prompt
    assert "正面参考图" in prompt
    assert "subject_reference" in prompt
    assert "subject_robot" in prompt
    assert "Use for character appearance only." in prompt


def test_runtime_handoff_apply_registers_concept_image_and_rebuilds_plan(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(created.run_dir, role="user", text="Create a compact robot display scene.")
    run_bounded_runtime_loop(
        created.run_dir,
        max_steps=8,
        dry_run=True,
        response_text_by_node=_fixture_responses(),
    )
    handoff = plan_next_delegated_handoff(created.run_dir)
    image = tmp_path / "worker_concept.png"
    image.write_bytes(b"worker concept image")

    result = apply_concept_handoff_result(
        created.run_dir,
        handoff_id=handoff.record.handoff_id,
        image_results=[
            {
                "image_path": str(image),
                "subject_id": "subject_robot",
                "artifact_id": "subject_robot_concept_001",
                "final_preview": True,
            }
        ],
    )
    state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((Path(created.run_dir) / "runtime_plan.json").read_text(encoding="utf-8"))
    bundle = build_runtime_run_bundle(created.run_dir)
    audit = audit_runtime_run(created.run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "applied"
    assert result.record.artifact_ids == ["subject_robot_concept_001"]
    assert result.record.checkpoint_id is not None
    assert state["phase"] == "CONCEPT_REVIEW"
    assert state["concept_bundle"]["final_preview_image_id"] == "subject_robot_concept_001"
    assert state["concept_bundle"]["subject_concept_images"]["subject_robot"] == ["subject_robot_concept_001"]
    assert state["artifacts"][0]["artifact_type"] == "SUBJECT_CONCEPT_IMAGE"
    assert plan["runtime_plan"]["jobs"][0]["kind"] == "user_gate"
    assert bundle.runtime_handoff_apply_summary is not None
    assert audit.ok is True


def test_runtime_handoff_apply_registers_subject_asset_and_rebuilds_plan(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    run_dir.mkdir(parents=True)
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="subject_robot_concept_001",
            subject_concept_images={"subject_robot": ["subject_robot_concept_001"]},
            approved=True,
        ),
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    build_and_save_runtime_dispatch_plan(run_dir)
    step = execute_next_runtime_job(run_dir)
    handoff = plan_next_delegated_handoff(run_dir)
    glb = tmp_path / "subject_robot.glb"
    glb.write_bytes(b"glb")

    result = apply_subject_asset_handoff_result(
        run_dir,
        handoff_id=handoff.record.handoff_id,
        asset_results=[
            {
                "glb_path": str(glb),
                "subject_id": "subject_robot",
                "asset_id": "asset_subject_robot_001",
            }
        ],
    )
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    audit = audit_runtime_run(run_dir)

    assert step.record is not None
    assert step.record.status == "delegated"
    assert step.record.domain_tool_name == "build_subject_asset"
    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "applied"
    assert result.record.artifact_ids == ["asset_subject_robot_001"]
    assert state_payload["phase"] == "SUBJECT_ASSET_QA"
    assert state_payload["subject_assets"][0]["asset_id"] == "asset_subject_robot_001"
    assert state_payload["subject_assets"][0]["status"] == "succeeded"
    assert state_payload["artifacts"][0]["artifact_type"] == "SUBJECT_3D_ASSET"
    assert plan["runtime_plan"]["jobs"][0]["domain_tool_name"] == "build_scene_asset"
    assert audit.ok is True


def test_runtime_delegation_subject_asset_prompt_includes_concept_artifact_and_profile(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    run_dir.mkdir(parents=True)
    concept_path = tmp_path / "subject_robot_concept_001.png"
    concept_path.write_bytes(b"png")
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.CONCEPT_APPROVED,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="subject_robot_concept_001",
            subject_concept_images={"subject_robot": ["subject_robot_concept_001"]},
            approved=True,
        ),
        artifacts=[
            ArtifactRecord(
                artifact_id="subject_robot_concept_001",
                artifact_type=ArtifactType.SUBJECT_CONCEPT_IMAGE,
                uri=str(concept_path),
                mime_type="image/png",
                semantic_role="subject_concept_image",
                linked_subject_id="subject_robot",
            )
        ],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    build_and_save_runtime_dispatch_plan(run_dir, hunyuan3d_profile_id="fast_shape_50k_768")
    step = execute_next_runtime_job(run_dir)
    handoff = plan_next_delegated_handoff(run_dir)
    payload = json.loads(Path(handoff.record.handoff_json).read_text(encoding="utf-8"))
    prompt = payload["task_prompt"]

    assert step.record is not None
    assert step.record.domain_tool_name == "build_subject_asset"
    assert "Use the approved concept image artifact URI" in prompt
    assert "subject_robot_concept_001" in prompt
    assert str(concept_path) in prompt
    assert "fast_shape_50k_768" in prompt
    assert "Do not edit state.json" in prompt
    assert "workflow_runner/Hunyuan3D service path" in prompt


def test_runtime_handoff_apply_registers_scene_asset_and_rebuilds_plan(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    run_dir.mkdir(parents=True)
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.SUBJECT_ASSET_QA,
        scene_spec=_scene_spec(),
        concept_bundle=ConceptBundle(
            concept_version=1,
            final_preview_image_id="subject_robot_concept_001",
            subject_concept_images={"subject_robot": ["subject_robot_concept_001"]},
            approved=True,
        ),
        subject_assets=[
            Asset3DRecord(
                asset_id="asset_subject_robot_001",
                subject_id="subject_robot",
                source_image_id="subject_robot_concept_001",
                glb_uri=str(tmp_path / "subject_robot.glb"),
                status="succeeded",
            )
        ],
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    build_and_save_runtime_dispatch_plan(run_dir)
    step = execute_next_runtime_job(run_dir)
    handoff = plan_next_delegated_handoff(run_dir)
    worldmirror_output = tmp_path / "worldmirror_output"
    worldmirror_output.mkdir()
    (worldmirror_output / "scene_All.glb").write_bytes(b"scene glb")
    (worldmirror_output / "camera_params.json").write_text("{}", encoding="utf-8")

    result = apply_scene_asset_handoff_result(
        run_dir,
        handoff_id=handoff.record.handoff_id,
        scene_asset_results=[
            {
                "output_dir": str(worldmirror_output),
                "scene_asset_id": "scene_asset_001",
                "source_scene_concept_image_ids": ["scene_concept_001"],
                "source_prompt": "simple clean studio scene",
            }
        ],
    )
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    audit = audit_runtime_run(run_dir)

    assert step.record is not None
    assert step.record.status == "delegated"
    assert step.record.domain_tool_name == "build_scene_asset"
    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "applied"
    assert set(result.record.artifact_ids) == {"scene_asset_001_camera_params_json", "scene_asset_001_scene_glb"}
    assert state_payload["phase"] == "SCENE_ASSET_ADAPTATION"
    assert state_payload["scene_asset"]["scene_asset_id"] == "scene_asset_001"
    assert state_payload["scene_asset"]["status"] == "adapted"
    assert state_payload["scene_asset"]["adapted_artifact_ids"] == ["scene_asset_001_scene_glb"]
    assert {artifact["artifact_type"] for artifact in state_payload["artifacts"]} == {"SCENE_3D_ASSET"}
    assert plan["runtime_plan"]["jobs"][0]["node_name"] == "BlenderAssemblyPlanner"
    assert audit.ok is True


def test_runtime_handoff_apply_registers_blender_outputs_and_waits_for_preview_approval(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    run_dir.mkdir(parents=True)
    state = AgentProjectState(
        project_id="p",
        thread_id="t",
        phase=WorkflowPhase.BLENDER_ASSEMBLY_EXECUTION,
        scene_spec=_scene_spec(),
        scene_asset=Scene3DRecord(
            scene_asset_id="scene_asset_001",
            service="hy_world",
            raw_output_type="mesh",
            adapted_artifact_ids=["scene_asset_001_scene_glb"],
            blender_import_mode="mesh_import",
            status="adapted",
        ),
    )
    (run_dir / "state.json").write_text(state.model_dump_json(), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"ok": True, "workflow": "runtime-console"}), encoding="utf-8")
    blend = tmp_path / "scene.blend"
    viewer_glb = tmp_path / "viewer_scene.glb"
    scene_state = tmp_path / "scene_state.json"
    preview = tmp_path / "preview.png"
    blend.write_bytes(b"blend")
    viewer_glb.write_bytes(b"viewer glb")
    scene_state.write_text(json.dumps({"viewer_scene_id": "viewer_scene_001", "objects": []}), encoding="utf-8")
    preview.write_bytes(b"png")

    result = apply_blender_assembly_result(
        run_dir,
        blender_results=[
            {
                "blend_path": str(blend),
                "viewer_scene_path": str(viewer_glb),
                "scene_state_json_path": str(scene_state),
                "preview_image_path": str(preview),
                "blender_scene_id": "blender_scene_001",
                "viewer_scene_id": "viewer_scene_001",
            }
        ],
    )
    state_payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "runtime_plan.json").read_text(encoding="utf-8"))
    bundle = build_runtime_run_bundle(run_dir)
    audit = audit_runtime_run(run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "applied"
    assert set(result.record.applied_fields) == {"artifacts", "blender_scene", "viewer_scene", "phase"}
    assert state_payload["phase"] == "BLENDER_PREVIEW"
    assert state_payload["blender_scene"]["blender_scene_id"] == "blender_scene_001"
    assert state_payload["viewer_scene"]["viewer_scene_id"] == "viewer_scene_001"
    assert state_payload["viewer_scene"]["viewer_scene_path"].endswith(".glb")
    assert {
        "BLENDER_FILE",
        "BLENDER_PREVIEW_RENDER",
        "VIEWER_SCENE_GLB",
        "VIEWER_SCENE_STATE_JSON",
    } <= {artifact["artifact_type"] for artifact in state_payload["artifacts"]}
    assert plan["runtime_plan"]["jobs"][0]["kind"] == "user_gate"
    assert plan["runtime_plan"]["jobs"][0]["phase"] == "BLENDER_PREVIEW"
    assert bundle.web_surface is not None
    assert bundle.web_surface.viewer_scene_url is not None
    assert audit.ok is True


def test_runtime_delegation_noops_without_delegated_execution(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")

    result = plan_next_delegated_handoff(created.run_dir)

    assert result.ok is True
    assert result.record is None
    assert result.message == "no_unplanned_delegated_execution"
    assert result.summary.total_records == 0


def _fixture_responses() -> dict[str, str]:
    return {
        "ReferenceBindingValidator": json.dumps(
            {
                "valid_bindings": [],
                "requires_clarification": False,
                "open_questions": [],
                "issues": [],
            }
        ),
        "SceneInterpreter": json.dumps(
            {
                "user_goal": "Create a compact robot display.",
                "subject_summaries": ["A compact friendly robot."],
                "environment_summary": "Clean display area.",
                "style_summary": "polished",
                "open_questions": [],
            }
        ),
        "SceneSpecCompiler": json.dumps(
            {
                "scene_id": "scene_001",
                "title": "Robot Display",
                "user_goal": "Create a compact robot display scene.",
                "style": {"style_keywords": ["clean"], "rendering_style": "stylized"},
                "environment": {
                    "environment_type": "studio",
                    "description": "A small clean display area.",
                },
                "lighting": {"description": "Soft lighting."},
                "camera": {"shot_type": "three quarter", "target_subject_ids": ["subject_robot"]},
                "subjects": [
                    {
                        "subject_id": "subject_robot",
                        "display_name": "Robot",
                        "category": "character",
                        "description": "A compact friendly robot.",
                    }
                ],
                "open_questions": [],
            }
        ),
        "ConceptPromptPlanner": json.dumps(
            {
                "final_preview_prompt": "A compact robot on a clean pedestal.",
                "subject_prompts": {"subject_robot": "Compact friendly robot, three-quarter view."},
                "scene_prompts": ["Clean pedestal display."],
                "negative_prompt": "blurry",
            }
        ),
    }


def _scene_spec() -> SceneSpec:
    return SceneSpec(
        scene_id="scene_001",
        title="Robot Display",
        user_goal="Create a robot display scene.",
        style=StyleSpec(style_keywords=["clean"], rendering_style="stylized"),
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
