#!/usr/bin/env python3
"""Probe the currently wired live concept-image backend capability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_runtime.artifacts import utc_now_iso
from agent_runtime.concept_image_execution import CodexSelfMCPConceptImageBackend


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write-report",
        default=str(ROOT / "outputs/runs/round04b_probe/live_image_backend_probe.json"),
    )
    args = parser.parse_args()

    backend = CodexSelfMCPConceptImageBackend()
    capability = backend.capability()
    report = {
        "ok": bool(
            capability.text_to_image
            and capability.image_guided_single_reference
            and capability.multi_image_composite
            and capability.structured_file_attachments
        ),
        "generated_at": utc_now_iso(),
        "backend": capability.backend_name,
        "capability": _model_to_dict(capability),
        "live_acceptance_ready": False,
        "notes": [
            "Round04B live acceptance requires real local reference-image attachments and multi-image composition.",
            "The current codex-self helper is usable only where its capability flags are true.",
        ],
    }
    report["live_acceptance_ready"] = report["ok"]

    path = Path(args.write_report).expanduser().resolve()
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
