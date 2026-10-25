"""Turn the structured SRS into Markdown (no LLM: deterministic and free)."""

from __future__ import annotations

from collections import OrderedDict

from codedoc.schemas import SRSDocument
from codedoc.text import md_cell


def _bullets(items: list[str], empty: str = "_None identified._") -> str:
    items = [i for i in items if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else empty


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "_None identified._"
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(md_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def render_srs_markdown(srs: SRSDocument, *, stack: list[str], module_summaries: list[dict],
                        files_analysed: int, warnings: list[str], model_info: str,
                        generated_on: str) -> str:
    name = srs.project_name or "Project"
    out: list[str] = [
        f"# Software Requirements Specification (SRS)\n## {name}",
        f"> Reverse-engineered from source code by **codedoc** on {generated_on}. "
        f"Files analysed: {files_analysed}. {model_info}\n>\n"
        "> This is a *draft* produced by an AI acting as a Business Analyst. Items marked "
        "**Low** confidence and everything under *Assumptions* / *Open Questions* must be "
        "validated with stakeholders.",
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
        "## Appendix A. Module Overview\n" + _table(
            ["Module", "Purpose", "Files"],
            [[m["module"], m.get("purpose", ""), len(m.get("files", []))]
             for m in sorted(module_summaries, key=lambda m: m["module"])]),
    ]
    if warnings:
        out.append("## Appendix B. Analysis Notes\n" + _bullets(warnings))
    return "\n\n".join(out) + "\n"
