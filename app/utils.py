from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from .models import OperationalEvent, OperationalEventCreate, Need, Resource, Responder


def pipe_list(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split("|") if x.strip()]


def json_list(value: str | None, fallback: list[Any] | None = None) -> list[Any]:
    if not value:
        return fallback or []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else fallback or []
    except json.JSONDecodeError:
        return fallback or []


def event_to_memory(event: OperationalEvent) -> str:
    needs = "; ".join(
        f"{n.category} {n.quantity or ''}{n.unit} [{n.priority}/{n.status}] {n.notes}".strip()
        for n in event.needs
    ) or "none"
    resources = "; ".join(
        f"{r.item}: available {r.available}, committed {r.committed} {r.unit} at {r.location} ({r.status})"
        for r in event.resources
    ) or "none"
    responders = "; ".join(
        f"{r.organization} / {r.team}: {r.status}, ETA {r.eta_minutes or 'unknown'} min, {r.location}"
        for r in event.responders
    ) or "none"
    return f"""Disaster response operational memory event #{event.id}
Kind: {event.kind}
Title: {event.title}
Location: {event.location}
Coordinates: {event.lat}, {event.lon}
Urgency: {event.urgency}
Status: {event.status}
Affected people: {event.affected_people}
Sector: {event.sector}
Occurred at: {event.occurred_at.isoformat()}
Situation: {event.details}
Urgent needs: {needs}
Available resources: {resources}
Responders: {responders}
Transport constraints: {", ".join(event.transport_constraints) or "none"}
Local operational conditions: {", ".join(event.operational_conditions) or "none"}
Attempted actions: {", ".join(event.attempted_actions) or "none"}
Outcome: {event.outcome or "not recorded"}
Source: {event.source}
Source type: {event.source_type}
""".strip()


def events_from_csv(text: str) -> tuple[list[OperationalEventCreate], list[str]]:
    rows = csv.DictReader(io.StringIO(text))
    events: list[OperationalEventCreate] = []
    errors: list[str] = []
    for line, row in enumerate(rows, start=2):
        try:
            needs = [
                Need.model_validate(x) for x in json_list(row.get("needs_json"))
            ]
            resources = [
                Resource.model_validate(x) for x in json_list(row.get("resources_json"))
            ]
            responders = [
                Responder.model_validate(x) for x in json_list(row.get("responders_json"))
            ]
            raw_date = (row.get("occurred_at") or "").strip()
            occurred_at = (
                datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                if raw_date else datetime.now(timezone.utc)
            )
            events.append(
                OperationalEventCreate(
                    kind=(row.get("kind") or "situation").strip(),
                    title=(row.get("title") or "Untitled field report").strip(),
                    location=(row.get("location") or "Unknown sector").strip(),
                    lat=float(row.get("lat") or 0),
                    lon=float(row.get("lon") or 0),
                    urgency=(row.get("urgency") or "medium").strip().lower(),
                    status=(row.get("status") or "open").strip().lower(),
                    affected_people=int(row.get("affected_people") or 0),
                    sector=(row.get("sector") or "multi-sector").strip(),
                    details=(row.get("details") or "").strip(),
                    needs=needs, resources=resources, responders=responders,
                    transport_constraints=pipe_list(row.get("transport_constraints")),
                    operational_conditions=pipe_list(row.get("operational_conditions")),
                    attempted_actions=pipe_list(row.get("attempted_actions")),
                    outcome=(row.get("outcome") or "").strip(),
                    source=(row.get("source") or "csv").strip(),
                    occurred_at=occurred_at,
                )
            )
        except Exception as exc:
            errors.append(f"Row {line}: {exc}")
    return events, errors


def compact_record(event: OperationalEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")
