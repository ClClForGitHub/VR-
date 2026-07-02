import json
import base64
from pathlib import Path

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.concept_image_execution import (
    ConceptImageBackend,
    ConceptImageBackendCapability,
    ConceptImageBackendGenerationRequest,
    ConceptImageBackendGenerationResult,
)
from agent_runtime.runtime_delegation import RuntimeDelegatedHandoffRecord
from agent_runtime.runtime_worker import execute_next_runtime_worker, read_runtime_worker_summary
from agent_runtime.state import (
    AgentProjectState,
    CameraSpec,
    ConceptBundle,
    ConceptImageRequirement,
    ConceptPromptPack,
    EnvironmentSpec,
    LightingSpec,
    SceneSpec,
    StyleSpec,
    SubjectSpec,
    WorkflowPhase,
)


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_runtime_worker_live_image_backend_applies_structured_concepts(tmp_path: Path) -> None:
    run_dir = _write_structured_concept_run(tmp_path)
    backend = _FakeConceptBackend()

    result = execute_next_runtime_worker(
        run_dir,
        backend="live_image",
        dry_run=False,
        confirm_execute=True,
        concept_image_backend=backend,
    )
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    worker_summary = read_runtime_worker_summary(run_dir)
    call_rows = _read_jsonl(run_dir / "live_generation_calls.jsonl")

    assert result.ok is True
    assert result.record is not None
    assert result.record.status == "applied"
    assert result.record.backend == "live_image"
    assert result.record.applied_artifact_ids == [
        "live_subject_concept_robot",
        "live_scene_concept_studio",
        "live_target_render_final_preview",
    ]
    assert state["phase"] == "CONCEPT_REVIEW"
    assert state["concept_bundle"]["subject_concept_images"]["subject_robot"] == ["live_subject_concept_robot"]
    assert state["concept_bundle"]["scene_concept_image_ids"] == ["live_scene_concept_studio"]
    assert state["concept_bundle"]["final_preview_image_id"] == "live_target_render_final_preview"
    assert call_rows[2]["source_image_paths"] == [call_rows[0]["output_image_path"], call_rows[1]["output_image_path"]]
    assert len(backend.calls) == 3
    assert worker_summary is not None
    assert worker_summary["handled_handoff_ids"] == ["handoff_001"]


class _FakeConceptBackend(ConceptImageBackend):
    backend_name = "fake_live_image"

    def __init__(self) -> None:
        self.calls: list[ConceptImageBackendGenerationRequest] = []

    def capability(self) -> ConceptImageBackendCapability:
        return ConceptImageBackendCapability(
            backend_name=self.backend_name,
            text_to_image=True,
            image_guided_single_reference=True,
            multi_image_composite=True,
            output_extraction=True,
            structured_file_attachments=True,
        )

    def generate(self, request: ConceptImageBackendGenerationRequest) -> ConceptImageBackendGenerationResult:
        self.calls.append(request)
        output = Path(request.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(PNG_BYTES)
        return ConceptImageBackendGenerationResult(ok=True, backend=self.backend_name, output_image_path=str(output))


def _write_structured_concept_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    requirements = [
        ConceptImageRequirement(
            requirement_id="subject_concept:robot",
            output_type="subject_concept",
            target_id="subject_robot",
            prompt_key="subject_prompts.subject_robot",
            user_review_label="Robot subject concept",
            purpose="subject source for 3D",
            generation_mode="text_to_image",
        ),
        ConceptImageRequirement(
            requirement_id="scene_concept:studio",
            output_type="scene_concept",
            target_id="scene_robot_studio",
            prompt_key="scene_prompts.0",
            user_review_label="Studio scene concept",
            purpose="scene source",
            generation_mode="text_to_image",
        ),
        ConceptImageRequirement(
            requirement_id="target_render:final_preview",
            output_type="target_render",
            target_id="scene_robot_studio",
            prompt_key="final_preview_prompt",
            user_review_label="Target render",
            purpose="composed target render",
            generation_mode="multi_image_composite",
            source_requirement_ids=["subject_concept:robot", "scene_concept:studio"],
            must_use_image_inputs=True,
        ),
    ]
    pack = ConceptPromptPack(
        final_preview_prompt="Composite the robot with the clean studio.",
        subject_prompts={"subject_robot": "Friendly compact robot."},
        scene_prompts=["Clean studio pedestal."],
        negative_prompt="blurry",
        image_requirements=requirements,
    )
    state = AgentProjectState(
        project_id="project_001",
        thread_id="thread_001",
        phase=WorkflowPhase.CONCEPT_GENERATION,
        scene_spec=SceneSpec(
            scene_id="scene_robot_studio",
            title="Robot Studio",
            user_goal="Create a compact robot display.",
            style=StyleSpec(style_keywords=["clean"], rendering_style="stylized"),
            environment=EnvironmentSpec(environment_type="studio", description="Clean studio."),
            lighting=LightingSpec(description="Soft light."),
            camera=CameraSpec(shot_type="three quarter"),
            subjects=[
                SubjectSpec(
                    subject_id="subject_robot",
                    display_name="Robot",
                    category="character",
                    description="Friendly compact robot.",
                )
            ],
        ),
        concept_bundle=ConceptBundle(concept_version=1, prompt_pack=pack),
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    _write_json(run_dir / "state.json", _model_to_dict(state))
    _write_json(run_dir / "summary.json", {"ok": True, "workflow": "test"})

    handoff_payload = {
        "handoff_id": "handoff_001",
        "run_dir": str(run_dir),
        "state_summary": {"subject_ids": ["subject_robot"]},
        "concept_generation": {
            "ok": True,
            "execution_order": [requirement.requirement_id for requirement in requirements],
            "requirements": [_requirement_payload(requirement, pack) for requirement in requirements],
        },
    }
    handoff_path = run_dir / "runtime_handoff" / "handoff_001.json"
    _write_json(handoff_path, handoff_payload)
    record = RuntimeDelegatedHandoffRecord(
        handoff_id="handoff_001",
        execution_id="exec_001",
        job_id="job_001",
        domain_tool_name="generate_concept_images",
        executor="domain_tool",
        status="planned",
        ok=True,
        created_at=utc_now_iso(),
        handoff_json=str(handoff_path),
    )
    _append_jsonl(run_dir / "runtime_handoff.jsonl", _model_to_dict(record))
    return run_dir


def _requirement_payload(requirement: ConceptImageRequirement, pack: ConceptPromptPack) -> dict:
    payload = _model_to_dict(requirement)
    if requirement.prompt_key == "final_preview_prompt":
        payload["prompt"] = pack.final_preview_prompt
    elif requirement.prompt_key.startswith("subject_prompts."):
        payload["prompt"] = pack.subject_prompts[requirement.prompt_key.split(".", 1)[1]]
    else:
        payload["prompt"] = pack.scene_prompts[0]
    payload["negative_prompt"] = pack.negative_prompt
    payload["resolved_input_images"] = []
    return payload


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
