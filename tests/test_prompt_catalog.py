from pathlib import Path

from agent_runtime.agent_prompts import NODE_SPECS, build_node_prompt
from agent_runtime.prompt_catalog import render_prompt_catalog, write_prompt_catalog


def test_prompt_catalog_lists_all_nodes_and_full_contract() -> None:
    catalog = render_prompt_catalog()

    for node_name in NODE_SPECS:
        assert f"### {node_name}" in catalog
    assert "Do not execute tools" in catalog
    assert "Do not call raw MCP tools" in catalog
    assert "Output only one JSON object" in catalog
    assert "棉花" in catalog
    assert "\\u68c9" not in catalog


def test_prompt_catalog_can_be_written_for_user_review(tmp_path: Path) -> None:
    target = write_prompt_catalog(tmp_path / "agent_prompt_catalog.md")

    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "# Agent Prompt Catalog" in text
    assert "ReferenceBindingValidator" in text
    assert "output_json_schema" in text


def test_built_prompt_keeps_chinese_user_text_readable() -> None:
    prompt = build_node_prompt(
        "SceneInterpreter",
        context_json={
            "user_text": "请做一个黄色棉花娃娃，图1是主体参考。",
            "input_images": [{"image_id": "image_subject_001"}],
            "reference_bindings": [],
        },
    )

    assert "黄色棉花娃娃" in prompt.system_prompt
    assert "\\u9ec4" not in prompt.system_prompt
