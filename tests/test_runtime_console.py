import json
from pathlib import Path

import pytest

from agent_runtime.runtime_console import (
    append_console_message,
    create_runtime_console_run,
    read_console_messages,
    read_console_uploads,
    resolve_runtime_console_run_dir,
    save_console_upload,
)


def test_create_runtime_console_run_writes_state_summary_and_frontend_status(tmp_path: Path) -> None:
    result = create_runtime_console_run(root=tmp_path, run_id="run_001")
    run_dir = Path(result.run_dir)

    assert result.ok is True
    assert (run_dir / "state.json").exists()
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "frontend_status.json").exists()
    assert json.loads((run_dir / "state.json").read_text())["phase"] == "INTAKE"


def test_append_console_message_records_chat_and_user_turn(tmp_path: Path) -> None:
    result = create_runtime_console_run(root=tmp_path, run_id="run_001")
    message = append_console_message(result.run_dir, role="user", text="Make a robot.", attachment_ids=["image_001"])

    rows = read_console_messages(result.run_dir)
    state = json.loads((Path(result.run_dir) / "state.json").read_text())

    assert rows[0].message_id == message.message_id
    assert state["user_turns"][0]["text"] == "Make a robot."
    assert state["user_turns"][0]["image_ids"] == ["image_001"]


def test_save_console_upload_sanitizes_file_and_updates_input_image_state(tmp_path: Path) -> None:
    result = create_runtime_console_run(root=tmp_path, run_id="run_001")
    upload = save_console_upload(
        result.run_dir,
        filename="../robot ref.png",
        content=b"fake-png",
        mime_type="image/png",
    )
    state = json.loads((Path(result.run_dir) / "state.json").read_text())

    assert upload.filename == "robot_ref.png"
    assert Path(upload.uri).exists()
    assert upload.image_id is not None
    assert state["input_images"][0]["image_id"] == upload.image_id
    assert state["artifacts"][0]["artifact_type"] == "INPUT_IMAGE"
    assert read_console_uploads(result.run_dir)[0].upload_id == upload.upload_id


def test_resolve_runtime_console_run_dir_blocks_unsafe_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe run_id"):
        resolve_runtime_console_run_dir(root=tmp_path, run_id="../escape")

