from pathlib import Path

from agent_runtime.artifacts import FileArtifactStore
from agent_runtime.asset_quality import (
    apply_subject_asset_repair_decision,
    evaluate_subject_asset,
    plan_subject_asset_repair,
)
from agent_runtime.state import AgentProjectState, Asset3DRecord, WorkflowPhase


def _state() -> AgentProjectState:
    return AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.SUBJECT_ASSET_QA,
    )


def _minimal_glb() -> bytes:
    return b"glTF" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little")


def test_subject_asset_quality_passes_minimal_valid_glb(tmp_path: Path) -> None:
    glb = tmp_path / "asset.glb"
    glb.write_bytes(_minimal_glb())
    state = _state()
    asset = Asset3DRecord(
        asset_id="asset_001",
        subject_id="subject_001",
        source_image_id="image_001",
        glb_uri=str(glb),
        status="succeeded",
    )
    state.subject_assets.append(asset)

    result, updated_state = evaluate_subject_asset(
        state=state,
        asset=asset,
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
    )

    assert result.status == "pass"
    assert result.score == 1.0
    assert result.issues == []
    assert updated_state.subject_assets[0].status == "succeeded"
    assert updated_state.subject_assets[0].quality_score == 1.0
    assert updated_state.subject_assets[0].generation_params["quality"]["status"] == "pass"


def test_subject_asset_quality_fails_invalid_glb_header(tmp_path: Path) -> None:
    glb = tmp_path / "asset.glb"
    glb.write_bytes(b"BAD!" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little"))
    state = _state()
    asset = Asset3DRecord(
        asset_id="asset_001",
        subject_id="subject_001",
        source_image_id="image_001",
        glb_uri=str(glb),
        status="succeeded",
    )
    state.subject_assets.append(asset)

    result, updated_state = evaluate_subject_asset(
        state=state,
        asset=asset,
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
    )

    assert result.status == "fail"
    assert result.suggested_action == "rerun_hunyuan3d"
    assert "invalid_glb_magic" in result.issues
    assert updated_state.subject_assets[0].status == "needs_regen"
    assert updated_state.subject_assets[0].quality_score == 0.0


def test_subject_asset_quality_preview_dry_run_uses_render_preview_tool(tmp_path: Path) -> None:
    glb = tmp_path / "asset.glb"
    glb.write_bytes(_minimal_glb())
    root = tmp_path / "repo"
    blender = tmp_path / "blender"
    (root / "tools").mkdir(parents=True)
    (root / "tools/render_glb_preview.py").write_text("# placeholder\n", encoding="utf-8")
    blender.write_bytes(b"placeholder")
    state = _state()
    asset = Asset3DRecord(
        asset_id="asset_001",
        subject_id="subject_001",
        source_image_id="image_001",
        glb_uri=str(glb),
        status="succeeded",
    )
    state.subject_assets.append(asset)

    result, updated_state = evaluate_subject_asset(
        state=state,
        asset=asset,
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
        root=root,
        output_dir=tmp_path / "qa",
        blender_path=blender,
        render_preview=True,
        dry_run=True,
    )

    assert result.status == "uncertain"
    assert result.suggested_action == "ask_user"
    assert result.render_tool_call_id == state.tool_call_log[0].tool_call_id
    assert result.checks["preview_render"]["tool_call_status"] == "succeeded"
    assert updated_state.subject_assets[0].status == "uncertain"
    assert updated_state.tool_call_log[0].domain_tool_name == "render_preview"
    assert updated_state.tool_call_log[0].phase.value == "SUBJECT_ASSET_QA"


def test_subject_asset_quality_merges_visual_qa_failure(tmp_path: Path) -> None:
    glb = tmp_path / "asset.glb"
    glb.write_bytes(_minimal_glb())
    state = _state()
    asset = Asset3DRecord(
        asset_id="asset_001",
        subject_id="subject_001",
        source_image_id="image_001",
        glb_uri=str(glb),
        status="succeeded",
    )
    state.subject_assets.append(asset)

    result, updated_state = evaluate_subject_asset(
        state=state,
        asset=asset,
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
        visual_qa_result={
            "ok": True,
            "status": "fail",
            "score": 0.2,
            "issues": ["wrong_shape"],
            "suggested_action": "rerun_hunyuan3d",
        },
    )

    assert result.status == "fail"
    assert result.score == 0.2
    assert "visual_similarity_failed" in result.issues
    assert "wrong_shape" in result.issues
    assert result.visual_qa["status"] == "fail"
    assert updated_state.subject_assets[0].status == "needs_regen"
    assert updated_state.subject_assets[0].generation_params["quality"]["status"] == "fail"


def test_subject_asset_repair_decision_retries_hunyuan_once_for_hard_failure(tmp_path: Path) -> None:
    glb = tmp_path / "asset.glb"
    glb.write_bytes(b"BAD!" + (2).to_bytes(4, "little") + (12).to_bytes(4, "little"))
    state = _state()
    asset = Asset3DRecord(
        asset_id="asset_001",
        subject_id="subject_001",
        source_image_id="image_001",
        glb_uri=str(glb),
        status="succeeded",
    )
    state.subject_assets.append(asset)

    quality, state = evaluate_subject_asset(
        state=state,
        asset=asset,
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
    )
    decision = plan_subject_asset_repair(quality, retry_count=0, max_hunyuan_retries=1)
    state = apply_subject_asset_repair_decision(state=state, asset_id=asset.asset_id, decision=decision)

    assert decision.action == "retry_hunyuan3d"
    assert decision.user_visible is False
    assert decision.next_stage == "SUBJECT_ASSET_GENERATION"
    assert state.subject_assets[0].status == "needs_regen"
    assert state.subject_assets[0].generation_params["repair_decision"]["action"] == "retry_hunyuan3d"


def test_subject_asset_repair_decision_asks_user_for_uncertain_preview(tmp_path: Path) -> None:
    glb = tmp_path / "asset.glb"
    glb.write_bytes(_minimal_glb())
    state = _state()
    asset = Asset3DRecord(
        asset_id="asset_001",
        subject_id="subject_001",
        source_image_id="image_001",
        glb_uri=str(glb),
        status="succeeded",
    )
    state.subject_assets.append(asset)

    quality, _ = evaluate_subject_asset(
        state=state,
        asset=asset,
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
        visual_qa_result={"ok": True, "status": "uncertain", "score": 0.5, "issues": ["uncertain_similarity"]},
    )
    decision = plan_subject_asset_repair(quality)

    assert decision.action == "ask_user"
    assert decision.user_visible is True
    assert decision.next_stage == "USER_REVIEW"


def test_subject_asset_repair_decision_regenerates_subject_image_for_semantic_failure(tmp_path: Path) -> None:
    glb = tmp_path / "asset.glb"
    glb.write_bytes(_minimal_glb())
    state = _state()
    asset = Asset3DRecord(
        asset_id="asset_001",
        subject_id="subject_001",
        source_image_id="image_001",
        glb_uri=str(glb),
        status="succeeded",
    )
    state.subject_assets.append(asset)

    quality, _ = evaluate_subject_asset(
        state=state,
        asset=asset,
        artifact_store=FileArtifactStore(tmp_path / "artifacts"),
        visual_qa_result={"ok": True, "status": "fail", "score": 0.2, "issues": ["wrong_shape"]},
    )
    decision = plan_subject_asset_repair(quality)

    assert quality.suggested_action == "regenerate_subject_image"
    assert decision.action == "regenerate_subject_image"
    assert decision.user_visible is False
    assert decision.next_stage == "CONCEPT_GENERATION"
