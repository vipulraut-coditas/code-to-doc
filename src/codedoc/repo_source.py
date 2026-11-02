"""Accept either a local folder or a git URL (cloned to a temp folder)."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_URL = re.compile(r"^(https?://|git@|ssh://)")
_BAD_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CLONE_TIMEOUT = 600  # seconds; override with CODEDOC_CLONE_TIMEOUT


def is_remote(repo: str) -> bool:
    return bool(_URL.match(repo.strip()))


def repo_display_name(repo: str) -> str:
    repo = re.split(r"[?#]", repo.strip())[0].rstrip("/\\")
    name = re.split(r"[/\\:]", repo)[-1]
    name = name[:-4] if name.endswith(".git") else name
    return _BAD_NAME_CHARS.sub("-", name).rstrip(" .") or "project"


def _clone_timeout() -> int:
    try:
        return max(1, int(os.environ.get("CODEDOC_CLONE_TIMEOUT") or CLONE_TIMEOUT))
    except ValueError:
        return CLONE_TIMEOUT


def _force_remove(func, path, _exc) -> None:
    """git writes read-only pack files; Windows refuses to delete them until the flag is cleared."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _remove_tree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_force_remove)
    else:
        shutil.rmtree(path, onerror=_force_remove)


@contextmanager
def open_repo(repo: str) -> Iterator[tuple[Path, str]]:
    """Yield ``(local_path, project_name)``; remote repos are deleted afterwards."""
    repo = repo.strip()
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
        timeout = _clone_timeout()
        try:
            # GIT_TERMINAL_PROMPT=0: a private repo fails fast instead of waiting for a password forever
            proc = subprocess.run(["git", "clone", "--depth", "1", repo, str(tmp / "repo")],
                                  capture_output=True, text=True, timeout=timeout,
                                  env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"git clone did not finish within {timeout}s "
                               "(set CODEDOC_CLONE_TIMEOUT to allow more time).") from None
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {proc.stderr.strip()[:500]}")
        yield tmp / "repo", repo_display_name(repo)
    finally:
        _remove_tree(tmp)
