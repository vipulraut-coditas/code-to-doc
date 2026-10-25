"""Accept either a local folder or a git URL (cloned to a temp folder)."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_URL = re.compile(r"^(https?://|git@|ssh://)")


def is_remote(repo: str) -> bool:
    return bool(_URL.match(repo.strip()))


def repo_display_name(repo: str) -> str:
    repo = repo.strip().rstrip("/\\")
    name = re.split(r"[/\\:]", repo)[-1]
    return name[:-4] if name.endswith(".git") else name or "project"


@contextmanager
def open_repo(repo: str) -> Iterator[tuple[Path, str]]:
    """Yield ``(local_path, project_name)``; remote repos are deleted afterwards."""
    if not is_remote(repo):
        path = Path(repo).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"Folder not found: {path}")
        yield path, path.name
        return

    if not shutil.which("git"):
        raise RuntimeError("git is required to document a remote repository URL.")
    tmp = Path(tempfile.mkdtemp(prefix="codedoc-repo-"))
    try:
        proc = subprocess.run(["git", "clone", "--depth", "1", repo, str(tmp / "repo")],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {proc.stderr.strip()[:500]}")
        yield tmp / "repo", repo_display_name(repo)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
