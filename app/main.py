from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import (
    create_event,
    dashboard_stats,
    get_event,
    init_db,
    latest_analysis,
    list_analyses,
    list_events,
    store_analysis,
    store_live_intel,
)
from .hindsight_service import CrisisMemory, hindsight_configured
from .live_data import DEFAULT_LAT, DEFAULT_LON, get_live_data
from .models import Need, OperationalEventCreate, Resource, Responder, ResponsePlanAnalysis, ResponsePlanInput
from .utils import events_from_csv, pipe_list


BASE_DIR = Path(__file__).resolve().parents[1]
app = FastAPI(title="CrisisOps — Disaster Response Memory Engine")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")

DEMO_A_TITLE = "North Ward Flooding — Incident A"
DEMO_B_TITLE = "North Ward Flooding — Incident B"
DEMO_C_TITLE = "North Ward Flooding — Incident C"


@app.on_event("startup")
def startup() -> None:
    init_db()


def status_message() -> str:
    if hindsight_configured():
        return "Hindsight is configured. Memory operations are live when you run them."
    return "Demo fallback. Connect Hindsight Cloud for persistent cross-incident memory."


def source_category(source_type: str) -> str:
    return "SYNTHETIC" if source_type == "synthetic" else "OPERATOR INPUT"


def parse_simple_items(value: str | None) -> list[str]:
    return pipe_list(value)


def parse_needs(value: str | None) -> list[Need]:
    return [Need(category=item) for item in parse_simple_items(value)]


def parse_resources(value: str | None) -> list[Resource]:
    return [Resource(item=item, available=0, committed=0, unit="units") for item in parse_simple_items(value)]


def parse_responders(value: str | None) -> list[Responder]:
    return [Responder(organization=item, team="Field Team", status="unknown") for item in parse_simple_items(value)]


def local_similarity(plan: ResponsePlanInput, events) -> list[dict]:
    haystack = " ".join(
        [
            plan.objective,
            " ".join(plan.locations),
            " ".join(plan.resources),
            plan.transport_plan,
            " ".join(plan.constraints),
            " ".join(plan.proposed_actions),
            plan.context,
        ]
    ).lower()
    words = {w.strip(".,:;()[]") for w in haystack.split() if len(w.strip(".,:;()[]")) > 4}
    scored = []
    for event in events:
        text = (
            f"{event.title} {event.location} {event.sector} {event.details} "
            f"{' '.join(event.transport_constraints)} {' '.join(event.operational_conditions)} "
            f"{' '.join(event.attempted_actions)} {event.outcome}"
        ).lower()
        score = sum(1 for word in words if word in text)
        if score:
            scored.append((score, event))
    scored.sort(key=lambda item: (item[0], item[1].occurred_at), reverse=True)
    return [
        {
            "id": event.id,
            "text": f"{event.title}: {event.details}",
            "type": "local-demo-fallback",
            "metadata": {
                "location": event.location,
                "source_type": event.source_type,
                "source": event.source,
            },
        }
        for _, event in scored[:8]
    ]


def response_plan_from_values(
    objective: str,
    locations: str = "",
    resources: str = "",
    transport_plan: str = "",
    constraints: str = "",
    proposed_actions: str = "",
    context: str = "",
) -> ResponsePlanInput:
    return ResponsePlanInput(
        objective=objective,
        locations=pipe_list(locations),
        resources=pipe_list(resources),
        transport_plan=transport_plan,
        constraints=pipe_list(constraints),
        proposed_actions=pipe_list(proposed_actions),
        context=context,
    )


def memory_free_baseline() -> dict:
    return {
        "mode": "memory-free",
        "summary": "Review the current situation, verify needs, check resources, validate routes, coordinate responders, and keep a human decision-maker in approval.",
        "recommended_actions": [
            "Confirm the latest field conditions.",
            "Verify available versus committed resources.",
            "Validate the proposed transport route and an alternate route.",
            "Confirm ownership with the on-scene coordinator.",
        ],
    }


