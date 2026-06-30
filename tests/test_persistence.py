from pathlib import Path

from agent_runtime.artifacts import sha256_file
from agent_runtime.persistence import FileStateCheckpointStore, langgraph_thread_config
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    ToolCallRecord,
    ToolCallStatus,
    WorkflowPhase,
)


def _sample_state(*, project_id: str = "project_001", phase: WorkflowPhase = WorkflowPhase.SCENE_ASSET_ADAPTATION):
    return AgentProjectState(
        project_id=project_id,
        thread_id="thread_001",
        phase=phase,
        artifacts=[
            ArtifactRecord(
                artifact_id="asset_001",
                artifact_type=ArtifactType.SCENE_3D_ASSET,
                uri="/tmp/asset.glb",
                mime_type="model/gltf-binary",
            )
        ],
        tool_call_log=[
            ToolCallRecord(
                tool_call_id="tool_001",
                project_id=project_id,
                phase=phase,
                domain_tool_name="adapt_scene_asset",
                status=ToolCallStatus.SUCCEEDED,
                started_at="2026-06-27T00:00:00+00:00",
            )
        ],
    )


def test_file_state_checkpoint_store_saves_loads_state_and_events(tmp_path: Path) -> None:
    store = FileStateCheckpointStore(tmp_path / "checkpoints")
    state = _sample_state()

    checkpoint = store.save_checkpoint(
        state,
        reason="scene_asset_adapted",
        node_name="SceneAssetAdapter",
        metadata={"stage": "register_existing_output"},
    )

    assert checkpoint.checkpoint_id.startswith("ckpt_project_001_thread_001_")
    assert checkpoint.project_id == "project_001"
    assert checkpoint.thread_id == "thread_001"
    assert checkpoint.phase == WorkflowPhase.SCENE_ASSET_ADAPTATION
    assert checkpoint.state_version == 1
    assert checkpoint.reason == "scene_asset_adapted"
    assert checkpoint.node_name == "SceneAssetAdapter"
    assert checkpoint.artifact_ids == ["asset_001"]
    assert checkpoint.important_artifacts == ["asset_001"]
    assert checkpoint.tool_call_count == 1
    assert checkpoint.metadata == {"stage": "register_existing_output"}
    assert Path(checkpoint.state_snapshot_uri).is_file()
    assert checkpoint.state_snapshot_sha256 == sha256_file(Path(checkpoint.state_snapshot_uri))
    assert (tmp_path / "checkpoints/checkpoints.jsonl").is_file()
    assert (tmp_path / "checkpoints/events.jsonl").is_file()

    loaded = store.load_checkpoint(checkpoint.checkpoint_id)
    assert loaded.project_id == state.project_id
    assert loaded.thread_id == state.thread_id
    assert loaded.phase == state.phase
    assert loaded.artifacts[0].artifact_id == "asset_001"
    assert loaded.tool_call_log[0].domain_tool_name == "adapt_scene_asset"

    events = store.list_events()
    assert len(events) == 1
    assert events[0].event_type == "checkpoint_created"
    assert events[0].checkpoint_id == checkpoint.checkpoint_id
    assert events[0].payload["reason"] == "scene_asset_adapted"


def test_file_state_checkpoint_store_filters_latest_and_restores(tmp_path: Path) -> None:
    store = FileStateCheckpointStore(tmp_path / "checkpoints")
    first = store.save_checkpoint(_sample_state(), reason="first")
    store.save_checkpoint(_sample_state(project_id="project_other"), reason="other")
    second = store.save_checkpoint(
        _sample_state(phase=WorkflowPhase.BLENDER_PREVIEW),
        reason="second",
        parent_checkpoint_id=first.checkpoint_id,
    )

    assert store.latest_checkpoint(project_id="project_001").checkpoint_id == second.checkpoint_id
    assert store.latest_checkpoint(project_id="missing") is None
    assert [record.checkpoint_id for record in store.list_checkpoints(thread_id="thread_001")] == [
        first.checkpoint_id,
        store.list_checkpoints()[1].checkpoint_id,
        second.checkpoint_id,
    ]
    assert second.parent_checkpoint_id == first.checkpoint_id

    restored = store.restore_checkpoint(first.checkpoint_id, reason="rollback_test")
    assert restored.project_id == "project_001"
    assert restored.phase == WorkflowPhase.SCENE_ASSET_ADAPTATION

    events = store.list_events()
    assert events[-1].event_type == "checkpoint_restored"
    assert events[-1].checkpoint_id == first.checkpoint_id
    assert events[-1].source_checkpoint_id == first.checkpoint_id
    assert events[-1].target_checkpoint_id == first.checkpoint_id
    assert events[-1].payload == {"reason": "rollback_test"}


def test_langgraph_thread_config_uses_project_state_thread_id() -> None:
    assert langgraph_thread_config(_sample_state()) == {"configurable": {"thread_id": "thread_001"}}
