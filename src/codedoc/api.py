"""Public Python API:  ``from codedoc import generate_docs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from langchain_core.language_models.chat_models import BaseChatModel

from codedoc.cache import SummaryCache
from codedoc.config import BACKEND_CLAUDE_CODE, Settings, apply_env_overrides, load_settings
from codedoc.doctypes import get_doc_type, parse_doc_types
from codedoc.graph import AgentDeps, build_graph
from codedoc.llm import build_llm
from codedoc.repo_source import open_repo


@dataclass
class GeneratedDocument:
    doc_type: str
    label: str
    ok: bool
    output_path: Path | None = None   # None when the document failed
    markdown: str = ""
    data: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class GenerationResult:
    output_dir: Path
    documents: list[GeneratedDocument]
    files_analysed: int
    warnings: list[str] = field(default_factory=list)

    def get(self, doc_type: str) -> GeneratedDocument | None:
        return next((d for d in self.documents if d.doc_type == doc_type), None)


def default_output_dir(repo: str) -> Path:
    from codedoc.repo_source import is_remote, repo_display_name

    if is_remote(repo):
        return Path.cwd() / f"{repo_display_name(repo)}-docs"
    return Path(repo).expanduser().resolve() / "docs"


def model_label(settings: Settings) -> str:
    source = "Claude Code" if settings.backend == BACKEND_CLAUDE_CODE else settings.provider
    return f"LLM: {source} ({settings.fast_model} / {settings.smart_model})."


def generate_docs(repo: str, doc_types: str | Iterable[str] = ("srs",), output_dir: str | Path | None = None,
                  settings: Settings | None = None, *,
                  on_progress: Callable[..., Any] | None = None, use_cache: bool = True,
                  fast_llm: BaseChatModel | None = None,
                  smart_llm: BaseChatModel | None = None) -> GenerationResult:
    """Analyse ``repo`` (folder or git URL) once and write one Markdown file per chosen document.

    ``doc_types``: ids from ``codedoc.DOC_TYPES`` (srs, user_manual, api, technical, design),
    as a list or a comma-separated string; ``"all"`` selects every type.
    """
    doc_ids = parse_doc_types(doc_types if isinstance(doc_types, str) else list(doc_types))
    settings = settings or apply_env_overrides(load_settings() or Settings())
    fast = fast_llm or build_llm(settings, "fast")
    smart = smart_llm or build_llm(settings, "smart")
    out_dir = Path(output_dir).expanduser().resolve() if output_dir else default_output_dir(repo)

    cache = SummaryCache.for_repo(repo, model_id=f"{settings.backend}:{settings.provider}:{settings.fast_model}",
                                  enabled=use_cache)
    deps = AgentDeps(fast_llm=fast, smart_llm=smart, cache=cache,
                     on_progress=on_progress or (lambda *a, **k: None),
                     max_files=settings.max_files, model_info=model_label(settings))

    with open_repo(repo) as (repo_path, project_name):
        graph = build_graph(deps)
        try:
            state = graph.invoke({"repo_path": str(repo_path), "project_name": project_name,
                                  "doc_types": doc_ids},
                                 config={"max_concurrency": max(1, settings.concurrency)})
        finally:
            cache.save()  # keep finished summaries even if a later step fails

    by_type = {d["doc_type"]: d for d in state.get("documents", [])}
    documents: list[GeneratedDocument] = []
    for doc_id in doc_ids:  # menu order, not completion order
        d = by_type[doc_id]
        path = None
        if d["ok"]:
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / get_doc_type(doc_id).filename
            path.write_text(d["markdown"], encoding="utf-8")
        documents.append(GeneratedDocument(doc_type=doc_id, label=d["label"], ok=d["ok"], output_path=path,
                                           markdown=d["markdown"], data=d["data"], error=d["error"]))
    return GenerationResult(
        output_dir=out_dir,
        documents=documents,
        files_analysed=len(state.get("files", [])),
        warnings=state.get("warnings", []),
    )
