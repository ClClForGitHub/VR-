import subprocess
import base64
import json
from pathlib import Path

import pytest

from agent_runtime.codex_self_mcp import CodexSelfMCPAdapter, extract_last_image_from_codex_mcp_log


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "codex-self-mcp"
    script = repo / "scripts" / "call_codex_mcp.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return repo


def _make_codex(tmp_path: Path) -> Path:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\n", encoding="utf-8")
    codex.chmod(0o755)
    return codex


def test_codex_self_mcp_status_probes_cli_and_local_helper(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    codex = _make_codex(tmp_path)
    calls = []

    def fake_run(args, timeout):
        calls.append(args)
        if args == [str(codex), "--help"]:
            return subprocess.CompletedProcess(args, 0, "Commands:\n  mcp-server\n", "")
        if args == [str(codex), "login", "status"]:
            return subprocess.CompletedProcess(args, 0, "Logged in using ChatGPT\n", "")
        if args == [str(codex), "mcp", "list"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "Name         Command  Args  Env  Cwd  Status   Auth\n"
                "blender_lab  blender  -     -    -    enabled  Unsupported\n",
                "",
            )
        raise AssertionError(args)

    adapter = CodexSelfMCPAdapter(repo_path=repo, codex_command=str(codex), run_command=fake_run)
    status = adapter.status()

    assert status.ok is True
    assert status.client_script_exists is True
    assert status.codex_cli_found is True
    assert status.login_status_ok is True
    assert status.login_status_summary == "Logged in using ChatGPT"
    assert status.mcp_server_supported is True
    assert status.configured_in_codex_mcp_list is False
    assert status.mcp_list_servers == ["blender_lab"]
    assert status.smoke_ok is None
    assert status.issues == []
    assert calls == [
        [str(codex), "--help"],
        [str(codex), "login", "status"],
        [str(codex), "mcp", "list"],
    ]


def test_codex_self_mcp_status_can_run_explicit_smoke(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    codex = _make_codex(tmp_path)

    def fake_run(args, timeout):
        if args == [str(codex), "--help"]:
            return subprocess.CompletedProcess(args, 0, "mcp-server\n", "")
        if args == [str(codex), "login", "status"]:
            return subprocess.CompletedProcess(args, 0, "Logged in using ChatGPT\n", "")
        if args == [str(codex), "mcp", "list"]:
            return subprocess.CompletedProcess(args, 0, "Name Command\ncodex codex\n", "")
        if args[0] == "python" and "call_codex_mcp.py" in args[1]:
            return subprocess.CompletedProcess(args, 0, "event: task_started\nMCP_OK\n", "")
        raise AssertionError(args)

    adapter = CodexSelfMCPAdapter(repo_path=repo, codex_command=str(codex), run_command=fake_run)
    status = adapter.status(run_smoke=True, smoke_cwd=tmp_path)

    assert status.ok is True
    assert status.configured_in_codex_mcp_list is True
    assert status.mcp_list_servers == ["codex"]
    assert status.smoke_ok is True
    assert "MCP_OK" in status.smoke_output
    assert status.issues == []


def test_codex_self_mcp_build_call_plan_validates_prompt_source(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    adapter = CodexSelfMCPAdapter(repo_path=repo)
    prompt = "hello " * 40

    plan = adapter.build_call_plan(
        prompt=prompt,
        cwd=tmp_path,
        sandbox="read-only",
        approval_policy="never",
        timeout_seconds=120,
        log_path=tmp_path / "call.jsonl",
    )

    assert plan.cwd == str(tmp_path.resolve())
    assert plan.sandbox == "read-only"
    assert plan.approval_policy == "never"
    assert plan.timeout_seconds == 120
    assert plan.log_path == str(tmp_path / "call.jsonl")
    assert plan.prompt_source == "inline"
    assert plan.prompt_file is None
    assert len(plan.prompt_preview) <= 160
    assert "--prompt" in plan.command
    assert str(repo / "scripts/call_codex_mcp.py") in plan.command

    with pytest.raises(ValueError):
        adapter.build_call_plan(cwd=tmp_path)
    with pytest.raises(ValueError):
        adapter.build_call_plan(prompt="x", prompt_file=tmp_path / "prompt.md", cwd=tmp_path)


def test_codex_self_mcp_run_call_plan_returns_structured_result(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    calls = []

    def fake_run(args, timeout):
        calls.append((args, timeout))
        return subprocess.CompletedProcess(args, 0, "line1\nhandoff ok\n", "")

    adapter = CodexSelfMCPAdapter(repo_path=repo, run_command=fake_run)
    plan = adapter.build_call_plan(
        prompt="handoff",
        cwd=tmp_path,
        timeout_seconds=42,
        log_path=tmp_path / "call.jsonl",
    )

    result = adapter.run_call_plan(plan)

    assert result.ok is True
    assert result.returncode == 0
    assert result.stdout_tail == "line1\nhandoff ok"
    assert result.stderr_tail == ""
    assert result.plan == plan
    assert result.issues == []
    assert calls == [(plan.command, 42)]


def test_codex_self_mcp_run_call_plan_captures_timeout(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    def fake_run(args, timeout):
        raise subprocess.TimeoutExpired(args, timeout, output="partial stdout", stderr="partial stderr")

    adapter = CodexSelfMCPAdapter(repo_path=repo, run_command=fake_run)
    plan = adapter.build_call_plan(
        prompt="handoff",
        cwd=tmp_path,
        timeout_seconds=42,
        log_path=tmp_path / "call.jsonl",
    )

    result = adapter.run_call_plan(plan)

    assert result.ok is False
    assert result.returncode is None
    assert result.stdout_tail == "partial stdout"
    assert result.stderr_tail == "partial stderr"
    assert result.issues == ["codex_self_mcp_call_timeout"]


def test_extract_last_image_from_codex_mcp_log_decodes_image_generation_result(tmp_path: Path) -> None:
    log_path = tmp_path / "call.jsonl"
    output_path = tmp_path / "last.png"
    image_bytes = b"fake-png-bytes"
    log_path.write_text(
        "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "codex/event",
                        "params": {
                            "msg": {
                                "type": "image_generation_end",
                                "result": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = extract_last_image_from_codex_mcp_log(log_path, output_path)

    assert result.ok is True
    assert result.size_bytes == len(image_bytes)
    assert output_path.read_bytes() == image_bytes


def test_extract_last_image_from_codex_mcp_log_reports_missing_result(tmp_path: Path) -> None:
    log_path = tmp_path / "call.jsonl"
    output_path = tmp_path / "last.png"
    log_path.write_text(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), encoding="utf-8")

    result = extract_last_image_from_codex_mcp_log(log_path, output_path)

    assert result.ok is False
    assert result.issues == ["missing_image_generation_result"]
    assert output_path.exists() is False


def test_codex_self_mcp_status_reports_missing_helper_or_cli(tmp_path: Path) -> None:
    adapter = CodexSelfMCPAdapter(
        repo_path=tmp_path / "missing-repo",
        codex_command=str(tmp_path / "missing-codex"),
    )

    status = adapter.status()

    assert status.ok is False
    assert status.client_script_exists is False
    assert status.codex_cli_found is False
    assert "missing_client_script" in status.issues
    assert "missing_codex_cli" in status.issues