async def analyze_plan(plan: ResponsePlanInput) -> dict:
    baseline = memory_free_baseline()
    similar: list[dict] = []
    memory_live = False

    try:
        memory = CrisisMemory()
        similar = await memory.recall(plan)
        reflection = await memory.reflect(plan)
        memory_live = True
    except Exception as exc:
        similar = local_similarity(plan, list_events())
        reflection = ResponsePlanAnalysis(
            risk_level="medium",
            confidence="low",
            summary="Hindsight is unavailable. This review is a clearly labelled local demo fallback, not persistent Hindsight memory.",
            memory_recalled=[item["text"] for item in similar],
            recurring_patterns=["Route and resource conditions must be re-verified against the latest field update."],
            resource_conflicts=["Verify available and committed quantities before action."],
            transport_constraints=["Check the current route status and keep an alternate route ready."],
            recommended_actions=["Confirm latest field status.", "Cross-check resource counts.", "Keep a human incident commander in approval."],
            unanswered_questions=["When was each location last verified?", "Which team confirmed ownership of the task?"],
            evidence=[f"Local fallback reason: {exc}"],
        )

    return {
        "baseline": baseline,
        "analysis": reflection.model_dump(),
        "similar": similar,
        "memory_live": memory_live,
        "source_type": "HINDSIGHT SYNTHESIS" if memory_live else "LOCAL DEMO FALLBACK",
    }


def find_demo_event(title: str):
    for event in list_events(500):
        if event.title == title and event.source_type == "synthetic":
            return event
    return None


def canonical_demo_events() -> tuple[OperationalEventCreate, OperationalEventCreate]:
    incident_a = OperationalEventCreate(
        title=DEMO_A_TITLE,
        kind="situation",
        location="North Ward",
        lat=17.45,
        lon=78.40,
        urgency="high",
        status="resolved",
        affected_people=120,
        sector="flood",
        details="Flooding affected North Ward. Bridge access was closed.",
        needs=[
            Need(category="water", priority="high", quantity=200, unit="kits", status="open"),
            Need(category="medical support", priority="high", quantity=1, unit="team", status="open"),
        ],
        resources=[],
        responders=[],
        transport_constraints=["bridge closed"],
        operational_conditions=["waterlogging on road approach"],
        attempted_actions=["road delivery"],
        outcome="Route became inaccessible.",
        source="demo-seed",
        source_type="synthetic",
        occurred_at=datetime(2026, 9, 25, 7, 0, tzinfo=timezone.utc),
    )
    incident_b = OperationalEventCreate(
        title=DEMO_B_TITLE,
        kind="decision",
        location="North Ward",
        lat=17.45,
        lon=78.40,
        urgency="high",
        status="open",
        affected_people=150,
        sector="flood",
        details="A new North Ward flooding situation requires a response plan.",
        needs=[Need(category="evacuation support", priority="high", quantity=150, unit="people", status="open")],
        resources=[
            Resource(item="boats", available=2, unit="units", location="Depot 2"),
            Resource(item="truck", available=1, unit="unit", location="Depot 2"),
        ],
        responders=[],
        transport_constraints=["Bridge 4 closed"],
        operational_conditions=["road access uncertain"],
        attempted_actions=[],
        outcome="",
        source="demo-seed",
        source_type="synthetic",
        occurred_at=datetime(2026, 9, 27, 7, 0, tzinfo=timezone.utc),
    )
    return incident_a, incident_b


async def seed_canonical_demo() -> dict:
    a_spec, b_spec = canonical_demo_events()
    a = find_demo_event(DEMO_A_TITLE)
    if not a:
        a = create_event(a_spec)

    b = find_demo_event(DEMO_B_TITLE)
    if not b:
        b = create_event(b_spec)

    retained_id = None
    try:
        retained_id = await CrisisMemory().retain(a)
    except Exception:
        pass

    return {
        "incident_a_id": a.id,
        "incident_b_id": b.id,
        "retained_memory_id": retained_id,
        "incident_a_source_type": a.source_type,
        "incident_b_source_type": b.source_type,
        "incident_b_is_retained": False,
        "hindsight_configured": hindsight_configured(),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "events": list_events(),
            "stats": dashboard_stats(),
            "status": status_message(),
        },
    )


@app.get("/analysis", response_class=HTMLResponse)
def analysis_page(request: Request):
    return templates.TemplateResponse(request, "analysis.html", {"request": request, "status": status_message()})


