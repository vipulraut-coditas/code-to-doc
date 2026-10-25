"""Use an already-installed Claude Code CLI as a LangChain chat model.

This is the *Adapter pattern*: ``claude -p`` (headless mode) is wrapped in a
``BaseChatModel`` so the LangGraph nodes cannot tell it apart from
ChatAnthropic, ChatOpenAI or any other model.

Uses the user's own Claude Code login (subscription), so no API key is needed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from codedoc.text import message_text

_STDIN_INSTRUCTION = "Follow the instructions provided via stdin."
# Newer CLI versions support these flags; older ones are retried without them.
_LEGACY_CLI = False
_WORKDIR: str | None = None


class ClaudeCLIError(RuntimeError):
    pass


def find_claude(explicit_path: str | None = None) -> str | None:
    if explicit_path and shutil.which(explicit_path):
        return shutil.which(explicit_path)
    return shutil.which("claude")


def _empty_workdir() -> str:
    """Run Claude Code in an empty folder so it never wanders into other files."""
    global _WORKDIR
    if _WORKDIR is None:
        _WORKDIR = tempfile.mkdtemp(prefix="codedoc-claude-")
    return _WORKDIR


def _parse_output(stdout: str) -> dict:
    stdout = stdout.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Some versions print warnings before the JSON line.
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        raise ClaudeCLIError(f"Could not read Claude Code output: {stdout[:300]}")


def run_claude(prompt: str, *, model: str | None, system: str | None,
               claude_path: str, timeout: int) -> str:
    global _LEGACY_CLI
    if not _LEGACY_CLI:
        cmd = [claude_path, "-p", _STDIN_INSTRUCTION, "--output-format", "json",
               "--tools", "", "--no-session-persistence"]
        if system:
            # one line: newlines inside arguments break Windows .cmd launchers
            cmd += ["--system-prompt", " ".join(system.split())]
        stdin = prompt
    else:
        cmd = [claude_path, "-p", _STDIN_INSTRUCTION, "--output-format", "json"]
        stdin = f"[SYSTEM]\n{system}\n\n{prompt}" if system else prompt
    if model:
        cmd += ["--model", model]

    try:
        proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout, cwd=_empty_workdir())
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCLIError(f"Claude Code did not answer within {timeout}s") from exc
    except FileNotFoundError as exc:
        raise ClaudeCLIError(f"Claude Code executable not found: {claude_path}") from exc

    if proc.returncode != 0 and not _LEGACY_CLI and "unknown option" in proc.stderr.lower():
        _LEGACY_CLI = True
        return run_claude(prompt, model=model, system=system,
                          claude_path=claude_path, timeout=timeout)

    if not proc.stdout.strip():
        raise ClaudeCLIError((proc.stderr or "Claude Code returned no output").strip()[:500])

    data = _parse_output(proc.stdout)
    if data.get("is_error") or proc.returncode != 0:
        raise ClaudeCLIError(str(data.get("result") or proc.stderr or data)[:500])
    return str(data.get("result", ""))


class ClaudeCLIChatModel(BaseChatModel):
    """LangChain chat model backed by the local ``claude`` command."""

    model: str = "sonnet"
    claude_path: str | None = None
    timeout: int = 600

    @property
    def _llm_type(self) -> str:
        return "claude-code-cli"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model}

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        path = find_claude(self.claude_path)
        if not path:
            raise ClaudeCLIError("Claude Code ('claude') is not installed or not on PATH.")

        system = "\n\n".join(message_text(m) for m in messages if isinstance(m, SystemMessage))
        convo = [m for m in messages if not isinstance(m, SystemMessage)]
        if len(convo) == 1:
            prompt = message_text(convo[0])
        else:
            prompt = "\n\n".join(f"[{m.type.upper()}]\n{message_text(m)}" for m in convo)

        text = run_claude(prompt, model=self.model, system=system or None,
                          claude_path=path, timeout=self.timeout)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


@dataclass
class ClaudeStatus:
    installed: bool
    path: str | None = None
    version: str | None = None
    logged_in: bool = False
    message: str = ""


def check_claude_code(model: str = "haiku", claude_path: str | None = None) -> ClaudeStatus:
    """Is Claude Code installed, and can it answer a prompt (i.e. is it logged in)?"""
    path = find_claude(claude_path)
    if not path:
        return ClaudeStatus(False, message="The 'claude' command was not found on PATH.")

    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
        version = (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else None
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ClaudeStatus(False, path=path, message=f"Could not run '{path} --version': {exc}")

    try:
        reply = run_claude("Reply with exactly: OK", model=model, system=None,
                           claude_path=path, timeout=180)
    except ClaudeCLIError as exc:
        return ClaudeStatus(True, path=path, version=version, logged_in=False, message=str(exc))
    return ClaudeStatus(True, path=path, version=version, logged_in=True,
                        message=f"Claude Code replied: {reply.strip()[:40]}")
