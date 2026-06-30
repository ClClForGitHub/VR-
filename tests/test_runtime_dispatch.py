from pathlib import Path

from agent_runtime.runtime_console import create_runtime_console_run, save_console_upload
from agent_runtime.runtime_dispatch import build_and_save_runtime_dispatch_plan, read_runtime_dispatch_plan


def test_runtime_dispatch_plan_writes_controller_and_jobs_for_intake_run(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")

    result = build_and_save_runtime_dispatch_plan(created.run_dir)
    saved = read_runtime_dispatch_plan(created.run_dir)

    assert result.ok is True
    assert result.controller.actions[0].node_name == "ReferenceBindingValidator"
    assert result.runtime_plan.jobs[0].kind == "llm_node"
    assert Path(result.runtime_plan_json).exists()
    assert saved is not None
    assert saved["runtime_plan"]["phase"] == "INTAKE"


def test_runtime_dispatch_plan_blocks_unbound_uploaded_reference_image(tmp_path: Path) -> None:
    created = create_runtime_console_run(root=tmp_path, run_id="run_001")
    upload = save_console_upload(
        created.run_dir,
        filename="reference.png",
        content=b"fake-image",
        mime_type="image/png",
    )

    result = build_and_save_runtime_dispatch_plan(created.run_dir)

    assert result.ok is False
    assert result.controller.requires_user is True
    assert result.controller.blocked is True
    assert f"image_missing_binding:{upload.image_id}" in result.controller.issues
    assert result.runtime_plan.jobs[0].kind == "user_gate"
    assert result.runtime_plan.jobs[0].status == "waiting_user"
