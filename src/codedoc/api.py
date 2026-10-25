"""Public Python API:  ``from codedoc import generate_docs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from langchain_core.language_models.chat_models import BaseChatModel

from codedoc import formats as fmt
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
    outputs: dict[str, str] = field(default_factory=dict)  # format id -> file path or Google Docs URL
    markdown: str = ""
    data: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def output_path(self) -> Path | None:
        """First local file written (Markdown, else Word); None if the document failed or is Google-only."""
        local = self.outputs.get("md") or self.outputs.get("docx")
        return Path(local) if local else None


@dataclass
class GenerationResult:
    output_dir: Path | None
    documents: list[GeneratedDocument]
    files_analysed: int
    formats: list[str] = field(default_factory=lambda: ["md"])
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
                  settings: Settings | None = None, *, formats: str | Iterable[str] = ("md",),
                  google_folder: str | None = None,
                  on_progress: Callable[..., Any] | None = None, use_cache: bool = True,
                  fast_llm: BaseChatModel | None = None,
                  smart_llm: BaseChatModel | None = None) -> GenerationResult:
    """Analyse ``repo`` (folder or git URL) once and write every chosen document in every chosen format.

    ``doc_types``: ids from ``codedoc.DOC_TYPES`` (srs, user_manual, api, technical, design).
    ``formats``: ids from ``codedoc.FORMATS`` (md, docx, gdoc). Both accept a list, a comma-separated
    string or ``"all"``. ``google_folder``: optional Drive folder id for Google Docs output.
    """
    doc_ids = parse_doc_types(doc_types if isinstance(doc_types, str) else list(doc_types))
    format_ids = fmt.parse_formats(formats if isinstance(formats, str) else list(formats))
    # sign in to Google before the (long) analysis, so a setup problem shows up immediately
    google_creds = fmt.google_authorize() if "gdoc" in format_ids else None

    settings = settings or apply_env_overrides(load_settings() or Settings())
    fast = fast_llm or build_llm(settings, "fast")
    smart = smart_llm or build_llm(settings, "smart")
    out_dir = None
    if fmt.needs_output_dir(format_ids):
        out_dir = Path(output_dir).expanduser().resolve() if output_dir else default_output_dir(repo)

    cache = SummaryCache.for_repo(repo, model_id=f"{settings.backend}:{settings.provider}:{settings.fast_model}",
                                  enabled=use_cache)
    progress = on_progress or (lambda *a, **k: None)
    deps = AgentDeps(fast_llm=fast, smart_llm=smart, cache=cache, on_progress=progress,
                     max_files=settings.max_files, model_info=model_label(settings))

    with open_repo(repo) as (repo_path, project_name):
        graph = build_graph(deps)
        try:
            state = graph.invoke({"repo_path": str(repo_path), "project_name": project_name,
                                  "doc_types": doc_ids},
                                 config={"max_concurrency": max(1, settings.concurrency)})
        finally:
            cache.save()  # keep finished summaries even if a later step fails

    warnings = list(state.get("warnings", []))
    by_type = {d["doc_type"]: d for d in state.get("documents", [])}
    documents: list[GeneratedDocument] = []
    for doc_id in doc_ids:  # menu order, not completion order
        d = by_type[doc_id]
        outputs: dict[str, str] = {}
        if d["ok"]:
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
            name = d["data"].get("project_name") or project_name
            outputs, export_warnings = fmt.export_document(
                d["markdown"], formats=format_ids, output_dir=out_dir, filename=get_doc_type(doc_id).filename,
                title=f"{name} - {d['label']}", google_creds=google_creds, google_folder=google_folder)
            warnings += export_warnings
            progress("export_done", doc_type=doc_id, label=d["label"], outputs=outputs)
        documents.append(GeneratedDocument(doc_type=doc_id, label=d["label"], ok=d["ok"], outputs=outputs,
                                           markdown=d["markdown"], data=d["data"], error=d["error"]))
    return GenerationResult(
        output_dir=out_dir,
        documents=documents,
        files_analysed=len(state.get("files", [])),
        formats=format_ids,
        warnings=warnings,
    )
