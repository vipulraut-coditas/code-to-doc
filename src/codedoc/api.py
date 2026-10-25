"""Public Python API:  ``from codedoc import generate_srs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from langchain_core.language_models.chat_models import BaseChatModel

from codedoc.cache import SummaryCache
from codedoc.config import BACKEND_CLAUDE_CODE, Settings, apply_env_overrides, load_settings
from codedoc.graph import AgentDeps, build_graph
from codedoc.llm import build_llm
from codedoc.repo_source import open_repo


@dataclass
class GenerationResult:
    output_path: Path
    markdown: str
    files_analysed: int
    functional_requirements: int
    warnings: list[str] = field(default_factory=list)


def default_output_path(repo: str) -> Path:
    from codedoc.repo_source import is_remote, repo_display_name

    if is_remote(repo):
        return Path.cwd() / f"{repo_display_name(repo)}-SRS.md"
    return Path(repo).expanduser().resolve() / "docs" / "SRS.md"


def model_label(settings: Settings) -> str:
    source = "Claude Code" if settings.backend == BACKEND_CLAUDE_CODE else settings.provider
    return f"LLM: {source} ({settings.fast_model} / {settings.smart_model})."


def generate_srs(repo: str, output: str | Path | None = None, settings: Settings | None = None, *,
                 on_progress: Callable[..., Any] | None = None, use_cache: bool = True,
                 fast_llm: BaseChatModel | None = None,
                 smart_llm: BaseChatModel | None = None) -> GenerationResult:
    """Analyse ``repo`` (folder or git URL) and write an SRS Markdown file."""
    settings = settings or apply_env_overrides(load_settings() or Settings())
    fast = fast_llm or build_llm(settings, "fast")
    smart = smart_llm or build_llm(settings, "smart")
    output_path = Path(output).expanduser().resolve() if output else default_output_path(repo)

    cache = SummaryCache.for_repo(repo, model_id=f"{settings.backend}:{settings.provider}:{settings.fast_model}",
                                  enabled=use_cache)
    deps = AgentDeps(fast_llm=fast, smart_llm=smart, cache=cache,
                     on_progress=on_progress or (lambda *a, **k: None),
                     max_files=settings.max_files, model_info=model_label(settings))

    with open_repo(repo) as (repo_path, project_name):
        graph = build_graph(deps)
        try:
            state = graph.invoke({"repo_path": str(repo_path), "project_name": project_name},
                                 config={"max_concurrency": max(1, settings.concurrency)})
        finally:
            cache.save()  # keep finished summaries even if a later step fails

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(state["srs_markdown"], encoding="utf-8")
    return GenerationResult(
        output_path=output_path,
        markdown=state["srs_markdown"],
        files_analysed=len(state.get("files", [])),
        functional_requirements=len(state.get("srs", {}).get("functional_requirements", [])),
        warnings=state.get("warnings", []),
    )