@app.post("/events")
async def add_event(
    kind: str = Form("situation"),
    title: str = Form(...),
    location: str = Form(...),
    lat: float = Form(DEFAULT_LAT),
    lon: float = Form(DEFAULT_LON),
    urgency: str = Form("medium"),
    status: str = Form("open"),
    affected_people: int = Form(0),
    sector: str = Form("multi-sector"),
    details: str = Form(""),
    needs: str = Form(""),
    resources: str = Form(""),
    responders: str = Form(""),
    transport_constraints: str = Form(""),
    operational_conditions: str = Form(""),
    attempted_actions: str = Form(""),
    outcome: str = Form(""),
):
    event = create_event(
        OperationalEventCreate(
            kind=kind,
            title=title,
            location=location,
            lat=lat,
            lon=lon,
            urgency=urgency,
            status=status,
            affected_people=affected_people,
            sector=sector,
            details=details,
            needs=parse_needs(needs),
            resources=parse_resources(resources),
            responders=parse_responders(responders),
            transport_constraints=pipe_list(transport_constraints),
            operational_conditions=pipe_list(operational_conditions),
            attempted_actions=pipe_list(attempted_actions),
            outcome=outcome,
            source="field-report",
            source_type="operator",
        )
    )
    try:
        await CrisisMemory().retain(event)
    except Exception:
        pass
    return RedirectResponse(url=f"/#event-{event.id}", status_code=303)


@app.post("/import")
async def import_events(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8")
    events, _errors = events_from_csv(content)
    for event_data in events:
        event = create_event(event_data)
        try:
            await CrisisMemory().retain(event)
        except Exception:
            pass
    return RedirectResponse(url="/", status_code=303)


@app.get("/demo")
async def demo_data():
    await seed_canonical_demo()
    return RedirectResponse(url="/", status_code=303)


@app.post("/analyze")
async def analyze_response(
    objective: str = Form(...),
    locations: str = Form(""),
    resources: str = Form(""),
    transport_plan: str = Form(""),
    constraints: str = Form(""),
    proposed_actions: str = Form(""),
    context: str = Form(""),
):
    plan = response_plan_from_values(objective, locations, resources, transport_plan, constraints, proposed_actions, context)
    result = await analyze_plan(plan)
    store_analysis(plan.model_dump(), result)
    return RedirectResponse(url="/analysis?ready=1", status_code=303)


@app.get("/api/analyze/compare")
async def api_analyze_compare(
    objective: str,
    locations: str = "",
    resources: str = "",
    transport_plan: str = "",
    constraints: str = "",
    proposed_actions: str = "",
    context: str = "",
):
    plan = response_plan_from_values(objective, locations, resources, transport_plan, constraints, proposed_actions, context)
    result = await analyze_plan(plan)
    store_analysis(plan.model_dump(), result)
    return result


@app.get("/api/live-data")
def api_live_data(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON):
    return get_live_data(lat, lon)


@app.post("/api/live-data/retain")
async def retain_live_data(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON):
    snapshot = await asyncio.to_thread(get_live_data, lat, lon)
    try:
        count = await CrisisMemory().retain_live_snapshot(snapshot)
        for provider, payload in [
            ("open-meteo", snapshot.get("weather")),
            ("usgs", snapshot.get("earthquakes")),
            ("imd-cap", snapshot.get("imd_alerts")),
            ("gdacs", snapshot.get("gdacs_events")),
        ]:
            if payload not in (None, [], {}):
                store_live_intel(provider, payload, snapshot.get("generated_at", ""), True)
        return {"ok": True, "retained": count, "source_type": "REAL"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"ok": False, "source_type": "REAL", "error": str(exc)})


@app.post("/api/demo/seed")
async def api_demo_seed():
    return await seed_canonical_demo()


