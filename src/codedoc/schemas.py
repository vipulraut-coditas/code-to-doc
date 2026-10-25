"""Pydantic schemas for everything the LLM returns.

Every field has a default, so a slightly incomplete answer still validates.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileSummary(BaseModel):
    purpose: str = Field("", description="1-2 sentences: what this file does, in business terms")
    key_elements: list[str] = Field(default_factory=list, description="Important classes, functions, endpoints, screens")
    business_logic: list[str] = Field(default_factory=list, description="Rules, validations, calculations, workflows")
    entities: list[str] = Field(default_factory=list, description="Business/data entities used or defined")
    integrations: list[str] = Field(default_factory=list, description="External systems, APIs, queues, databases")
    api_endpoints: list[str] = Field(default_factory=list, description="HTTP/RPC endpoints: 'METHOD /path - purpose (params)'")
    public_interfaces: list[str] = Field(default_factory=list, description="Key public classes/functions with signature")
    user_interactions: list[str] = Field(default_factory=list, description="Screens, CLI commands, forms, user flows")
    configuration: list[str] = Field(default_factory=list, description="Env vars, settings, config keys and their meaning")
    dependencies: list[str] = Field(default_factory=list, description="Libraries/frameworks/internal modules it relies on")


class ModuleSummary(BaseModel):
    purpose: str = Field("", description="What this module/feature area is for")
    capabilities: list[str] = Field(default_factory=list, description="What a user or system can do via this module")
    business_rules: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list, description="Who uses this module (roles, systems)")
    api_endpoints: list[str] = Field(default_factory=list)
    public_interfaces: list[str] = Field(default_factory=list)
    user_interactions: list[str] = Field(default_factory=list)
    configuration: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class Actor(BaseModel):
    name: str
    description: str = ""


class Feature(BaseModel):
    name: str
    description: str = ""


class Requirement(BaseModel):
    id: str = Field(description="FR-001, FR-002 ...")
    feature: str = Field("", description="Name of the feature it belongs to")
    statement: str = Field(description="'The system shall ...'")
    priority: str = Field("Should", description="Must / Should / Could")
    confidence: str = Field("Medium", description="High / Medium / Low")
    sources: list[str] = Field(default_factory=list, description="Modules or file paths that support it")


class NonFunctionalRequirement(BaseModel):
    id: str = Field(description="NFR-001 ...")
    category: str = Field("", description="Security, Performance, Reliability, Usability, ...")
    statement: str
    confidence: str = "Medium"
    sources: list[str] = Field(default_factory=list)


class DataEntity(BaseModel):
    name: str
    description: str = ""
    key_attributes: list[str] = Field(default_factory=list)


class ExternalInterface(BaseModel):
    name: str
    type: str = Field("", description="REST API, Database, Message queue, Email, Payment gateway, ...")
    description: str = ""


class GlossaryTerm(BaseModel):
    term: str
    definition: str = ""


class SRSDocument(BaseModel):
    project_name: str = ""
    purpose: str = ""
    scope: str = ""
    product_overview: str = ""
    actors: list[Actor] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    functional_requirements: list[Requirement] = Field(default_factory=list)
    non_functional_requirements: list[NonFunctionalRequirement] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    data_entities: list[DataEntity] = Field(default_factory=list)
    external_interfaces: list[ExternalInterface] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    glossary: list[GlossaryTerm] = Field(default_factory=list)


# ---------------------------------------------------------------- User Manual
class ManualSection(BaseModel):
    title: str
    overview: str = ""
    steps: list[str] = Field(default_factory=list, description="Numbered how-to steps from the user's point of view")
    tips: list[str] = Field(default_factory=list)


class FAQ(BaseModel):
    question: str
    answer: str = ""


class TroubleshootingItem(BaseModel):
    problem: str
    solution: str = ""


class UserManual(BaseModel):
    project_name: str = ""
    introduction: str = ""
    audience: str = ""
    getting_started: list[str] = Field(default_factory=list, description="First steps: access, sign-in, install, ...")
    roles: list[Actor] = Field(default_factory=list, description="User roles and what each one may do")
    sections: list[ManualSection] = Field(default_factory=list, description="One section per task/feature")
    faq: list[FAQ] = Field(default_factory=list)
    troubleshooting: list[TroubleshootingItem] = Field(default_factory=list)
    glossary: list[GlossaryTerm] = Field(default_factory=list)


# ---------------------------------------------------------------- API Documentation
class APIParameter(BaseModel):
    name: str
    location: str = Field("", description="path / query / header / body / cookie")
    type: str = ""
    required: bool = False
    description: str = ""


class APIResponse(BaseModel):
    status: str = Field("", description="200, 201, 404, ...")
    description: str = ""


class Endpoint(BaseModel):
    method: str = Field("", description="GET / POST / ... (or RPC, WS, CLI for non-HTTP)")
    path: str
    group: str = Field("", description="Resource or module the endpoint belongs to")
    summary: str = ""
    auth_required: str = Field("", description="Yes / No / Unknown")
    parameters: list[APIParameter] = Field(default_factory=list)
    request_body: str = Field("", description="Short description or example JSON of the body")
    responses: list[APIResponse] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class DataModel(BaseModel):
    name: str
    description: str = ""
    fields: list[str] = Field(default_factory=list, description="'name: type - meaning'")


class APIDocumentation(BaseModel):
    project_name: str = ""
    overview: str = ""
    base_url: str = ""
    authentication: str = ""
    endpoints: list[Endpoint] = Field(default_factory=list)
    public_interfaces: list[str] = Field(default_factory=list,
                                         description="Library/SDK functions when there is no HTTP API")
    data_models: list[DataModel] = Field(default_factory=list)
    error_handling: str = ""
    notes: list[str] = Field(default_factory=list, description="Rate limits, versioning, pagination, ...")


# ---------------------------------------------------------------- Technical / Developer Documentation
class NamedItem(BaseModel):
    name: str
    description: str = ""


class Component(BaseModel):
    name: str
    responsibility: str = ""
    key_elements: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class TechnicalDocument(BaseModel):
    project_name: str = ""
    overview: str = ""
    tech_stack: list[NamedItem] = Field(default_factory=list, description="Technology and what it is used for")
    project_structure: list[NamedItem] = Field(default_factory=list, description="Folder/module and its purpose")
    prerequisites: list[str] = Field(default_factory=list)
    setup_steps: list[str] = Field(default_factory=list)
    run_steps: list[str] = Field(default_factory=list)
    test_steps: list[str] = Field(default_factory=list)
    configuration: list[NamedItem] = Field(default_factory=list, description="Env var / setting and its meaning")
    components: list[Component] = Field(default_factory=list)
    conventions: list[str] = Field(default_factory=list, description="Coding conventions and patterns observed")
    extension_points: list[str] = Field(default_factory=list, description="How to add a feature/module/provider")
    known_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- Software Design Document
class DesignDecision(BaseModel):
    decision: str
    rationale: str = ""


class DesignDocument(BaseModel):
    project_name: str = ""
    introduction: str = ""
    architecture_overview: str = ""
    architectural_style: str = Field("", description="Layered, MVC, microservices, pipeline, ...")
    architecture_diagram: str = Field("", description="Mermaid 'flowchart' source, no code fences")
    components: list[Component] = Field(default_factory=list)
    data_flow: list[str] = Field(default_factory=list, description="Key runtime flows, step by step")
    data_design: list[DataEntity] = Field(default_factory=list)
    interfaces: list[ExternalInterface] = Field(default_factory=list)
    design_decisions: list[DesignDecision] = Field(default_factory=list)
    cross_cutting: list[NamedItem] = Field(default_factory=list,
                                           description="Security, error handling, logging, caching, concurrency ...")
    constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
