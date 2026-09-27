from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

EventKind = Literal[
    "situation", "need", "resource", "responder_update",
    "transport", "condition", "action", "decision"
]
Urgency = Literal["critical", "high", "medium", "low"]
EventStatus = Literal["open", "active", "resolved", "monitoring", "blocked", "unknown"]
SourceType = Literal["operator", "synthetic"]


class Need(BaseModel):
    category: str
    priority: Urgency = "medium"
    quantity: float | None = None
    unit: str = ""
    status: EventStatus = "open"
    notes: str = ""


class Resource(BaseModel):
    item: str
    available: float = 0
    committed: float = 0
    unit: str = ""
    location: str = ""
    status: str = "available"


class Responder(BaseModel):
    organization: str
    team: str
    role: str = ""
    status: str = "deployed"
    eta_minutes: int | None = None
    location: str = ""


class OperationalEventCreate(BaseModel):
    kind: EventKind = "situation"
    title: str
    location: str
    lat: float
    lon: float
    urgency: Urgency = "medium"
    status: EventStatus = "open"
    affected_people: int = 0
    sector: str = "multi-sector"
    details: str = ""
    needs: list[Need] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    responders: list[Responder] = Field(default_factory=list)
    transport_constraints: list[str] = Field(default_factory=list)
    operational_conditions: list[str] = Field(default_factory=list)
    attempted_actions: list[str] = Field(default_factory=list)
    outcome: str = ""
    source: str = "field-report"
    source_type: SourceType = "operator"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OperationalEvent(OperationalEventCreate):
    id: int
    created_at: datetime


class ResponsePlanInput(BaseModel):
    objective: str
    locations: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    transport_plan: str = ""
    constraints: list[str] = Field(default_factory=list)
    proposed_actions: list[str] = Field(default_factory=list)
    context: str = ""


class ResponsePlanAnalysis(BaseModel):
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    confidence: Literal["low", "medium", "high"] = "medium"
    summary: str = ""
    memory_recalled: list[str] = Field(default_factory=list)
    recurring_patterns: list[str] = Field(default_factory=list)
    resource_conflicts: list[str] = Field(default_factory=list)
    transport_constraints: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    unanswered_questions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class DashboardStats(BaseModel):
    events: int = 0
    affected_people: int = 0
    open_needs: int = 0
    resources_available: float = 0
    active_responders: int = 0
    blocked_routes: int = 0
