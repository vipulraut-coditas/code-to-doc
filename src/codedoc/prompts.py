"""All prompts in one place. Each one starts with a TASK tag (handy for tests and debugging)."""

_GROUNDING = """Never invent features that the code does not support; when you infer something,
say so through a lower confidence or an assumption. Always answer with valid JSON only."""

SYSTEM_ANALYST = """You are a senior software analyst who reads source code.
You capture both what a system does for its users and the business (behaviour, rules,
entities) and how it is built (endpoints, public interfaces, configuration, dependencies),
so that requirement, user, API, developer and design documents can later be written
from your notes. """ + _GROUNDING

SYSTEM_BA = """You are a senior Business Analyst who can read source code.
You reverse-engineer what a software system does for its users and the business,
and you describe it in clear, non-technical language suitable for an SRS
(Software Requirements Specification). Describe behaviour, not implementation.
""" + _GROUNDING

SYSTEM_TECH_WRITER = """You are an experienced technical writer who writes user manuals.
You explain, step by step and in plain language, how end users accomplish their tasks
with the product. Avoid code, class names and implementation detail.
""" + _GROUNDING

SYSTEM_DEVELOPER = """You are a senior software engineer writing documentation for other developers.
You are precise about endpoints, parameters, types, configuration, setup and code structure,
and you cite the files your statements come from.
""" + _GROUNDING

SYSTEM_ARCHITECT = """You are a software architect writing a Software Design Document (SDD).
You describe the architecture, components, their responsibilities and interactions, data design
and the key design decisions with their rationale.
""" + _GROUNDING

FILE_SUMMARY = """TASK: summarize_file
Project: {project_name}
Tech stack: {stack}
File: {path} ({language}){truncated_note}

Read the file and summarise what it contributes to the product: its business purpose and
rules, plus the technical facts (endpoints, public interfaces, user interactions,
configuration, dependencies). Leave a list empty when the file has nothing for it.

<file_content>
{content}
</file_content>"""

MODULE_SUMMARY = """TASK: summarize_module
Project: {project_name}
Tech stack: {stack}
Module: {module}

Below are summaries of the files in this module. Combine them into one summary of the
module as a feature area: what users/systems can do with it, its business rules,
entities, integrations and actors, and its endpoints, public interfaces, user
interactions, configuration and dependencies (keep the concrete details).

<file_summaries>
{summaries}
</file_summaries>"""

_CONTEXT = """Project: {project_name}
Tech stack: {stack}
Files analysed: {file_count}

<readme>
{readme}
</readme>

<module_summaries>
{modules}
</module_summaries>
"""

WRITE_SRS = "TASK: write_srs\n" + _CONTEXT + """
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

WRITE_USER_MANUAL = "TASK: write_user_manual\n" + _CONTEXT + """
Write the User Manual for the end users of this system. Using ONLY the evidence above:
- Introduce the product and say who the manual is for.
- Explain how to get started (access, sign-in, installation or first launch).
- List the user roles and what each one may do.
- Write one section per user task or feature, with an overview and numbered steps
  that describe what the user does and sees (screens, commands, buttons, forms), plus tips.
- Add an FAQ, a troubleshooting list (common errors and how to fix them) and a glossary.
Describe behaviour from the user's point of view, not code."""

WRITE_API_DOC = "TASK: write_api_doc\n" + _CONTEXT + """
Write the API Documentation for developers who integrate with this system. Using ONLY the evidence above:
- Give an overview, the base URL (if known) and how authentication works.
- Document every endpoint you can find: method, path, group, summary, whether auth is
  required, parameters (name, location, type, required, description), request body,
  responses (status + meaning) and source files.
- If the system exposes no HTTP/RPC API, leave endpoints empty and document its public
  programmatic interface (library functions, CLI commands) in public_interfaces.
- Describe the main data models (request/response objects) with their fields.
- Explain error handling and notes such as pagination, versioning or rate limits."""

WRITE_TECHNICAL_DOC = "TASK: write_technical_doc\n" + _CONTEXT + """
Write the Technical / Developer Documentation for engineers who will maintain this code. Using ONLY the evidence above:
- Give a technical overview and the tech stack (each technology and what it is used for).
- Describe the project structure (folders/modules and their purpose).
- List prerequisites and the steps to set up, run and test the project.
- Document configuration (environment variables, settings) and their meaning.
- Describe the main components: responsibility, key classes/functions, source files.
- Note the coding conventions and patterns used, the extension points (how to add a new
  feature/module), and known issues or technical debt visible in the code."""

WRITE_DESIGN_DOC = "TASK: write_design_doc\n" + _CONTEXT + """
Write the Software Design Document for this system. Using ONLY the evidence above:
- Introduce the system and give an architecture overview and the architectural style.
- Provide a Mermaid flowchart (source only, no code fences) of the main components and
  how they connect.
- Describe each component's responsibility, key elements and source files.
- Describe the key runtime data flows step by step.
- Describe the data design (entities with key attributes) and the external interfaces.
- List the design decisions you can see with their likely rationale.
- Cover cross-cutting concerns (security, error handling, logging, caching, concurrency),
  constraints and risks."""

SCHEMA_SUFFIX = """

Return ONLY a JSON object (no markdown, no commentary) that follows this JSON schema:
{schema}"""

FIX_JSON = """Your previous reply could not be parsed: {error}
Return ONLY the corrected JSON object that follows the schema. No markdown, no commentary."""
