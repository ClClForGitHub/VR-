import base64
import json
from pathlib import Path

from agent_runtime.codex_self_mcp import CodexSelfMCPCallPlan, CodexSelfMCPRunResult
from agent_runtime.runtime_audit import audit_runtime_run
from agent_runtime.runtime_console import append_console_message, create_runtime_console_run
from agent_runtime.runtime_delegation import plan_next_delegated_handoff
from agent_runtime.runtime_loop import run_bounded_runtime_loop
from agent_runtime.runtime_runs import build_runtime_run_bundle
from agent_runtime.runtime_worker import (
    execute_next_runtime_worker,
    read_runtime_worker_summary,
)


def test_runtime_worker_fixture_dry_run_writes_evidence_without_state_mutation(tmp_path: Path) -> None:
    created, handoff = _concept_handoff(tmp_path)
    before_state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))

    result = execute_next_runtime_worker(
        created.run_dir,
        dry_run=True,
        fixture_payload={"image_results": [{"image_path": str(tmp_path / "missing.png")}]},
    )
    after_state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    handoff_payload = json.loads(Path(handoff.record.handoff_json).read_text(encoding="utf-8"))
    bundle = build_runtime_run_bundle(created.run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "dry_run"
    assert result.record.handoff_id == handoff.record.handoff_id
    assert result.record.worker_json is not None
    assert "fixture_worker_dry_run_no_state_mutation" in result.record.issues
    assert before_state["phase"] == after_state["phase"] == "CONCEPT_GENERATION"
    assert not (Path(created.run_dir) / "runtime_handoff_apply.jsonl").exists()
    assert handoff_payload["runtime_job"]["job_id"] == handoff.record.job_id
    assert bundle.runtime_worker_summary is not None
    assert {"runtime_worker", "runtime_worker_summary"} <= {
        item.label for item in bundle.file_manifest.files if item.exists
    }


def test_runtime_worker_fixture_applies_concept_result_and_skips_reexecute(tmp_path: Path) -> None:
    created, handoff = _concept_handoff(tmp_path)
    image = tmp_path / "worker_concept.png"
    image.write_bytes(b"worker concept image")

    result = execute_next_runtime_worker(
        created.run_dir,
        dry_run=False,
        fixture_payload={
            "image_results": [
                {
                    "image_path": str(image),
                    "subject_id": "subject_robot",
                    "artifact_id": "subject_robot_concept_worker_001",
                    "final_preview": True,
                }
            ]
        },
    )
    rerun = execute_next_runtime_worker(
        created.run_dir,
        dry_run=False,
        fixture_payload={"image_results": []},
    )
    state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((Path(created.run_dir) / "runtime_plan.json").read_text(encoding="utf-8"))
    summary = read_runtime_worker_summary(created.run_dir)
    audit = audit_runtime_run(created.run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "applied"
    assert result.record.apply_id is not None
    assert result.record.applied_artifact_ids == ["subject_robot_concept_worker_001"]
    assert state["phase"] == "CONCEPT_REVIEW"
    assert state["concept_bundle"]["final_preview_image_id"] == "subject_robot_concept_worker_001"
    assert plan["runtime_plan"]["jobs"][0]["kind"] == "user_gate"
    assert summary is not None
    assert summary["handled_handoff_ids"] == [handoff.record.handoff_id]
    assert rerun.record is None
    assert rerun.message == "no_planned_handoff_for_worker"
    assert audit.ok is True


def test_runtime_worker_fixture_fails_when_result_payload_missing(tmp_path: Path) -> None:
    created, handoff = _concept_handoff(tmp_path)

    result = execute_next_runtime_worker(created.run_dir, dry_run=False, fixture_payload={})
    summary = read_runtime_worker_summary(created.run_dir)

    assert result.ok is False
    assert result.record is not None
    assert result.record.status == "failed"
    assert result.record.handoff_id == handoff.record.handoff_id
    assert "fixture_worker_missing_image_results" in result.record.issues
    assert summary is not None
    assert summary["handled_handoff_ids"] == []


def test_runtime_worker_codex_self_requires_confirm_before_calling_adapter(tmp_path: Path) -> None:
    created, handoff = _concept_handoff(tmp_path)
    adapter = _FakeCodexAdapter(create_image=True)
    before_state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))

    result = execute_next_runtime_worker(
        created.run_dir,
        backend="codex_self_mcp",
        dry_run=False,
        confirm_execute=False,
        codex_adapter=adapter,
    )
    after_state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "dry_run"
    assert result.record.backend == "codex_self_mcp"
    assert result.record.handoff_id == handoff.record.handoff_id
    assert "codex_self_worker_requires_confirm_execute" in result.record.issues
    assert adapter.calls == []
    assert len(adapter.plans) == 1
    assert adapter.plans[0].sandbox == "read-only"
    assert before_state["phase"] == after_state["phase"] == "CONCEPT_GENERATION"
    assert not (Path(created.run_dir) / "runtime_handoff_apply.jsonl").exists()


