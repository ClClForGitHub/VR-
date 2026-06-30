"""Natural-language scenario fixtures for runtime smoke and prompt review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent_runtime.runtime_console import append_console_message, create_runtime_console_run
from agent_runtime.state import (
    AgentProjectState,
    ArtifactRecord,
    ArtifactType,
    InputImage,
    ReferenceBinding,
)


DEFAULT_SCENARIO_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "natural_language_scene_cases.json"
)


class ScenarioImageFixture(BaseModel):
    image_id: str
    artifact_id: str
    uri: str
    mime_type: str = "image/png"
    user_declared_label: str | None = None
    notes: str | None = None


class ScenarioExpectedOutcome(BaseModel):
    stop_reason: str
    final_phase: str
    subject_ids: list[str] = Field(default_factory=list)
    reference_binding_count: int = 0
    has_prompt_pack: bool = False
    first_runtime_status: str | None = None


class NaturalLanguageSceneCase(BaseModel):
    case_id: str
    language: str
    category: str
    description: str
    user_text: str
    input_images: list[ScenarioImageFixture] = Field(default_factory=list)
    declared_bindings: list[dict[str, Any]] = Field(default_factory=list)
    fixture_responses: dict[str, dict[str, Any]] = Field(default_factory=dict)
    expected: ScenarioExpectedOutcome

    def response_text_by_node(self) -> dict[str, str]:
        return {
            node_name: json.dumps(payload, ensure_ascii=False)
            for node_name, payload in self.fixture_responses.items()
        }


def load_natural_language_scene_cases(
    path: str | Path | None = None,
) -> list[NaturalLanguageSceneCase]:
    fixture_path = Path(path).expanduser().resolve() if path is not None else DEFAULT_SCENARIO_FIXTURE_PATH
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return [NaturalLanguageSceneCase(**item) for item in payload["cases"]]


def materialize_runtime_scenario_case(
    *,
    root: str | Path,
    case: NaturalLanguageSceneCase,
) -> Path:
    """Create a runtime-console run seeded with one scenario case."""

    created = create_runtime_console_run(root=root, run_id=case.case_id)
    run_dir = Path(created.run_dir)
    state = _read_state(run_dir)
    state.input_images.extend(_input_image(image) for image in case.input_images)
    state.artifacts.extend(_artifact_record(image, project_id=state.project_id) for image in case.input_images)
    state.reference_bindings.extend(ReferenceBinding(**binding) for binding in case.declared_bindings)
    _write_state(run_dir, state)
    append_console_message(
        run_dir,
        role="user",
        text=case.user_text,
        attachment_ids=[image.image_id for image in case.input_images],
        metadata={
            "scenario_case_id": case.case_id,
            "scenario_category": case.category,
            "scenario_language": case.language,
        },
    )
    return run_dir


def _input_image(image: ScenarioImageFixture) -> InputImage:
    return InputImage(
        image_id=image.image_id,
        artifact_id=image.artifact_id,
        uri=image.uri,
        mime_type=image.mime_type,
        user_declared_label=image.user_declared_label,
        notes=image.notes,
    )


def _artifact_record(image: ScenarioImageFixture, *, project_id: str) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=image.artifact_id,
        artifact_type=ArtifactType.INPUT_IMAGE,
        uri=image.uri,
        mime_type=image.mime_type,
        project_id=project_id,
        semantic_role="scenario_fixture_reference",
        metadata={
            "image_id": image.image_id,
            "user_declared_label": image.user_declared_label,
            "fixture_only": True,
        },
    )


def _read_state(run_dir: Path) -> AgentProjectState:
    return AgentProjectState(**json.loads((run_dir / "state.json").read_text(encoding="utf-8")))


def _write_state(run_dir: Path, state: AgentProjectState) -> None:
    payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else state.dict()
    (run_dir / "state.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
