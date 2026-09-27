from __future__ import annotations

import io
import json
import os
import time
import urllib.request
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
from .hindsight_service import CrisisMemory, hindsight_ready
from .live_data import DEFAULT_LAT, DEFAULT_LON, get_live_data
from .models import Need, OperationalEventCreate, Resource, Responder, ResponsePlanAnalysis, ResponsePlanInput
from .utils import events_from_csv


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
    if hindsight_ready():
        return "Hindsight connected · retain, recall and reflect are available."
    if os.getenv("HINDSIGHT_BASE_URL"):
        return "Hindsight configured · connection will be verified on the first memory operation."
    return "Demo fallback · connect Hindsight Cloud for persistent cross-session memory."


def source_category(value: str) -> str:
    value = (value or "").lower()
    if value == "synthetic" or "demo" in value or "seed" in value:
        return "SYNTHETIC"
    return "OPERATOR INPUT"


def local_similarity(plan: ResponsePlanInput, events) -> list:
    haystack = " ".join([
        plan.objective, " ".join(plan.locations), " ".join(plan.resources),
        plan.transport_plan, " ".join(plan.constraints),
        " ".join(plan.proposed_actions), plan.context,
    ]).lower()
    scored = []
    words = {w.strip(".,:;()[]") for w in haystack.split() if len(w.strip(".,:;()[]")) > 4}
    for event in events:
        text = f"{event.title} {event.location} {event.sector} {event.details} {' '.join(event.transport_constraints)} {' '.join(event.operational_conditions)} {' '.join(event.attempted_actions)} {event.outcome}".lower()
        score = sum(1 for w in words if w in text)
        if score:
            scored.append((score, event))
    scored.sort(key=lambda x: (x[0], x[1].occurred_at), reverse=True)
    return [
        {
            "id": e.id, "text": e.title + ": " + e.details, "type": "local-demo-fallback",
            "metadata": {"location": e.location, "source_type": e.source_type, "source": e.source},
        }
        for _, e in scored[:8]
    ]


def response_plan_from_values(objective: str, locations: str = "", resources: str = "", transport_plan: str = "", constraints: str = "", proposed_actions: str = "", context: str = "") -> ResponsePlanInput:
    return ResponsePlanInput(
        objective=objective,
        locations=[x.strip() for x in locations.split("|") if x.strip()],
        resources=[x.strip() for x in resources.split("|") if x.strip()],
        transport_plan=transport_plan,
        constraints=[x.strip() for x in constraints.split("|") if x.strip()],
        proposed_actions=[x.strip() for x in proposed_actions.split("|") if x.strip()],
        context=context,
    )


