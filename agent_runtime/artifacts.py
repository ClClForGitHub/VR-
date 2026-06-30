"""Filesystem artifact metadata store for the V1 agent runtime."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_runtime.state import ArtifactRecord, ArtifactType


EXPLICIT_MIME_TYPES = {
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".blend": "application/x-blender",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_to_json_line(record: ArtifactRecord) -> str:
    if hasattr(record, "model_dump"):
        payload = record.model_dump(mode="json")
    else:
        payload = record.dict()
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def guess_mime_type(path: Path) -> str:
    return EXPLICIT_MIME_TYPES.get(
        path.suffix.lower(),
        mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )


class FileArtifactStore:
    """Append-only metadata store.

    The store can either register existing files in place or copy them under
    the store root. In both modes, graph state receives only ArtifactRecord
    metadata and never the binary payload.
    """

    def __init__(self, root: str | Path, metadata_filename: str = "artifacts.jsonl") -> None:
        self.root = Path(root).expanduser().resolve()
        self.metadata_path = self.root / metadata_filename

    def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.touch(exist_ok=True)

    def register_file(
        self,
        source_path: str | Path,
        artifact_type: ArtifactType,
        *,
        semantic_role: str | None = None,
        artifact_id: str | None = None,
        version: int = 1,
        mime_type: str | None = None,
        copy_into_store: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        source = Path(source_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        if not source.is_file():
            raise ValueError(f"artifact source is not a file: {source}")

        self.ensure_ready()
        artifact_id = artifact_id or f"{artifact_type.value.lower()}_{uuid4().hex[:12]}"
        target = source
        if copy_into_store:
            target_dir = self.root / artifact_type.value.lower()
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{artifact_id}{source.suffix}"
            if target != source:
                shutil.copy2(source, target)

        stat = target.stat()
        detected_mime = guess_mime_type(target)
        record = ArtifactRecord(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            uri=str(target),
            mime_type=mime_type or detected_mime,
            semantic_role=semantic_role,
            version=version,
            size_bytes=stat.st_size,
            sha256=sha256_file(target),
            created_at=utc_now_iso(),
            metadata=metadata or {},
        )
        self.append_record(record)
        return record

    def append_record(self, record: ArtifactRecord) -> None:
        self.ensure_ready()
        with self.metadata_path.open("a", encoding="utf-8") as handle:
            handle.write(model_to_json_line(record) + "\n")

    def load_records(self) -> list[ArtifactRecord]:
        if not self.metadata_path.exists():
            return []
        records = []
        with self.metadata_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                records.append(ArtifactRecord(**json.loads(line)))
        return records
