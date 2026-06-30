"""Thin adapter for the local codex-self-mcp helper."""

from __future__ import annotations

import shutil
import subprocess
import base64
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - compatibility for Pydantic v1 environments
    from pydantic import BaseModel, Field


SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]
ApprovalPolicy = Literal["untrusted", "on-failure", "on-request", "never"]
CommandRunner = Callable[[list[str], float], subprocess.CompletedProcess[str]]


class CodexSelfMCPCallPlan(BaseModel):
    command: list[str]
    cwd: str
    sandbox: SandboxMode
    approval_policy: ApprovalPolicy
    timeout_seconds: float
    log_path: str
    prompt_source: Literal["inline", "file"]
    prompt_preview: str | None = None
    prompt_file: str | None = None
    extract_last_image_to: str | None = None


class CodexSelfMCPRunResult(BaseModel):
    ok: bool
    returncode: int | None = None
    stdout_tail: str | None = None
    stderr_tail: str | None = None
    plan: CodexSelfMCPCallPlan
    issues: list[str] = Field(default_factory=list)


class CodexSelfMCPImageExtractResult(BaseModel):
    ok: bool
    log_path: str
    output_path: str
    size_bytes: int | None = None
    issues: list[str] = Field(default_factory=list)
    error: str | None = None


class CodexSelfMCPStatus(BaseModel):
    ok: bool
    repo_path: str
    client_script_path: str
    client_script_exists: bool
    codex_command: str
    codex_cli_path: str | None = None
    codex_cli_found: bool = False
    login_status_ok: bool | None = None
    login_status_summary: str | None = None
    mcp_server_supported: bool | None = None
    configured_in_codex_mcp_list: bool | None = None
    mcp_list_servers: list[str] = Field(default_factory=list)
    smoke_ok: bool | None = None
    smoke_output: str | None = None
    issues: list[str] = Field(default_factory=list)


