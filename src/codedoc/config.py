"""User settings: where they are stored and how they are loaded.

Settings live in ``~/.codedoc/config.json`` (override the folder with the
``CODEDOC_HOME`` environment variable). Environment variables can override any
saved value, which is handy for CI pipelines.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

BACKEND_API = "api"
BACKEND_CLAUDE_CODE = "claude-code"


def config_dir() -> Path:
    return Path(os.environ.get("CODEDOC_HOME") or Path.home() / ".codedoc")


def config_file() -> Path:
    return config_dir() / "config.json"


@dataclass
class Settings:
    backend: str = BACKEND_API          # "api" or "claude-code"
    provider: str = "anthropic"         # used when backend == "api"
    fast_model: str = ""                # cheap model: per-file and per-module summaries
    smart_model: str = ""               # strong model: requirement inference
    base_url: str | None = None         # Ollama / OpenAI-compatible endpoints
    api_key: str | None = None          # only stored if the user explicitly agreed
    claude_path: str | None = None      # full path of the `claude` executable
    concurrency: int = 4                # parallel LLM calls
    max_files: int = 300                # cap on files analysed per run

    def is_complete(self) -> bool:
        if not (self.fast_model and self.smart_model):
            return False
        return self.backend == BACKEND_CLAUDE_CODE or bool(self.provider)

    def describe(self) -> str:
        if self.backend == BACKEND_CLAUDE_CODE:
            where = "Claude Code (installed CLI)"
        else:
            from codedoc.providers import get_provider

            where = get_provider(self.provider).label
        return f"{where} | fast: {self.fast_model} | smart: {self.smart_model}"


def load_settings(path: Path | None = None) -> Settings | None:
    path = path or config_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    defaults = Settings()
    values = {}
    for f in fields(Settings):
        value = data.get(f.name)
        if value is None:
            continue
        default = getattr(defaults, f.name)
        if isinstance(default, int):  # a hand-edited "4" or "abc" must not crash every run
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            if value < 1:
                continue
        elif not isinstance(value, str):
            continue
        values[f.name] = value
    return Settings(**values)


def save_settings(settings: Settings, *, include_api_key: bool = False, path: Path | None = None) -> Path:
    path = path or config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(settings)
    if not include_api_key:
        data["api_key"] = None
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # best effort; no-op on Windows
    except OSError:
        pass
    return path


ENV_OVERRIDES = {
    "CODEDOC_BACKEND": "backend",
    "CODEDOC_PROVIDER": "provider",
    "CODEDOC_FAST_MODEL": "fast_model",
    "CODEDOC_SMART_MODEL": "smart_model",
    "CODEDOC_BASE_URL": "base_url",
}


def apply_env_overrides(settings: Settings) -> Settings:
    for env, attr in ENV_OVERRIDES.items():
        value = os.environ.get(env)
        if value:
            setattr(settings, attr, value)
    return settings
