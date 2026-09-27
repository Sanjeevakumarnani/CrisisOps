from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from .models import OperationalEvent, ResponsePlanAnalysis, ResponsePlanInput
from .utils import event_to_memory

load_dotenv()


class HindsightUnavailable(RuntimeError):
    pass


BANK_ID = "crisisops-disaster-response-memory"
RETENTION_MISSION = """Create durable disaster-response memory from field reports, urgent needs,
available and committed resources, responder positions, transport constraints, local operational
conditions, attempted actions, outcomes, and decisions. Preserve what changed over time and what
future responders should know. Prefer concrete operational facts and lessons over transient chatter."""
OBSERVATION_MISSION = """Track stable operational patterns across locations, resources, routes,
responders, needs, and interventions. Highlight repeated bottlenecks, successful tactics, and
conditions that change what actions are feasible."""
SAFETY_DIRECTIVE = """CrisisOps is decision support, not an autonomous dispatch system.
Never invent live status, never claim a person is safe without evidence, and never execute
real-world actions. Surface uncertainty and ask for human confirmation for high-impact choices."""


@lru_cache(maxsize=1)
def get_client():
    base_url = os.getenv("HINDSIGHT_BASE_URL", "").strip()
    api_key = os.getenv("HINDSIGHT_API_KEY", "").strip()
    if not base_url:
        raise HindsightUnavailable("HINDSIGHT_BASE_URL is not configured")
    try:
        from hindsight_client import Hindsight
    except ImportError as exc:
        raise HindsightUnavailable("hindsight-client is not installed") from exc
    kwargs: dict[str, Any] = {"base_url": base_url}
    if api_key:
        kwargs["api_key"] = api_key
    return Hindsight(**kwargs)


class CrisisMemory:
    def __init__(self) -> None:
        self.client = get_client()

    def ensure_bank(self) -> None:
        try:
            self.client.create_bank(bank_id=BANK_ID, name="CrisisOps Operational Memory")
        except Exception:
            pass
        try:
            self.client.update_bank_config(
                BANK_ID,
                retain_mission=RETENTION_MISSION,
                retain_extraction_mode="verbose",
                observations_mission=OBSERVATION_MISSION,
                disposition_skepticism=6,
                disposition_literalism=5,
                disposition_empathy=3,
            )
        except Exception:
            pass
        try:
            self.client.create_directive(
                bank_id=BANK_ID, name="Response Safety", content=SAFETY_DIRECTIVE
            )
        except Exception:
            pass

    def retain(self, event: OperationalEvent) -> None:
        self.ensure_bank()
        tags = [
            f"kind:{event.kind}",
            f"urgency:{event.urgency}",
            f"status:{event.status}",
            f"sector:{event.sector.lower().replace(' ', '-')}",
        ]
        self.client.retain(
            bank_id=BANK_ID,
            content=event_to_memory(event),
            context="humanitarian disaster-response operational report",
            timestamp=event.occurred_at,
            document_id=f"crisis-event-{event.id}",
            tags=tags,
            metadata={"location": event.location, "event_id": str(event.id)},
        )

    def recall(self, plan: ResponsePlanInput, limit: int = 8) -> list[dict[str, Any]]:
        self.ensure_bank()
        query = f"""Find operational memories relevant to this proposed disaster-response plan.
Objective: {plan.objective}
Locations: {", ".join(plan.locations)}
Resources: {", ".join(plan.resources)}
Transport plan: {plan.transport_plan}
Constraints: {", ".join(plan.constraints)}
Proposed actions: {", ".join(plan.proposed_actions)}
Context: {plan.context}"""
        response = self.client.recall(
            bank_id=BANK_ID,
            query=query,
            max_tokens=5000,
            tags_match="any",
            prefer_observations=True,
        )
        results = getattr(response, "results", []) or []
        output = []
        for item in list(results)[:limit]:
            output.append(
                {
                    "id": getattr(item, "id", None),
                    "text": getattr(item, "text", str(item)),
                    "type": getattr(item, "type", "memory"),
                    "context": getattr(item, "context", ""),
                    "metadata": getattr(item, "metadata", {}) or {},
                }
            )
        return output

    def reflect(self, plan: ResponsePlanInput) -> ResponsePlanAnalysis:
        self.ensure_bank()
        query = f"""You are a humanitarian operations memory analyst.

Proposed response plan:
Objective: {plan.objective}
Locations: {", ".join(plan.locations)}
Resources: {", ".join(plan.resources)}
Transport plan: {plan.transport_plan}
Constraints: {", ".join(plan.constraints)}
Proposed actions: {", ".join(plan.proposed_actions)}
Context: {plan.context}

Use persistent operational memory to identify prior similar situations, recurring needs,
resource bottlenecks, transport failures, responder coordination patterns, successful actions,
and exceptions. Do not invent current facts and do not issue autonomous dispatch orders.
Return structured decision support with concise evidence and explicit unanswered questions."""
        response = self.client.reflect(
            bank_id=BANK_ID,
            query=query,
            budget="mid",
            max_tokens=5000,
            response_schema=ResponsePlanAnalysis.model_json_schema(),
            include_facts=True,
        )
        structured = getattr(response, "structured_output", None) or {}
        try:
            return ResponsePlanAnalysis.model_validate(structured)
        except ValidationError:
            text = getattr(response, "text", "") or ""
            return ResponsePlanAnalysis(
                risk_level="medium",
                confidence="low",
                summary=text[:1500] or "Hindsight returned no structured analysis.",
                evidence=[text] if text else [],
            )

    def memory_lenses(self) -> dict[str, str]:
        self.ensure_bank()
        queries = {
            "What keeps breaking": "Across the response history, what recurring operational bottlenecks or failure modes appear?",
            "What actually worked": "Which response actions repeatedly worked, and under what local conditions?",
            "Where capacity is fragile": "Where do resource shortages, transport constraints, or responder gaps repeatedly occur?",
            "Institutional memory": "What durable response lessons should a new incident commander know before acting?",
        }
        result: dict[str, str] = {}
        for name, query in queries.items():
            try:
                answer = self.client.reflect(bank_id=BANK_ID, query=query, budget="low", include_facts=True)
                result[name] = getattr(answer, "text", "") or "No synthesized memory available yet."
            except Exception as exc:
                result[name] = f"Unavailable: {exc}"
        return result


def hindsight_ready() -> bool:
    try:
        CrisisMemory()
        return True
    except Exception:
        return False
