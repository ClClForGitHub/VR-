import pytest

from agent_runtime.domain_dispatcher import BlenderMCPDomainToolDispatcher
from agent_runtime.mcp_client_manager import build_default_mcp_client_manager
from agent_runtime.state import AgentProjectState, BlenderObjectRecord, BlenderSceneState, WorkflowPhase


def _objects_summary(*, object_name: str = "Hero") -> dict:
    return {
        "status": "ok",
        "result": {
            "status": "ok",
            "scene_name": "Scene",
            "active_object": object_name,
            "object_mode": "OBJECT",
            "camera_object": "Camera",
            "collections": [
                {
                    "name": "Scene Collection",
                    "objects": [
                        {
                            "name": object_name,
                            "type": "MESH",
                            "parent": None,
                            "data_name": object_name,
                            "selected": True,
                            "visible": True,
                            "hide_viewport": False,
                        }
                    ],
                    "children": [],
                }
            ],
        },
    }


def _blender_edit_state() -> AgentProjectState:
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.BLENDER_EDIT,
    )
    state.blender_scene = BlenderSceneState(
        blender_scene_id="Scene",
        objects=[
            BlenderObjectRecord(
                object_id="hero",
                blender_name="Hero",
                object_type="subject_asset",
            )
        ],
    )
    return state


def test_default_mcp_client_manager_registers_existing_channels_without_new_transport() -> None:
    manager = build_default_mcp_client_manager(
        blender_status_checker=lambda: {"ok": True, "issues": []},
        codex_self_status_checker=lambda: {"ok": True, "issues": []},
    )

    assert [server.server_name for server in manager.list_servers()] == ["blender_lab", "codex_self_mcp"]
    assert [tool.tool_name for tool in manager.list_tools("blender_lab")] == [
        "get_objects_summary",
        "execute_blender_code",
    ]
    assert [tool.tool_name for tool in manager.list_tools("codex_self_mcp")] == [
        "codex_subagent_call_plan",
        "codex_subagent_smoke",
    ]

    blender_health = manager.health_check("blender_lab")
    assert blender_health.ok is False
    assert blender_health.adapter_status == {"ok": True, "issues": []}
    assert blender_health.raw_tool_caller_registered is False
    assert blender_health.tool_count == 2
    assert blender_health.issues == ["missing_raw_tool_caller"]

    codex_health = manager.health_check("codex_self_mcp")
    assert codex_health.ok is True
    assert codex_health.role == "sub_agent"


def test_mcp_client_manager_calls_registered_raw_tool_and_logs_summary() -> None:
    raw_calls = []

    def raw_tool_caller(tool_name, arguments):
        raw_calls.append((tool_name, arguments))
        return _objects_summary(object_name="Hero")

    manager = build_default_mcp_client_manager(blender_raw_tool_caller=raw_tool_caller)
    result = manager.call_tool("blender_lab", "get_objects_summary", {})

    assert result["result"]["scene_name"] == "Scene"
    assert raw_calls == [("get_objects_summary", {})]
    assert len(manager.raw_call_log) == 1
    record = manager.raw_call_log[0]
    assert record.server_name == "blender_lab"
    assert record.tool_name == "get_objects_summary"
    assert record.status == "succeeded"
    assert record.result_summary["result.scene_name"] == "Scene"


def test_mcp_client_manager_reports_missing_injected_caller_as_raw_failure() -> None:
    manager = build_default_mcp_client_manager()

    result = manager.call_tool("blender_lab", "get_objects_summary", {})

    assert result["status"] == "error"
    assert "no raw MCP tool caller registered" in result["message"]
    assert manager.raw_call_log[0].status == "failed"


def test_mcp_client_manager_rejects_unregistered_raw_tools() -> None:
    manager = build_default_mcp_client_manager()

    with pytest.raises(ValueError, match="not registered"):
        manager.call_tool("blender_lab", "delete_everything", {})


def test_blender_dispatcher_can_use_mcp_client_manager_boundary() -> None:
    def raw_tool_caller(tool_name, arguments):
        assert tool_name == "get_objects_summary"
        assert arguments == {}
        return _objects_summary(object_name="Hero")

    manager = build_default_mcp_client_manager(blender_raw_tool_caller=raw_tool_caller)
    dispatcher = BlenderMCPDomainToolDispatcher.from_mcp_client_manager(
        state=_blender_edit_state(),
        manager=manager,
    )
    result = dispatcher.dispatch("get_blender_scene_summary", {})

    assert result.ok is True
    assert result.outputs["blender_scene_object_count"] == 1
    assert dispatcher.state.blender_scene.objects[0].blender_name == "Hero"
    assert dispatcher.state.tool_call_log[0].raw_tool_calls[0]["server"] == "blender_lab"
    assert manager.raw_call_log[0].tool_name == "get_objects_summary"
