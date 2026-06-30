from agent_runtime.agent_prompts import NODE_SPECS, build_node_prompt, get_prompt_node_spec


def test_concept_prompt_planner_prompt_is_json_only_contract() -> None:
    prompt = build_node_prompt(
        "ConceptPromptPlanner",
        context_json={
            "scene_spec": {"scene_id": "scene_001", "title": "demo"},
            "active_review_patches": [],
        },
    )

    assert prompt.node_name == "ConceptPromptPlanner"
    assert "Output only one JSON object" in prompt.system_prompt
    assert "Do not call raw MCP tools" in prompt.system_prompt
    assert "final_preview_prompt" in prompt.output_schema["properties"]
    assert "generate_concept_images" in prompt.allowed_domain_tools


def test_blender_assembly_prompt_uses_split_viewer_and_render_tools() -> None:
    spec = get_prompt_node_spec("BlenderAssemblyPlanner")

    assert "export_viewer_scene" in spec.allowed_domain_tools
    assert "render_preview" in spec.allowed_domain_tools
    assert "export_viewer_scene render_preview" not in spec.allowed_domain_tools


def test_all_prompt_nodes_are_non_executing_json_contracts() -> None:
    for spec in NODE_SPECS.values():
        prompt = build_node_prompt(spec.node_name, context_json={})
        assert spec.may_execute_tools is False
        assert prompt.output_schema["type"] == "object"
        assert "Do not execute tools" in prompt.system_prompt
