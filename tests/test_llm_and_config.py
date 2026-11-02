import json
import subprocess

import pytest

from codedoc import llm_claude_cli
from codedoc.config import Settings, apply_env_overrides, load_settings, save_settings
from codedoc.llm import LLMConfigError, build_llm
from codedoc.llm_claude_cli import ClaudeCLIChatModel, ClaudeCLIError


def test_settings_roundtrip_hides_key_by_default():
    s = Settings(backend="api", provider="openai", fast_model="a", smart_model="b", api_key="sk-secret")
    path = save_settings(s)
    assert "sk-secret" not in path.read_text()
    loaded = load_settings()
    assert loaded.provider == "openai" and loaded.api_key is None

    save_settings(s, include_api_key=True)
    assert load_settings().api_key == "sk-secret"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("CODEDOC_PROVIDER", "xai")
    monkeypatch.setenv("CODEDOC_SMART_MODEL", "grok-x")
    s = apply_env_overrides(Settings(provider="openai", smart_model="gpt"))
    assert s.provider == "xai" and s.smart_model == "grok-x"


def test_build_llm_claude_code():
    s = Settings(backend="claude-code", fast_model="haiku", smart_model="sonnet")
    llm = build_llm(s, "smart")
    assert isinstance(llm, ClaudeCLIChatModel) and llm.model == "sonnet"


def test_build_llm_reports_missing_package_or_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigError):
        build_llm(Settings(backend="api", provider="xai", fast_model="a", smart_model="b"), "fast")


def test_unknown_provider():
    with pytest.raises(ValueError):
        build_llm(Settings(backend="api", provider="nope", fast_model="a", smart_model="b"), "fast")


class FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def test_claude_cli_model_parses_json(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["input"] = cmd, kwargs["input"]
        return FakeProc(stdout="warning line\n" + json.dumps({"is_error": False, "result": "hello"}))

    monkeypatch.setattr(llm_claude_cli, "find_claude", lambda p=None: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", fake_run)
    reply = ClaudeCLIChatModel(model="haiku").invoke([("system", "be a BA"), ("human", "hi")])
    assert reply.content == "hello"
    assert "--model" in seen["cmd"] and "haiku" in seen["cmd"]
    assert "--system-prompt" in seen["cmd"] and seen["input"] == "hi"


def test_claude_cli_old_version_fails_closed(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "--tools" in cmd:
            return FakeProc(stderr="error: unknown option '--tools'", returncode=1)
        return FakeProc(stdout=json.dumps({"result": "ok"}))

    monkeypatch.setattr(llm_claude_cli, "find_claude", lambda p=None: "claude")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ClaudeCLIError, match="claude update"):
        ClaudeCLIChatModel().invoke("x")
    assert len(calls) == 1  # never retried without --tools ""


def test_claude_cli_error(monkeypatch):
    monkeypatch.setattr(llm_claude_cli, "find_claude", lambda p=None: "claude")
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **k: FakeProc(stdout=json.dumps({"is_error": True, "result": "Not logged in"})))
    with pytest.raises(ClaudeCLIError, match="Not logged in"):
        ClaudeCLIChatModel().invoke("x")
