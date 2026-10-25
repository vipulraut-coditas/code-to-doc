"""Turn the structured documents into Markdown (no LLM: deterministic and free).

Every renderer has the same keyword signature, so ``doctypes.py`` can call them uniformly.
"""

from __future__ import annotations

from collections import OrderedDict

from codedoc.schemas import APIDocumentation, DesignDocument, SRSDocument, TechnicalDocument, UserManual
from codedoc.text import md_cell


def _bullets(items: list[str], empty: str = "_None identified._") -> str:
    items = [i for i in items if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else empty


def _numbered(items: list[str], empty: str = "_None identified._") -> str:
    items = [i for i in items if str(i).strip()]
    return "\n".join(f"{n}. {i}" for n, i in enumerate(items, 1)) if items else empty


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "_None identified._"
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(md_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _header(title: str, name: str, *, files_analysed: int, model_info: str, generated_on: str,
            note: str) -> str:
    return (f"# {title}\n## {name}\n\n"
            f"> Reverse-engineered from source code by **codedoc** on {generated_on}. "
            f"Files analysed: {files_analysed}. {model_info}\n>\n> {note}")


def _toc(sections: list[str]) -> str:
    return "## Table of Contents\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(sections, 1))


def _footer(out: list[str], warnings: list[str], label: str) -> str:
    if warnings:
        out.append(f"## {label}. Analysis Notes\n" + _bullets(warnings))
    return "\n\n".join(out) + "\n"


def _module_table(module_summaries: list[dict]) -> str:
    return _table(["Module", "Purpose", "Files"],
                  [[m["module"], m.get("purpose", ""), len(m.get("files", []))]
                   for m in sorted(module_summaries, key=lambda m: m["module"])])


_DRAFT = ("This is a *draft* produced by an AI. Verify it against the running system "
          "before publishing it.")


# ---------------------------------------------------------------- SRS
def render_srs_markdown(srs: SRSDocument, *, stack: list[str], module_summaries: list[dict],
                        files_analysed: int, warnings: list[str], model_info: str,
                        generated_on: str) -> str:
    name = srs.project_name or "Project"
    out: list[str] = [
        _header("Software Requirements Specification (SRS)", name, files_analysed=files_analysed,
                model_info=model_info, generated_on=generated_on,
                note="This is a *draft* produced by an AI acting as a Business Analyst. Items marked "
                     "**Low** confidence and everything under *Assumptions* / *Open Questions* must be "
                     "validated with stakeholders."),
        "## Table of Contents\n1. Introduction\n2. Overall Description\n"
        "3. Features and Functional Requirements\n4. Non-Functional Requirements\n"
        "5. Business Rules\n6. Data Requirements\n7. External Interfaces\n"
        "8. Assumptions\n9. Open Questions for Stakeholders\n10. Glossary\n"
        "Appendix A. Module Overview",
        "## 1. Introduction",
        f"### 1.1 Purpose\n{srs.purpose or '_Not determined._'}",
        f"### 1.2 Scope\n{srs.scope or '_Not determined._'}",
        "### 1.3 Confidence Legend\n"
        "- **High** - behaviour is directly visible in the code.\n"
        "- **Medium** - strongly implied by the code structure or naming.\n"
        "- **Low** - an educated guess; please confirm.",
        "## 2. Overall Description",
        f"### 2.1 Product Overview\n{srs.product_overview or '_Not determined._'}",
        "### 2.2 User Classes and Actors\n"
        + _table(["Actor", "Description"], [[a.name, a.description] for a in srs.actors]),
        "### 2.3 Technology Stack (observed)\n" + _bullets(stack, "_Not detected._"),
        "## 3. Features and Functional Requirements",
    ]

    # group FRs under their features, keeping the feature order from the model
    groups: "OrderedDict[str, list]" = OrderedDict((f.name, []) for f in srs.features)
    descriptions = {f.name: f.description for f in srs.features}
    for req in srs.functional_requirements:
        groups.setdefault(req.feature or "General", []).append(req)
    if not groups:
        out.append("_No functional requirements identified._")
    for i, (feature, reqs) in enumerate(groups.items(), start=1):
        block = f"### 3.{i} {feature}"
        if descriptions.get(feature):
            block += f"\n{descriptions[feature]}"
        block += "\n\n" + _table(["ID", "Requirement", "Priority", "Confidence", "Source"],
                                 [[r.id, r.statement, r.priority, r.confidence, r.sources] for r in reqs])
        out.append(block)

    out += [
        "## 4. Non-Functional Requirements\n" + _table(
            ["ID", "Category", "Requirement", "Confidence", "Source"],
            [[n.id, n.category, n.statement, n.confidence, n.sources] for n in srs.non_functional_requirements]),
        "## 5. Business Rules\n" + _bullets([f"**BR-{i:03d}:** {r}" for i, r in enumerate(srs.business_rules, 1)]),
        "## 6. Data Requirements\n" + _table(
            ["Entity", "Description", "Key Attributes"],
            [[e.name, e.description, e.key_attributes] for e in srs.data_entities]),
        "## 7. External Interfaces\n" + _table(
            ["Interface", "Type", "Description"],
            [[x.name, x.type, x.description] for x in srs.external_interfaces]),
        "## 8. Assumptions\n" + _bullets(srs.assumptions),
        "## 9. Open Questions for Stakeholders\n" + _bullets(srs.open_questions),
        "## 10. Glossary\n" + _table(["Term", "Definition"], [[g.term, g.definition] for g in srs.glossary]),
        "## Appendix A. Module Overview\n" + _module_table(module_summaries),
    ]
    return _footer(out, warnings, "Appendix B")


# ---------------------------------------------------------------- User Manual
def render_user_manual_markdown(doc: UserManual, *, stack: list[str], module_summaries: list[dict],
                                files_analysed: int, warnings: list[str], model_info: str,
                                generated_on: str) -> str:
    out: list[str] = [
        _header("User Manual", doc.project_name or "Project", files_analysed=files_analysed,
                model_info=model_info, generated_on=generated_on, note=_DRAFT),
        _toc(["Introduction", "Getting Started", "User Roles", "Using the System",
              "Frequently Asked Questions", "Troubleshooting", "Glossary"]),
        f"## 1. Introduction\n{doc.introduction or '_Not determined._'}"
        + (f"\n\n**Who this manual is for:** {doc.audience}" if doc.audience else ""),
        "## 2. Getting Started\n" + _numbered(doc.getting_started, "_No setup steps identified._"),
        "## 3. User Roles\n" + _table(["Role", "What they can do"], [[r.name, r.description] for r in doc.roles]),
        "## 4. Using the System",
    ]
    if not doc.sections:
        out.append("_No user tasks identified._")
    for i, s in enumerate(doc.sections, 1):
        block = f"### 4.{i} {s.title}"
        if s.overview:
            block += f"\n{s.overview}"
        if s.steps:
            block += "\n\n" + _numbered(s.steps)
        if s.tips:
            block += "\n\n" + "\n".join(f"> **Tip:** {t}" for t in s.tips)
        out.append(block)
    faq = "\n\n".join(f"**Q: {f.question}**\n\n{f.answer}" for f in doc.faq) or "_None identified._"
    out += [
        "## 5. Frequently Asked Questions\n" + faq,
        "## 6. Troubleshooting\n" + _table(["Problem", "Solution"],
                                           [[t.problem, t.solution] for t in doc.troubleshooting]),
        "## 7. Glossary\n" + _table(["Term", "Definition"], [[g.term, g.definition] for g in doc.glossary]),
    ]
    return _footer(out, warnings, "Appendix A")


# ---------------------------------------------------------------- API Documentation
def render_api_markdown(doc: APIDocumentation, *, stack: list[str], module_summaries: list[dict],
                        files_analysed: int, warnings: list[str], model_info: str,
                        generated_on: str) -> str:
    out: list[str] = [
        _header("API Documentation", doc.project_name or "Project", files_analysed=files_analysed,
                model_info=model_info, generated_on=generated_on, note=_DRAFT),
        _toc(["Overview", "Authentication", "Endpoints", "Data Models", "Error Handling", "Notes"]),
        f"## 1. Overview\n{doc.overview or '_Not determined._'}"
        + (f"\n\n**Base URL:** `{doc.base_url}`" if doc.base_url else ""),
        f"## 2. Authentication\n{doc.authentication or '_Not determined._'}",
        "## 3. Endpoints",
    ]
    if not doc.endpoints:
        out.append("_No HTTP API detected._" + (
            "\n\n### Public Interface\n" + _bullets(doc.public_interfaces) if doc.public_interfaces else ""))
    else:
        out.append(_table(["Method", "Path", "Summary"], [[e.method, e.path, e.summary] for e in doc.endpoints]))
        groups: "OrderedDict[str, list]" = OrderedDict()
        for e in doc.endpoints:
            groups.setdefault(e.group or "General", []).append(e)
        for i, (group, endpoints) in enumerate(groups.items(), 1):
            out.append(f"### 3.{i} {group}")
            for e in endpoints:
                block = "#### `" + " ".join(p for p in (e.method, e.path) if p) + "`"
                if e.summary:
                    block += f"\n{e.summary}"
                if e.auth_required:
                    block += f"\n\n**Authentication required:** {e.auth_required}"
                if e.parameters:
                    block += "\n\n**Parameters**\n\n" + _table(
                        ["Name", "In", "Type", "Required", "Description"],
                        [[p.name, p.location, p.type, "Yes" if p.required else "No", p.description]
                         for p in e.parameters])
                if e.request_body:
                    body = e.request_body.strip()
                    block += ("\n\n**Request body**\n\n```json\n" + body + "\n```"
                              if body.startswith(("{", "[")) else f"\n\n**Request body:** {body}")
                if e.responses:
                    block += "\n\n**Responses**\n\n" + _table(["Status", "Description"],
                                                             [[r.status, r.description] for r in e.responses])
                if e.sources:
                    block += "\n\n_Source: " + ", ".join(f"`{s}`" for s in e.sources) + "_"
                out.append(block)
        if doc.public_interfaces:
            out.append("### Public Interface\n" + _bullets(doc.public_interfaces))
    out += [
        "## 4. Data Models\n" + _table(["Model", "Description", "Fields"],
                                       [[m.name, m.description, m.fields] for m in doc.data_models]),
        f"## 5. Error Handling\n{doc.error_handling or '_Not determined._'}",
        "## 6. Notes\n" + _bullets(doc.notes),
    ]
    return _footer(out, warnings, "Appendix A")


# ---------------------------------------------------------------- Technical Documentation
def render_technical_markdown(doc: TechnicalDocument, *, stack: list[str], module_summaries: list[dict],
                              files_analysed: int, warnings: list[str], model_info: str,
                              generated_on: str) -> str:
    tech = _table(["Technology", "Used for"], [[t.name, t.description] for t in doc.tech_stack]) \
        if doc.tech_stack else _bullets(stack, "_Not detected._")
    out: list[str] = [
        _header("Technical Documentation", doc.project_name or "Project", files_analysed=files_analysed,
                model_info=model_info, generated_on=generated_on, note=_DRAFT),
        _toc(["Overview", "Technology Stack", "Project Structure", "Getting Started", "Configuration",
              "Components", "Conventions", "Extending the System", "Known Issues", "Module Overview"]),
        f"## 1. Overview\n{doc.overview or '_Not determined._'}",
        "## 2. Technology Stack\n" + tech,
        "## 3. Project Structure\n" + _table(["Path / Module", "Purpose"],
                                             [[p.name, p.description] for p in doc.project_structure]),
        "## 4. Getting Started",
        "### 4.1 Prerequisites\n" + _bullets(doc.prerequisites),
        "### 4.2 Setup\n" + _numbered(doc.setup_steps),
        "### 4.3 Running\n" + _numbered(doc.run_steps),
        "### 4.4 Testing\n" + _numbered(doc.test_steps),
        "## 5. Configuration\n" + _table(["Setting", "Meaning"], [[c.name, c.description] for c in doc.configuration]),
        "## 6. Components",
    ]
    if not doc.components:
        out.append("_None identified._")
    for i, c in enumerate(doc.components, 1):
        block = f"### 6.{i} {c.name}\n{c.responsibility}"
        if c.key_elements:
            block += "\n\n**Key elements**\n" + _bullets(c.key_elements)
        if c.sources:
            block += "\n\n_Source: " + ", ".join(f"`{s}`" for s in c.sources) + "_"
        out.append(block)
    out += [
        "## 7. Conventions\n" + _bullets(doc.conventions),
        "## 8. Extending the System\n" + _bullets(doc.extension_points),
        "## 9. Known Issues\n" + _bullets(doc.known_issues),
        "## 10. Module Overview\n" + _module_table(module_summaries),
    ]
    return _footer(out, warnings, "Appendix A")


# ---------------------------------------------------------------- Software Design Document
def render_design_markdown(doc: DesignDocument, *, stack: list[str], module_summaries: list[dict],
                           files_analysed: int, warnings: list[str], model_info: str,
                           generated_on: str) -> str:
    diagram = doc.architecture_diagram.strip()
    if diagram.startswith("```"):  # the model added fences anyway
        diagram = diagram.strip("`").removeprefix("mermaid").strip()
    out: list[str] = [
        _header("Software Design Document (SDD)", doc.project_name or "Project", files_analysed=files_analysed,
                model_info=model_info, generated_on=generated_on, note=_DRAFT),
        _toc(["Introduction", "Architecture", "Components", "Data Flow", "Data Design", "Interface Design",
              "Design Decisions", "Cross-Cutting Concerns", "Constraints and Risks"]),
        f"## 1. Introduction\n{doc.introduction or '_Not determined._'}",
        f"## 2. Architecture\n{doc.architecture_overview or '_Not determined._'}"
        + (f"\n\n**Architectural style:** {doc.architectural_style}" if doc.architectural_style else "")
        + (f"\n\n```mermaid\n{diagram}\n```" if diagram else "")
        + "\n\n**Technology stack (observed):** " + (", ".join(stack) or "not detected"),
        "## 3. Components",
    ]
    if not doc.components:
        out.append("_None identified._")
    for i, c in enumerate(doc.components, 1):
        block = f"### 3.{i} {c.name}\n{c.responsibility}"
        if c.key_elements:
            block += "\n\n" + _bullets(c.key_elements)
        if c.sources:
            block += "\n\n_Source: " + ", ".join(f"`{s}`" for s in c.sources) + "_"
        out.append(block)
    out += [
        "## 4. Data Flow\n" + _numbered(doc.data_flow),
        "## 5. Data Design\n" + _table(["Entity", "Description", "Key Attributes"],
                                       [[e.name, e.description, e.key_attributes] for e in doc.data_design]),
        "## 6. Interface Design\n" + _table(["Interface", "Type", "Description"],
                                            [[x.name, x.type, x.description] for x in doc.interfaces]),
        "## 7. Design Decisions\n" + _table(["Decision", "Rationale"],
                                            [[d.decision, d.rationale] for d in doc.design_decisions]),
        "## 8. Cross-Cutting Concerns\n" + _table(["Concern", "Approach"],
                                                  [[c.name, c.description] for c in doc.cross_cutting]),
        "## 9. Constraints and Risks\n### 9.1 Constraints\n" + _bullets(doc.constraints)
        + "\n\n### 9.2 Risks\n" + _bullets(doc.risks),
    ]
    return _footer(out, warnings, "Appendix A")
