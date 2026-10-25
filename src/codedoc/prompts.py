"""All prompts in one place. Each one starts with a TASK tag (handy for tests and debugging)."""

SYSTEM_BA = """You are a senior Business Analyst who can read source code.
You reverse-engineer what a software system does for its users and the business,
and you describe it in clear, non-technical language suitable for an SRS
(Software Requirements Specification). Describe behaviour, not implementation.
Never invent features that the code does not support; when you infer something,
say so through a lower confidence or an assumption. Always answer with valid JSON only."""

FILE_SUMMARY = """TASK: summarize_file
Project: {project_name}
Tech stack: {stack}
File: {path} ({language}){truncated_note}

Read the file and summarise what it contributes to the product from a business point of view.

<file_content>
{content}
</file_content>"""

MODULE_SUMMARY = """TASK: summarize_module
Project: {project_name}
Tech stack: {stack}
Module: {module}

Below are summaries of the files in this module. Combine them into one summary of the
module as a feature area: what users/systems can do with it, its business rules,
entities, integrations and actors.

<file_summaries>
{summaries}
</file_summaries>"""

REQUIREMENTS = """TASK: infer_requirements
Project: {project_name}
Tech stack: {stack}
Files analysed: {file_count}

<readme>
{readme}
</readme>

<module_summaries>
{modules}
</module_summaries>

Act as the Business Analyst writing the SRS for this system. Using ONLY the evidence above:
- Explain purpose, scope and a short product overview in plain business language.
- Identify actors (user roles and external systems).
- Group behaviour into features, then write atomic functional requirements
  ("The system shall ...") with ids FR-001, FR-002, ... Each one gets a feature name,
  priority (Must/Should/Could), confidence (High = directly visible in code,
  Medium = strongly implied, Low = guess) and sources (module names or file paths).
- Add non-functional requirements (security, performance, reliability, usability,
  auditability, ...) that the code shows evidence of, ids NFR-001, ...
- List business rules, data entities (with key attributes), external interfaces.
- Put everything you had to guess into assumptions, and write open questions a BA
  would ask stakeholders to confirm the gaps.
- Add a small glossary of domain terms."""

SCHEMA_SUFFIX = """

Return ONLY a JSON object (no markdown, no commentary) that follows this JSON schema:
{schema}"""

FIX_JSON = """Your previous reply could not be parsed: {error}
Return ONLY the corrected JSON object that follows the schema. No markdown, no commentary."""
