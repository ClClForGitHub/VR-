"""Round04 live user sample contracts and report helpers.

The runner uses this module as a thin layer over the existing runtime files.
It does not introduce another state store: case reports summarize the
authoritative run-local state, frontend status, runtime logs, and artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_runtime.runtime_runs import build_runtime_run_bundle


ReferenceTargetType = Literal["subject", "scene", "style", "pose", "texture", "layout"]
ReferenceUsage = Literal[
    "subject_reference",
    "scene_reference",
    "style_reference",
    "pose_reference",
    "texture_reference",
    "layout_reference",
]


class Round04ReferenceImage(BaseModel):
    slot: str
    image_id: str
    path: str
    declared_target_type: ReferenceTargetType
    declared_target_id: str | None = None
    usage: ReferenceUsage
    required_for_generation: bool = True
    upload_stage: str = "initial_request"
    source_text_span: str | None = None
    notes: str | None = None


class Round04ScriptedUserAction(BaseModel):
    gate: str
    action: str
    text: str
    reference_image_ids: list[str] = Field(default_factory=list)
    expected_next_phase: str | None = None
    notes: str | None = None


class Round04ExpectedMinimumCounts(BaseModel):
    concept_rounds: int = 1
    subject_concept_images: int = 1
    scene_concept_images: int = 1
    target_render_images: int = 1
    subject_glbs: int = 1
    scene_assets: int = 1
    preview_renders: int = 1
    viewer_glbs: int = 1


class Round04SubjectContract(BaseModel):
    subject_id: str
    display_name: str
    category: str = "character"
    needs_3d_asset: bool = True
    reference_image_ids: list[str] = Field(default_factory=list)


class Round04CaseManifest(BaseModel):
    case_id: str
    title: str
    category: str
    initial_user_request: str
    expected_subjects: list[Round04SubjectContract] = Field(default_factory=list)
    expected_scene: str
    reference_images: list[Round04ReferenceImage] = Field(default_factory=list)
    scripted_user_actions: list[Round04ScriptedUserAction] = Field(default_factory=list)
    expected_minimum_counts: Round04ExpectedMinimumCounts = Field(default_factory=Round04ExpectedMinimumCounts)
    raw_sample_source: str | None = None
    parse_notes: list[str] = Field(default_factory=list)

    def reference_path(self, case_dir: str | Path, image: Round04ReferenceImage) -> Path:
        path = Path(image.path)
        if path.is_absolute():
            return path
        return Path(case_dir).expanduser().resolve() / path


class Round04ValidationResult(BaseModel):
    ok: bool
    case_count: int
    cases: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class Round04CaseRunResult(BaseModel):
    case_id: str
    status: Literal["completed", "failed", "blocked", "partial"]
    run_dir: str
    concept_round_count: int = 0
    artifact_counts: dict[str, int] = Field(default_factory=dict)
    reference_handling: dict[str, Any] = Field(default_factory=dict)
    identity_research: dict[str, Any] = Field(default_factory=dict)
    state_paths: dict[str, str | None] = Field(default_factory=dict)
    frontend_evidence: dict[str, Any] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


def load_round04_case_manifest(path: str | Path) -> Round04CaseManifest:
    manifest_path = Path(path).expanduser().resolve()
    return Round04CaseManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))


def discover_round04_case_manifest_paths(
    fixtures_root: str | Path = "tests/fixtures/live_user_samples/round04",
) -> list[Path]:
    root = Path(fixtures_root).expanduser().resolve()
    if not root.exists():
        return []
    return sorted(root.glob("*/case_manifest.json"))


def load_round04_case_manifests(
    fixtures_root: str | Path = "tests/fixtures/live_user_samples/round04",
) -> list[tuple[Path, Round04CaseManifest]]:
    return [(path.parent, load_round04_case_manifest(path)) for path in discover_round04_case_manifest_paths(fixtures_root)]


def validate_round04_case_manifests(
    fixtures_root: str | Path = "tests/fixtures/live_user_samples/round04",
    *,
    expected_case_count: int = 12,
) -> Round04ValidationResult:
    issues: list[str] = []
    loaded = load_round04_case_manifests(fixtures_root)
    case_ids = [manifest.case_id for _case_dir, manifest in loaded]
    if len(loaded) != expected_case_count:
        issues.append(f"expected_{expected_case_count}_cases_got_{len(loaded)}")
    duplicates = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
    issues.extend(f"duplicate_case_id:{case_id}" for case_id in duplicates)
    for case_dir, manifest in loaded:
        if not (case_dir / "user_script.md").is_file():
            issues.append(f"missing_user_script:{manifest.case_id}")
        image_ids = [image.image_id for image in manifest.reference_images]
        duplicates = sorted({image_id for image_id in image_ids if image_ids.count(image_id) > 1})
        issues.extend(f"duplicate_reference_image_id:{manifest.case_id}:{image_id}" for image_id in duplicates)
        for image in manifest.reference_images:
            path = manifest.reference_path(case_dir, image)
            if not path.is_file():
                issues.append(f"missing_reference_image:{manifest.case_id}:{image.image_id}:{path}")
        known_image_ids = set(image_ids)
        for action in manifest.scripted_user_actions:
            for image_id in action.reference_image_ids:
                if image_id not in known_image_ids:
                    issues.append(f"action_unknown_reference_image:{manifest.case_id}:{action.action}:{image_id}")
    return Round04ValidationResult(ok=not issues, case_count=len(loaded), cases=case_ids, issues=issues)


def round04_case_run_dir(
    *,
    output_root: str | Path = "outputs/runs/round04_live_user_samples",
    case_id: str,
) -> Path:
    root = Path(output_root).expanduser().resolve()
    run_dir = (root / case_id).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"case_id escapes output root: {case_id}") from exc
    return run_dir


def build_round04_case_report(
    *,
    case_dir: str | Path,
    manifest: Round04CaseManifest,
    run_dir: str | Path,
    status: Literal["completed", "failed", "blocked", "partial"],
    issues: list[str] | None = None,
) -> Round04CaseRunResult:
    run_path = Path(run_dir).expanduser().resolve()
    state = _read_json(run_path / "state.json") or {}
    frontend_status = _read_json(run_path / "frontend_status.json") or {}
    summary = _read_json(run_path / "summary.json") or {}
    generation_calls = _read_jsonl(run_path / "live_generation_calls.jsonl")
    identity_rows = _read_jsonl(run_path / "identity_research.jsonl")
    bundle = build_runtime_run_bundle(run_path) if run_path.exists() else None
    artifact_counts = _artifact_counts(state)
    reference_rows = manifest.reference_images
    missing_required_inputs = [
        image.image_id
        for image in reference_rows
        if image.required_for_generation and not _reference_was_used(image.image_id, generation_calls)
    ]
    state_paths = {
        "state_json": str(run_path / "state.json") if (run_path / "state.json").exists() else None,
        "summary_json": str(run_path / "summary.json") if (run_path / "summary.json").exists() else None,
        "frontend_status_json": str(run_path / "frontend_status.json") if (run_path / "frontend_status.json").exists() else None,
        "runtime_plan_json": str(run_path / "runtime_plan.json") if (run_path / "runtime_plan.json").exists() else None,
    }
    frontend_evidence = {
        "api_snapshot": str(run_path / "runtime_api_bundle_snapshot.json")
        if (run_path / "runtime_api_bundle_snapshot.json").exists()
        else None,
        "asset_library_visible": bool(frontend_status.get("asset_library")),
        "active_selection_visible": bool(frontend_status.get("active_assembly_selection")),
        "file_manifest_count": len(bundle.file_manifest.files) if bundle and bundle.file_manifest else 0,
    }
    return Round04CaseRunResult(
        case_id=manifest.case_id,
        status=status,
        run_dir=str(run_path),
        concept_round_count=_concept_round_count(state, manifest),
        artifact_counts=artifact_counts,
        reference_handling={
            "reference_image_count": len(reference_rows),
            "uploaded_reference_count": _uploaded_reference_count(state),
            "image_generation_calls_with_required_inputs": _calls_with_inputs(generation_calls),
            "missing_required_inputs": missing_required_inputs,
        },
        identity_research={
            "required": _identity_research_required(manifest),
            "source_count": sum(len(row.get("source_urls") or []) for row in identity_rows if isinstance(row, dict)),
            "issues": [issue for row in identity_rows if isinstance(row, dict) for issue in row.get("issues", [])],
        },
        state_paths=state_paths,
        frontend_evidence=frontend_evidence,
        issues=list(issues or []),
    )


def write_round04_case_reports(
    *,
    case_dir: str | Path,
    manifest: Round04CaseManifest,
    run_dir: str | Path,
    status: Literal["completed", "failed", "blocked", "partial"],
    issues: list[str] | None = None,
) -> Round04CaseRunResult:
    report = build_round04_case_report(
        case_dir=case_dir,
        manifest=manifest,
        run_dir=run_dir,
        status=status,
        issues=issues,
    )
    run_path = Path(run_dir).expanduser().resolve()
    run_path.mkdir(parents=True, exist_ok=True)
    _write_json(run_path / "case_live_report.json", _model_to_dict(report))
    (run_path / "case_report.md").write_text(_case_report_markdown(report), encoding="utf-8")
    snapshot = build_runtime_run_bundle(run_path) if (run_path / "state.json").exists() else None
    if snapshot is not None:
        _write_json(run_path / "runtime_api_bundle_snapshot.json", _model_to_dict(snapshot))
    return report


def _artifact_counts(state: dict[str, Any]) -> dict[str, int]:
    artifacts = state.get("artifacts") if isinstance(state, dict) else []
    asset_library = state.get("asset_library") if isinstance(state, dict) else []
    by_type: dict[str, int] = {
        "subject_concept_images": 0,
        "scene_concept_images": 0,
        "target_render_images": 0,
        "subject_glbs": 0,
        "scene_assets": 0,
        "blender_files": 0,
        "preview_renders": 0,
        "viewer_scene_glbs": 0,
        "packages": 0,
    }
    for artifact in artifacts if isinstance(artifacts, list) else []:
        kind = artifact.get("artifact_type") if isinstance(artifact, dict) else None
        if kind == "SUBJECT_CONCEPT_IMAGE":
            by_type["subject_concept_images"] += 1
        elif kind == "SCENE_CONCEPT_IMAGE":
            by_type["scene_concept_images"] += 1
        elif kind == "FINAL_PREVIEW_IMAGE":
            by_type["target_render_images"] += 1
        elif kind == "SUBJECT_3D_ASSET":
            by_type["subject_glbs"] += 1
        elif kind == "SCENE_3D_ASSET":
            by_type["scene_assets"] += 1
        elif kind == "BLENDER_FILE":
            by_type["blender_files"] += 1
        elif kind == "BLENDER_PREVIEW_RENDER":
            by_type["preview_renders"] += 1
        elif kind == "VIEWER_SCENE_GLB":
            by_type["viewer_scene_glbs"] += 1
        elif kind == "EXPORT_PACKAGE":
            by_type["packages"] += 1
    for item in asset_library if isinstance(asset_library, list) else []:
        kind = item.get("asset_kind") if isinstance(item, dict) else None
        if kind == "subject_model":
            by_type["subject_glbs"] = max(by_type["subject_glbs"], 1)
        elif kind == "scene_asset":
            by_type["scene_assets"] = max(by_type["scene_assets"], 1)
    return by_type


def _concept_round_count(state: dict[str, Any], manifest: Round04CaseManifest) -> int:
    bundle = state.get("concept_bundle") if isinstance(state, dict) else None
    if isinstance(bundle, dict) and bundle.get("concept_version"):
        return int(bundle["concept_version"])
    return max(1, sum(1 for action in manifest.scripted_user_actions if action.gate == "concept_review"))


def _uploaded_reference_count(state: dict[str, Any]) -> int:
    images = state.get("input_images") if isinstance(state, dict) else []
    return len(images) if isinstance(images, list) else 0


def _calls_with_inputs(calls: list[dict[str, Any]]) -> int:
    return sum(1 for row in calls if row.get("input_image_paths") or row.get("source_image_paths"))


def _reference_was_used(image_id: str, calls: list[dict[str, Any]]) -> bool:
    for row in calls:
        if image_id in (row.get("input_reference_image_ids") or []):
            return True
        if image_id in " ".join(str(item) for item in row.get("input_image_paths") or []):
            return True
    return False


def _identity_research_required(manifest: Round04CaseManifest) -> bool:
    text = f"{manifest.title}\n{manifest.initial_user_request}\n{manifest.category}"
    markers = ["IP", "英雄联盟", "云顶", "TFT", "鸣潮", "崩坏", "星穹", "Helltaker", "剑星", "葬送"]
    return any(marker in text for marker in markers)


def _case_report_markdown(report: Round04CaseRunResult) -> str:
    payload = _model_to_dict(report)
    lines = [
        f"# Round04 Case Report: {report.case_id}",
        "",
        f"- status: {report.status}",
        f"- run_dir: {report.run_dir}",
        f"- concept_round_count: {report.concept_round_count}",
        f"- issues: {', '.join(report.issues) if report.issues else 'none'}",
        "",
        "## Artifact Counts",
        "",
    ]
    for key, value in report.artifact_counts.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## JSON", "", "```json", json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
