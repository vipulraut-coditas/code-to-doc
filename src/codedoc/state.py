"""LangGraph state definitions.

``Annotated[list, operator.add]`` = a *reducer*: when several parallel branches
(one per file / module) return results, LangGraph appends them instead of
overwriting.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class DocState(TypedDict, total=False):
    repo_path: str
    doc_types: list[str]                                 # ids from doctypes.DOC_TYPES
    project_name: str
    stack: list[str]
    readme: str
    files: list[dict]                                    # from the scanner
    total_candidates: int
    skipped_secrets: int
    file_summaries: Annotated[list[dict], operator.add]  # map step 1 (parallel)
    modules: dict[str, list[dict]]                       # file summaries grouped by module
    module_summaries: Annotated[list[dict], operator.add]  # map step 2 (parallel)
    documents: Annotated[list[dict], operator.add]       # one per doc type (parallel)
    warnings: Annotated[list[str], operator.add]


class FileTask(TypedDict):
    """Payload sent to one ``summarize_file`` branch via ``Send``."""
    file: dict
    project_name: str
    stack: list[str]


class ModuleTask(TypedDict):
    """Payload sent to one ``summarize_module`` branch via ``Send``."""
    module: str
    summaries: list[dict]
    project_name: str
    stack: list[str]


class DocumentTask(TypedDict):
    """Payload sent to one ``write_document`` branch via ``Send``."""
    doc_type: str
    project_name: str
    stack: list[str]
    readme: str
    file_count: int
    module_summaries: list[dict]
    warnings: list[str]
