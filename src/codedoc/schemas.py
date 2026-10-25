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


class ModuleSummary(BaseModel):
    purpose: str = Field("", description="What this module/feature area is for")
    capabilities: list[str] = Field(default_factory=list, description="What a user or system can do via this module")
    business_rules: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list, description="Who uses this module (roles, systems)")


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
