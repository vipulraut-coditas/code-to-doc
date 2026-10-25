"""The LangGraph workflow.

    START
      -> scan                      (plain Python)
      -> summarize_file  x N       (parallel via Send, fast model, cached)
      -> group_modules             (plain Python)
      -> summarize_module x M      (parallel via Send, fast model)
      -> infer_requirements        (smart model)
      -> render_srs                (plain Python -> Markdown)
      -> END

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
from codedoc.render import render_srs_markdown
from codedoc.scanner import scan_repository
from codedoc.schemas import FileSummary, ModuleSummary, SRSDocument
from codedoc.state import DocState, FileTask, ModuleTask
from codedoc.structured import invoke_structured
from codedoc.text import truncate

ProgressFn = Callable[..., None]


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
            summary = invoke_structured(deps.fast_llm, prompt, FileSummary)
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
                      "entities": s.get("entities", []), "integrations": s.get("integrations", []), "actors": []}
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
            summary = invoke_structured(deps.fast_llm, prompt, ModuleSummary)
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

    def infer_requirements(state: DocState) -> dict:
        modules = sorted(state.get("module_summaries", []), key=lambda m: m["module"])
        progress("requirements_start", modules=len(modules))
        started = time.monotonic()
        prompt = prompts.REQUIREMENTS.format(
            project_name=state["project_name"], stack=", ".join(state.get("stack", [])) or "unknown",
            file_count=len(state.get("files", [])),
            readme=truncate(state.get("readme", "") or "(no README)", 6_000),
            modules=truncate(json.dumps(modules, indent=1), 120_000),
        )
        srs = invoke_structured(deps.smart_llm, prompt, SRSDocument)
        if not srs.project_name:
            srs.project_name = state["project_name"]
        progress("requirements_done", requirements=len(srs.functional_requirements),
                 nfrs=len(srs.non_functional_requirements), seconds=time.monotonic() - started)
        return {"srs": srs.model_dump()}

    def render_srs(state: DocState) -> dict:
        markdown = render_srs_markdown(
            SRSDocument.model_validate(state["srs"]),
            stack=state.get("stack", []),
            module_summaries=state.get("module_summaries", []),
            files_analysed=len(state.get("files", [])),
            warnings=state.get("warnings", []),
            model_info=deps.model_info,
            generated_on=date.today().isoformat(),
        )
        progress("render_done")
        return {"srs_markdown": markdown}

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
            return "infer_requirements"
        return [Send("summarize_module", {"module": name, "summaries": items,
                                          "project_name": state["project_name"],
                                          "stack": state.get("stack", [])})
                for name, items in modules.items()]

    # ---------- wiring ----------
    g = StateGraph(DocState)
    g.add_node("scan", scan)
    g.add_node("summarize_file", summarize_file, input_schema=FileTask)
    g.add_node("group_modules", group_modules)
    g.add_node("summarize_module", summarize_module, input_schema=ModuleTask)
    g.add_node("infer_requirements", infer_requirements)
    g.add_node("render_srs", render_srs)

    g.add_edge(START, "scan")
    g.add_conditional_edges("scan", fan_out_files, ["summarize_file", "group_modules"])
    g.add_edge("summarize_file", "group_modules")
    g.add_conditional_edges("group_modules", fan_out_modules, ["summarize_module", "infer_requirements"])
    g.add_edge("summarize_module", "infer_requirements")
    g.add_edge("infer_requirements", "render_srs")
    g.add_edge("render_srs", END)
    return g.compile()
