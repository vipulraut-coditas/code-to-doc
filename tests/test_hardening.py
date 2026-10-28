"""Regression tests for the angry-tester findings (AT-001 ... AT-016)."""

import json
import os
import subprocess

import pytest

from codedoc import cli, formats, repo_source
from codedoc.cache import SummaryCache
from codedoc.config import Settings, load_settings
from codedoc.render import _bullets
from codedoc.scanner import redact_secrets, scan_repository
from codedoc.structured import invoke_structured
from codedoc.text import md_cell, md_safe


# ---------------------------------------------------------------- AT-001 .env is never loaded
def test_dotenv_in_working_dir_is_ignored(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("CODEDOC_BASE_URL=http://evil.invalid\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CODEDOC_BASE_URL", raising=False)
    seen = {}
    monkeypatch.setattr(cli, "cmd_doctor", lambda: seen.update(os.environ) or 0)
    cli.main(["doctor"])
    assert "CODEDOC_BASE_URL" not in seen


# ---------------------------------------------------------------- AT-002 secrets
@pytest.mark.parametrize("name", ["service-account.json", "firebase-adminsdk-x1.json", "kubeconfig.yaml",
                                  "wp-config.php"])
def test_credential_files_are_skipped(tmp_path, name):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / name).write_text("x: 1\n", encoding="utf-8")
    assert name not in [f["path"] for f in scan_repository(tmp_path).files]


def test_secret_values_are_redacted_but_code_is_not():
    code = ('AWS = "AKIAABCDEFGHIJKLMNOP"\nDB_PASSWORD = "S3cret#Pass"\n'
            'password = request.form["password"]\nTOKEN_TYPE = "Bearer"\n')
    out = redact_secrets(code, "Python")
    assert "AKIAABCDEFGHIJKLMNOP" not in out and "S3cret#Pass" not in out
    assert 'password = request.form["password"]' in out and '"Bearer"' in out
    yaml = "db:\r\n  POSTGRES_PASSWORD: Compose123\r\n  image: postgres\r\n"
    assert redact_secrets(yaml, "YAML") == "db:\r\n  POSTGRES_PASSWORD: [REDACTED]\r\n  image: postgres\r\n"
    assert "Conn#2" not in redact_secrets('{"db": "Server=x;Password=Conn#2"}', "JSON")
    assert "hunter22" not in redact_secrets('URL = "postgres://u:hunter22@db/x"', "Python")


def test_redaction_is_fast_on_long_lines():
    import time

    start = time.time()
    redact_secrets("x" * 200_000, "YAML")
    redact_secrets("password" * 25_000, "Python")
    assert time.time() - start < 5


# ---------------------------------------------------------------- AT-005 / AT-016 / AT-015 git clone
def test_clone_has_timeout_no_prompt_and_stripped_url(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(cmd=cmd, **kw)
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(repo_source.shutil, "which", lambda _: "git")
    monkeypatch.setattr(repo_source.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="did not finish"):
        with repo_source.open_repo("  https://example.invalid/repo.git "):
            pass
    assert "https://example.invalid/repo.git" in seen["cmd"]
    assert seen["timeout"] > 0 and seen["env"]["GIT_TERMINAL_PROMPT"] == "0"


@pytest.mark.parametrize("url,name", [("https://github.com/org/shop.git", "shop"),
                                      ("https://host/org/repo?ref=main", "repo"),
                                      ("git@github.com:org/my-app.git", "my-app")])
def test_display_name_is_a_valid_folder_name(url, name):
    assert repo_source.repo_display_name(url) == name


def test_read_only_files_are_removed(tmp_path):
    folder = tmp_path / "clone"
    folder.mkdir()
    locked = folder / "pack.idx"
    locked.write_text("x", encoding="utf-8")
    os.chmod(locked, 0o444)
    repo_source._remove_tree(folder)
    assert not folder.exists()


# ---------------------------------------------------------------- AT-006 key stays out of os.environ
def test_saved_api_key_is_not_copied_to_environment(monkeypatch):
    import langchain.chat_models as lcm

    from codedoc.llm import build_llm

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    captured = {}
    monkeypatch.setattr(lcm, "init_chat_model", lambda model, **kw: captured.update(kw))
    build_llm(Settings(provider="anthropic", fast_model="m", smart_model="m", api_key="sk-test-123"), "fast")
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert captured["api_key"] == "sk-test-123"


# ---------------------------------------------------------------- AT-008 escaping
def test_model_html_and_headings_are_neutralised():
    md = _bullets(['<img src=x onerror=alert(1)>\n\n# Injected'])
    assert "<img" not in md and "\n# Injected" not in md
    assert md_safe("use `List<String>` here") == "use `List<String>` here"
    assert md_safe("a < b and plain text") == "a < b and plain text"
    assert "<script" not in md_cell("<script>x</script>")


# ---------------------------------------------------------------- AT-009 backup instead of overwrite
def test_existing_file_is_backed_up(tmp_path):
    (tmp_path / "SRS.md").write_text("hand written", encoding="utf-8")
    outputs, warnings = formats.export_document("# new", formats=["md"], output_dir=tmp_path,
                                                filename="SRS.md", title="t")
    backups = [p for p in tmp_path.iterdir() if p.name.startswith("SRS.backup-")]
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "hand written"
    assert (tmp_path / "SRS.md").read_text(encoding="utf-8") == "# new"
    assert any("kept as" in w for w in warnings)


# ---------------------------------------------------------------- AT-010 damaged config / cache
@pytest.mark.parametrize("content", ["[]", '{"concurrency": "4", "max_files": -1, "fast_model": 5}'])
def test_damaged_config_does_not_crash(tmp_path, content):
    path = tmp_path / "config.json"
    path.write_text(content, encoding="utf-8")
    settings = load_settings(path)
    if settings is not None:
        assert settings.concurrency == 4 and settings.max_files == 300 and settings.fast_model == ""


def test_damaged_cache_is_ignored(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert SummaryCache(path, "m").get("a.py", "x") is None


# ---------------------------------------------------------------- AT-011 control characters in docx
def test_control_characters_do_not_drop_docx(tmp_path):
    outputs, warnings = formats.export_document("# T\n\nRule\x0bA \x1b[31mred", formats=["docx"],
                                                output_dir=tmp_path, filename="SRS.md", title="t")
    assert "docx" in outputs and not warnings


# ---------------------------------------------------------------- AT-012 nested JSON
def test_deeply_nested_reply_is_a_value_error(fake_llm, monkeypatch):
    from langchain_core.messages import AIMessage
    from pydantic import BaseModel

    class Doc(BaseModel):
        a: int = 0

    monkeypatch.setattr(type(fake_llm), "invoke", lambda self, messages: AIMessage(content="[" * 100_000))
    with pytest.raises(ValueError):
        invoke_structured(fake_llm, "x", Doc)


# ---------------------------------------------------------------- AT-013 / AT-014 CLI input checks
@pytest.mark.parametrize("args", [["--max-files", "0"], ["--max-files", "-5"],
                                  ["--concurrency", "0"], ["--concurrency", "100000"]])
def test_invalid_numbers_are_rejected(tmp_path, args):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["generate", str(tmp_path), *args])
    assert exc.value.code == 2


def test_unknown_provider_is_a_clean_error(tmp_path):
    assert cli.main(["generate", str(tmp_path), "--provider", "nope", "--fast-model", "f",
                     "--smart-model", "s", "--plain"]) == 2
