from __future__ import annotations

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
    if os.getenv("HINDSIGHT_BASE_URL") and os.getenv("HINDSIGHT_API_KEY"):
        return "Hindsight configured · the live memory connection is verified when an operation runs."
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
    """Deterministic baseline using only the current plan; no Hindsight context."""
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