class CodexSelfMCPAdapter:
    """Probe and plan calls to the local Codex MCP stdio helper.

    The adapter deliberately treats codex-self-mcp as a sub-agent/MCP channel,
    not as an ordinary chat-model provider.
    """

    def __init__(
        self,
        repo_path: str | Path = "/home/team/zouzhiyuan/codex-self-mcp",
        *,
        codex_command: str = "codex",
        run_command: CommandRunner | None = None,
    ) -> None:
        self.repo_path = Path(repo_path).expanduser().resolve()
        self.codex_command = codex_command
        self.client_script_path = self.repo_path / "scripts" / "call_codex_mcp.py"
        self._run_command = run_command or _run_command

    def status(
        self,
        *,
        run_smoke: bool = False,
        smoke_cwd: str | Path = "/home/team/zouzhiyuan/safe",
        timeout_seconds: float = 30,
    ) -> CodexSelfMCPStatus:
        issues = []
        client_script_exists = self.client_script_path.is_file()
        if not client_script_exists:
            issues.append("missing_client_script")

        codex_cli_path = shutil.which(self.codex_command)
        codex_cli_found = codex_cli_path is not None
        if not codex_cli_found:
            issues.append("missing_codex_cli")

        login_status_ok = None
        login_status_summary = None
        mcp_server_supported = None
        configured_in_codex_mcp_list = None
        mcp_list_servers: list[str] = []
        smoke_ok = None
        smoke_output = None

        if codex_cli_found:
            help_result = self._run_command([self.codex_command, "--help"], timeout_seconds)
            mcp_server_supported = help_result.returncode == 0 and "mcp-server" in help_result.stdout
            if not mcp_server_supported:
                issues.append("codex_mcp_server_not_supported")

            login_result = self._run_command([self.codex_command, "login", "status"], timeout_seconds)
            login_status_summary = _compact_output(login_result.stdout or login_result.stderr)
            login_status_ok = login_result.returncode == 0 and "Logged in" in login_status_summary
            if not login_status_ok:
                issues.append("codex_not_logged_in")

            mcp_list_result = self._run_command([self.codex_command, "mcp", "list"], timeout_seconds)
            if mcp_list_result.returncode == 0:
                mcp_list_servers = _parse_mcp_list_names(mcp_list_result.stdout)
                configured_in_codex_mcp_list = "codex" in mcp_list_servers

        if run_smoke and client_script_exists and codex_cli_found:
            smoke = self.run_smoke(cwd=smoke_cwd, timeout_seconds=max(timeout_seconds, 60))
            smoke_ok = smoke["ok"]
            smoke_output = smoke["stdout_tail"]
            if not smoke_ok:
                issues.append("codex_self_mcp_smoke_failed")

        ok = (
            client_script_exists
            and codex_cli_found
            and bool(mcp_server_supported)
            and bool(login_status_ok)
            and (smoke_ok is not False)
        )
        return CodexSelfMCPStatus(
            ok=ok,
            repo_path=str(self.repo_path),
            client_script_path=str(self.client_script_path),
            client_script_exists=client_script_exists,
            codex_command=self.codex_command,
            codex_cli_path=codex_cli_path,
            codex_cli_found=codex_cli_found,
            login_status_ok=login_status_ok,
            login_status_summary=login_status_summary,
            mcp_server_supported=mcp_server_supported,
            configured_in_codex_mcp_list=configured_in_codex_mcp_list,
            mcp_list_servers=mcp_list_servers,
            smoke_ok=smoke_ok,
            smoke_output=smoke_output,
            issues=issues,
        )

    def build_call_plan(
        self,
        *,
        prompt: str | None = None,
        prompt_file: str | Path | None = None,
        cwd: str | Path,
        sandbox: SandboxMode = "workspace-write",
        approval_policy: ApprovalPolicy = "never",
        timeout_seconds: float = 300,
        log_path: str | Path = "/tmp/codex-self-mcp-call.jsonl",
        extract_last_image_to: str | Path | None = None,
    ) -> CodexSelfMCPCallPlan:
        if (prompt is None) == (prompt_file is None):
            raise ValueError("exactly one of prompt or prompt_file is required")
        command = [
            "python",
            str(self.client_script_path),
            "--cwd",
            str(Path(cwd).expanduser().resolve()),
            "--sandbox",
            sandbox,
            "--approval-policy",
            approval_policy,
            "--timeout",
            str(timeout_seconds),
            "--log",
            str(Path(log_path).expanduser()),
        ]
        prompt_source: Literal["inline", "file"]
        prompt_preview = None
        prompt_file_value = None
        if prompt is not None:
            command.extend(["--prompt", prompt])
            prompt_source = "inline"
            prompt_preview = _preview_prompt(prompt)
        else:
            prompt_path = Path(prompt_file).expanduser().resolve()
            command.extend(["--prompt-file", str(prompt_path)])
            prompt_source = "file"
            prompt_file_value = str(prompt_path)
        extract_path = None
        if extract_last_image_to is not None:
            extract_path = str(Path(extract_last_image_to).expanduser())
            command.extend(["--extract-last-image-to", extract_path])
        return CodexSelfMCPCallPlan(
            command=command,
            cwd=str(Path(cwd).expanduser().resolve()),
            sandbox=sandbox,
            approval_policy=approval_policy,
            timeout_seconds=timeout_seconds,
            log_path=str(Path(log_path).expanduser()),
            prompt_source=prompt_source,
            prompt_preview=prompt_preview,
            prompt_file=prompt_file_value,
            extract_last_image_to=extract_path,
        )

    def run_call_plan(self, plan: CodexSelfMCPCallPlan) -> CodexSelfMCPRunResult:
        try:
            result = self._run_command(plan.command, plan.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            return CodexSelfMCPRunResult(
                ok=False,
                returncode=None,
                stdout_tail=_tail_text(_timeout_output_to_text(exc.stdout)),
                stderr_tail=_tail_text(_timeout_output_to_text(exc.stderr)),
                plan=plan,
                issues=["codex_self_mcp_call_timeout"],
            )
        stdout_tail = _tail_text(result.stdout)
        stderr_tail = _tail_text(result.stderr)
        issues = []
        if result.returncode != 0:
            issues.append("codex_self_mcp_call_failed")
        return CodexSelfMCPRunResult(
            ok=result.returncode == 0,
            returncode=result.returncode,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            plan=plan,
            issues=issues,
        )

    def run_smoke(
        self,
        *,
        cwd: str | Path,
        timeout_seconds: float = 120,
        log_path: str | Path = "/tmp/codex-self-mcp-smoke.jsonl",
    ) -> dict[str, Any]:
        plan = self.build_call_plan(
            prompt="请只回复 MCP_OK，不要运行命令。",
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
        )
        result = self.run_call_plan(plan)
        return {
            "ok": result.ok and bool(result.stdout_tail and "MCP_OK" in result.stdout_tail),
            "returncode": result.returncode,
            "stdout_tail": result.stdout_tail,
            "stderr_tail": result.stderr_tail,
            "plan": _model_to_dict(plan),
        }


def extract_last_image_from_codex_mcp_log(
    log_path: str | Path,
    output_path: str | Path,
) -> CodexSelfMCPImageExtractResult:
    """Decode the last image_generation result from a codex MCP JSONL log."""

    log = Path(log_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    last_result: str | None = None
    try:
        with log.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("method") != "codex/event":
                    continue
                msg = obj.get("params", {}).get("msg", {})
                item = msg.get("item") or {}
                if item.get("type") in {"image_generation_call", "ImageGeneration"} and item.get("result"):
                    last_result = item["result"]
                if msg.get("type") == "image_generation_end" and msg.get("result"):
                    last_result = msg["result"]
        if not last_result:
            return CodexSelfMCPImageExtractResult(
                ok=False,
                log_path=str(log),
                output_path=str(output),
                issues=["missing_image_generation_result"],
                error=f"No image_generation result found in {log}",
            )
        raw = base64.b64decode(last_result)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        return CodexSelfMCPImageExtractResult(
            ok=True,
            log_path=str(log),
            output_path=str(output),
            size_bytes=len(raw),
        )
    except Exception as exc:
        return CodexSelfMCPImageExtractResult(
            ok=False,
            log_path=str(log),
            output_path=str(output),
            issues=["image_extract_failed"],
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_command(args: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


def _timeout_output_to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _parse_mcp_list_names(output: str) -> list[str]:
    names = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Name "):
            continue
        names.append(stripped.split()[0])
    return names


def _compact_output(text: str, *, limit: int = 400) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


def _tail_text(text: str, *, lines: int = 20) -> str:
    return "\n".join(text.splitlines()[-lines:])


def _preview_prompt(prompt: str, *, limit: int = 160) -> str:
    compact = " ".join(prompt.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _model_to_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()