def test_runtime_worker_codex_self_confirmed_blocks_structured_concept_handoff(tmp_path: Path) -> None:
    created, handoff = _concept_handoff(tmp_path)
    adapter = _FakeCodexAdapter(create_image=True)

    result = execute_next_runtime_worker(
        created.run_dir,
        backend="codex_self_mcp",
        dry_run=False,
        confirm_execute=True,
        codex_adapter=adapter,
    )
    state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    summary = read_runtime_worker_summary(created.run_dir)

    assert result.ok is False
    assert result.record is not None
    assert result.record.status == "failed"
    assert result.record.backend == "codex_self_mcp"
    assert result.record.handoff_id == handoff.record.handoff_id
    assert "codex_self_worker_cannot_execute_multi_requirement_concept_handoff" in result.record.issues
    assert "codex_self_worker_cannot_resolve_source_requirement_images:target_render:final_preview" in result.record.issues
    assert len(adapter.calls) == 0
    assert state["phase"] == "CONCEPT_GENERATION"
    assert result.record.result_summary["reason"] == "codex_self_mcp_not_sufficient_for_structured_concept_handoff"
    assert not (Path(created.run_dir) / "runtime_handoff_apply.jsonl").exists()
    assert summary is not None
    assert summary["handled_handoff_ids"] == []