def memory_free_baseline(plan: ResponsePlanInput) -> dict:
    """Return advice using only the current plan; no Hindsight context is passed."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return {
            "mode": "local-no-memory-baseline",
            "summary": "Review the current situation, verify the latest needs and route conditions, check resource availability, coordinate responders, and keep a human incident commander in approval.",
            "recommended_actions": [
                "Confirm current field conditions and affected locations.",
                "Verify available versus committed resources before dispatch.",
                "Validate transport routes and alternate access.",
                "Confirm ownership with the on-scene coordinator.",
            ],
        }
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "Provide concise disaster-response decision support using ONLY the current plan. Do not reference history, memory, or prior incidents."},
            {"role": "user", "content": json.dumps(plan.model_dump())},
        ],
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read().decode())
        text = body["choices"][0]["message"]["content"].strip()
        return {"mode": "groq-no-memory-baseline", "summary": text, "recommended_actions": []}
    except Exception as exc:
        return {
            "mode": "local-no-memory-baseline",
            "summary": "Baseline LLM unavailable; showing a memory-free generic response using only the current plan.",
            "recommended_actions": ["Verify current field conditions.", "Check resources and routes.", "Confirm the human incident commander."],
            "error": str(exc),
        }


def analyze_plan(plan: ResponsePlanInput) -> dict:
    baseline = memory_free_baseline(plan)
    similar = []
    memory_live = False
    try:
        memory = CrisisMemory()
        similar = memory.recall(plan)
        reflection = memory.reflect(plan)
        memory_live = True
    except Exception as exc:
        similar = local_similarity(plan, list_events())
        reflection = ResponsePlanAnalysis(
            risk_level="medium", confidence="low",
            summary="Hindsight unavailable. This is a clearly labeled local demo fallback, not persistent Hindsight memory.",
            memory_recalled=[x["text"] for x in similar],
            recurring_patterns=["Resource and route constraints are only as reliable as the latest field update."],
            resource_conflicts=["Verify available and committed quantities before dispatch."],
            transport_constraints=["Check route closure reports against the latest timestamp."],
            recommended_actions=["Confirm latest field status.", "Cross-check resource counts.", "Keep a human incident commander in approval."],
            unanswered_questions=["When was each location last verified?", "Which team confirmed ownership of the task?"],
            evidence=[f"demo fallback: {exc}"],
        )
    result = {
        "baseline": baseline,
        "analysis": reflection.model_dump(),
        "similar": similar,
        "memory_live": memory_live,
        "source_type": "HINDSIGHT SYNTHESIS" if memory_live else "LOCAL DEMO FALLBACK",
    }
    return result


def find_demo_event(title: str):
    for event in list_events(500):
        if event.title == title and event.source_type == "synthetic":
            return event
    return None


def canonical_demo_events() -> tuple:
    a = OperationalEventCreate(
        title=DEMO_A_TITLE, kind="situation", location="North Ward", lat=17.45, lon=78.40,
        urgency="high", status="resolved", affected_people=120, sector="flood",
        details="Flooding affected North Ward. Bridge access was closed.",
        needs=[Need(category="water", priority="high", quantity=200, unit="kits", status="open"), Need(category="medical support", priority="high", quantity=1, unit="team", status="open")],
        resources=[], responders=[], transport_constraints=["bridge closed"],
        operational_conditions=["waterlogging on road approach"],
        attempted_actions=["road delivery"], outcome="Route became inaccessible.",
        source="demo-seed", source_type="synthetic",
        occurred_at=datetime(2026, 9, 25, 7, 0, tzinfo=timezone.utc),
    )
    b = OperationalEventCreate(
        title=DEMO_B_TITLE, kind="decision", location="North Ward", lat=17.45, lon=78.40,
        urgency="high", status="open", affected_people=150, sector="flood",
        details="A new North Ward flooding situation requires a response plan.",
        needs=[Need(category="evacuation support", priority="high", quantity=150, unit="people", status="open")],
        resources=[Resource(item="boats", available=2, committed=0, unit="units", location="Depot 2"), Resource(item="truck", available=1, committed=0, unit="unit", location="Depot 2")],
        responders=[], transport_constraints=["Bridge 4 closed"],
        operational_conditions=["road access uncertain"], attempted_actions=[],
        outcome="", source="demo-seed", source_type="synthetic",
        occurred_at=datetime(2026, 9, 27, 7, 0, tzinfo=timezone.utc),
    )
    return a, b


def seed_canonical_demo() -> dict:
    a_spec, b_spec = canonical_demo_events()
    a = find_demo_event(DEMO_A_TITLE)
    if not a:
        a = create_event(a_spec)
    b = find_demo_event(DEMO_B_TITLE)
    if not b:
        b = create_event(b_spec)
    memory_id = None
    try:
        memory_id = CrisisMemory().retain(a)
    except Exception as exc:
        memory_id = None
    return {
        "incident_a_id": a.id, "incident_b_id": b.id,
        "retained_memory_id": memory_id or f"crisis-event-{a.id}",
        "incident_a_source_type": a.source_type, "incident_b_source_type": b.source_type,
        "incident_b_is_retained": False,
        "hindsight_available": hindsight_ready(),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "request": request, "events": list_events(), "stats": dashboard_stats(), "status": status_message(),
    })


@app.get("/analysis", response_class=HTMLResponse)
def analysis_page(request: Request):
    return templates.TemplateResponse(request, "analysis.html", {"request": request, "status": status_message()})


@app.post("/events")
def add_event(
    kind: str = Form("situation"), title: str = Form(...), location: str = Form(...),
    lat: float = Form(...), lon: float = Form(...), urgency: str = Form("medium"),
    status: str = Form("open"), affected_people: int = Form(0), sector: str = Form("multi-sector"),
    details: str = Form(""), needs_json: str = Form("[]"), resources_json: str = Form("[]"),
    responders_json: str = Form("[]"), transport_constraints: str = Form(""),
    operational_conditions: str = Form(""), attempted_actions: str = Form(""), outcome: str = Form(""),
):
    event = create_event(OperationalEventCreate(
        kind=kind, title=title, location=location, lat=lat, lon=lon, urgency=urgency, status=status,
        affected_people=affected_people, sector=sector, details=details,
        needs=[Need.model_validate(x) for x in json.loads(needs_json or "[]")],
        resources=[Resource.model_validate(x) for x in json.loads(resources_json or "[]")],
        responders=[Responder.model_validate(x) for x in json.loads(responders_json or "[]")],
        transport_constraints=[x.strip() for x in transport_constraints.split("|") if x.strip()],
        operational_conditions=[x.strip() for x in operational_conditions.split("|") if x.strip()],
        attempted_actions=[x.strip() for x in attempted_actions.split("|") if x.strip()],
        outcome=outcome, source="field-report", source_type="operator",
    ))
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
        memory = CrisisMemory(); memory.ensure_bank()
    except Exception:
        pass
    for event_data in events:
        if event_data.source_type != "synthetic":
            event_data.source_type = "operator"
        event = create_event(event_data)
        if memory:
            try: memory.retain(event)
            except Exception: pass
    return RedirectResponse(url="/", status_code=303)


@app.get("/demo")
def demo_data():
    seed_canonical_demo()
    return RedirectResponse(url="/", status_code=303)


@app.post("/analyze")
def analyze_response(
    objective: str = Form(...), locations: str = Form(""), resources: str = Form(""),
    transport_plan: str = Form(""), constraints: str = Form(""), proposed_actions: str = Form(""), context: str = Form(""),
):
    plan = response_plan_from_values(objective, locations, resources, transport_plan, constraints, proposed_actions, context)
    result = analyze_plan(plan)
    store_analysis(plan.model_dump(), result)
    return RedirectResponse(url="/analysis?ready=1", status_code=303)


@app.get("/api/analyze/compare")
def api_analyze_compare(
    objective: str, locations: str = "", resources: str = "", transport_plan: str = "",
    constraints: str = "", proposed_actions: str = "", context: str = "",
):
    plan = response_plan_from_values(objective, locations, resources, transport_plan, constraints, proposed_actions, context)
    result = analyze_plan(plan)
    store_analysis(plan.model_dump(), result)
    return result


@app.get("/api/live-data")
def api_live_data(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON):
    return get_live_data(lat, lon)


@app.post("/api/live-data/retain")
def retain_live_data(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON):
    snapshot = get_live_data(lat, lon)
    try:
        count = CrisisMemory().retain_live_snapshot(snapshot)
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
def api_demo_seed():
    return seed_canonical_demo()


@app.api_route("/api/demo/verify-loop", methods=["GET", "POST"])
def api_demo_verify_loop():
    start = time.perf_counter()
    seeded = seed_canonical_demo()
    a_id = seeded["incident_a_id"]
    _, b_spec = canonical_demo_events()
    plan = ResponsePlanInput(
        objective="Respond to North Ward flooding again with 2 boats and 1 truck using the canal route.",
        locations=["North Ward"], resources=["2 boats", "1 truck"],
        transport_plan="Use canal route", constraints=["Bridge 4 closed"],
        proposed_actions=["Stage boats", "Move water and medical support"],
        context="150 people affected; current road access is uncertain.",
    )
    try:
        memory = CrisisMemory()
        recalled = memory.recall(plan)
        reflection = memory.reflect(plan)
        live = True
    except Exception as exc:
        recalled = local_similarity(plan, [get_event(a_id)])
        reflection = ResponsePlanAnalysis(risk_level="medium", confidence="low", summary="Demo fallback: Hindsight unavailable.", memory_recalled=[x["text"] for x in recalled], evidence=[str(exc)])
        live = False
    text_blob = " ".join([reflection.summary] + reflection.transport_constraints + reflection.recommended_actions + reflection.memory_recalled).lower()
    return {
        "retained_memory_id": seeded["retained_memory_id"],
        "recalled_memory_ids": [x.get("id") for x in recalled],
        "reflection": reflection.model_dump(),
        "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        "hindsight_live": live,
        "demo_expectations": {
            "road_delivery_failure_surface": any(x in text_blob for x in ["road delivery", "route became inaccessible", "inaccessible"]),
            "canal_or_boat_route_surface": any(x in text_blob for x in ["canal", "boat"]),
            "bridge_closure_surface": "bridge" in text_blob,
        },
    }


@app.post("/api/demo/learning-curve")
def api_demo_learning_curve():
    seeded = seed_canonical_demo()
    _, b_spec = canonical_demo_events()
    plan = response_plan_from_values(
        "Respond to North Ward flooding again with 2 boats and 1 truck using the canal route.",
        "North Ward", "2 boats|1 truck", "Use canal route", "Bridge 4 closed", "Stage boats|Move water and medical support", "150 people affected; current road access is uncertain.",
    )
    before = analyze_plan(plan)["analysis"]
    c = find_demo_event(DEMO_C_TITLE)
    if not c:
        c_spec = OperationalEventCreate(
            title=DEMO_C_TITLE, kind="action", location="North Ward", lat=17.45, lon=78.40,
            urgency="high", status="resolved", affected_people=150, sector="flood",
            details="A related North Ward response used the canal approach while a road route remained constrained.",
            needs=[Need(category="water", priority="high", quantity=180, unit="kits", status="resolved")],
            resources=[Resource(item="boats", available=2, committed=2, unit="units", location="Depot 2", status="ready")],
            responders=[], transport_constraints=["Bridge 4 closed"],
            operational_conditions=["canal route available"], attempted_actions=["staged boats at Depot 2", "used canal route"],
            outcome="Canal route remained usable; boat staging reduced road dependence.",
            source="demo-learning-curve", source_type="synthetic",
            occurred_at=datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc),
        )
        c = create_event(c_spec)
    try:
        retained_id = CrisisMemory().retain(c)
        after_result = analyze_plan(plan)
        after = after_result["analysis"]
        live = after_result["memory_live"]
    except Exception as exc:
        after = before
        retained_id = f"crisis-event-{c.id}"
        live = False
    return {"before": before, "after": after, "third_incident_id": c.id, "third_retained_memory_id": retained_id, "hindsight_live": live}


@app.get("/api/dashboard")
def api_dashboard():
    return {"stats": dashboard_stats().model_dump(), "status": status_message()}


@app.get("/api/events")
def api_events():
    return [e.model_dump(mode="json") | {"source_category": source_category(e.source_type)} for e in list_events()]


@app.get("/api/events/{event_id}")
def api_event(event_id: int):
    e = get_event(event_id)
    return e.model_dump(mode="json") | {"source_category": source_category(e.source_type)}


@app.get("/api/latest-analysis")
def api_latest_analysis():
    return latest_analysis() or {}


@app.get("/api/analysis-history")
def api_analysis_history():
    return list_analyses(20)


@app.get("/api/memory")
def api_memory():
    try:
        return {"live": True, "source_type": "HINDSIGHT SYNTHESIS", "lenses": CrisisMemory().memory_lenses()}
    except Exception as exc:
        return {"live": False, "source_type": "LOCAL DEMO FALLBACK", "lenses": {}, "error": str(exc)}


@app.get("/health")
def health():
    return {
        "status": "ok", "project": "CrisisOps",
        "hindsight_configured": bool(os.getenv("HINDSIGHT_BASE_URL")),
        "hindsight_ready": hindsight_ready(),
        "memory_bank": "crisisops-disaster-response-memory",
    }
