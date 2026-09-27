from __future__ import annotations

import csv
import io
import json
import os
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
    list_events,
    store_analysis,
)
from .hindsight_service import CrisisMemory, HindsightUnavailable, hindsight_ready
from .live_data import DEFAULT_LAT, DEFAULT_LON, get_live_data
from .models import (
    Need,
    OperationalEventCreate,
    Resource,
    Responder,
    ResponsePlanAnalysis,
    ResponsePlanInput,
)
from .utils import events_from_csv


BASE_DIR = Path(__file__).resolve().parents[1]
app = FastAPI(title="CrisisOps — Disaster Response Memory Engine")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@app.on_event("startup")
def startup() -> None:
    init_db()


def status_message() -> str:
    if not os.getenv("HINDSIGHT_BASE_URL"):
        return "Demo memory active · connect Hindsight Cloud to make the operational memory persistent across sessions."
    if hindsight_ready():
        return "Hindsight connected · retain, recall and reflect are available."
    return "Hindsight configured but unavailable; verify the base URL and API key."


def local_similarity(plan: ResponsePlanInput, events) -> list:
    haystack = " ".join([
        plan.objective,
        " ".join(plan.locations),
        " ".join(plan.resources),
        plan.transport_plan,
        " ".join(plan.constraints),
        " ".join(plan.proposed_actions),
        plan.context,
    ]).lower()
    scored = []
    for event in events:
        text = f"{event.title} {event.location} {event.sector} {event.details} {' '.join(event.transport_constraints)} {' '.join(event.operational_conditions)} {' '.join(event.attempted_actions)}".lower()
        words = {w for w in haystack.split() if len(w) > 4}
        score = sum(1 for w in words if w in text)
        if score:
            scored.append((score, event))
    scored.sort(key=lambda x: (x[0], x[1].occurred_at), reverse=True)
    return [
        {"id": e.id, "text": e.title + ": " + e.details, "type": "local-memory", "metadata": {"location": e.location}}
        for _, e in scored[:8]
    ]


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
    return templates.TemplateResponse(
        request,
        "analysis.html",
        {"request": request, "status": status_message()},
    )


@app.post("/events")
def add_event(
    kind: str = Form("situation"),
    title: str = Form(...),
    location: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    urgency: str = Form("medium"),
    status: str = Form("open"),
    affected_people: int = Form(0),
    sector: str = Form("multi-sector"),
    details: str = Form(""),
    needs_json: str = Form("[]"),
    resources_json: str = Form("[]"),
    responders_json: str = Form("[]"),
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
            needs=[Need.model_validate(x) for x in json.loads(needs_json or "[]")],
            resources=[Resource.model_validate(x) for x in json.loads(resources_json or "[]")],
            responders=[Responder.model_validate(x) for x in json.loads(responders_json or "[]")],
            transport_constraints=[x.strip() for x in transport_constraints.split("|") if x.strip()],
            operational_conditions=[x.strip() for x in operational_conditions.split("|") if x.strip()],
            attempted_actions=[x.strip() for x in attempted_actions.split("|") if x.strip()],
            outcome=outcome,
        )
    )
    try:
        CrisisMemory().retain(event)
    except Exception:
        pass
    return RedirectResponse(url=f"/#event-{event.id}", status_code=303)


@app.post("/import")
async def import_events(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8")
    events, _errors = events_from_csv(content)
    memory = None
    try:
        memory = CrisisMemory()
        memory.ensure_bank()
    except Exception:
        pass
    for event_data in events:
        event = create_event(event_data)
        if memory:
            try:
                memory.retain(event)
            except Exception:
                pass
    return RedirectResponse(url="/", status_code=303)


@app.get("/demo")
def demo_data():
    if list_events(1):
        return RedirectResponse(url="/")
    demo = BASE_DIR / "data" / "demo_response.csv"
    content = demo.read_text(encoding="utf-8")
    events, _errors = events_from_csv(content)
    memory = None
    try:
        memory = CrisisMemory()
        memory.ensure_bank()
    except Exception:
        pass
    for event_data in events:
        event = create_event(event_data)
        if memory:
            try:
                memory.retain(event)
            except Exception:
                pass
    return RedirectResponse(url="/", status_code=303)


@app.post("/analyze")
def analyze_response(
    objective: str = Form(...),
    locations: str = Form(""),
    resources: str = Form(""),
    transport_plan: str = Form(""),
    constraints: str = Form(""),
    proposed_actions: str = Form(""),
    context: str = Form(""),
):
    plan = ResponsePlanInput(
        objective=objective,
        locations=[x.strip() for x in locations.split("|") if x.strip()],
        resources=[x.strip() for x in resources.split("|") if x.strip()],
        transport_plan=transport_plan,
        constraints=[x.strip() for x in constraints.split("|") if x.strip()],
        proposed_actions=[x.strip() for x in proposed_actions.split("|") if x.strip()],
        context=context,
    )

    similar = []
    live = False
    try:
        memory = CrisisMemory()
        similar = memory.recall(plan)
        result = memory.reflect(plan)
        live = True
    except Exception as exc:
        similar = local_similarity(plan, list_events())
        result = ResponsePlanAnalysis(
            risk_level="medium",
            confidence="low",
            summary="Demo mode: this review used the local incident timeline. Connect Hindsight for semantic recall and agentic reflection across the operational memory bank.",
            memory_recalled=[x["text"] for x in similar],
            recurring_patterns=["Resource and route constraints are only as reliable as the latest field update."],
            resource_conflicts=["Verify available and committed quantities before dispatch."],
            transport_constraints=["Check route closure reports against the latest timestamp."],
            recommended_actions=["Confirm latest field status.", "Cross-check resource counts.", "Keep a human incident commander in approval."],
            unanswered_questions=["When was each location last verified?", "Which team has confirmed ownership of the task?"],
            evidence=[str(exc)],
        )

    store_analysis(plan.model_dump(), {
        "analysis": result.model_dump(),
        "similar": similar,
        "memory_live": live,
    })
    return RedirectResponse(url="/analysis?ready=1", status_code=303)


@app.get("/api/live-data")
def api_live_data(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON):
    """Live public hazard/weather feeds; never presented as verified field status."""
    return get_live_data(lat, lon)


@app.post("/api/live-data/retain")
def retain_live_data(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON):
    snapshot = get_live_data(lat, lon)
    try:
        count = CrisisMemory().retain_live_snapshot(snapshot)
        return {"ok": True, "retained": count}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(exc)})


@app.get("/api/dashboard")
def api_dashboard():
    return {"stats": dashboard_stats().model_dump(), "status": status_message()}


@app.get("/api/events")
def api_events():
    return [e.model_dump(mode="json") for e in list_events()]


@app.get("/api/events/{event_id}")
def api_event(event_id: int):
    return get_event(event_id).model_dump(mode="json")


@app.get("/api/latest-analysis")
def api_latest_analysis():
    return latest_analysis() or {}


@app.get("/api/memory")
def api_memory():
    try:
        return {"live": True, "lenses": CrisisMemory().memory_lenses()}
    except Exception as exc:
        return {"live": False, "lenses": {}, "error": str(exc)}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "project": "CrisisOps",
        "hindsight_configured": bool(os.getenv("HINDSIGHT_BASE_URL")),
        "hindsight_ready": hindsight_ready(),
    }