@app.api_route("/api/demo/verify-loop", methods=["GET", "POST"])
async def api_demo_verify_loop():
    started = time.perf_counter()
    seeded = await seed_canonical_demo()
    plan = ResponsePlanInput(
        objective="Respond to North Ward flooding again with 2 boats and 1 truck using the canal route.",
        locations=["North Ward"],
        resources=["2 boats", "1 truck"],
        transport_plan="Use canal route",
        constraints=["Bridge 4 closed"],
        proposed_actions=["Stage boats", "Move water and medical support"],
        context="150 people affected; current road access is uncertain.",
    )

    try:
        memory = CrisisMemory()
        recalled = await memory.recall(plan)
        reflection = await memory.reflect(plan)
        live = True
    except Exception as exc:
        recalled = local_similarity(plan, [get_event(seeded["incident_a_id"])])
        reflection = ResponsePlanAnalysis(
            risk_level="medium",
            confidence="low",
            summary="Hindsight unavailable. Local demo fallback shown instead.",
            memory_recalled=[item["text"] for item in recalled],
            evidence=[str(exc)],
        )
        live = False

    text_blob = " ".join(
        [reflection.summary, *reflection.transport_constraints, *reflection.recommended_actions, *reflection.memory_recalled]
    ).lower()

    return {
        "retained_memory_id": seeded["retained_memory_id"],
        "recalled_memory_ids": [item.get("id") for item in recalled],
        "reflection": reflection.model_dump(),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "hindsight_live": live,
        "demo_expectations": {
            "road_delivery_failure_surface": any(term in text_blob for term in ["road delivery", "route became inaccessible", "inaccessible"]),
            "canal_or_boat_route_surface": any(term in text_blob for term in ["canal", "boat"]),
            "bridge_closure_surface": "bridge" in text_blob,
        },
    }


@app.post("/api/demo/learning-curve")
async def api_demo_learning_curve():
    seeded = await seed_canonical_demo()
    plan = ResponsePlanInput(
        objective="Respond to North Ward flooding again with 2 boats and 1 truck using the canal route.",
        locations=["North Ward"],
        resources=["2 boats", "1 truck"],
        transport_plan="Use canal route",
        constraints=["Bridge 4 closed"],
        proposed_actions=["Stage boats", "Move water and medical support"],
        context="150 people affected; current road access is uncertain.",
    )

    before_result = await analyze_plan(plan)
    before = before_result["analysis"]

    incident_c = find_demo_event(DEMO_C_TITLE)
    if not incident_c:
        incident_c = create_event(
            OperationalEventCreate(
                title=DEMO_C_TITLE,
                kind="action",
                location="North Ward",
                lat=17.45,
                lon=78.40,
                urgency="high",
                status="resolved",
                affected_people=150,
                sector="flood",
                details="A related North Ward response used the canal approach while a road route remained constrained.",
                needs=[Need(category="water", priority="high", quantity=180, unit="kits", status="resolved")],
                resources=[Resource(item="boats", available=2, committed=2, unit="units", location="Depot 2", status="ready")],
                responders=[],
                transport_constraints=["Bridge 4 closed"],
                operational_conditions=["canal route available"],
                attempted_actions=["staged boats at Depot 2", "used canal route"],
                outcome="Canal route remained usable; boat staging reduced road dependence.",
                source="demo-learning-curve",
                source_type="synthetic",
                occurred_at=datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc),
            )
        )

    try:
        retained_id = await CrisisMemory().retain(incident_c)
        after_result = await analyze_plan(plan)
        after = after_result["analysis"]
        live = after_result["memory_live"]
    except Exception:
        retained_id = None
        after = before
        live = False

    return {
        "base_incident_a_id": seeded["incident_a_id"],
        "third_incident_id": incident_c.id,
        "third_retained_memory_id": retained_id,
        "before": before,
        "after": after,
        "hindsight_live": live,
    }


@app.get("/api/dashboard")
def api_dashboard():
    return {"stats": dashboard_stats().model_dump(), "status": status_message()}


@app.get("/api/events")
def api_events():
    return [
        e.model_dump(mode="json") | {"source_category": source_category(e.source_type)}
        for e in list_events()
    ]


@app.get("/api/events/{event_id}")
def api_event(event_id: int):
    event = get_event(event_id)
    return event.model_dump(mode="json") | {"source_category": source_category(event.source_type)}


@app.get("/api/latest-analysis")
def api_latest_analysis():
    return latest_analysis() or {}


@app.get("/api/analysis-history")
def api_analysis_history():
    return list_analyses(20)


@app.get("/api/memory")
async def api_memory():
    try:
        return {
            "live": True,
            "source_type": "HINDSIGHT SYNTHESIS",
            "lenses": await CrisisMemory().memory_lenses(),
        }
    except Exception as exc:
        return {
            "live": False,
            "source_type": "LOCAL DEMO FALLBACK",
            "lenses": {},
            "error": str(exc),
        }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "project": "CrisisOps",
        "hindsight_configured": hindsight_configured(),
        "memory_bank": "crisisops-disaster-response-memory",
    }
