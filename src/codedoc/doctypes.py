"""The documents codedoc can write.

To add a new document type: write a schema (schemas.py), a prompt (prompts.py),
a renderer (render.py) and add one ``DocType`` entry below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel

from codedoc import prompts
from codedoc.render import (render_api_markdown, render_design_markdown, render_srs_markdown,
                            render_technical_markdown, render_user_manual_markdown)
from codedoc.schemas import APIDocumentation, DesignDocument, SRSDocument, TechnicalDocument, UserManual


@dataclass(frozen=True)
class DocType:
    id: str
    label: str
    description: str                       # shown in the menu
    filename: str
    schema: type[BaseModel]
    prompt: str
    system: str
    render: Callable[..., str]
    stats: Callable[[BaseModel], str]      # short summary for the progress log


DOC_TYPES: list[DocType] = [
    DocType("srs", "Software Requirements Specification (SRS)",
            "features, functional & non-functional requirements, business rules",
            "SRS.md", SRSDocument, prompts.WRITE_SRS, prompts.SYSTEM_BA, render_srs_markdown,
            lambda d: f"{len(d.functional_requirements)} functional + "
                      f"{len(d.non_functional_requirements)} non-functional requirements"),
    DocType("user_manual", "User Manual",
            "step-by-step guide for end users: getting started, tasks, FAQ, troubleshooting",
            "USER_MANUAL.md", UserManual, prompts.WRITE_USER_MANUAL, prompts.SYSTEM_TECH_WRITER,
            render_user_manual_markdown, lambda d: f"{len(d.sections)} sections, {len(d.faq)} FAQs"),
    DocType("api", "API Documentation",
            "endpoints, parameters, request/response models, authentication, errors",
            "API.md", APIDocumentation, prompts.WRITE_API_DOC, prompts.SYSTEM_DEVELOPER,
            render_api_markdown, lambda d: f"{len(d.endpoints)} endpoints, {len(d.data_models)} data models"),
    DocType("technical", "Technical / Developer Documentation",
            "code structure, components, setup, configuration, conventions",
            "TECHNICAL.md", TechnicalDocument, prompts.WRITE_TECHNICAL_DOC, prompts.SYSTEM_DEVELOPER,
            render_technical_markdown, lambda d: f"{len(d.components)} components"),
    DocType("design", "Software Design Document (SDD)",
            "architecture, components, data flow, data design, design decisions",
            "DESIGN.md", DesignDocument, prompts.WRITE_DESIGN_DOC, prompts.SYSTEM_ARCHITECT,
            render_design_markdown, lambda d: f"{len(d.components)} components, "
                                              f"{len(d.design_decisions)} design decisions"),
]

DOC_TYPE_IDS = [d.id for d in DOC_TYPES]
_BY_ID = {d.id: d for d in DOC_TYPES}


def get_doc_type(doc_id: str) -> DocType:
    try:
        return _BY_ID[doc_id]
    except KeyError:
        raise ValueError(f"Unknown document type '{doc_id}'. Choose from: {', '.join(DOC_TYPE_IDS)}") from None


def parse_doc_types(value: str | list[str] | tuple[str, ...]) -> list[str]:
    """'srs,api' / ['srs', 'api'] / 'all' -> validated ids in menu order, without duplicates."""
    items = value.split(",") if isinstance(value, str) else list(value)
    items = [i.strip().lower() for i in items if i.strip()]
    if "all" in items:
        return list(DOC_TYPE_IDS)
    if not items:
        raise ValueError(f"Choose at least one document type: {', '.join(DOC_TYPE_IDS)}")
    for i in items:
        get_doc_type(i)
    return [d for d in DOC_TYPE_IDS if d in items]