def test_runtime_worker_codex_self_confirmed_applies_extracted_concept_image(tmp_path: Path) -> None:
    created, handoff = _concept_handoff(tmp_path)
    _remove_concept_generation(handoff)
    adapter = _FakeCodexAdapter(create_image=True)

    result = execute_next_runtime_worker(
        created.run_dir,
        backend="codex_self_mcp",
        dry_run=False,
        confirm_execute=True,
        codex_adapter=adapter,
    )
    state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((Path(created.run_dir) / "runtime_plan.json").read_text(encoding="utf-8"))
    worker_json = json.loads(Path(result.record.worker_json).read_text(encoding="utf-8"))
    audit = audit_runtime_run(created.run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "applied"
    assert result.record.backend == "codex_self_mcp"
    assert result.record.apply_id is not None
    assert len(adapter.calls) == 1
    assert adapter.calls[0].sandbox == "read-only"
    assert result.record.applied_artifact_ids[0].startswith(f"{handoff.record.job_id}_worker_")
    assert state["phase"] == "CONCEPT_REVIEW"
    assert state["concept_bundle"]["final_preview_image_id"] == result.record.applied_artifact_ids[0]
    assert state["concept_bundle"]["subject_concept_images"]["subject_robot"] == result.record.applied_artifact_ids
    assert plan["runtime_plan"]["jobs"][0]["kind"] == "user_gate"
    assert worker_json["handoff_json"]["runtime_job"]["job_id"] == handoff.record.job_id
    assert worker_json["apply_payload"]["image_results"][0]["subject_id"] == "subject_robot"
    assert audit.ok is True


def test_runtime_worker_codex_self_missing_image_is_not_handled(tmp_path: Path) -> None:
    created, handoff = _concept_handoff(tmp_path)
    _remove_concept_generation(handoff)
    adapter = _FakeCodexAdapter(create_image=False)

    result = execute_next_runtime_worker(
        created.run_dir,
        backend="codex_self_mcp",
        dry_run=False,
        confirm_execute=True,
        codex_adapter=adapter,
    )
    state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    summary = read_runtime_worker_summary(created.run_dir)

    assert result.ok is False
    assert result.record is not None
    assert result.record.status == "failed"
    assert "codex_self_worker_missing_extracted_image" in result.record.issues
    assert len(adapter.calls) == 1
    assert state["phase"] == "CONCEPT_GENERATION"
    assert not (Path(created.run_dir) / "runtime_handoff_apply.jsonl").exists()
    assert summary is not None
    assert summary["handled_handoff_ids"] == []


def test_runtime_worker_codex_self_log_extracts_and_applies_concept_image(tmp_path: Path) -> None:
    created, handoff = _concept_handoff(tmp_path)
    codex_log = tmp_path / "codex_self_mcp_call.jsonl"
    codex_log.write_text(
        json.dumps(
            {
                "method": "codex/event",
                "params": {
                    "msg": {
                        "type": "image_generation_end",
                        "result": base64.b64encode(b"codex log concept image").decode("ascii"),
                    }
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = execute_next_runtime_worker(
        created.run_dir,
        backend="codex_self_log",
        dry_run=False,
        fixture_payload={
            "log_path": str(codex_log),
            "artifact_id": "subject_robot_codex_log_001",
        },
    )
    state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    worker_json = json.loads(Path(result.record.worker_json).read_text(encoding="utf-8"))
    audit = audit_runtime_run(created.run_dir)

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "applied"
    assert result.record.backend == "codex_self_log"
    assert result.record.handoff_id == handoff.record.handoff_id
    assert result.record.applied_artifact_ids == ["subject_robot_codex_log_001"]
    assert worker_json["extract_result"]["ok"] is True
    assert Path(worker_json["extract_result"]["output_path"]).read_bytes() == b"codex log concept image"
    assert worker_json["handoff_json"]["runtime_job"]["job_id"] == handoff.record.job_id
    assert state["phase"] == "CONCEPT_REVIEW"
    assert state["concept_bundle"]["final_preview_image_id"] == "subject_robot_codex_log_001"
    assert audit.ok is True


def test_runtime_worker_codex_self_log_missing_image_is_not_handled(tmp_path: Path) -> None:
    created, _handoff = _concept_handoff(tmp_path)
    codex_log = tmp_path / "codex_self_mcp_call.jsonl"
    codex_log.write_text('{"method":"codex/event","params":{"msg":{"type":"response"}}}\n', encoding="utf-8")

    result = execute_next_runtime_worker(
        created.run_dir,
        backend="codex_self_log",
        dry_run=False,
        fixture_payload={"log_path": str(codex_log)},
    )
    state = json.loads((Path(created.run_dir) / "state.json").read_text(encoding="utf-8"))
    summary = read_runtime_worker_summary(created.run_dir)

    assert result.ok is False
    assert result.record is not None
    assert result.record.status == "failed"
    assert result.record.backend == "codex_self_log"
    assert "missing_image_generation_result" in result.record.issues
    assert state["phase"] == "CONCEPT_GENERATION"
    assert not (Path(created.run_dir) / "runtime_handoff_apply.jsonl").exists()
    assert summary is not None
    assert summary["handled_handoff_ids"] == []


def _concept_handoff(tmp_path: Path):
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    append_console_message(created.run_dir, role="user", text="Create a compact robot display scene.")
    run_bounded_runtime_loop(
        created.run_dir,
        max_steps=8,
        dry_run=True,
        response_text_by_node=_fixture_responses(),
    )
    handoff = plan_next_delegated_handoff(created.run_dir)
    assert handoff.record is not None
    assert handoff.record.domain_tool_name == "generate_concept_images"
    return created, handoff


def _remove_concept_generation(handoff) -> None:
    path = Path(handoff.record.handoff_json)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("concept_generation", None)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class _FakeCodexAdapter:
    def __init__(self, *, create_image: bool) -> None:
        self.create_image = create_image
        self.plans: list[CodexSelfMCPCallPlan] = []
        self.calls: list[CodexSelfMCPCallPlan] = []

    def build_call_plan(self, **kwargs) -> CodexSelfMCPCallPlan:
        plan = CodexSelfMCPCallPlan(
            command=["fake-codex-self"],
            cwd=str(Path(kwargs["cwd"]).resolve()),
            sandbox=kwargs["sandbox"],
            approval_policy=kwargs["approval_policy"],
            timeout_seconds=kwargs["timeout_seconds"],
            log_path=str(kwargs["log_path"]),
            prompt_source="inline",
            prompt_preview=str(kwargs.get("prompt") or "")[:160],
            extract_last_image_to=str(kwargs["extract_last_image_to"]) if kwargs.get("extract_last_image_to") else None,
        )
        self.plans.append(plan)
        return plan

    def run_call_plan(self, plan: CodexSelfMCPCallPlan) -> CodexSelfMCPRunResult:
        self.calls.append(plan)
        assert Path(plan.log_path).parent.exists()
        if self.create_image and plan.extract_last_image_to:
            output = Path(plan.extract_last_image_to)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"codex self generated concept")
        return CodexSelfMCPRunResult(
            ok=True,
            returncode=0,
            stdout_tail="ok",
            stderr_tail="",
            plan=plan,
        )


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
