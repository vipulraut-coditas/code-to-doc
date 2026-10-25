"""File-summary cache: unchanged files are not sent to the LLM again.

Key = sha256(prompt version + model + file path + file content).
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from codedoc.config import config_dir

PROMPT_VERSION = "1"


class SummaryCache:
    def __init__(self, path: Path | None, model_id: str):
        self.path = path
        self.model_id = model_id
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._dirty = False
        if path and path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._data = {}

    @classmethod
    def for_repo(cls, repo: str, model_id: str, enabled: bool = True) -> "SummaryCache":
        if not enabled:
            return cls(None, model_id)
        repo_key = hashlib.sha256(repo.strip().lower().encode()).hexdigest()[:16]
        return cls(config_dir() / "cache" / f"{repo_key}.json", model_id)

    def key(self, path: str, content: str) -> str:
        raw = f"{PROMPT_VERSION}|{self.model_id}|{path}|{content}"
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()

    def get(self, path: str, content: str) -> dict | None:
        if not self.path:
            return None
        with self._lock:
            return self._data.get(self.key(path, content))

    def put(self, path: str, content: str, summary: dict) -> None:
        if not self.path:
            return
        with self._lock:
            self._data[self.key(path, content)] = summary
            self._dirty = True

    def save(self) -> None:
        if not self.path or not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.path.write_text(json.dumps(self._data), encoding="utf-8")
            self._dirty = False
