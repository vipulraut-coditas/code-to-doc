"""The LangGraph workflow.

    START
      -> scan                      (plain Python)
      -> summarize_file  x N       (parallel via Send, fast model, cached)
      -> group_modules             (plain Python)
      -> summarize_module x M      (parallel via Send, fast model)
      -> plan_documents            (plain Python, join point)
      -> write_document x K        (parallel via Send, one per chosen doc type,
                                    smart model + plain Python -> Markdown)
      -> END

The repo is scanned and summarised once; every chosen document (SRS, user manual,
API doc, ...) is written from the same module summaries.

Dependencies (LLMs, cache, progress callback) are injected through
``AgentDeps`` so the graph can be tested with fake models.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from codedoc import prompts
from codedoc.cache import SummaryCache
from codedoc.doctypes import get_doc_type
from codedoc.scanner import scan_repository
from codedoc.schemas import FileSummary, ModuleSummary
from codedoc.state import DocState, DocumentTask, FileTask, ModuleTask
from codedoc.structured import invoke_structured
from codedoc.text import truncate

ProgressFn = Callable[..., None]

# technical facts collected next to the business view (used by API / developer / design docs)
TECHNICAL_FIELDS = ("api_endpoints", "public_interfaces", "user_interactions", "configuration", "dependencies")


def _noop(event: str, **data: Any) -> None:
    pass


@dataclass
class AgentDeps:
    fast_llm: BaseChatModel
    smart_llm: BaseChatModel
    cache: SummaryCache = field(default_factory=lambda: SummaryCache(None, "none"))
    on_progress: ProgressFn = _noop
    max_files: int = 300
    model_info: str = ""


def build_graph(deps: AgentDeps):
    progress = deps.on_progress

    # ---------- nodes ----------
    def scan(state: DocState) -> dict:
        progress("scan_start", repo=state["repo_path"])
        result = scan_repository(state["repo_path"], max_files=deps.max_files)
        warnings = []
        if result.total_candidates > len(result.files):
            warnings.append(
                f"Repository has {result.total_candidates} relevant files; the "
                f"{len(result.files)} most informative were analysed (raise --max-files to include more)."
            )
        if result.skipped_secrets:
            warnings.append(f"{result.skipped_secrets} secret-looking files (.env, keys, ...) were never sent to the LLM.")
        progress("scan_done", files=len(result.files), stack=result.stack,
                 total_candidates=result.total_candidates, skipped_secrets=result.skipped_secrets)
        return {"files": result.files, "stack": result.stack, "readme": result.readme,
                "total_candidates": result.total_candidates,
                "skipped_secrets": result.skipped_secrets, "warnings": warnings}

    def summarize_file(task: FileTask) -> dict:
        f = task["file"]
        cached = deps.cache.get(f["path"], f["content"])
        if cached is not None:
            progress("file_done", path=f["path"], cached=True, ok=True, seconds=0.0)
            return {"file_summaries": [cached]}

        prompt = prompts.FILE_SUMMARY.format(
            project_name=task["project_name"], stack=", ".join(task["stack"]) or "unknown",
            path=f["path"], language=f["language"], content=f["content"],
            truncated_note=" [content truncated]" if f.get("truncated") else "",
        )
        progress("file_start", path=f["path"], module=f["module"])
        started = time.monotonic()
        error = None
        try:
            summary = invoke_structured(deps.fast_llm, prompt, FileSummary, system=prompts.SYSTEM_ANALYST)
            record = {"path": f["path"], "module": f["module"], **summary.model_dump()}
            deps.cache.put(f["path"], f["content"], record)
            warnings: list[str] = []
        except Exception as exc:  # one bad file must not kill the whole run
            record = {"path": f["path"], "module": f["module"], "purpose": "", "error": str(exc)[:200]}
            warnings = [f"Could not summarise {f['path']}: {str(exc)[:200]}"]
            error = str(exc)[:200]
        progress("file_done", path=f["path"], cached=False, ok=error is None,
                 seconds=time.monotonic() - started, error=error)
        return {"file_summaries": [record], "warnings": warnings}

    def group_modules(state: DocState) -> dict:
        modules: dict[str, list[dict]] = defaultdict(list)
        for s in state.get("file_summaries", []):
            if s.get("purpose") or s.get("key_elements"):
                modules[s["module"]].append(s)
        progress("modules_start", modules=len(modules))
        return {"modules": dict(modules)}

    def summarize_module(task: ModuleTask) -> dict:
        name, summaries = task["module"], task["summaries"]
        files = [s["path"] for s in summaries]
        if len(summaries) == 1:  # nothing to merge: skip the LLM call
            s = summaries[0]
            record = {"module": name, "files": files, "purpose": s.get("purpose", ""),
                      "capabilities": s.get("key_elements", []), "business_rules": s.get("business_logic", []),
                      "entities": s.get("entities", []), "integrations": s.get("integrations", []), "actors": [],
                      **{k: s.get(k, []) for k in TECHNICAL_FIELDS}}
            progress("module_done", module=name, files=1, merged=False, ok=True, seconds=0.0)
            return {"module_summaries": [record]}

        compact = [{k: v for k, v in s.items() if k not in {"module", "error"} and v} for s in summaries]
        prompt = prompts.MODULE_SUMMARY.format(
            project_name=task["project_name"], stack=", ".join(task["stack"]) or "unknown",
            module=name, summaries=truncate(json.dumps(compact, indent=1), 60_000),
        )
        progress("module_start", module=name, files=len(files))
        started = time.monotonic()
        error = None
        try:
            summary = invoke_structured(deps.fast_llm, prompt, ModuleSummary, system=prompts.SYSTEM_ANALYST)
            record = {"module": name, "files": files, **summary.model_dump()}
            warnings: list[str] = []
        except Exception as exc:
            record = {"module": name, "files": files,
                      "purpose": "; ".join(s.get("purpose", "") for s in summaries)[:1500]}
            warnings = [f"Could not summarise module {name}: {str(exc)[:200]}"]
            error = str(exc)[:200]
        progress("module_done", module=name, files=len(files), merged=True, ok=error is None,
                 seconds=time.monotonic() - started, error=error)
        return {"module_summaries": [record], "warnings": warnings}

    def plan_documents(state: DocState) -> dict:
        progress("documents_start", doc_types=state.get("doc_types", []),
                 modules=len(state.get("module_summaries", [])))
        return {}

    def write_document(task: DocumentTask) -> dict:
        dt = get_doc_type(task["doc_type"])
        modules = sorted(task["module_summaries"], key=lambda m: m["module"])
        progress("document_start", doc_type=dt.id, label=dt.label)
        started = time.monotonic()
        prompt = dt.prompt.format(
            project_name=task["project_name"], stack=", ".join(task["stack"]) or "unknown",
            file_count=task["file_count"],
            readme=truncate(task["readme"] or "(no README)", 6_000),
            modules=truncate(json.dumps(modules, indent=1), 120_000),
        )
        try:  # one failed document must not lose the others
            doc = invoke_structured(deps.smart_llm, prompt, dt.schema, system=dt.system)
            if not doc.project_name:
                doc.project_name = task["project_name"]
            markdown = dt.render(
                doc, stack=task["stack"], module_summaries=modules, files_analysed=task["file_count"],
                warnings=task["warnings"], model_info=deps.model_info, generated_on=date.today().isoformat(),
            )
        except Exception as exc:
            error = str(exc)[:200]
            progress("document_done", doc_type=dt.id, label=dt.label, ok=False,
                     seconds=time.monotonic() - started, stats="", error=error)
            return {"documents": [{"doc_type": dt.id, "label": dt.label, "ok": False, "error": error,
                                   "data": {}, "markdown": ""}],
                    "warnings": [f"Could not write the {dt.label}: {error}"]}
        progress("document_done", doc_type=dt.id, label=dt.label, ok=True,
                 seconds=time.monotonic() - started, stats=dt.stats(doc), error=None)
        return {"documents": [{"doc_type": dt.id, "label": dt.label, "ok": True, "error": None,
                               "data": doc.model_dump(), "markdown": markdown}]}

    # ---------- fan-out routers (they return Send objects = parallel branches) ----------
    def fan_out_files(state: DocState):
        files = state.get("files", [])
        if not files:
            return "group_modules"
        return [Send("summarize_file", {"file": f, "project_name": state["project_name"],
                                        "stack": state.get("stack", [])}) for f in files]

    def fan_out_modules(state: DocState):
        modules = state.get("modules", {})
        if not modules:
            return "plan_documents"
        return [Send("summarize_module", {"module": name, "summaries": items,
                                          "project_name": state["project_name"],
                                          "stack": state.get("stack", [])})
                for name, items in modules.items()]

    def fan_out_documents(state: DocState):
        return [Send("write_document", {"doc_type": doc_id, "project_name": state["project_name"],
                                        "stack": state.get("stack", []), "readme": state.get("readme", ""),
                                        "file_count": len(state.get("files", [])),
                                        "module_summaries": state.get("module_summaries", []),
                                        "warnings": state.get("warnings", [])})
                for doc_id in state.get("doc_types") or ["srs"]]

    # ---------- wiring ----------
    g = StateGraph(DocState)
    g.add_node("scan", scan)
    g.add_node("summarize_file", summarize_file, input_schema=FileTask)
    g.add_node("group_modules", group_modules)
    g.add_node("summarize_module", summarize_module, input_schema=ModuleTask)
    g.add_node("plan_documents", plan_documents)
    g.add_node("write_document", write_document, input_schema=DocumentTask)

    g.add_edge(START, "scan")
    g.add_conditional_edges("scan", fan_out_files, ["summarize_file", "group_modules"])
    g.add_edge("summarize_file", "group_modules")
    g.add_conditional_edges("group_modules", fan_out_modules, ["summarize_module", "plan_documents"])
    g.add_edge("summarize_module", "plan_documents")
    g.add_conditional_edges("plan_documents", fan_out_documents, ["write_document"])
    g.add_edge("write_document", END)
    return g.compile()
