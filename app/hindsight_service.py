from __future__ import annotations

import hashlib
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
RETENTION_MISSION = """Create durable disaster-response memory from field reports, needs, resources,
responders, transport constraints, local conditions, attempted actions, outcomes, and decisions.
Preserve concrete facts, changes over time, and lessons that could help a future responder."""
OBSERVATION_MISSION = """Across response history, identify repeated bottlenecks, route failures,
successful tactics, resource pressure, and conditions that change what actions are feasible."""
REFLECT_MISSION = """CrisisOps is decision support for a human responder. Use recalled evidence, distinguish
known facts from uncertainty, never invent current status, and never issue autonomous dispatch orders."""


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

    async def ensure_bank(self) -> None:
        try:
            await self.client.acreate_bank(
                bank_id=BANK_ID,
                name="CrisisOps Operational Memory",
                retain_mission=RETENTION_MISSION,
                retain_extraction_mode="verbose",
                enable_observations=True,
                observations_mission=OBSERVATION_MISSION,
                reflect_mission=REFLECT_MISSION,
                enable_text_search=True,
                enable_temporal_retrieval=True,
            )
        except Exception as exc:
            raise HindsightUnavailable(f"Hindsight bank unavailable: {exc}") from exc

    async def retain(self, event: OperationalEvent) -> str:
        await self.ensure_bank()
        source_type = "synthetic" if event.source_type == "synthetic" else "operator"
        document_id = f"crisis-event-{event.id}"
        try:
            await self.client.aretain(
                bank_id=BANK_ID,
                content=event_to_memory(event),
                context="humanitarian disaster-response operational report",
                timestamp=event.occurred_at,
                document_id=document_id,
                tags=[
                    f"kind:{event.kind}",
                    f"urgency:{event.urgency}",
                    f"status:{event.status}",
                    f"sector:{event.sector.lower().replace(' ', '-')}",
                    f"source_type:{source_type}",
                ],
                metadata={
                    "location": event.location,
                    "event_id": str(event.id),
                    "source_type": source_type,
                    "source": event.source,
                },
                update_mode="replace",
            )
        except Exception as exc:
            raise HindsightUnavailable(f"Hindsight retain failed: {exc}") from exc
        return document_id

    async def retain_live_snapshot(self, snapshot: dict[str, Any]) -> int:
        await self.ensure_bank()
        retained = 0
        location = snapshot.get("location", {})
        generated_at = snapshot.get("generated_at")
        providers = [
            ("open-meteo", snapshot.get("weather")),
            ("usgs", snapshot.get("earthquakes")),
            ("imd-cap", snapshot.get("imd_alerts")),
            ("gdacs", snapshot.get("gdacs_events")),
        ]
        for provider, payload in providers:
            if payload in (None, [], {}):
                continue
            items = payload if isinstance(payload, list) else [payload]
            for idx, item in enumerate(items):
                identity = item.get("id") or item.get("guid") or item.get("event_id") or item.get("observed_at") or f"item-{idx}"
                digest = hashlib.sha256(
                    f"{provider}|{location.get('latitude')}|{location.get('longitude')}|{identity}".encode("utf-8")
                ).hexdigest()[:20]
                document_id = f"live-{provider}-{digest}"
                try:
                    await self.client.aretain(
                        bank_id=BANK_ID,
                        content=f"REAL public intelligence from {provider}. Retrieved at {generated_at}. Location {location}. Signal: {item}",
                        context="real public disaster-response intelligence; not verified field status",
                        timestamp=generated_at,
                        document_id=document_id,
                        tags=["source_type:real", f"provider:{provider}"],
                        metadata={
                            "source_type": "real",
                            "provider": provider,
                            "retrieved_at": generated_at,
                            "location": location,
                        },
                        update_mode="replace",
                    )
                    retained += 1
                except Exception as exc:
                    raise HindsightUnavailable(f"Hindsight live-intel retain failed for {provider}: {exc}") from exc
        return retained

    async def recall(self, plan: ResponsePlanInput, limit: int = 8) -> list[dict[str, Any]]:
        await self.ensure_bank()
        query = f"""Find the most relevant prior disaster-response experiences for this plan.
Prioritize exact similarities in location, hazard, route constraints, attempted actions, resources, and outcomes.
Pay special attention to flooding, North Ward, bridge closure, road-delivery failure, inaccessible routes, boats, and canal routes when those facts exist.

Current plan:
Objective: {plan.objective}
Locations: {", ".join(plan.locations)}
Resources: {", ".join(plan.resources)}
Transport plan: {plan.transport_plan}
Constraints: {", ".join(plan.constraints)}
Proposed actions: {", ".join(plan.proposed_actions)}
Context: {plan.context}"""
        try:
            response = await self.client.arecall(
                bank_id=BANK_ID,
                query=query,
                max_tokens=5000,
                budget="mid",
                include_source_facts=True,
                include_chunks=True,
            )
        except Exception as exc:
            raise HindsightUnavailable(f"Hindsight recall failed: {exc}") from exc
        results = getattr(response, "results", []) or []
        output: list[dict[str, Any]] = []
        for item in list(results)[:limit]:
            output.append({
                "id": getattr(item, "id", None),
                "text": getattr(item, "text", str(item)),
                "type": getattr(item, "type", "memory"),
                "context": getattr(item, "context", ""),
                "metadata": getattr(item, "metadata", {}) or {},
            })
        return output

    async def reflect(self, plan: ResponsePlanInput) -> ResponsePlanAnalysis:
        await self.ensure_bank()
        query = f"""Review this disaster-response plan using persistent operational memory.
Explicitly surface concrete prior evidence when available. For a North Ward flooding plan, connect any prior road-delivery failure, bridge closure, route inaccessibility, and canal/boat evidence instead of returning only generic advice.

Proposed response plan:
Objective: {plan.objective}
Locations: {", ".join(plan.locations)}
Resources: {", ".join(plan.resources)}
Transport plan: {plan.transport_plan}
Constraints: {", ".join(plan.constraints)}
Proposed actions: {", ".join(plan.proposed_actions)}
Context: {plan.context}

Never invent current facts and never issue autonomous dispatch orders. Return structured decision support with concise evidence and explicit unanswered questions."""
        try:
            response = await self.client.areflect(
                bank_id=BANK_ID,
                query=query,
                budget="mid",
                max_tokens=5000,
                response_schema=ResponsePlanAnalysis.model_json_schema(),
                include_facts=True,
            )
        except Exception as exc:
            raise HindsightUnavailable(f"Hindsight reflect failed: {exc}") from exc
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

    async def memory_lenses(self) -> dict[str, str]:
        await self.ensure_bank()
        queries = {
            "What keeps breaking": "Across the response history, what recurring operational bottlenecks or failure modes appear? Use concrete evidence.",
            "What actually worked": "Which response actions repeatedly worked, and under what conditions? Use concrete evidence.",
            "Where capacity is fragile": "Where do resource shortages, transport constraints, or responder gaps repeatedly occur? Use concrete evidence.",
            "Institutional memory": "What durable response lessons should a new incident commander know before acting? Use concrete evidence.",
        }
        result: dict[str, str] = {}
        for name, query in queries.items():
            response = await self.client.areflect(bank_id=BANK_ID, query=query, budget="low", include_facts=True)
            result[name] = getattr(response, "text", "") or "No synthesized memory available yet."
        return result


def hindsight_configured() -> bool:
    return bool(os.getenv("HINDSIGHT_BASE_URL") and os.getenv("HINDSIGHT_API_KEY"))