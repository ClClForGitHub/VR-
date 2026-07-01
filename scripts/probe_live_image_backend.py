#!/usr/bin/env python3
"""Probe the currently wired live concept-image backend capability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.concept_image_execution import CodexSelfMCPImage2ConceptBackend


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-report",
        default=str(ROOT / "outputs/runs/round04c_probe/live_image_backend_probe.json"),
    )
    args = parser.parse_args()

    path = Path(args.write_report).expanduser().resolve()
    backend = CodexSelfMCPImage2ConceptBackend(
        verify_view_image=True,
        probe_dir=path.parent / "codex_self_image2_probe",
    )
    capability = backend.capability()
    report = {
        "ok": bool(
            capability.text_to_image
            and capability.image_guided_single_reference
            and capability.multi_image_composite
            and capability.structured_file_attachments
            and capability.agent_view_image_then_generate
        ),
        "generated_at": utc_now_iso(),
        "backend": capability.backend_name,
        "capability": _model_to_dict(capability),
        "live_acceptance_ready": False,
        "notes": [
            "Round04C uses a fresh Codex child-agent session per concept requirement.",
            "The official codex MCP tool has no native images[] parameter; this backend uses child-agent view_image calls as the reference-image attachment boundary.",
        ],
    }
    report["live_acceptance_ready"] = report["ok"]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


if __name__ == "__main__":
    raise SystemExit(main())
